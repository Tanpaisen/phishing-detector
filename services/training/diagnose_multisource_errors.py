"""Reproduce G1.6 weighted RF and export private, unreviewed validation cases."""
import argparse
import csv
import json
from pathlib import Path
import sys
import numpy as np
from threadpoolctl import threadpool_limits
import train_multisource_experiment as ms
from common import base,rows,write_rows,checked_file,output_dir,save_manifest
import review_errors as review
VERSION='url-multisource-diagnostics-v1'
SCENARIO='mixed_source_class_balanced'
MODEL='random_forest'


def verify_run(run,dataset,external,baseline):
    m=base.load_json(run/'manifest.json')
    expected={k:base.sha(p/'manifest.json') for k,p in [('dataset',dataset),('external',external),('baseline',baseline)]}
    if m['version']!=ms.VERSION or m['inputs']!=expected:raise base.TrainingError('G1.6 input snapshot mismatch.')
    names={'train_multisource_experiment.py','train_url_baselines.py','evaluate_external_development.py','audit_url_structure.py'}
    if set(m['code_sha256'])!=names:raise base.TrainingError('Unknown code snapshot.')
    for name in names:
        if base.sha(Path(__file__).parent/name)!=m['code_sha256'][name]:raise base.TrainingError('Frozen G1.6 code changed.')
    for name in ['report.json','external-assignments.jsonl']:checked_file(run,m,name)
    r=base.load_json(run/'report.json')
    if (r['version']!=ms.VERSION or r['runtime']!=base.environment() or r['feature_schema']!=base.schema()
        or r['threshold']!=base.THRESHOLD or r['params']!=base.PARAMS or r['split_rule']!=ms.SPLIT_RULE):
        raise base.TrainingError('G1.6 configuration/runtime mismatch.')
    return r


def reproduce(actual,expected):
    if actual['confusion_matrix']!=expected['confusion_matrix']:raise base.TrainingError('Confusion matrix does not reproduce G1.6.')
    for k in ['accuracy','precision','recall','f1','fpr','average_precision','roc_auc']:
        if not np.isclose(actual[k],expected[k],atol=1e-8,rtol=0):raise base.TrainingError('Metrics do not reproduce G1.6.')


def assignments(meta,mask):
    return sorted(({**r,'role':'train' if flag else 'reused_validation'} for r,flag in zip(meta,mask)),key=lambda r:r['sample_id'])


def masks_for(x):
    f=lambda name:x[:,base.FEATURE_NAMES.index(name)]
    return {'all':np.ones(len(x),dtype=bool),'http':f('is_https')==0,'https':f('is_https')==1,
      'empty_path':f('path_length')==0,'nonempty_path':f('path_length')>0,
      'has_query':f('has_query')==1,'no_query':f('has_query')==0,
      'has_subdomain':f('subdomain_count')>0,'no_subdomain':f('subdomain_count')==0,
      'ip_host':f('is_ip')==1,'hostname_host':f('is_ip')==0,
      'length_lt_34':f('url_length')<34,'length_ge_34':f('url_length')>=34}


def describe(records,x,y,scores,source):
    if not len(records)==len(x)==len(y)==len(scores):raise base.TrainingError('Record alignment mismatch.')
    if not np.isfinite(scores).all() or np.any((scores<0)|(scores>1)):raise base.TrainingError('Invalid scores.')
    cases=[]
    for r,features,label,score in zip(records,x,y,scores):
        inspected=base.inspect_url(r['input_url'])
        if (r['y']!=label or ms.ev.prep.digest_text(inspected['url']['normalized_url'])!=r['sample_id']
            or ms.ev.prep.grouping(inspected)!=r['group_id']):raise base.TrainingError('Review fingerprint/label mismatch.')
        predicted=int(score>=base.THRESHOLD)
        if predicted==label:continue
        cases.append({'sample_id':r['sample_id'],'group_id':r['group_id'],'source_record':r['source_record'],
          'source_id':r['source_id'],'evaluation_source':source,'source_y':int(label),
          'url_display':review.defang(inspected['url']['normalized_url']),
          'original_input_display':review.defang(r['input_url']),
          'features':dict(zip(base.FEATURE_NAMES,map(float,features))),
          'model_errors':[{'model':MODEL,'scenario':SCENARIO,'error_type':'FP' if label==0 else 'FN',
                           'predicted_y':predicted,'score':float(score),'score_type':'MODEL_SCORE'}],
          'usage':'VALIDATION_REVIEW_ONLY'})
    return cases,{name:ms.ev.slice_metrics(y,scores,mask) for name,mask in masks_for(x).items()}


def diagnose(dataset,external,baseline,primary,run,output,workers=2):
    if output.exists() or not 1<=workers<=4:raise base.TrainingError('Use new output and workers 1-4.')
    original=verify_run(run,dataset,external,baseline)
    snapshots={str(p):base.sha(p) for p in [run/'manifest.json',dataset/'manifest.json',external/'manifest.json',baseline/'manifest.json']}
    base.validate_manifest(dataset)
    em,_,er,_,_=ms.ev.validate_inputs(external,baseline,primary,'mendeley-v3')
    if original['primary_sha256']!=base.sha(primary) or em['base_dataset_manifest_sha256']!=base.sha(dataset/'manifest.json'):
        raise base.TrainingError('Primary/base source changed.')
    dr=base.load_json(dataset/'report.json')
    xt,yt,ti,tg=base.load_split(dataset,'train',dr['splits']['train'])
    xv,yv,vi,vg=base.load_split(dataset,'validation',dr['splits']['validation']);ms.assert_disjoint(ti,tg,vi,vg)
    xe,ye,meta=ms.ev.load_development(external,er,em['source'])
    records=list(rows(external/'development.jsonl'))
    with primary.open(encoding='utf-8-sig',newline='') as f:ms.verify_primary_rows(records,list(csv.DictReader(f)))
    ms.assert_disjoint(ti|vi,tg|vg,{r['sample_id'] for r in meta},{r['group_id'] for r in meta})
    mask=ms.partition(meta,ye)
    if list(rows(run/'external-assignments.jsonl'))!=assignments(meta,mask):raise base.TrainingError('Assignments differ from G1.6.')
    xm=np.concatenate((xt,xe[mask]));ym=np.concatenate((yt,ye[mask]))
    weights=ms.weights_for(ym,np.concatenate((np.zeros(len(yt),dtype=int),np.ones(int(mask.sum()),dtype=int))))
    model=base.estimators(workers)[MODEL];model.set_params(class_weight=None)
    print('Reproducing G1.6 weighted Random Forest.',file=sys.stderr,flush=True)
    with threadpool_limits(limits=workers):model.fit(xm,ym,sample_weight=weights)
    evaluations={'phiusiil_validation':(list(rows(dataset/'validation.jsonl')),xv,yv),
                 'external_reused_validation':([r for r,m in zip(records,mask) if not m],xe[~mask],ye[~mask])}
    summaries={};cases=[]
    for source,(records,x,y) in evaluations.items():
        with threadpool_limits(limits=workers):scores=model.predict_proba(x)[:,1]
        measured=base.metrics(y,scores);reproduce(measured,original['results'][SCENARIO][MODEL][source]['metrics'])
        subset,slices=describe(records,x,y,scores,source);cases.extend(subset)
        summaries[source]={'metrics':measured,'slices':slices,'review_cases':len(subset)}
    if len({r['sample_id'] for r in cases})!=len(cases):raise base.TrainingError('Repeated review sample.')
    cases.sort(key=lambda r:r['sample_id'])
    decisions=[{'sample_id':r['sample_id'],'status':'UNREVIEWED','proposed_y':None,'reviewer':None,
                'reviewed_at':None,'evidence_refs':[],'reason':''} for r in cases]
    report={'stage':'G1.7','version':VERSION,'status':'DIAGNOSTICS_AND_UNREVIEWED_PACKET_ONLY',
      'scenario':SCENARIO,'model':MODEL,'threshold':base.THRESHOLD,'reproduced_g16':True,
      'sources':summaries,'review_cases':len(cases),'reviewed_cases':0,'runtime':base.environment(),
      'test_file_opened':False,'external_holdout_file_opened':False,'frozen_labels_changed':False,
      'new_features_added':False,'model_activated':False,
      'limitations':['Slice groups overlap; do not sum counts across groups.',
        'Source labels are historical and not independently verified.',
        'Reused validation is exploratory, not a final test. No automatic corrections or threshold tuning.']}
    if any(base.sha(Path(p))!=h for p,h in snapshots.items()):raise base.TrainingError('Input manifests changed.')
    verify_run(run,dataset,external,baseline);base.validate_manifest(dataset)
    ms.ev.validate_inputs(external,baseline,primary,'mendeley-v3')
    with output_dir(output) as stage:
        base.write_json(stage/'report.json',report)
        packet=stage/'review-packet';packet.mkdir()
        write_rows(packet/'cases.jsonl',cases);write_rows(packet/'decisions-template.jsonl',decisions)
        base.write_json(packet/'summary.json',{'unique_cases':len(cases),'reviewed_cases':0,'note':'Private defanged URLs; never commit packet. Model errors do not prove source labels wrong.'})
        save_manifest(packet,{'version':review.VERSION,'producer':VERSION,'g16_manifest_sha256':base.sha(run/'manifest.json')})
        base.write_json(stage/'manifest.json',{'version':VERSION,'g16_manifest_sha256':base.sha(run/'manifest.json'),
          'code_sha256':base.sha(Path(__file__)),'files':{'report.json':base.sha(stage/'report.json'),'review-packet/manifest.json':base.sha(packet/'manifest.json')}})
    return {'status':report['status'],'reproduced_g16':True,'review_cases':len(cases),'reviewed_cases':0}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['dataset','external','baseline-run','primary-file','experiment-run','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--primary-origin',choices=['mendeley-v3'],required=True);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    try:print(json.dumps(diagnose(a.dataset,a.external,a.baseline_run,a.primary_file,a.experiment_run,a.output,a.workers),indent=2))
    except (OSError,ValueError,KeyError,TypeError) as e:
        print('ERROR: '+(str(e) if isinstance(e,base.TrainingError) else type(e).__name__+': check inputs/environment.'),file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
