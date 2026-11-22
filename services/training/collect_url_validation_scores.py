"""Reproduce every G1.8 model before publishing all validation scores, without URLs."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys
import numpy as np
import train_url_feature_experiments as ex
from common import base,rows,write_rows,output_dir,save_manifest,checked_file
VERSION='url-validation-score-packet-v1'
SOURCES=('phiusiil_validation','external_reused_validation')


def verify_g18(feature_run,dataset,external,baseline,g16,primary):
    m=base.load_json(feature_run/'manifest.json')
    expected={k:base.sha(p/'manifest.json') for k,p in [('dataset',dataset),('external',external),('baseline',baseline),('g16',g16)]}
    if m['version']!=ex.VERSION or m['inputs']!=expected or m['primary_sha256']!=base.sha(primary):
        raise base.TrainingError('G1.8 input snapshot mismatch.')
    paths={'train_url_feature_experiments.py':Path(ex.__file__),
           'url_feature_extensions.py':Path(ex.features.__file__),
           'diagnose_multisource_errors.py':Path(ex.dg.__file__)}
    if set(m['code_sha256'])!=set(paths) or any(base.sha(p)!=m['code_sha256'][k] for k,p in paths.items()):
        raise base.TrainingError('Frozen G1.8 code changed.')
    if m['protocol_sha256']!=base.sha(ex.PROTOCOL):raise base.TrainingError('G1.8 protocol changed.')
    for name in ['report.json','protocol.json']:checked_file(feature_run,m,name)
    r=base.load_json(feature_run/'report.json')
    if (r['version']!=ex.VERSION or r['runtime']!=base.environment() or r['threshold']!=base.THRESHOLD
        or r['protocol']!=ex.validate_protocol() or r['params']!={**base.PARAMS[ex.dg.MODEL],'class_weight':None}
        or r['feature_schemas']!={k:ex.features.schema(k) for k in ex.features.SCENARIOS}):
        raise base.TrainingError('G1.8 schema/configuration/runtime mismatch.')
    return r


def collect(dataset,external,baseline,primary,g16,feature_run,output,workers=2):
    if output.exists() or not 1<=workers<=4:raise base.TrainingError('Use new output and workers 1-4.')
    expected=verify_g18(feature_run,dataset,external,baseline,g16,primary)
    original=ex.dg.verify_run(g16,dataset,external,baseline)
    watched=[p/'manifest.json' for p in [dataset,external,baseline,g16,feature_run]]+[ex.PROTOCOL]
    snapshots={str(p):base.sha(p) for p in watched}
    base.validate_manifest(dataset)
    em,_,er,_,_=ex.dg.ms.ev.validate_inputs(external,baseline,primary,'mendeley-v3')
    if em['base_dataset_manifest_sha256']!=base.sha(dataset/'manifest.json'):raise base.TrainingError('Base dataset differs.')
    dr=base.load_json(dataset/'report.json')
    xt,yt,ti,tg=ex.load_base(dataset,'train',dr['splits']['train'])
    xv,yv,vi,vg=ex.load_base(dataset,'validation',dr['splits']['validation']);ex.dg.ms.assert_disjoint(ti,tg,vi,vg)
    xe,ye,meta,records=ex.load_external(external,er,em['source'])
    with primary.open(encoding='utf-8-sig',newline='') as f:ex.dg.ms.verify_primary_rows(records,list(csv.DictReader(f)))
    ex.dg.ms.assert_disjoint(ti|vi,tg|vg,{r['sample_id'] for r in meta},{r['group_id'] for r in meta})
    mask=ex.dg.ms.partition(meta,ye)
    if list(rows(g16/'external-assignments.jsonl'))!=ex.dg.assignments(meta,mask):raise base.TrainingError('G1.6 assignments differ.')
    ym=np.concatenate((yt,ye[mask]));source=np.concatenate((np.zeros(len(yt),dtype=int),np.ones(int(mask.sum()),dtype=int)))
    weights=ex.dg.ms.weights_for(ym,source)
    labels={SOURCES[0]:yv,SOURCES[1]:ye[~mask]}
    metadata={SOURCES[0]:[{k:r[k] for k in ['sample_id','group_id']} for r in rows(dataset/'validation.jsonl')],
              SOURCES[1]:[{k:r[k] for k in ['sample_id','group_id']} for r,m in zip(meta,mask) if not m]}
    all_scores={};reproduction={}
    for scenario in ex.features.SCENARIOS:
        print('Reproducing G1.8: '+scenario,file=sys.stderr,flush=True)
        xm=np.concatenate((xt[scenario],xe[scenario][mask]))
        evaluations={SOURCES[0]:(xv[scenario],yv),SOURCES[1]:(xe[scenario][~mask],ye[~mask])}
        scores,mtry=ex.fit_scenario(xm,ym,weights,evaluations,workers)
        stored=expected['results'][scenario]
        if stored['feature_count']!=xm.shape[1] or stored['max_features_per_split']!=mtry:raise base.TrainingError('Model feature count mismatch.')
        reproduction[scenario]={}
        for name in SOURCES:
            measured=base.metrics(labels[name],scores[name]);ex.dg.reproduce(measured,stored['sources'][name]['metrics'])
            if scenario=='baseline':ex.dg.reproduce(measured,original['results'][ex.dg.SCENARIO][ex.dg.MODEL][name]['metrics'])
            reproduction[scenario][name]=measured
        all_scores[scenario]=scores
    source_stats={name:{'rows':len(labels[name]),'groups':len({r['group_id'] for r in metadata[name]}),
                        'labels':dict(Counter(str(int(y)) for y in labels[name]))} for name in SOURCES}
    if any(base.sha(Path(p))!=h for p,h in snapshots.items()):raise base.TrainingError('Inputs changed during collection.')
    verify_g18(feature_run,dataset,external,baseline,g16,primary);ex.dg.verify_run(g16,dataset,external,baseline)
    base.validate_manifest(dataset);ex.dg.ms.ev.validate_inputs(external,baseline,primary,'mendeley-v3')
    def records_out():
        for name in SOURCES:
            if len(metadata[name])!=len(labels[name]):raise base.TrainingError('Metadata/score alignment mismatch.')
            for i,(m,y) in enumerate(zip(metadata[name],labels[name])):
                yield {**m,'source':name,'y':int(y),'scores':{k:float(all_scores[k][name][i]) for k in ex.features.SCENARIOS}}
    with output_dir(output) as stage:
        write_rows(stage/'validation-scores.jsonl',records_out())
        report={'version':VERSION,'status':'REPRODUCED_VALIDATION_SCORES_ONLY','sources':source_stats,
            'scenarios':list(ex.features.SCENARIOS),'reproduced_g18':True,'reproduction_at_0_5':reproduction,
            'runtime':base.environment(),'score_type':'MODEL_SCORE','calibration_version':None,
            'test_file_opened':False,'external_holdout_file_opened':False,'contains_raw_urls':False}
        base.write_json(stage/'report.json',report)
        save_manifest(stage,{'version':VERSION,'g18_manifest_sha256':base.sha(feature_run/'manifest.json'),
            'code_sha256':base.sha(Path(__file__))})
    return {'status':report['status'],'sources':source_stats,'reproduced_g18':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['dataset','external','baseline-run','primary-file','experiment-run','feature-run','output']:p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--primary-origin',choices=['mendeley-v3'],required=True);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    try:print(json.dumps(collect(a.dataset,a.external,a.baseline_run,a.primary_file,a.experiment_run,a.feature_run,a.output,a.workers),indent=2))
    except (OSError,ValueError,KeyError,TypeError) as e:
        print('ERROR: '+(str(e) if isinstance(e,base.TrainingError) else type(e).__name__+': check inputs/environment.'),file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
