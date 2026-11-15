"""Local, human review packets. Never changes labels in the frozen dataset or trains a model."""
import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from common import base,prep,rows,write_rows,checked_file,save_manifest,output_dir,run

VERSION='url-error-review-v1'
STATES={'UNREVIEWED','CONFIRM_SOURCE','CORRECT_SOURCE','INSUFFICIENT_EVIDENCE'}


def defang(value):
    return value.replace('https://','hxxps://').replace('http://','hxxp://').replace('.','[.]')


def export(dataset,diagnostics,output):
    base.validate_manifest(dataset)
    dataset_hash=base.sha(dataset/'manifest.json')
    manifest=base.load_json(diagnostics/'manifest.json')
    if manifest['version']!='url-diagnostics-v1' or manifest['dataset_manifest_sha256']!=dataset_hash:
        raise base.TrainingError('Diagnostics do not belong to this dataset.')
    checked_file(diagnostics,manifest,'error-review.jsonl');checked_file(diagnostics,manifest,'report.json')
    requested=list(rows(diagnostics/'error-review.jsonl'));by_id={}
    for item in requested:by_id.setdefault(item['sample_id'],[]).append(item)
    matched={}
    for item in rows(dataset/'validation.jsonl'):
        if item['sample_id'] in by_id:matched[item['sample_id']]=item
    if set(matched)!=set(by_id):raise base.TrainingError('Review sample is not in validation.')
    cases=[]
    for sid in sorted(by_id):
        sample=matched[sid];inspected=prep.inspect_url(sample['input_url'])
        if prep.digest_text(inspected['url']['normalized_url'])!=sid:raise base.TrainingError('Review URL fingerprint mismatch.')
        signals=[]
        for error in by_id[sid]:
            if error['source_record']!=sample['source_record'] or error['group_id']!=sample['group_id'] or error['source_y']!=sample['y']:
                raise base.TrainingError('Review metadata differs from validation.')
            expected='FP' if sample['y']==0 else 'FN'
            if error['error_type']!=expected or error['predicted_y']==sample['y']:
                raise base.TrainingError('Invalid error type.')
            signals.append({key:error[key] for key in ('model','error_type','predicted_y','score','score_type')})
        cases.append({'sample_id':sid,'group_id':sample['group_id'],'source_record':sample['source_record'],
                      'source_id':sample['source_id'],'source_y':sample['y'],'url_display':defang(inspected['url']['normalized_url']),
                      'original_input_display':defang(sample['input_url']),'model_errors':signals,
                      'usage':'VALIDATION_REVIEW_ONLY'})
    decisions=[{'sample_id':c['sample_id'],'status':'UNREVIEWED','proposed_y':None,'reviewer':None,
                'reviewed_at':None,'evidence_refs':[],'reason':''} for c in cases]
    with output_dir(output) as stage:
        write_rows(stage/'cases.jsonl',cases);write_rows(stage/'decisions-template.jsonl',decisions)
        base.write_json(stage/'summary.json',{'diagnostic_rows':len(requested),'unique_cases':len(cases),'reviewed_cases':0,
                    'final_test_file_opened':False,'note':'Defanged display still contains source URL data; keep private. Source labels are not independent verification.'})
        save_manifest(stage,{'version':VERSION,'dataset_manifest_sha256':dataset_hash,
            'diagnostics_manifest_sha256':base.sha(diagnostics/'manifest.json'),'code_sha256':base.sha(Path(__file__))})
    return {'status':'REVIEW_PACKET_CREATED','unique_cases':len(cases),'reviewed_cases':0}


def validate(packet,decisions_file,output):
    manifest=base.load_json(packet/'manifest.json')
    if manifest['version']!=VERSION:raise base.TrainingError('Unknown review packet version.')
    checked_file(packet,manifest,'cases.jsonl');checked_file(packet,manifest,'decisions-template.jsonl')
    cases={r['sample_id']:r for r in rows(packet/'cases.jsonl')}
    items=list(rows(decisions_file));seen=set();changes=[];counts=Counter()
    fields={'sample_id','status','proposed_y','reviewer','reviewed_at','evidence_refs','reason'}
    for item in items:
        if set(item)!=fields:raise base.TrainingError('Decision fields do not match the template.')
        sid=item['sample_id'];status=item['status']
        if sid not in cases or sid in seen or status not in STATES:raise base.TrainingError('Unknown, repeated or invalid decision.')
        seen.add(sid);counts[status]+=1
        if status=='UNREVIEWED':
            if item!=dict(sample_id=sid,status=status,proposed_y=None,reviewer=None,reviewed_at=None,evidence_refs=[],reason=''):
                raise base.TrainingError('Unreviewed decision must not contain a label assertion.')
            continue
        for field in ('reviewer','reason','reviewed_at'):
            if not isinstance(item[field],str) or not item[field].strip():raise base.TrainingError('Reviewed decisions need reviewer, date and reason.')
        if len(item['reason'].strip())<10:raise base.TrainingError('Provide a meaningful review reason (at least 10 characters).')
        try:
            date=datetime.fromisoformat(item['reviewed_at'].replace('Z','+00:00'))
            if date.tzinfo is None:raise ValueError()
        except (ValueError,AttributeError):raise base.TrainingError('reviewed_at must include ISO8601 timezone.') from None
        refs=item['evidence_refs']
        if not isinstance(refs,list) or not all(isinstance(ref,str) and ref.strip() for ref in refs):
            raise base.TrainingError('Evidence references must be nonempty strings in a list.')
        if status=='INSUFFICIENT_EVIDENCE':
            if item['proposed_y'] is not None:raise base.TrainingError('Insufficient evidence cannot assign a label.')
            continue
        if type(item['proposed_y']) is not int or item['proposed_y'] not in (0,1) or not refs:
            raise base.TrainingError('Label decisions require binary label and evidence references.')
        agrees=item['proposed_y']==cases[sid]['source_y']
        if (status=='CONFIRM_SOURCE')!=agrees:raise base.TrainingError('Decision contradicts source label/status.')
        if status=='CORRECT_SOURCE':changes.append({**item,'source_y':cases[sid]['source_y'],'usage':'PROPOSED_CORRECTION_ONLY_NOT_TRAINING_DATA'})
    if seen!=set(cases):raise base.TrainingError('Decisions must cover all cases; leave unfinished cases UNREVIEWED.')
    summary={'status':'DECISION_STRUCTURE_VALID','unique_cases':len(cases),'status_counts':dict(counts),
             'proposed_corrections':len(changes),'reviewer_identity_authenticated':False,'evidence_contents_verified':False,
             'eligible_for_training':False,'frozen_labels_changed':False,
             'note':'Checks completeness and consistency, not truth of evidence or reviewer authorization.'}
    with output_dir(output) as stage:
        base.write_json(stage/'summary.json',summary);write_rows(stage/'proposed-label-changes.jsonl',changes)
        # Preserve exact submitted decision snapshot, but never overwrite the original packet/dataset.
        write_rows(stage/'decisions-snapshot.jsonl',items)
        save_manifest(stage,{'version':VERSION,'packet_manifest_sha256':base.sha(packet/'manifest.json'),
                             'decisions_sha256':base.sha(decisions_file),'code_sha256':base.sha(Path(__file__))})
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    e=sub.add_parser('export')
    for name in ('dataset','diagnostics','output'):e.add_argument('--'+name,type=Path,required=True)
    v=sub.add_parser('validate')
    for name in ('packet','decisions','output'):v.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();result=export(a.dataset,a.diagnostics,a.output) if a.command=='export' else validate(a.packet,a.decisions,a.output)
    print(json.dumps(result,ensure_ascii=True,indent=2))
if __name__=='__main__':run(main)
