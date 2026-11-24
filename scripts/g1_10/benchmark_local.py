"""Bounded-memory URL inspection/feature workload, not a training scalability claim."""
import argparse
import itertools
import json
from pathlib import Path
import subprocess
import sys
import time
from common import ROOT, VERSION, SYNTHETIC, Monitor, machine, sha, write_report, latency
sys.path.insert(0, str(ROOT / 'services/ai'))
sys.path.insert(0, str(ROOT / 'packages/python-core/src'))
from url_analysis import inspect_url, URLInputError
from phishing_core.url_feature_extensions import extract_all

MAX_LINE = 65536


def train_urls(path):
    path = Path(path)
    if path.name != 'train.jsonl': raise ValueError('Only a file named train.jsonl is accepted.')
    with path.open('r', encoding='utf-8') as f:
        while True:
            line = f.readline(MAX_LINE + 1)
            if not line: return
            if len(line) > MAX_LINE: raise ValueError('Input record exceeds limit.')
            row = json.loads(line)
            if not isinstance(row, dict): raise ValueError('Input record must be an object.')
            raw = row.get('input_url')
            if not isinstance(raw, str) or not 1 <= len(raw) <= 4096:
                raise ValueError('Invalid input_url field.')
            yield raw


def source(rows, train):
    if not train:
        yield from itertools.islice(itertools.cycle(SYNTHETIC), rows)
        return
    # No implicit replay of real samples. Too few rows is a configuration error.
    count = 0
    for raw in train_urls(train):
        yield raw
        count += 1
        if count == rows: return
    raise ValueError('Requested more rows than the TRAIN file contains.')


def run(rows, mode, train=None):
    if not 1 <= rows <= 10_000_000: raise ValueError('rows must be 1..10000000.')
    if mode not in ('inspection', 'features'): raise ValueError('Unknown mode.')
    if train and Path(train).name != 'train.jsonl': raise ValueError('Only train.jsonl is accepted.')
    digest = sha(train) if train else None
    operation = inspect_url if mode == 'inspection' else lambda raw: extract_all(raw, inspect_url)
    t = time.perf_counter(); operation(SYNTHETIC[0]); first = (time.perf_counter() - t) * 1000
    for raw in itertools.islice(itertools.cycle(SYNTHETIC), 100): operation(raw)
    valid = invalid = 0
    # Bounded latency sample: first 1000 real workload items, not claimed representative.
    durations = []
    with Monitor() as monitor:
        for raw in source(rows, train):
            started = time.perf_counter()
            try:
                operation(raw)
                valid += 1
                if len(durations) < 1000: durations.append((time.perf_counter() - started) * 1000)
            except URLInputError:
                invalid += 1
    if train and sha(train) != digest: raise ValueError('TRAIN file changed during benchmark.')
    return {'version': VERSION, 'scope': mode, 'rows': rows, 'valid': valid, 'invalid': invalid,
            'status': 'MEASURED' if not invalid else 'MEASURED_WITH_REJECTED_INPUTS',
            'source': 'train_prefix' if train else 'synthetic_cycle_8_not_accuracy_data',
            'train_sha256': digest, 'first_call_after_import_ms': first,
            'warmup_synthetic_calls': 100, 'timing': monitor.report(),
            'processed_rows_per_second': rows / monitor.elapsed,
            'successful_rows_per_second': valid / monitor.elapsed,
            'first_1000_successful_call_latency': latency(durations), 'machine': machine(),
            'code_sha256': sha(__file__), 'inspector_sha256': sha(ROOT / 'services/ai/url_analysis.py'),
            'extensions_sha256': sha(ROOT / 'packages/python-core/src/phishing_core/url_feature_extensions.py'),
            'test_or_holdout_opened': False, 'model_inference_measured': False,
            'training_measured': False, 'http_measured': False, 'database_measured': False,
            'limitations': ['This streams and discards features; frozen training loaders still accumulate arrays.',
                           'No proof of Big Data readiness or production capacity.',
                           'RSS covers this process only; imports precede measurement; latency is an ordered prefix.',
                           'Synthetic repetition has low diversity; training prefix is not an accuracy evaluation.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rows', nargs='+', type=int, default=[10000, 100000])
    p.add_argument('--mode', choices=['inspection', 'features'], default='features')
    p.add_argument('--train-jsonl', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    a = p.parse_args()
    try:
        if a.output.exists(): raise ValueError('Output already exists; use a new path.')
        if any(n < 1 or n > 10_000_000 for n in a.rows) or len(set(a.rows)) != len(a.rows):
            raise ValueError('Use unique row counts between 1 and 10000000.')
        if a.worker:
            if len(a.rows) != 1: raise ValueError('Worker takes one size.')
            write_report(a.output, run(a.rows[0], a.mode, a.train_jsonl))
            return 0
        a.output.mkdir(parents=True)
        results = []
        for n in a.rows:
            print(f'Measuring {a.mode}: {n} rows in a fresh process', flush=True)
            target = a.output / f'rows-{n}.json'
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', '--rows', str(n),
                       '--mode', a.mode, '--output', str(target.resolve())]
            if a.train_jsonl: command += ['--train-jsonl', str(a.train_jsonl.resolve())]
            subprocess.run(command, check=True)
            results.append(json.loads(target.read_text(encoding='utf-8')))
        write_report(a.output / 'report.json', {'stage': 'G1.10', 'version': VERSION,
                     'status': 'PERFORMANCE_MEASUREMENTS_ONLY', 'runs': results,
                     'production_ready': False, 'database_measured': False, 'model_inference_measured': False})
        print('Report: ' + str(a.output / 'report.json'))
    except (ValueError, OSError, subprocess.CalledProcessError):
        # Never print raw records or exception text which may include input URL.
        print('ERROR: benchmark failed; check paths, row count and environment. Partial per-size reports may remain.', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
