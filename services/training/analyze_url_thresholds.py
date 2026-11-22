"""Empirical joint-source threshold study on reproduced validation scores only."""
import argparse
from collections import Counter
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import numpy as np
import collect_url_validation_scores as collector
from common import base,rows,checked_file,output_dir,save_manifest
VERSION='url-threshold-study-v1'
PROTOCOL=base.ROOT/'docs/g1-9/protocol.json'
CAPS=('0.001','0.005','0.01','0.02','0.05')
FIXED=(0.5,0.6,0.7,0.8,0.9,0.95,0.99)
SCENARIOS=collector.ex.features.SCENARIOS
SOURCES=collector.SOURCES


def validate_arrays(y,s):
    y=np.asarray(y);s=np.asarray(s)
    if (y.ndim!=1 or s.ndim!=1 or len(y)!=len(s) or y.dtype.kind=='b' or set(y.tolist())!={0,1}
        or s.dtype.kind not in 'fiu' or not np.isfinite(s).all() or np.any((s<0)|(s>1))):
        raise base.TrainingError('Invalid labels or MODEL_SCORE values.')
    return y,s


def allowed_fp(cap,negatives):
    value=Fraction(str(cap))
    if not 0<=value<=1 or type(negatives) is not int or negatives<=0:raise base.TrainingError('Invalid FPR budget.')
    return (value.numerator*negatives)//value.denominator


def point(y,s,threshold):
    y,s=validate_arrays(y,s)
    if not math.isfinite(threshold) or threshold<0:raise base.TrainingError('Invalid threshold.')
    predicted=s>=threshold
    tn=int(np.sum((y==0)&~predicted));fp=int(np.sum((y==0)&predicted))
    fn=int(np.sum((y==1)&~predicted));tp=int(np.sum((y==1)&predicted))
    return {'rows':len(y),'negatives':tn+fp,'positives':tp+fn,
            'confusion_matrix':{'tn':tn,'fp':fp,'fn':fn,'tp':tp},
            'predicted_positives':tp+fp,'fpr':fp/(fp+tn),'recall':tp/(tp+fn),
            'precision':tp/(tp+fp) if tp+fp else None,'accuracy':(tn+tp)/len(y),
            'f1':2*tp/(2*tp+fp+fn)}


def joint_points(data,caps=CAPS):
    if set(data)!=set(SOURCES):raise base.TrainingError('Both validation sources are required.')
    data={k:validate_arrays(*v) for k,v in data.items()}
    all_scores=np.concatenate([s for y,s in data.values()])
    sentinel=float(np.nextafter(float(np.max(all_scores)),np.inf))
    candidates=np.unique(np.concatenate(([0.],all_scores,[sentinel])))
    fp_arrays={name:int(np.sum(y==0))-np.searchsorted(np.sort(s[y==0]),candidates,side='left') for name,(y,s) in data.items()}
    result=[]
    for cap in caps:
        budgets={name:allowed_fp(cap,int(np.sum(y==0))) for name,(y,s) in data.items()}
        feasible=np.ones(len(candidates),dtype=bool)
        for name in data:feasible &= fp_arrays[name]<=budgets[name]
        choices=np.flatnonzero(feasible)
        if not len(choices):raise base.TrainingError('Internal error: no reject-all candidate.')
        index=int(choices[0]);threshold=float(candidates[index])
        measured={name:point(y,s,threshold) for name,(y,s) in data.items()}
        no_alerts=all(m['predicted_positives']==0 for m in measured.values())
        result.append({'empirical_fpr_cap':cap,'allowed_false_positives':budgets,'threshold':threshold,
            'candidate_index':index,'threshold_above_score_range':threshold>1,
            'status':'NO_POSITIVE_PREDICTIONS_ON_OBSERVED_VALIDATION' if no_alerts else 'EMPIRICAL_CONSTRAINT_MET_ONLY',
            'sources':measured})
    return {'candidate_count':len(candidates),'joint_cap_points':result,
            'fixed_threshold_points':[{'threshold':t,'sources':{name:point(y,s,t) for name,(y,s) in data.items()}} for t in FIXED]}


def validate_protocol():
    p=base.load_json(PROTOCOL)
    if (p['version']!='url-threshold-study-protocol-v1' or p['scenarios']!=list(SCENARIOS)
        or p['source_names']!=list(SOURCES) or p['empirical_fpr_caps']!=list(CAPS)
        or p['fixed_thresholds']!=list(FIXED) or p['prediction_rule']!='score >= threshold'):
        raise base.TrainingError('Threshold study protocol changed.')
    return p


def load_packet(packet):
    m=base.load_json(packet/'manifest.json')
    if m['version']!=collector.VERSION:raise base.TrainingError('Unknown score packet.')
    for name in ['report.json','validation-scores.jsonl']:checked_file(packet,m,name)
    r=base.load_json(packet/'report.json')
    if (r['version']!=collector.VERSION or r['reproduced_g18'] is not True or r['score_type']!='MODEL_SCORE'
        or r['calibration_version'] is not None or r['scenarios']!=list(SCENARIOS) or set(r['sources'])!=set(SOURCES)):
        raise base.TrainingError('Score packet metadata mismatch.')
    labels={k:[] for k in SOURCES};scores={k:{s:[] for s in SCENARIOS} for k in SOURCES}
    seen=set();groups={k:set() for k in SOURCES}
    for row in rows(packet/'validation-scores.jsonl'):
        if set(row)!={'sample_id','group_id','source','y','scores'}:raise base.TrainingError('Unexpected score record fields.')
        name=row['source'];sid=row['sample_id'];gid=row['group_id']
        if (name not in SOURCES or not isinstance(sid,str) or not sid or sid in seen
            or not isinstance(gid,str) or not gid or type(row['y']) is not int or row['y'] not in (0,1)
            or set(row['scores'])!=set(SCENARIOS)):raise base.TrainingError('Duplicate, missing or invalid score metadata.')
        seen.add(sid);groups[name].add(gid);labels[name].append(row['y'])
        for scenario in SCENARIOS:
            value=row['scores'][scenario]
            if type(value) not in (int,float) or not math.isfinite(value) or not 0<=value<=1:raise base.TrainingError('Invalid MODEL_SCORE.')
            scores[name][scenario].append(value)
    if groups[SOURCES[0]] & groups[SOURCES[1]]:raise base.TrainingError('Cross-source domain overlap.')
    for name in SOURCES:
        expected=r['sources'][name]
        if (len(labels[name])!=expected['rows'] or len(groups[name])!=expected['groups']
            or dict(Counter(str(v) for v in labels[name]))!=expected['labels']):raise base.TrainingError('Score counts mismatch.')
        labels[name]=np.asarray(labels[name],dtype=int)
        for scenario in SCENARIOS:
            scores[name][scenario]=np.asarray(scores[name][scenario],dtype=float)
            validate_arrays(labels[name],scores[name][scenario])
            collector.ex.dg.reproduce(base.metrics(labels[name],scores[name][scenario]),r['reproduction_at_0_5'][scenario][name])
    return r,labels,scores


def analyze(packet,output):
    if output.exists():raise base.TrainingError('Output exists; choose new output.')
    protocol=validate_protocol();protocol_hash=base.sha(PROTOCOL);manifest_hash=base.sha(packet/'manifest.json')
    metadata,labels,scores=load_packet(packet)
    results={scenario:joint_points({name:(labels[name],scores[name][scenario]) for name in SOURCES}) for scenario in SCENARIOS}
    resolution={name:{'negative_rows':int(np.sum(labels[name]==0)),'positive_rows':int(np.sum(labels[name]==1)),
        'one_false_positive_fpr_step':1/int(np.sum(labels[name]==0)),
        'allowed_false_positives_by_cap':{cap:allowed_fp(cap,int(np.sum(labels[name]==0))) for cap in CAPS}} for name in SOURCES}
    if base.sha(packet/'manifest.json')!=manifest_hash or base.sha(PROTOCOL)!=protocol_hash:raise base.TrainingError('Input snapshot changed.')
    m=base.load_json(packet/'manifest.json')
    for name in ['report.json','validation-scores.jsonl']:checked_file(packet,m,name)
    report={'stage':'G1.9','version':VERSION,'status':'EXPLORATORY_THRESHOLDS_NOT_FOR_DEPLOYMENT',
        'protocol':protocol,'protocol_sha256':protocol_hash,'score_manifest_sha256':manifest_hash,
        'resolution':resolution,'results':results,'selection_and_measurement_use_same_validation':True,
        'model_selected':None,'deployment_threshold':None,'model_activated':False,
        'test_file_opened':False,'external_holdout_file_opened':False,'runtime':base.environment(),
        'limitations':['Empirical caps are not population guarantees. Thresholds were selected on the same observed validation.',
                       'Only 472 external negative rows in the reference run; group dependence and prior adaptation remain.',
                       'Historical labels are not independent verification. MODEL_SCORE is not calibrated probability.',
                       'No minimum-recall acceptance target, unbiased confidence interval or production claim.']}
    with output_dir(output) as stage:
        base.write_json(stage/'report.json',report);base.write_json(stage/'protocol.json',protocol)
        save_manifest(stage,{'version':VERSION,'score_manifest_sha256':manifest_hash,'protocol_sha256':protocol_hash,
            'code_sha256':base.sha(Path(__file__))})
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scores',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        r=analyze(a.scores,a.output)
        print(json.dumps({'status':r['status'],'report_file':str(a.output/'report.json'),
                          'deployment_threshold':None,'model_activated':False,'results':r['results']},indent=2))
    except (OSError,ValueError,KeyError,TypeError) as e:
        print('ERROR: '+(str(e) if isinstance(e,base.TrainingError) else type(e).__name__+': check score packet/protocol.'),file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
