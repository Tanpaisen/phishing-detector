"""G1.6 research-only source mixing. Never read final test or external holdout."""
import argparse
from collections import Counter
import csv
import hashlib
from pathlib import Path
import sys
import warnings
import numpy as np
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
import train_url_baselines as base
import evaluate_external_development as ev
from audit_url_structure import verify_primary_rows
from common import rows, output_dir, save_manifest, write_rows

VERSION = 'url-multisource-experiment-v1'
SPLIT_RULE = 'sha256(g16-external-v1:group_id) modulo 100 < 80 -> train; otherwise validation'


def partition(metadata, y):
    train = np.array([int(hashlib.sha256(('g16-external-v1:'+r['group_id']).encode()).hexdigest(),16)%100<80 for r in metadata])
    for mask in (train, ~train):
        if set(y[mask]) != {0,1}:
            raise base.TrainingError('Both external partitions must contain both labels; do not search for a better seed.')
    return train


def weights_for(y, sources):
    cells=Counter(zip(sources.tolist(), y.tolist()))
    if len(cells)!=4:raise base.TrainingError('Expected both labels in both training sources.')
    return np.array([len(y)/(4*cells[(s,v)]) for s,v in zip(sources,y)])


def assert_disjoint(ids_a, groups_a, ids_b, groups_b):
    if ids_a & ids_b or groups_a & groups_b:
        raise base.TrainingError('Sample or domain leakage between sources/splits.')


def summarize(y, groups):
    return {'rows':len(y),'groups':len(set(groups)), 'labels':dict(Counter(str(v) for v in y))}


def fit_models(xt,yt,evaluations,workers,weights=None):
    result={}
    for name,model in base.estimators(workers).items():
        print('Fitting '+name,file=sys.stderr,flush=True)
        kwargs={}
        if weights is not None:
            if name=='logistic_regression':
                model.set_params(classifier__class_weight=None)
                kwargs={'scale__sample_weight':weights,'classifier__sample_weight':weights}
            else:
                model.set_params(class_weight=None);kwargs={'sample_weight':weights}
        with threadpool_limits(limits=workers),warnings.catch_warnings():
            warnings.simplefilter('error',ConvergenceWarning)
            model.fit(xt,yt,**kwargs)
            if list(model.classes_)!=[0,1]:raise base.TrainingError('Wrong positive class.')
            result[name]={}
            for source,(x,y) in evaluations.items():
                scores=model.predict_proba(x)[:,1]
                result[name][source]={'metrics':base.metrics(y,scores),'slices':{
                    'http':ev.slice_metrics(y,scores,x[:,base.FEATURE_NAMES.index('is_https')]==0),
                    'https':ev.slice_metrics(y,scores,x[:,base.FEATURE_NAMES.index('is_https')]==1)}}
    return result


def experiment(dataset,external,baseline_run,primary,output,workers=2):
    if output.exists() or not 1<=workers<=4:raise base.TrainingError('Use a new output directory and workers 1-4.')
    manifests={str(p):base.sha(p) for p in (dataset/'manifest.json',external/'manifest.json',baseline_run/'manifest.json')}
    dm=base.validate_manifest(dataset)
    em,_,er,_,_=ev.validate_inputs(external,baseline_run,primary,'mendeley-v3')
    if em['base_dataset_manifest_sha256']!=base.sha(dataset/'manifest.json'):
        raise base.TrainingError('External source was filtered against another base dataset.')
    dr=base.load_json(dataset/'report.json')
    xt,yt,ti,tg=base.load_split(dataset,'train',dr['splits']['train'])
    xv,yv,vi,vg=base.load_split(dataset,'validation',dr['splits']['validation'])
    assert_disjoint(ti,tg,vi,vg)
    xe,ye,meta=ev.load_development(external,er,em['source'])
    with primary.open(encoding='utf-8-sig',newline='') as f:
        verify_primary_rows(list(rows(external/'development.jsonl')),list(csv.DictReader(f)))
    assert_disjoint(ti|vi,tg|vg,{r['sample_id'] for r in meta},{r['group_id'] for r in meta})
    mask=partition(meta,ye)
    # Every group receives one role, independent of label, order and measured model scores.
    train_groups={r['group_id'] for r,m in zip(meta,mask) if m}
    val_groups={r['group_id'] for r,m in zip(meta,mask) if not m}
    assert_disjoint(set(),train_groups,set(),val_groups)
    evaluations={'phiusiil_validation':(xv,yv),'external_reused_validation':(xe[~mask],ye[~mask])}
    xm=np.concatenate((xt,xe[mask]));ym=np.concatenate((yt,ye[mask]))
    sources=np.concatenate((np.zeros(len(yt),dtype=int),np.ones(int(mask.sum()),dtype=int)))
    weighted=weights_for(ym,sources)
    results={}
    for scenario,x,y,w in [('phiusiil_only',xt,yt,None),('mixed_pooled',xm,ym,None),('mixed_source_class_balanced',xm,ym,weighted)]:
        print('Scenario: '+scenario,file=sys.stderr,flush=True)
        results[scenario]=fit_models(x,y,evaluations,workers,w)
    # Validate immutable inputs again before atomically publishing metadata-only outputs.
    if any(base.sha(Path(p))!=h for p,h in manifests.items()):raise base.TrainingError('Input manifest changed.')
    base.validate_manifest(dataset);ev.validate_inputs(external,baseline_run,primary,'mendeley-v3')
    report={'stage':'G1.6','version':VERSION,'status':'RESEARCH_EXPERIMENT_ONLY','split_rule':SPLIT_RULE,
        'threshold':base.THRESHOLD,'seed':base.SEED,'workers':workers,'feature_schema':base.schema(),
        'params':base.PARAMS,'weighted_scenario':'class_weight=None; each source-label cell has total weight N/4; scaler uses same train weights',
        'splits':{'phiusiil_train':dr['splits']['train'],'phiusiil_validation':dr['splits']['validation'],
                  'external_train':summarize(ye[mask],train_groups),'external_reused_validation':summarize(ye[~mask],val_groups)},
        'source_origin':'USER_ATTESTED_DIRECT_MENDELEY_V3_DOWNLOAD','primary_sha256':base.sha(primary),
        'source_labels_independently_verified':False,'results':results,'runtime':base.environment(),
        'test_file_opened':False,'external_holdout_file_opened':False,'model_exported':False,'model_activated':False,
        'limitations':['External development was observed in G1.5; its reused validation is exploratory, not an unbiased test.',
                       'Historical source labels are used for research, not independently verified ground truth.',
                       'No threshold tuning, calibration, production acceptance or automatic winner selection.',
                       'Source balancing changes effective prevalence; scores are MODEL_SCORE, not calibrated probabilities.']}
    with output_dir(output) as stage:
        base.write_json(stage/'report.json',report)
        write_rows(stage/'external-assignments.jsonl',sorted(
            ({**r,'role':'train' if m else 'reused_validation'} for r,m in zip(meta,mask)),key=lambda r:r['sample_id']))
        save_manifest(stage,{'version':VERSION,'inputs':{k:base.sha(p/'manifest.json') for k,p in [('dataset',dataset),('external',external),('baseline',baseline_run)]},
            'code_sha256':{p:base.sha(Path(__file__).parent/p) for p in ['train_multisource_experiment.py','train_url_baselines.py','evaluate_external_development.py','audit_url_structure.py']}})
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['dataset','external','baseline-run','primary-file','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--primary-origin',choices=['mendeley-v3'],required=True)
    p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    try:
        r=experiment(a.dataset,a.external,a.baseline_run,a.primary_file,a.output,a.workers)
        import json
        print(json.dumps(r,ensure_ascii=True,indent=2,allow_nan=False))
    except (OSError,ValueError,KeyError,TypeError,ConvergenceWarning) as e:
        print('ERROR: '+(str(e) if isinstance(e,base.TrainingError) else type(e).__name__+': check inputs/environment.'),file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
