"""G1.11: one fixed CPU LightGBM configuration against reproduced weighted RF."""
import argparse
import csv
import json
from pathlib import Path
import sys
import time
import numpy as np
import lightgbm as lgb
from threadpoolctl import threadpool_limits
import collect_url_validation_scores as collector
import analyze_url_thresholds as thresholds
from common import base, rows, output_dir, save_manifest
ex = collector.ex
VERSION = 'url-lightgbm-comparison-v1'
PROTOCOL = base.ROOT / 'docs/g1-11/protocol.json'
SCENARIO = 'baseline_plus_path_query'
LGB_VERSION = '4.6.0'
ROUNDS = 300
PARAMS = {
    'objective': 'binary', 'metric': 'None', 'boosting_type': 'gbdt',
    'learning_rate': .05, 'num_leaves': 31, 'max_depth': -1,
    'min_data_in_leaf': 20, 'min_sum_hessian_in_leaf': .001,
    'lambda_l1': 0., 'lambda_l2': 1., 'min_gain_to_split': 0.,
    'max_bin': 255, 'feature_fraction': 1., 'bagging_fraction': 1., 'bagging_freq': 0,
    'is_unbalance': False, 'scale_pos_weight': 1.,
    'device_type': 'cpu', 'deterministic': True, 'force_col_wise': True,
    'seed': 42, 'data_random_seed': 42, 'feature_fraction_seed': 42, 'bagging_seed': 42,
    'verbosity': -1,
}


def validate_protocol():
    p = base.load_json(PROTOCOL)
    if (p['version'] != VERSION or p['scenario'] != SCENARIO or p['params'] != PARAMS
        or p['num_boost_round'] != ROUNDS or p['lightgbm_version'] != LGB_VERSION
        or p['primary_empirical_fpr_cap'] != '0.01'
        or p['secondary_empirical_fpr_cap'] != '0.05'
        or p['early_stopping'] is not False or p['hyperparameter_search'] is not False):
        raise base.TrainingError('G1.11 protocol differs from fixed implementation.')
    thresholds.validate_protocol()
    if lgb.__version__ != LGB_VERSION: raise base.TrainingError('Install pinned LightGBM version.')
    return p


def fit_lightgbm(x, y, weights, evaluations, workers):
    if (x.ndim != 2 or x.shape[1] != 23 or len(x) != len(y) or len(y) != len(weights)
        or set(y.tolist()) != {0, 1} or not np.isfinite(x).all()
        or not np.isfinite(weights).all() or np.any(weights <= 0)):
        raise base.TrainingError('Invalid training features, labels or weights.')
    names = ex.features.schema(SCENARIO)['feature_names']
    # Only TRAIN is passed to Dataset/train. No eval_set, validation callbacks or early stopping.
    with threadpool_limits(limits=workers):
        dataset = lgb.Dataset(x, label=y, weight=weights, feature_name=names, free_raw_data=True)
        started = time.perf_counter()
        model = lgb.train({**PARAMS, 'num_threads': workers}, dataset, num_boost_round=ROUNDS)
        fit_seconds = time.perf_counter() - started
        if model.num_feature() != 23: raise base.TrainingError('Unexpected LightGBM feature count.')
        scores = {}; times = {}
        for name, (features, labels) in evaluations.items():
            started = time.perf_counter()
            values = np.asarray(model.predict(features, num_threads=workers), dtype=float)
            times[name] = time.perf_counter() - started
            thresholds.validate_arrays(labels, values)
            if len(values) != len(features): raise base.TrainingError('Prediction alignment mismatch.')
            scores[name] = values
    return scores, {'fit_seconds': fit_seconds, 'batch_predict_seconds': times,
                    'actual_boosting_iterations': model.current_iteration()}


def compare_at_cap(labels, rf_scores, lgb_scores, rf_points, lgb_points, cap):
    def at(points): return next(p for p in points['joint_cap_points'] if p['empirical_fpr_cap'] == cap)
    r = at(rf_points); n = at(lgb_points)
    sources = {}
    for source, y in labels.items():
        b = rf_scores[source] >= r['threshold']; a = lgb_scores[source] >= n['threshold']
        sources[source] = {
            'recall_delta': n['sources'][source]['recall'] - r['sources'][source]['recall'],
            'fpr_delta': n['sources'][source]['fpr'] - r['sources'][source]['fpr'],
            'corrected_fp': int(np.sum((y == 0) & b & ~a)),
            'introduced_fp': int(np.sum((y == 0) & ~b & a)),
            'corrected_fn': int(np.sum((y == 1) & ~b & a)),
            'introduced_fn': int(np.sum((y == 1) & b & ~a)),
        }
    return {'cap': cap, 'rf_threshold': r['threshold'], 'lightgbm_threshold': n['threshold'],
            'sources': sources,
            'minimum_source_recall_delta': min(m['recall'] for m in n['sources'].values()) - min(m['recall'] for m in r['sources'].values()),
            'independent_test_evidence': False}


def experiment(dataset, external, baseline, primary, g16, g18, output, workers=2):
    if output.exists() or not 1 <= workers <= 4:
        raise base.TrainingError('Use a new output directory and workers 1-4.')
    protocol = validate_protocol()
    expected = collector.verify_g18(g18, dataset, external, baseline, g16, primary)
    original = ex.dg.verify_run(g16, dataset, external, baseline)
    watched = [p / 'manifest.json' for p in [dataset, external, baseline, g16, g18]] + [PROTOCOL, thresholds.PROTOCOL]
    before = {str(p): base.sha(p) for p in watched}
    base.validate_manifest(dataset)
    em, _, er, _, _ = ex.dg.ms.ev.validate_inputs(external, baseline, primary, 'mendeley-v3')
    if em['base_dataset_manifest_sha256'] != base.sha(dataset / 'manifest.json'):
        raise base.TrainingError('Base dataset differs.')
    dr = base.load_json(dataset / 'report.json')
    xt, yt, ti, tg = ex.load_base(dataset, 'train', dr['splits']['train'])
    xv, yv, vi, vg = ex.load_base(dataset, 'validation', dr['splits']['validation'])
    ex.dg.ms.assert_disjoint(ti, tg, vi, vg)
    xe, ye, meta, records = ex.load_external(external, er, em['source'])
    with primary.open(encoding='utf-8-sig', newline='') as f:
        ex.dg.ms.verify_primary_rows(records, list(csv.DictReader(f)))
    ex.dg.ms.assert_disjoint(ti | vi, tg | vg, {r['sample_id'] for r in meta}, {r['group_id'] for r in meta})
    mask = ex.dg.ms.partition(meta, ye)
    if list(rows(g16 / 'external-assignments.jsonl')) != ex.dg.assignments(meta, mask):
        raise base.TrainingError('Frozen external assignments differ.')
    x = np.concatenate((xt[SCENARIO], xe[SCENARIO][mask]))
    y = np.concatenate((yt, ye[mask]))
    source = np.concatenate((np.zeros(len(yt), dtype=int), np.ones(int(mask.sum()), dtype=int)))
    weights = ex.dg.ms.weights_for(y, source)
    evaluations = {'phiusiil_validation': (xv[SCENARIO], yv),
                   'external_reused_validation': (xe[SCENARIO][~mask], ye[~mask])}
    labels = {name: pair[1] for name, pair in evaluations.items()}
    # Keep only matrices used in this comparison; frozen feature loader remains unchanged.
    del xt, xv, xe, records
    print('Reproducing frozen G1.8 path/query Random Forest', file=sys.stderr, flush=True)
    started = time.perf_counter()
    rf_scores, mtry = ex.fit_scenario(x, y, weights, evaluations, workers)
    rf_seconds = time.perf_counter() - started
    stored = expected['results'][SCENARIO]
    if stored['feature_count'] != x.shape[1] or stored['max_features_per_split'] != mtry:
        raise base.TrainingError('RF configuration mismatch.')
    for name in evaluations:
        ex.dg.reproduce(base.metrics(labels[name], rf_scores[name]), stored['sources'][name]['metrics'])
    print('Fitting fixed LightGBM on TRAIN only; no validation fitting or early stopping', file=sys.stderr, flush=True)
    started = time.perf_counter()
    lgb_scores, lgb_timing = fit_lightgbm(x, y, weights, evaluations, workers)
    lgb_total_seconds = time.perf_counter() - started
    scores = {'random_forest': rf_scores, 'lightgbm': lgb_scores}
    results = {}
    for model, predictions in scores.items():
        results[model] = {
            'at_0_5': {name: base.metrics(labels[name], predictions[name]) for name in evaluations},
            'threshold_study': thresholds.joint_points({name: (labels[name], predictions[name]) for name in evaluations}),
            'slices_at_0_5': {name: {key: ex.dg.ms.ev.slice_metrics(labels[name], predictions[name], selection)
                for key, selection in ex.dg.masks_for(features[:, :18]).items()}
                for name, (features, _) in evaluations.items()},
        }
    comparison = {cap: compare_at_cap(labels, rf_scores, lgb_scores,
                    results['random_forest']['threshold_study'], results['lightgbm']['threshold_study'], cap)
                  for cap in ('0.01', '0.05')}
    if any(base.sha(Path(p)) != h for p, h in before.items()):
        raise base.TrainingError('Input snapshot changed during run.')
    validate_protocol(); base.validate_manifest(dataset)
    collector.verify_g18(g18, dataset, external, baseline, g16, primary)
    ex.dg.verify_run(g16, dataset, external, baseline)
    ex.dg.ms.ev.validate_inputs(external, baseline, primary, 'mendeley-v3')
    report = {'stage': 'G1.11', 'version': VERSION, 'status': 'EXPLORATORY_MODEL_COMPARISON_ONLY',
              'protocol': protocol, 'protocol_sha256': base.sha(PROTOCOL),
              'threshold_protocol_sha256': base.sha(thresholds.PROTOCOL),
              'runtime': {**base.environment(), 'lightgbm_version': lgb.__version__,
                          'lightgbm_native_library_sha256': base.sha(Path(lgb.basic._LIB._name))},
              'workers': workers, 'feature_schema': ex.features.schema(SCENARIO),
              'splits': original['splits'], 'train_rows': len(y),
              'train_weight_totals': {f'{s}:{label}': float(weights[(source == s) & (y == label)].sum())
                                      for s in (0, 1) for label in (0, 1)},
              'random_forest_params': {**base.PARAMS[ex.dg.MODEL], 'class_weight': None},
              'lightgbm_params': {**PARAMS, 'num_threads': workers},
              'rf_reproduced_g18': True, 'results': results, 'comparison': comparison,
              'timing': {'random_forest_fit_and_batch_predict_seconds': rf_seconds,
                         'lightgbm_fit_and_batch_predict_seconds': lgb_total_seconds,
                         'lightgbm_details': lgb_timing, 'api_latency_measured': False},
              'score_type': 'MODEL_SCORE', 'calibration_version': None,
              'test_file_opened': False, 'external_holdout_file_opened': False,
              'frozen_labels_changed': False, 'model_exported': False, 'model_activated': False,
              'automatic_winner_selected': False, 'deployment_threshold': None,
              'limitations': ['Feature choice and hypotheses were informed by previously observed validation.',
                 'Thresholds are selected and measured on the same validation; empirical caps are not population guarantees.',
                 'Historical labels, one seed, no confidence interval or causal algorithm-superiority claim.',
                 'This is one fixed configuration per model, not an exhaustive comparison or deployment acceptance.',
                 'CPU deterministic mode does not guarantee identical scores across OS/compiler versions.',
                 'No external API inference, Big Data training claim or calibrated confidence.']}
    code_paths = [Path(__file__), Path(collector.__file__), Path(thresholds.__file__),
                  Path(ex.__file__), Path(ex.features.__file__)]
    with output_dir(output) as stage:
        base.write_json(stage / 'report.json', report)
        base.write_json(stage / 'protocol.json', protocol)
        save_manifest(stage, {'version': VERSION, 'inputs': {k: base.sha(p / 'manifest.json')
            for k, p in [('dataset', dataset), ('external', external), ('baseline', baseline), ('g16', g16), ('g18', g18)]},
            'primary_sha256': base.sha(primary), 'protocol_sha256': base.sha(PROTOCOL),
            'threshold_protocol_sha256': base.sha(thresholds.PROTOCOL),
            'code_sha256': {p.name: base.sha(p) for p in code_paths}})
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['dataset', 'external', 'baseline-run', 'primary-file', 'experiment-run', 'feature-run', 'output']:
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--primary-origin', choices=['mendeley-v3'], required=True)
    p.add_argument('--workers', type=int, default=2)
    a = p.parse_args()
    try:
        r = experiment(a.dataset, a.external, a.baseline_run, a.primary_file, a.experiment_run, a.feature_run, a.output, a.workers)
        print(json.dumps({'status': r['status'], 'rf_reproduced_g18': True,
                          'report_file': str(a.output / 'report.json'), 'comparison': r['comparison']}, indent=2))
    except (OSError, ValueError, KeyError, TypeError, lgb.basic.LightGBMError) as e:
        print('ERROR: ' + (str(e) if isinstance(e, base.TrainingError) else type(e).__name__ + ': check inputs/runtime.'), file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
