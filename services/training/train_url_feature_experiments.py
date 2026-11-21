"""G1.8: fixed, separate hostname and path/query feature experiments; no final test reads."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import numpy as np
from threadpoolctl import threadpool_limits
import diagnose_multisource_errors as dg
from common import base,rows,output_dir,save_manifest,checked_file
from phishing_core import url_feature_extensions as features

VERSION='url-feature-experiments-v1'
PROTOCOL=base.ROOT/'docs/g1-8/protocol.json'


def validate_protocol():
    p=base.load_json(PROTOCOL)
    if (p['version']!='url-feature-ablation-protocol-v1' or p['scenarios']!=list(features.SCENARIOS)
        or p['seed']!=base.SEED or p['threshold']!=base.THRESHOLD or p['class_weight'] is not None
        or p['base_scenario']!=dg.SCENARIO or p['model']!='RandomForestClassifier'):
        raise base.TrainingError('Experiment protocol/configuration mismatch.')
    return p


def load_base(directory,split,expected):
    if split not in ('train','validation'):raise base.TrainingError('Final split is forbidden.')
    vectors={name:[] for name in features.SCENARIOS};labels=[];ids=set();groups=set()
    for number,r in enumerate(rows(directory/(split+'.jsonl')),1):
        if r['source_label'] not in ('0','1') or type(r['y']) is not int or r['y']!=1-int(r['source_label']):
            raise base.TrainingError('Base label mapping mismatch.')
        inspected=base.inspect_url(r['input_url'])
        sid=dg.ms.ev.prep.digest_text(inspected['url']['normalized_url']);group=dg.ms.ev.prep.grouping(inspected)
        if r['sample_id']!=sid or r['group_id']!=group or sid in ids:raise base.TrainingError('Base fingerprint/group mismatch.')
        value=features.extract_all(r['input_url'],lambda _:inspected)
        for name in features.SCENARIOS:vectors[name].append(value[name])
        labels.append(r['y']);ids.add(sid);groups.add(group)
        if number%25000==0:print(f'{split}: extracted {number} rows',file=sys.stderr,flush=True)
    counts=dict(Counter(str(v) for v in labels))
    if len(labels)!=expected['rows'] or len(groups)!=expected['groups'] or counts!=expected['labels'] or set(labels)!={0,1}:
        raise base.TrainingError('Base split counts/classes mismatch.')
    return {k:np.asarray(v,dtype=np.float64) for k,v in vectors.items()},np.array(labels),ids,groups


def load_external(external,er,source):
    # The frozen loader checks role, source label, canonical fingerprints and counts.
    original,y,meta=dg.ms.ev.load_development(external,er,source)
    records=list(rows(external/'development.jsonl'));vectors={k:[] for k in features.SCENARIOS}
    for r in records:
        value=features.extract_all(r['input_url'],base.inspect_url)
        for k in vectors:vectors[k].append(value[k])
    vectors={k:np.asarray(v,dtype=np.float64) for k,v in vectors.items()}
    if not np.array_equal(original,vectors['baseline']):raise base.TrainingError('Legacy feature representation changed.')
    return vectors,y,meta,records


def paired_changes(y,baseline_scores,new_scores):
    if not len(y)==len(baseline_scores)==len(new_scores):raise base.TrainingError('Prediction alignment mismatch.')
    b=baseline_scores>=base.THRESHOLD;n=new_scores>=base.THRESHOLD
    negative=y==0;positive=y==1
    return {'corrected_fp':int(np.sum(negative & b & ~n)), 'introduced_fp':int(np.sum(negative & ~b & n)),
            'corrected_fn':int(np.sum(positive & ~b & n)), 'introduced_fn':int(np.sum(positive & b & ~n))}


def fit_scenario(xt,yt,weights,evaluations,workers):
    model=base.estimators(workers)[dg.MODEL];model.set_params(class_weight=None)
    with threadpool_limits(limits=workers):
        model.fit(xt,yt,sample_weight=weights)
        if list(model.classes_)!=[0,1]:raise base.TrainingError('Unexpected class order.')
        scores={name:model.predict_proba(x)[:,1] for name,(x,_) in evaluations.items()}
    return scores,model.estimators_[0].max_features_


def experiment(dataset,external,baseline,primary,run,output,workers=2):
    if output.exists() or not 1<=workers<=4:raise base.TrainingError('Use new output and workers 1-4.')
    protocol=validate_protocol()
    watched=[dataset/'manifest.json',external/'manifest.json',baseline/'manifest.json',run/'manifest.json',PROTOCOL]
    snapshot={str(p):base.sha(p) for p in watched}
    original=dg.verify_run(run,dataset,external,baseline)
    base.validate_manifest(dataset)
    em,_,er,_,_=dg.ms.ev.validate_inputs(external,baseline,primary,'mendeley-v3')
    if original['primary_sha256']!=base.sha(primary) or em['base_dataset_manifest_sha256']!=base.sha(dataset/'manifest.json'):
        raise base.TrainingError('Primary/base source mismatch.')
    dr=base.load_json(dataset/'report.json')
    xt,yt,ti,tg=load_base(dataset,'train',dr['splits']['train'])
    xv,yv,vi,vg=load_base(dataset,'validation',dr['splits']['validation']);dg.ms.assert_disjoint(ti,tg,vi,vg)
    xe,ye,meta,records=load_external(external,er,em['source'])
    with primary.open(encoding='utf-8-sig',newline='') as f:dg.ms.verify_primary_rows(records,list(csv.DictReader(f)))
    dg.ms.assert_disjoint(ti|vi,tg|vg,{r['sample_id'] for r in meta},{r['group_id'] for r in meta})
    mask=dg.ms.partition(meta,ye)
    if list(rows(run/'external-assignments.jsonl'))!=dg.assignments(meta,mask):raise base.TrainingError('G1.6 assignments changed.')
    ym=np.concatenate((yt,ye[mask]));source=np.concatenate((np.zeros(len(yt),dtype=int),np.ones(int(mask.sum()),dtype=int)))
    weights=dg.ms.weights_for(ym,source)
    results={};baseline_scores=None
    for scenario in features.SCENARIOS:
        print('Fitting '+scenario,file=sys.stderr,flush=True)
        xm=np.concatenate((xt[scenario],xe[scenario][mask]))
        evaluations={'phiusiil_validation':(xv[scenario],yv),'external_reused_validation':(xe[scenario][~mask],ye[~mask])}
        scores,mtry=fit_scenario(xm,ym,weights,evaluations,workers)
        measured={name:base.metrics(y,scores[name]) for name,(_,y) in evaluations.items()}
        if scenario=='baseline':
            for name in evaluations:dg.reproduce(measured[name],original['results'][dg.SCENARIO][dg.MODEL][name]['metrics'])
            baseline_scores=scores
        results[scenario]={'feature_count':xm.shape[1],'max_features_per_split':mtry,'sources':{}}
        for name,(x,y) in evaluations.items():
            results[scenario]['sources'][name]={'metrics':measured[name],
                'slices':{key:dg.ms.ev.slice_metrics(y,scores[name],selection) for key,selection in dg.masks_for(x[:,:len(base.FEATURE_NAMES)]).items()},
                'paired_changes_vs_baseline':paired_changes(y,baseline_scores[name],scores[name])}
    if any(base.sha(Path(p))!=h for p,h in snapshot.items()):raise base.TrainingError('Input snapshots changed during run.')
    dg.verify_run(run,dataset,external,baseline);base.validate_manifest(dataset)
    dg.ms.ev.validate_inputs(external,baseline,primary,'mendeley-v3');validate_protocol()
    report={'stage':'G1.8','version':VERSION,'status':'EXPLORATORY_FEATURE_EXPERIMENT_ONLY',
      'baseline_reproduced_g16':True,'protocol':protocol,'protocol_sha256':base.sha(PROTOCOL),
      'splits':original['splits'],'runtime':base.environment(),'workers':workers,
      'params':{**base.PARAMS[dg.MODEL],'class_weight':None},'threshold':base.THRESHOLD,
      'feature_schemas':{k:features.schema(k) for k in features.SCENARIOS},'results':results,
      'test_file_opened':False,'external_holdout_file_opened':False,'frozen_labels_changed':False,
      'model_exported':False,'model_activated':False,'automatic_winner_selected':False,
      'limitations':['Already-observed validation informed these hypotheses; results remain exploratory.',
                    'Historical source labels were not independently verified.',
                    'Single seed, no uncertainty interval. No causal claim or deployment acceptance.',
                    'MODEL_SCORE is uncalibrated. No threshold or hyperparameter search.']}
    with output_dir(output) as stage:
        base.write_json(stage/'report.json',report);base.write_json(stage/'protocol.json',protocol)
        save_manifest(stage,{'version':VERSION,'inputs':{k:base.sha(p/'manifest.json') for k,p in [('dataset',dataset),('external',external),('baseline',baseline),('g16',run)]},
            'primary_sha256':base.sha(primary),'protocol_sha256':base.sha(PROTOCOL),
            'code_sha256':{'train_url_feature_experiments.py':base.sha(Path(__file__)),
                'url_feature_extensions.py':base.sha(Path(features.__file__)),
                'diagnose_multisource_errors.py':base.sha(Path(dg.__file__))}})
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['dataset','external','baseline-run','primary-file','experiment-run','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--primary-origin',choices=['mendeley-v3'],required=True);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    try:print(json.dumps(experiment(a.dataset,a.external,a.baseline_run,a.primary_file,a.experiment_run,a.output,a.workers),indent=2,allow_nan=False))
    except (OSError,ValueError,KeyError,TypeError) as e:
        print('ERROR: '+(str(e) if isinstance(e,base.TrainingError) else type(e).__name__+': check inputs/environment.'),file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
