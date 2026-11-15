"""Read-only train/development structural audit; no model inference or holdout/test file reads."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from urllib.parse import urlsplit
import evaluate_external_development as evaluation
from common import base,rows,checked_file,output_dir,save_manifest


def structure_counts(records):
    counts={str(y):Counter() for y in (0,1)}
    for row in records:
        if type(row['y']) is not int or row['y'] not in (0,1):raise base.TrainingError('Invalid project label.')
        u=row['input_url'].strip(' ');p=urlsplit(u)
        if p.scheme.lower() not in ('http','https'):raise base.TrainingError('Unsupported scheme in prepared data.')
        c=counts[str(row['y'])];c['rows']+=1;c[p.scheme.lower()]+=1
        c['empty_path' if not p.path else ('slash_only_path' if p.path=='/' else 'non_root_path')]+=1
        c['exactly_two_slashes' if u.count('/')==2 else 'other_slash_count']+=1
    return {label:dict(values) for label,values in counts.items()}


def verify_primary_rows(development,primary_rows):
    for row in development:
        i=row['source_record']
        if type(i) is not int or not 1<=i<=len(primary_rows):raise base.TrainingError('Invalid source record.')
        original=primary_rows[i-1]
        if original['url']!=row['input_url'] or original['status']!=row['source_label'] or row['y']!={'legitimate':0,'phishing':1}.get(original['status']):
            raise base.TrainingError('Source row URL/label mismatch.')
    return len(development)


def audit(dataset,external,primary,output):
    base.validate_manifest(dataset)
    m=base.load_json(external/'manifest.json');lock=base.load_json(evaluation.intake.LOCK)
    if m['source']!=lock or base.sha(primary)!=lock['sha256'] or m['base_dataset_manifest_sha256']!=base.sha(dataset/'manifest.json'):
        raise base.TrainingError('Source/base dataset mismatch.')
    checked_file(external,m,'development.jsonl')
    development=list(rows(external/'development.jsonl'))
    if any(row['role']!='development' for row in development):raise base.TrainingError('Wrong external role.')
    with primary.open(encoding='utf-8-sig',newline='') as f:primary_rows=list(csv.DictReader(f))
    result={'external_development_original_rows_verified':verify_primary_rows(development,primary_rows),'final_test_read':False,
            'counts':{'phiusiil_train':structure_counts(rows(dataset/'train.jsonl')),
                      'external_development':structure_counts(development)}}
    with output_dir(output) as stage:
        base.write_json(stage/'report.json',result)
        save_manifest(stage,{'version':'url-structure-audit-v1','primary_sha256':base.sha(primary),
            'base_dataset_manifest_sha256':base.sha(dataset/'manifest.json'),
            'external_manifest_sha256':base.sha(external/'manifest.json'),'code_sha256':base.sha(Path(__file__))})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('dataset','external','primary-file','output'):p.add_argument('--'+flag,type=Path,required=True)
    a=p.parse_args()
    try:print(json.dumps(audit(a.dataset,a.external,a.primary_file,a.output),ensure_ascii=True,indent=2))
    except (OSError,ValueError,KeyError,TypeError) as e:
        print('ERROR: '+(str(e) if isinstance(e,base.TrainingError) else type(e).__name__+': check audit inputs.'));return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
