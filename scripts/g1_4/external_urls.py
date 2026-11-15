"""Prepare a PROVISIONAL external cohort; no training, evaluation or final-test file reads."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import urllib.request
from common import base,prep,output_dir,save_manifest,write_rows,run

LOCK=Path(__file__).with_name('source-lock.json')
VERSION='external-url-intake-v1'


def role(group):
    n=int(hashlib.sha256(('external-url-role-v1:'+group).encode()).hexdigest(),16)
    return 'development' if n%100<50 else 'holdout'


def download(output):
    lock=base.load_json(LOCK)
    with output_dir(output) as stage:
        with urllib.request.urlopen(lock['download_url'],timeout=90) as stream,(stage/'hannousse.csv').open('wb') as f:
            size=0
            while block:=stream.read(1024*1024):
                size+=len(block)
                if size>16*1024*1024:raise base.TrainingError('Source exceeds size limit.')
                f.write(block)
        if base.sha(stage/'hannousse.csv')!=lock['sha256']:raise base.TrainingError('External source checksum mismatch.')
        save_manifest(stage,{'source':lock})
    return {'status':'MIRROR_DOWNLOADED_AND_HASH_VERIFIED','primary_comparison_done':False}


def exclusions(source,dataset):
    manifest=base.validate_manifest(dataset)
    if base.sha(source)!=manifest['source']['csv_sha256']:raise base.TrainingError('Original PhiUSIIL checksum mismatch.')
    groups=set();ids=set()
    # Deliberately use original source URL column only; test.jsonl is never opened.
    with source.open(encoding='utf-8-sig',newline='') as f:
        for i,row in enumerate(csv.DictReader(f),1):
            try:inspected=prep.inspect_url(row['URL'])
            except prep.URLInputError:continue
            groups.add(prep.grouping(inspected));ids.add(prep.digest_text(inspected['url']['normalized_url']))
            if i%50000==0:print(f'Exclusion index: {i} source records',flush=True)
    return ids,groups,manifest


def summarize(values):
    out={'rows':len(values),'groups':len({r['group_id'] for r in values}),
         'labels':dict(Counter(str(r['y']) for r in values))}
    # Structural coverage only. No model scores are computed, including on reserved holdout.
    out['coverage']={
        'http_legitimate':sum(r['scheme']=='http' and r['y']==0 for r in values),
        'https_phishing':sum(r['scheme']=='https' and r['y']==1 for r in values),
        'legitimate_length_ge_34':sum(r['y']==0 and r['url_length']>=34 for r in values)}
    return out


def prepare(source,dataset,base_source,output):
    lock=base.load_json(LOCK)
    if base.sha(source)!=lock['sha256']:raise base.TrainingError('External source checksum mismatch.')
    old_ids,old_groups,manifest=exclusions(base_source,dataset)
    base_hash=base.sha(dataset/'manifest.json')
    candidates=defaultdict(list);rejected=[];counts=Counter();total=0
    with source.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not {'url','status'}.issubset(reader.fieldnames or []) or len(reader.fieldnames)!=len(set(reader.fieldnames)):
            raise base.TrainingError('Expected unique url/status columns.')
        for i,row in enumerate(reader,1):
            total+=1;label=row.get('status');counts[label if label in lock['label_map'] else 'INVALID']+=1
            reason=None
            if None in row or any(v is None for v in row.values()):reason='MALFORMED_ROW'
            elif label not in lock['label_map']:reason='INVALID_LABEL'
            else:
                try:inspected=prep.inspect_url(row['url'])
                except prep.URLInputError as e:reason=e.code
            if reason:
                rejected.append({'source_record':i,'reason':reason,'source_label':label if label in lock['label_map'] else None});continue
            canonical=inspected['url']['normalized_url'];sid=prep.digest_text(canonical)
            candidates[sid].append({'source_record':i,'input_url':row['url'],'normalized_url':canonical,
                    'sample_id':sid,'group_id':prep.grouping(inspected),'source_id':lock['source_id'],
                    'source_label':label,'y':lock['label_map'][label],'label_status':'SOURCE_ANNOTATION_UNREVIEWED',
                    'scheme':inspected['url']['scheme'],'url_length':inspected['features']['url_length']})
    if total!=lock['expected_rows']:raise base.TrainingError('Source record count differs from lock.')
    selected=[];duplicates=[]
    for sid,members in sorted(candidates.items()):
        if len({r['y'] for r in members})>1:reason='CONFLICTING_LABELS'
        elif sid in old_ids:reason='BASE_URL_OVERLAP'
        elif members[0]['group_id'] in old_groups:reason='BASE_DOMAIN_OVERLAP'
        else:reason=None
        if reason:
            rejected.extend({'source_record':r['source_record'],'reason':reason,'source_label':r['source_label']} for r in members);continue
        ordered=sorted(members,key=lambda r:(r['input_url'],r['source_record']));kept=ordered[0]
        kept['role']=role(kept['group_id']);selected.append(kept)
        duplicates.extend({'source_record':r['source_record'],'sample_id':sid,'kept_source_record':kept['source_record']} for r in ordered[1:])
    split={name:[r for r in selected if r['role']==name] for name in ('development','holdout')}
    if any({r['y'] for r in values}!={0,1} for values in split.values()):raise base.TrainingError('Both external roles must contain both classes.')
    if total!=len(selected)+len(rejected)+len(duplicates):raise base.TrainingError('Accounting mismatch.')
    if {r['group_id'] for r in split['development']}&{r['group_id'] for r in split['holdout']}:raise base.TrainingError('External role leakage.')
    report={'status':'PROVISIONAL_NOT_APPROVED_FOR_EVALUATION','input_rows':total,'source_labels':dict(counts),
            'retained_rows':len(selected),'excluded_rows':len(rejected),'duplicate_rows_removed':len(duplicates),
            'exclusion_reasons':dict(Counter(r['reason'] for r in rejected)),
            'exclusion_reasons_by_label':dict(Counter(f"{r['reason']}:{r['source_label']}" for r in rejected)),
            'base_groups_indexed':len(old_groups),'base_url_overlap_after_filter':0,'base_domain_overlap_after_filter':0,
            'development_holdout_group_overlap':0,'splits':{name:summarize(values) for name,values in split.items()},
            'primary_provenance_verified':False,'model_scoring_performed':False,'base_test_file_opened':False,
            'warnings':['Mirror is not byte-verified against primary release.','Cross-source and domain separation do not prove campaign independence.',
                        'Old source labels do not describe current website state.','No model training, threshold tuning or automatic label verification.']}
    if base.sha(dataset/'manifest.json')!=base_hash:raise base.TrainingError('Base manifest changed.')
    with output_dir(output) as stage:
        for name,values in split.items():write_rows(stage/f'{name}.jsonl',values)
        write_rows(stage/'exclusions.jsonl',sorted(rejected,key=lambda r:r['source_record']))
        write_rows(stage/'duplicates.jsonl',duplicates);base.write_json(stage/'report.json',report)
        save_manifest(stage,{'version':VERSION,'status':report['status'],'source':lock,'runtime':manifest['runtime'],
            'base_dataset_manifest_sha256':base_hash,'base_source_sha256':manifest['source']['csv_sha256'],
            'code_sha256':base.sha(Path(__file__)),'role_rule':'sha256(external-url-role-v1:+group_id) modulo100 <50 => development; else holdout'})
    return report


def primary_pairs(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not {'url','status'}.issubset(reader.fieldnames or []):raise base.TrainingError('Primary CSV requires url/status.')
        # Multiset, not set: preserves duplicate multiplicity. Ignores unused precomputed features.
        pairs=[]
        for row in reader:
            if row.get('status') not in {'legitimate','phishing'} or not row.get('url'):raise base.TrainingError('Invalid primary URL/label row.')
            pairs.append(prep.digest_text(json.dumps([row['url'],row['status']],ensure_ascii=False)))
    return len(pairs),prep.digest_text('\n'.join(sorted(pairs)))


def compare(primary,mirror,output):
    lock=base.load_json(LOCK)
    if base.sha(mirror)!=lock['sha256']:raise base.TrainingError('Mirror differs from source lock.')
    p=primary_pairs(primary);m=primary_pairs(mirror)
    with output_dir(output) as stage:
        result={'url_label_multiset_matches':p==m,'primary_candidate_sha256':base.sha(primary),
                'mirror_sha256':lock['sha256'],'primary_rows':p[0],'mirror_rows':m[0],
                'primary_pair_digest':p[1],'mirror_pair_digest':m[1],
                'origin_authenticated_by_this_command':False,
                'note':'User must obtain the primary candidate from the cited Mendeley V3 page. Matching contents alone does not authenticate its origin; no automatic promotion.'}
        base.write_json(stage/'comparison.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('download');d.add_argument('--output',type=Path,required=True)
    b=sub.add_parser('prepare')
    for name in ('source','dataset','base-source','output'):b.add_argument('--'+name,type=Path,required=True)
    c=sub.add_parser('compare-primary')
    for name in ('primary','mirror','output'):c.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    result=download(a.output) if a.command=='download' else (prepare(a.source,a.dataset,a.base_source,a.output) if a.command=='prepare' else compare(a.primary,a.mirror,a.output))
    print(json.dumps(result,ensure_ascii=True,indent=2))
if __name__=='__main__':run(main)
