"""G1.3 diagnostics only: no final test, threshold tuning, model activation or pickle load."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import warnings
import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import average_precision_score
from threadpoolctl import threadpool_limits
import train_url_baselines as base

VERSION = 'url-diagnostics-v1'
REPEATS = 3
LENGTHS = ('url_length', 'hostname_length', 'path_length', 'query_length', 'fragment_length')
SCENARIOS = {'full': (), 'without_https': ('is_https',), 'without_lengths': LENGTHS,
             'without_https_and_lengths': ('is_https', *LENGTHS)}


def columns_without(excluded):
    return [index for index, name in enumerate(base.FEATURE_NAMES) if name not in excluded]


def permutations(model, x, y, groups, repeats=REPEATS):
    """AP drop; joint shuffle within a feature group. Never mutate original X."""
    initial = float(average_precision_score(y, model.predict_proba(x)[:, 1]))
    result = []
    for name, cols in groups.items():
        rng = np.random.default_rng(base.SEED)
        drops = []
        for _ in range(repeats):
            shuffled = x.copy()
            order = rng.permutation(len(x))
            shuffled[:, cols] = x[order][:, cols]
            score = average_precision_score(y, model.predict_proba(shuffled)[:, 1])
            drops.append(float(initial-score))
        result.append({'group': name, 'features': [base.FEATURE_NAMES[i] for i in cols],
                       'ap_drop_mean': float(np.mean(drops)), 'shuffle_std': float(np.std(drops)),
                       'ap_drops': drops})
    return sorted(result, key=lambda item: (-item['ap_drop_mean'], item['group']))


def validation_metadata(directory):
    # Read identifiers only for local review; never export input_url or normalized_url.
    with (directory/'validation.jsonl').open(encoding='utf-8') as stream:
        return [{key: row[key] for key in ('sample_id', 'group_id', 'source_record')}
                for row in map(json.loads, stream)]


def error_summary(x, y, scores, metadata, length_edges):
    predicted = (scores >= base.THRESHOLD).astype(int)
    slices = {}
    definitions = {}
    for feature in ('is_https', 'is_ip'):
        column = base.FEATURE_NAMES.index(feature)
        for value in (0, 1): definitions[f'{feature}={value}'] = x[:, column] == value
    bins = np.searchsorted(length_edges, x[:, base.FEATURE_NAMES.index('url_length')], side='right')
    for value in range(4): definitions[f'url_length_bin={value}'] = bins == value
    for name, mask in definitions.items():
        negatives = int(np.sum(mask & (y == 0))); positives = int(np.sum(mask & (y == 1)))
        fp = int(np.sum(mask & (y == 0) & (predicted == 1)))
        fn = int(np.sum(mask & (y == 1) & (predicted == 0)))
        slices[name] = {'rows': int(mask.sum()), 'groups': len({metadata[i]['group_id'] for i in np.flatnonzero(mask)}),
                        'negatives': negatives, 'positives': positives, 'fp': fp, 'fn': fn,
                        'fpr': fp/negatives if negatives else None,
                        'recall': 1-fn/positives if positives else None}
    review = []
    for kind, indices in [('FP', np.flatnonzero((y == 0) & (predicted == 1))),
                          ('FN', np.flatnonzero((y == 1) & (predicted == 0)))]:
        ordered = sorted(indices, key=lambda i: ((-scores[i] if kind == 'FP' else scores[i]), metadata[i]['sample_id']))
        for i in ordered[:100]:
            review.append({**metadata[i], 'error_type': kind, 'source_y': int(y[i]),
                           'predicted_y': int(predicted[i]), 'score': float(scores[i]),
                           'score_type': 'MODEL_SCORE', 'review_status': 'UNREVIEWED'})
    return slices, review


def check_baseline(run, dataset_hash):
    manifest = base.load_json(run/'manifest.json')
    if manifest['version'] != base.VERSION or manifest['dataset_manifest_sha256'] != dataset_hash:
        raise base.TrainingError('Baseline run belongs to another dataset/version.')
    if manifest['runtime'] != base.environment():
        raise base.TrainingError('Use the same training environment as the baseline run.')
    for name, path in [('train_url_baselines.py', Path(base.__file__)),
                       ('url_features.py', base.ROOT/'packages/python-core/src/phishing_core/url_features.py'),
                       ('url_analysis.py', base.ROOT/'services/ai/url_analysis.py')]:
        if base.sha(path) != manifest['code_sha256'][name]:
            raise base.TrainingError('Baseline code/feature schema has changed.')
    if base.sha(run/'report.json') != manifest['files']['report.json']:
        raise base.TrainingError('Baseline report checksum mismatch.')
    report = base.load_json(run/'report.json')
    if report['dataset_manifest_sha256'] != dataset_hash or report['feature_schema'] != base.schema():
        raise base.TrainingError('Baseline report/schema mismatch.')
    return report


def reproduce_or_fail(actual, expected):
    if actual['confusion_matrix'] != expected['confusion_matrix'] or not np.isclose(actual['average_precision'], expected['average_precision'], atol=1e-8, rtol=0):
        raise base.TrainingError('Refitted full model does not reproduce the baseline; inspect environment before diagnostics.')


def diagnose(dataset, baseline_run, output, workers=2):
    if not 1 <= workers <= 4 or output.exists():
        raise base.TrainingError('Use workers 1–4 and a new output directory.')
    dataset_hash = base.sha(dataset/'manifest.json')
    manifest = base.validate_manifest(dataset)
    baseline_hash = base.sha(baseline_run/'manifest.json')
    original = check_baseline(baseline_run, dataset_hash)
    source_report = base.load_json(dataset/'report.json')
    xt, yt, tid, tg = base.load_split(dataset, 'train', source_report['splits']['train'])
    xv, yv, vid, vg = base.load_split(dataset, 'validation', source_report['splits']['validation'])
    if tid & vid or tg & vg:
        raise base.TrainingError('Train/validation leakage.')
    metadata = validation_metadata(dataset)
    if len(metadata) != len(yv):
        raise base.TrainingError('Validation metadata mismatch.')
    # Derived only from training, before seeing validation outcomes.
    edges = np.quantile(xt[:, base.FEATURE_NAMES.index('url_length')], [.25, .5, .75])
    groups = {name: [i] for i, name in enumerate(base.FEATURE_NAMES)}
    groups['length_family'] = [base.FEATURE_NAMES.index(name) for name in LENGTHS]
    groups['https_and_lengths'] = [base.FEATURE_NAMES.index('is_https'), *groups['length_family']]
    results, review = {}, []
    for scenario, removed in SCENARIOS.items():
        cols = columns_without(removed)
        results[scenario] = {'removed_features': list(removed), 'models': {}}
        for name, estimator in base.estimators(workers).items():
            print(f'Diagnostic fit: {scenario} / {name}', file=sys.stderr, flush=True)
            with threadpool_limits(limits=workers), warnings.catch_warnings():
                warnings.simplefilter('error', ConvergenceWarning)
                estimator.fit(xt[:, cols], yt)
                scores = estimator.predict_proba(xv[:, cols])[:, 1]
                entry = {'validation': base.metrics(yv, scores)}
                if scenario == 'full':
                    reproduce_or_fail(entry['validation'], original['results'][name]['validation'])
                    entry['reproduces_baseline'] = True
                    entry['permutation_importance'] = permutations(estimator, xv, yv, groups)
                    entry['error_slices'], cases = error_summary(xv, yv, scores, metadata, edges)
                    review.extend({'model': name, **case} for case in cases)
                else:
                    entry['ap_change_vs_full'] = entry['validation']['average_precision'] - results['full']['models'][name]['validation']['average_precision']
                results[scenario]['models'][name] = entry
    report = {'stage': 'G1.3', 'version': VERSION, 'status': 'DIAGNOSTICS_ONLY',
              'dataset_manifest_sha256': dataset_hash, 'baseline_manifest_sha256': baseline_hash,
              'train_rows': len(yt), 'validation_rows': len(yv), 'final_test_opened': False,
              'seed': base.SEED, 'workers': workers, 'threshold': base.THRESHOLD,
              'permutation_repeats': REPEATS, 'feature_schema': base.schema(),
              'length_bin_edges_from_train': edges.tolist(), 'results': results,
              'review_rows_exported': len(review), 'review_cap_per_model_error_type': 100,
              'runtime': base.environment(),
              'limitations': ['Validation reused for exploratory diagnosis; no final-test result.',
                             'Permutation AP drop is model reliance, not causality; shuffle std is not a confidence interval.',
                             'Correlated count features may preserve length information after length ablation.',
                             'Error labels are source annotations, not independent truth; no automatic relabeling.',
                             'No production threshold selection, model replacement, calibration, SHAP or activation.']}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.diagnostics-staging-', dir=output.parent))
    try:
        base.write_json(stage/'report.json', report)
        with (stage/'error-review.jsonl').open('w', encoding='utf-8', newline='\n') as stream:
            for row in review: stream.write(json.dumps(row, sort_keys=True, allow_nan=False)+'\n')
        base.write_json(stage/'manifest.json', {'version': VERSION, 'dataset_manifest_sha256': dataset_hash,
                        'baseline_manifest_sha256': baseline_hash,
                        'code_sha256': {'diagnose_url_baselines.py': base.sha(Path(__file__))},
                        'runtime': base.environment(), 'files': {p.name: base.sha(p) for p in sorted(stage.iterdir())}})
        if base.sha(dataset/'manifest.json') != dataset_hash or base.sha(baseline_run/'manifest.json') != baseline_hash:
            raise base.TrainingError('Input manifest changed during diagnostics.')
        base.validate_manifest(dataset)
        check_baseline(baseline_run, dataset_hash)
        if output.exists(): raise base.TrainingError('Output appeared during diagnostics.')
        stage.rename(output)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--baseline-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    try:
        result = diagnose(args.dataset, args.baseline_run, args.output, args.workers)
        print(json.dumps({'status': result['status'], 'final_test_opened': False,
                          'report_file': 'report.json', 'review_rows_exported': result['review_rows_exported']}, indent=2))
    except (OSError, ValueError, KeyError, ConvergenceWarning) as error:
        text = str(error) if isinstance(error, base.TrainingError) else type(error).__name__ + ': check environment and input metadata.'
        print('ERROR: '+text, file=sys.stderr); return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
