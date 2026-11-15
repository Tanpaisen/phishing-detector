"""G1.5: score only external development with existing, locally trained G1.2 models.

The operator attests a direct Mendeley V3 primary download. No fitting, calibration,
threshold optimization, activation, original test or external holdout file access.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
import json
import numpy as np
import joblib
from threadpoolctl import threadpool_limits
import train_url_baselines as base
import diagnose_url_baselines as diagnostics
sys.path.insert(0,str(base.ROOT/'scripts/g1_4'))
import external_urls as intake
from common import output_dir,save_manifest,checked_file,rows,prep

VERSION='external-development-evaluation-v1'
MODEL_NAMES=('logistic_regression','random_forest')


def validate_inputs(external,baseline_run,primary,origin):
    if origin!='mendeley-v3':raise base.TrainingError('Explicit Mendeley V3 origin attestation is required.')
    manifest=base.load_json(external/'manifest.json')
    lock=base.load_json(intake.LOCK)
    if manifest['version']!=intake.VERSION or manifest['source']!=lock:
        raise base.TrainingError('Unknown external intake/source snapshot.')
    primary_hash=base.sha(primary)
    if primary_hash!=lock['sha256']:
        raise base.TrainingError('Primary file does not byte-match the pinned source; compare/review before evaluating.')
    if manifest['runtime']!=prep.runtime() or manifest['code_sha256']!=base.sha(Path(intake.__file__)):
        raise base.TrainingError('External preprocessing/runtime/code differs from the intake manifest.')
    for name in ('development.jsonl','report.json'):checked_file(external,manifest,name)
    source_report=base.load_json(external/'report.json')
    if any(source_report[key]!=0 for key in ('base_url_overlap_after_filter','base_domain_overlap_after_filter','development_holdout_group_overlap')):
        raise base.TrainingError('Intake overlap checks did not pass.')
    original=diagnostics.check_baseline(baseline_run,manifest['base_dataset_manifest_sha256'])
    model_manifest=base.load_json(baseline_run/'manifest.json')
    if model_manifest['preprocessing']!=manifest['runtime'] or model_manifest['status']!='CANDIDATE':
        raise base.TrainingError('Baseline preprocessing/status mismatch.')
    if original['runtime']!=base.environment():raise base.TrainingError('Baseline runtime mismatch.')
    # Fixed filenames only; hashes are integrity checks, not authentication of arbitrary pickle files.
    for name in (*[m+'.joblib' for m in MODEL_NAMES],'feature-schema.json'):
        checked_file(baseline_run,model_manifest,name)
    if base.load_json(baseline_run/'feature-schema.json')!=base.schema():
        raise base.TrainingError('Baseline feature schema mismatch.')
    return manifest,model_manifest,source_report,original,primary_hash


def load_development(external,report,lock):
    x=[];y=[];metadata=[];seen=set();groups=set()
    for row in rows(external/'development.jsonl'):
        inspected=base.inspect_url(row['input_url']);canonical=inspected['url']['normalized_url']
        sid=prep.digest_text(canonical);group=prep.grouping(inspected)
        if (row['role']!='development' or intake.role(group)!='development' or row['group_id']!=group
                or row['sample_id']!=sid or row['normalized_url']!=canonical or sid in seen):
            raise base.TrainingError('Development role, grouping or canonical fingerprint mismatch.')
        if row['source_id']!=lock['source_id'] or row['source_label'] not in lock['label_map'] or type(row['y']) is not int or row['y']!=lock['label_map'][row['source_label']]:
            raise base.TrainingError('External source/label mapping mismatch.')
        if row['scheme']!=inspected['url']['scheme'] or row['url_length']!=inspected['features']['url_length']:
            raise base.TrainingError('External structural metadata mismatch.')
        seen.add(sid);groups.add(group)
        x.append(base.extract_features(row['input_url'],base.inspect_url));y.append(row['y'])
        metadata.append({'sample_id':sid,'group_id':group,'source_record':row['source_record']})
    expected=report['splits']['development']
    counts={str(k):v for k,v in sorted(Counter(y).items())}
    if len(x)!=expected['rows'] or len(groups)!=expected['groups'] or counts!=expected['labels'] or set(y)!={0,1}:
        raise base.TrainingError('Development counts/classes differ from the intake report.')
    return np.asarray(x,dtype=np.float64),np.asarray(y,dtype=np.int64),metadata


def slice_metrics(y,scores,mask):
    selected=y[mask];pred=(scores[mask]>=base.THRESHOLD).astype(int)
    tn=int(np.sum((selected==0)&(pred==0)));fp=int(np.sum((selected==0)&(pred==1)))
    fn=int(np.sum((selected==1)&(pred==0)));tp=int(np.sum((selected==1)&(pred==1)))
    return {'rows':len(selected),'negatives':tn+fp,'positives':tp+fn,'tn':tn,'fp':fp,'fn':fn,'tp':tp,
            'fpr':fp/(tn+fp) if tn+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
            'precision':tp/(tp+fp) if tp+fp else None}


def evaluate(external,baseline_run,primary,output,origin,workers=2):
    if output.exists() or not 1<=workers<=4:
        raise base.TrainingError('Choose a new output directory and workers 1–4.')
    external_hash=base.sha(external/'manifest.json');baseline_hash=base.sha(baseline_run/'manifest.json')
    manifest,model_manifest,intake_report,original,primary_hash=validate_inputs(external,baseline_run,primary,origin)
    x,y,metadata=load_development(external,intake_report,manifest['source'])
    print(f'Evaluating {len(y)} external DEVELOPMENT rows only; no fitting.',file=sys.stderr,flush=True)
    masks={
        'http':x[:,base.FEATURE_NAMES.index('is_https')]==0,
        'https':x[:,base.FEATURE_NAMES.index('is_https')]==1,
        'length_ge_34':x[:,base.FEATURE_NAMES.index('url_length')]>=34,
        'length_lt_34':x[:,base.FEATURE_NAMES.index('url_length')]<34,
        'ip_host':x[:,base.FEATURE_NAMES.index('is_ip')]==1,
    }
    results={}
    for name in MODEL_NAMES:
        path=baseline_run/(name+'.joblib')
        checked_file(baseline_run,model_manifest,path.name)
        # Only load the user's own G1.2 run. A downloaded pickle + its own hash is NOT a trust boundary.
        bundle=joblib.load(path)
        if (bundle['feature_schema']!=base.schema() or bundle['positive_label']!=1 or bundle['score_type']!='MODEL_SCORE'
                or bundle['calibration_version'] is not None or bundle['pipeline_version']!=base.VERSION):
            raise base.TrainingError('Model bundle schema/label/score metadata mismatch.')
        model=bundle['model']
        if list(model.classes_)!=[0,1] or model.n_features_in_!=len(base.FEATURE_NAMES):
            raise base.TrainingError('Model class order or feature count mismatch.')
        with threadpool_limits(limits=workers):scores=model.predict_proba(x)[:,1]
        measured=base.metrics(y,scores)
        results[name]={'external_development':measured,'phiusiil_validation_reference':original['results'][name]['validation'],
            'recall_change_vs_original_validation':measured['recall']-original['results'][name]['validation']['recall'],
            'fpr_change_vs_original_validation':measured['fpr']-original['results'][name]['validation']['fpr'],
            'slices':{key:slice_metrics(y,scores,mask) for key,mask in masks.items()},
            'model_sha256':model_manifest['files'][path.name]}
        del bundle,model
    provenance={'source_id':manifest['source']['source_id'],'source_page':manifest['source']['source_page'],
        'doi':manifest['source']['doi'],'origin_basis':'USER_ATTESTED_DIRECT_MENDELEY_V3_DOWNLOAD',
        'origin_authenticated_by_software':False,'primary_byte_match':True,'primary_sha256':primary_hash,
        'scope':'EXTERNAL_DEVELOPMENT_DIAGNOSTIC_EVALUATION_ONLY',
        'source_labels_independently_verified':False,'recorded_at':datetime.now(timezone.utc).isoformat()}
    report={'stage':'G1.5','version':VERSION,'status':'EXTERNAL_DEVELOPMENT_DIAGNOSTICS_ONLY',
        'evaluation_role':'development','rows':len(y),'groups':len({r['group_id'] for r in metadata}),
        'labels':dict(Counter(str(v) for v in y)), 'threshold':base.THRESHOLD,
        'external_manifest_sha256':external_hash,'baseline_manifest_sha256':baseline_hash,
        'provenance':provenance,'results':results,'runtime':base.environment(),
        'model_fit_performed':False,'threshold_tuning_performed':False,'model_activation_performed':False,
        'external_holdout_file_opened':False,'phiusiil_test_file_opened':False,
        'limitations':['This external development set is now observed; do not report it as an untouched final test.',
                      'Source labels are historical annotations; source-file equality does not verify every label.',
                      'AP/precision depend on class balance; cross-source metrics are descriptive, not a causal comparison.',
                      'No calibration, confidence intervals or production acceptance claim.']}
    # Refuse publishing if inputs changed while extracting/scoring. Never touch holdout.jsonl or test.jsonl.
    if base.sha(external/'manifest.json')!=external_hash or base.sha(baseline_run/'manifest.json')!=baseline_hash:
        raise base.TrainingError('Input manifests changed during evaluation.')
    validate_inputs(external,baseline_run,primary,origin)
    with output_dir(output) as stage:
        base.write_json(stage/'report.json',report);base.write_json(stage/'provenance-record.json',provenance)
        save_manifest(stage,{'version':VERSION,'external_manifest_sha256':external_hash,'baseline_manifest_sha256':baseline_hash,
            'primary_sha256':primary_hash,'runtime':base.environment(),
            'code_sha256':{'evaluate_external_development.py':base.sha(Path(__file__)),
                          'external_urls.py':base.sha(Path(intake.__file__)),
                          'train_url_baselines.py':base.sha(Path(base.__file__))}})
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('external','baseline-run','primary-file','output'):p.add_argument('--'+flag,type=Path,required=True)
    p.add_argument('--primary-origin',choices=['mendeley-v3'],required=True)
    p.add_argument('--workers',type=int,default=2)
    a=p.parse_args()
    try:
        result=evaluate(a.external,a.baseline_run,a.primary_file,a.output,a.primary_origin,a.workers)
        print(json.dumps(result,ensure_ascii=True,indent=2,allow_nan=False))
    except (OSError,ValueError,KeyError,TypeError,AttributeError) as e:
        message=str(e) if isinstance(e,base.TrainingError) else type(e).__name__+': check trusted model run, data and environment.'
        print('ERROR: '+message,file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
