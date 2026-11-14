"""G1.2: fit on train, compare on validation, never open test.jsonl."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time
import warnings

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services/ai'))
sys.path.insert(0, str(ROOT / 'packages/python-core/src'))
from url_analysis import inspect_url
from phishing_core.url_features import extract_features, schema, FEATURE_NAMES
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

VERSION = 'url-baselines-v1'
SEED = 42
THRESHOLD = 0.5
SELECTION_RULE = 'Highest validation average_precision; ties: lower FPR at 0.5, then Logistic Regression.'
PARAMS = {
    'logistic_regression': {'C': 1.0, 'solver': 'lbfgs', 'max_iter': 2000, 'class_weight': 'balanced', 'random_state': SEED},
    'random_forest': {'n_estimators': 100, 'max_depth': 16, 'min_samples_leaf': 2,
                      'max_features': 'sqrt', 'class_weight': 'balanced', 'random_state': SEED},
}

class TrainingError(ValueError):
    """Safe metadata-only error."""


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, data):
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')


def environment():
    return {'python_version': platform.python_version(),
            'packages': {name: version(name) for name in ('scikit-learn', 'numpy', 'scipy', 'joblib', 'threadpoolctl', 'idna', 'tldextract')}}


def validate_manifest(directory: Path) -> dict:
    manifest = load_json(directory/'manifest.json')
    if manifest.get('status') != 'FROZEN' or manifest.get('pipeline_version') != 'url-dataset-v1':
        raise TrainingError('Expected a frozen G1.1 URL dataset.')
    current = inspect_url('https://example.com/')
    resources = {'preprocessing_version': current['preprocessing_version'], **current['resources']}
    if manifest['runtime'] != resources:
        raise TrainingError('Use the same Python/Unicode/IDNA/PSL environment as the G1.1 dataset.')
    for name, path in [('prepare_urls.py', ROOT/'scripts/g1/prepare_urls.py'), ('url_analysis.py', ROOT/'services/ai/url_analysis.py')]:
        if manifest['code_sha256'][name] != sha(path):
            raise TrainingError('G1.1 pipeline code differs from frozen manifest.')
    if manifest['source'] != load_json(ROOT/'scripts/g1/source-lock.json'):
        raise TrainingError('Dataset source differs from the approved G1.1 source lock.')
    # Do not open, hash, parse or score the final test file. Its stored hash is metadata only.
    for name in ('train.jsonl', 'validation.jsonl', 'report.json'):
        if sha(directory/name) != manifest['files'][name]:
            raise TrainingError('Train/validation/report checksum mismatch.')
    return manifest


def load_split(directory: Path, split: str, expected: dict):
    if split not in ('train', 'validation'):
        raise TrainingError('G1.2 may only read train and validation.')
    vectors, labels, sample_ids, groups = [], [], set(), set()
    with (directory/f'{split}.jsonl').open(encoding='utf-8') as stream:
        for number, line in enumerate(stream, 1):
            row = json.loads(line)
            if row['source_label'] not in ('0', '1') or row['y'] != 1-int(row['source_label']):
                raise TrainingError('Dataset label mapping mismatch.')
            if row['sample_id'] in sample_ids:
                raise TrainingError('Repeated sample in a split.')
            vectors.append(extract_features(row['input_url'], inspect_url))
            labels.append(row['y']); sample_ids.add(row['sample_id']); groups.add(row['group_id'])
            if number % 25000 == 0:
                print(f'{split}: extracted {number} rows', file=sys.stderr, flush=True)
    counts = {str(label): count for label, count in sorted(Counter(labels).items())}
    if len(vectors) != expected['rows'] or len(groups) != expected['groups'] or counts != expected['labels'] or set(labels) != {0, 1}:
        raise TrainingError('Split size/classes differ from G1.1 report.')
    return np.asarray(vectors, dtype=np.float64), np.asarray(labels, dtype=np.int64), sample_ids, groups


def metrics(y, scores):
    if len(y) != len(scores) or set(y) != {0, 1} or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
        raise TrainingError('Invalid evaluation labels or scores.')
    prediction = (scores >= THRESHOLD).astype(np.int64)
    tn, fp, fn, tp = (int(value) for value in confusion_matrix(y, prediction, labels=[0, 1]).ravel())
    return {'threshold': THRESHOLD, 'accuracy': float(accuracy_score(y, prediction)),
            'precision': float(precision_score(y, prediction, zero_division=0)),
            'recall': float(recall_score(y, prediction)), 'f1': float(f1_score(y, prediction)),
            'fpr': fp/(fp+tn), 'average_precision': float(average_precision_score(y, scores)),
            'roc_auc': float(roc_auc_score(y, scores)),
            'confusion_matrix': {'tn': tn, 'fp': fp, 'fn': fn, 'tp': tp}}


def estimators(workers):
    return {
        'logistic_regression': Pipeline([('scale', StandardScaler()), ('classifier', LogisticRegression(**PARAMS['logistic_regression']))]),
        'random_forest': RandomForestClassifier(**PARAMS['random_forest'], n_jobs=workers),
    }


def fit_and_compare(x_train, y_train, x_val, y_val, output, workers):
    results = {}
    for name, model in estimators(workers).items():
        print(f'Fitting {name} on TRAIN only', file=sys.stderr, flush=True)
        started = time.perf_counter()
        with threadpool_limits(limits=workers), warnings.catch_warnings():
            warnings.simplefilter('error', ConvergenceWarning)
            model.fit(x_train, y_train)
            fit_seconds = time.perf_counter()-started
            if list(model.classes_) != [0, 1]:
                raise TrainingError('Unexpected model class order.')
            started = time.perf_counter()
            scores = model.predict_proba(x_val)[:, 1]
            predict_seconds = time.perf_counter()-started
        results[name] = {'validation': metrics(y_val, scores), 'fit_seconds': fit_seconds,
                         'validation_batch_predict_seconds': predict_seconds, 'params': model.get_params(deep=False) if name == 'random_forest' else PARAMS[name]}
        bundle = {'model': model, 'feature_schema': schema(), 'positive_label': 1,
                  'score_type': 'MODEL_SCORE', 'calibration_version': None, 'pipeline_version': VERSION}
        path = output/f'{name}.joblib'
        joblib.dump(bundle, path, compress=3)
        # Only deserialize the artifact just produced by this process, never an arbitrary downloaded model.
        restored = joblib.load(path)
        with threadpool_limits(limits=workers):
            roundtrip = restored['model'].predict_proba(x_val[:32])[:, 1]
        if not np.allclose(roundtrip, scores[:32], rtol=1e-12, atol=1e-12):
            raise TrainingError('Model serialization round-trip failed.')
        results[name]['artifact_sha256'] = sha(path)
    chosen = min(results, key=lambda name: (-results[name]['validation']['average_precision'],
                                           results[name]['validation']['fpr'], name != 'logistic_regression'))
    return results, chosen


def train(dataset: Path, output: Path, workers: int = 2):
    if not 1 <= workers <= 4:
        raise TrainingError('workers must be between 1 and 4.')
    if output.exists():
        raise TrainingError('Output exists; use a new run directory. No model is overwritten.')
    manifest_hash = sha(dataset/'manifest.json')
    manifest = validate_manifest(dataset)
    data_report = load_json(dataset/'report.json')
    print('Validating TRAIN and VALIDATION; final test is not opened.', file=sys.stderr, flush=True)
    xt, yt, train_ids, train_groups = load_split(dataset, 'train', data_report['splits']['train'])
    xv, yv, val_ids, val_groups = load_split(dataset, 'validation', data_report['splits']['validation'])
    if train_ids & val_ids or train_groups & val_groups:
        raise TrainingError('Train/validation sample or domain leakage.')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.baseline-staging-', dir=output.parent))
    try:
        results, chosen = fit_and_compare(xt, yt, xv, yv, staging, workers)
        report = {'stage': 'G1.2', 'pipeline_version': VERSION, 'status': 'CANDIDATE_ONLY',
                  'seed': SEED, 'workers': workers, 'feature_schema': schema(),
                  'dataset_manifest_sha256': manifest_hash,
                  'dataset_split_hashes': {name: manifest['files'][name] for name in ('train.jsonl', 'validation.jsonl')},
                  'train_rows': len(yt), 'validation_rows': len(yv), 'final_test_opened': False,
                  'selection_rule': SELECTION_RULE, 'candidate_for_further_evaluation': chosen,
                  'results': results, 'runtime': environment(),
                  'limitations': ['Validation metrics only; not an unbiased final test result.',
                                 'Default threshold 0.5 is a baseline comparison, not a production alert threshold.',
                                 'Scores are uncalibrated MODEL_SCORE, not calibrated confidence percentages.',
                                 'Source/coverage bias persists; no claim of real-world phishing recall.',
                                 'No model activation, API inference, calibration, SHAP or laptop latency SLA.']}
        write_json(staging/'report.json', report)
        write_json(staging/'feature-schema.json', schema())
        model_manifest = {'version': VERSION, 'status': 'CANDIDATE', 'preprocessing': manifest['runtime'],
                          'dataset_manifest_sha256': manifest_hash, 'runtime': environment(),
                          'code_sha256': {'train_url_baselines.py': sha(Path(__file__)),
                                          'url_features.py': sha(ROOT/'packages/python-core/src/phishing_core/url_features.py'),
                                          'url_analysis.py': sha(ROOT/'services/ai/url_analysis.py')},
                          'files': {p.name: sha(p) for p in sorted(staging.iterdir())}}
        write_json(staging/'manifest.json', model_manifest)
        # Detect dataset changes during extraction/fit without ever touching test.jsonl.
        if sha(dataset/'manifest.json') != manifest_hash:
            raise TrainingError('Dataset manifest changed during training.')
        validate_manifest(dataset)
        if output.exists():
            raise TrainingError('Output appeared during training.')
        staging.rename(output)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    try:
        result = train(args.dataset, args.output, args.workers)
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    except (TrainingError, OSError, ValueError, KeyError, ConvergenceWarning) as error:
        message = str(error) if isinstance(error, TrainingError) else type(error).__name__ + ': check environment and dataset metadata.'
        print('ERROR: ' + message, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
