"""Offline, checksum-locked URL preparation. Never fetches URLs from the CSV."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'services' / 'ai'))
from url_analysis import inspect_url, URLInputError

VERSION = 'url-dataset-v1'
SEED = 42
RATIOS = {'train': .70, 'validation': .15, 'test': .15}
LOCK = Path(__file__).with_name('source-lock.json')

class DataError(ValueError):
    """Safe error message, without input URLs."""


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, value) -> None:
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')


def write_jsonl(path: Path, rows) -> None:
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')


def runtime() -> dict:
    inspected = inspect_url('https://example.com/')
    return {'preprocessing_version': inspected['preprocessing_version'], **inspected['resources']}


def grouping(inspected: dict) -> str:
    url = inspected['url']
    key = ('ip:' + url['hostname_ascii']) if url['is_ip'] else ('domain:' + (url['registered_domain'] or url['hostname_ascii']))
    return digest_text(key)


def split_groups(rows: list[dict]) -> dict[str, str]:
    """One deterministic greedy assignment. Never search seeds using model metrics."""
    groups = defaultdict(Counter)
    totals = Counter()
    for row in rows:
        groups[row['group_id']][row['y']] += 1
        totals[row['y']] += 1
    for label in (0, 1):
        if sum(counts[label] > 0 for counts in groups.values()) < 3:
            raise DataError('Each label needs at least three distinct domain/IP groups.')
    targets = {split: {y: totals[y] * ratio for y in (0, 1)} for split, ratio in RATIOS.items()}
    assigned_counts = {split: Counter() for split in RATIOS}
    assigned = {}
    ordered = sorted(groups, key=lambda group: (-sum(groups[group].values()), digest_text(f'{SEED}:{group}')))
    for group in ordered:
        counts = groups[group]
        def cost(split):
            return sum(((assigned_counts[split][y] + counts[y] - targets[split][y]) ** 2
                        - (assigned_counts[split][y] - targets[split][y]) ** 2)
                       / targets[split][y] for y in (0, 1))
        chosen = min(RATIOS, key=cost)
        assigned[group] = chosen
        assigned_counts[chosen].update(counts)
    if any(not counts[0] or not counts[1] for counts in assigned_counts.values()):
        raise DataError('Group split lacks a class; review grouping/data instead of silently changing the seed.')
    return assigned


def prepare(source: Path, output: Path, lock: dict) -> dict:
    if output.exists():
        raise DataError('Output already exists; use a new version directory. Frozen data is never overwritten.')
    if not source.is_file() or sha_file(source) != lock['csv_sha256']:
        raise DataError('Source missing or SHA-256 mismatch; no dataset was produced.')
    env = runtime()
    for key, expected in lock['preprocessing'].items():
        if env.get(key) != expected:
            raise DataError(f'Preprocessing mismatch: {key}. Use pinned dependencies or review a new dataset version.')
    accepted = defaultdict(list)
    quarantine = []
    source_labels = Counter()
    rejected = Counter()
    total = 0
    csv.field_size_limit(64 * 1024 * 1024)
    with source.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if not {'URL', 'label'}.issubset(fields) or len(fields) != len(set(fields)):
            raise DataError('CSV requires unique columns including URL and label.')
        for record_number, row in enumerate(reader, 1):
            total += 1
            original = row.get('label')
            valid_label = original if original in ('0', '1') else None
            source_labels[valid_label or 'INVALID'] += 1
            reason = None
            if None in row or any(value is None for value in row.values()):
                reason = 'MALFORMED_RECORD'
            elif valid_label is None:
                reason = 'INVALID_LABEL'
            else:
                try:
                    inspected = inspect_url(row['URL'])
                except URLInputError as error:
                    reason = error.code
            if reason:
                quarantine.append({'source_record': record_number, 'source_label': valid_label, 'reason': reason})
                rejected[f'{reason}:source_label={valid_label}'] += 1
                continue
            accepted[inspected['url']['normalized_url']].append({
                'input_url': row['URL'], 'source_record': record_number,
                'source_label': valid_label, 'y': 1 - int(valid_label),
                'group_id': grouping(inspected),
            })
    if not total:
        raise DataError('Empty CSV.')
    clean = []
    duplicates = []
    conflicting_groups = 0
    for normalized_url, members in sorted(accepted.items()):
        sample_id = digest_text(normalized_url)
        if len({member['y'] for member in members}) > 1:
            conflicting_groups += 1
            for member in members:
                quarantine.append({'source_record': member['source_record'], 'source_label': member['source_label'],
                                   'reason': 'CONFLICTING_LABELS', 'sample_id': sample_id})
                rejected[f"CONFLICTING_LABELS:source_label={member['source_label']}"] += 1
            continue
        # Keep original representation for training/inference feature parity, including Unicode input.
        ordered = sorted(members, key=lambda member: (member['input_url'], member['source_record']))
        kept = ordered[0]
        clean.append({**kept, 'sample_id': sample_id, 'normalized_url': normalized_url,
                      'source_id': lock['source_id'], 'label_schema_version': 'url-labels-v1'})
        for duplicate in ordered[1:]:
            duplicates.append({'source_record': duplicate['source_record'], 'source_label': duplicate['source_label'],
                               'sample_id': sample_id, 'kept_source_record': kept['source_record']})
    assignments = split_groups(clean)
    splits = {split: [] for split in RATIOS}
    for row in sorted(clean, key=lambda row: row['sample_id']):
        splits[assignments[row['group_id']]].append(row)
    if total != len(clean) + len(duplicates) + len(quarantine):
        raise DataError('Accounting mismatch.')
    split_stats = {split: {'rows': len(rows), 'groups': len({r['group_id'] for r in rows}),
                          'labels': dict(sorted(Counter(r['y'] for r in rows).items())),
                          'fraction': len(rows) / len(clean)} for split, rows in splits.items()}
    report = {'input_rows': total, 'source_label_counts': dict(source_labels), 'clean_rows': len(clean),
              'duplicate_rows_removed': len(duplicates), 'quarantined_rows': len(quarantine),
              'conflicting_canonical_urls': conflicting_groups, 'quarantine_reasons_by_source_label': dict(rejected),
              'unique_groups': len(assignments), 'splits': split_stats,
              'warnings': ['Metrics apply only to retained, in-scope URLs. Rejected input is not a safe prediction.',
                           'Source labels are dataset annotations, not independently verified threat evidence.',
                           'Domain-disjoint split does not guarantee campaign-disjoint or temporal evaluation.']}
    if any(abs(stats['fraction'] - RATIOS[split]) > .02 for split, stats in split_stats.items()):
        report['warnings'].append('A split differs from its target by over 2 percentage points; inspect large groups. Do not split domains to force ratios.')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.url-data-staging-', dir=output.parent))
    try:
        for split, rows in splits.items():
            write_jsonl(staging / f'{split}.jsonl', rows)
        write_jsonl(staging / 'quarantine.jsonl', sorted(quarantine, key=lambda row: row['source_record']))
        write_jsonl(staging / 'duplicates.jsonl', sorted(duplicates, key=lambda row: row['source_record']))
        write_json(staging / 'report.json', report)
        manifest = {'schema_version': '1.0', 'pipeline_version': VERSION, 'status': 'FROZEN',
                    'source': lock, 'runtime': env, 'seed': SEED, 'ratios': RATIOS,
                    'split_algorithm': 'largest-group-first-class-target-squared-error-v1',
                    'label_mapping': {'0': {'y': 1, 'name': 'PHISHING'}, '1': {'y': 0, 'name': 'LEGITIMATE'}},
                    'code_sha256': {'prepare_urls.py': sha_file(Path(__file__)),
                                    'url_analysis.py': sha_file(ROOT / 'services/ai/url_analysis.py')},
                    'files': {p.name: sha_file(p) for p in sorted(staging.iterdir())}}
        write_json(staging / 'manifest.json', manifest)
        verify(staging)
        # Parent must be a local private research directory, with no concurrent writer for this version.
        if output.exists():
            raise DataError('Output appeared during preparation; refusing to replace it.')
        staging.rename(output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return report


def verify(directory: Path) -> dict:
    manifest = load_json(directory / 'manifest.json')
    expected_files = {'train.jsonl', 'validation.jsonl', 'test.jsonl', 'quarantine.jsonl', 'duplicates.jsonl', 'report.json'}
    if set(manifest['files']) != expected_files:
        raise DataError('Unexpected manifest file list.')
    for name, expected_hash in manifest['files'].items():
        if sha_file(directory / name) != expected_hash:
            raise DataError(f'Checksum mismatch: {name}.')
    if manifest['pipeline_version'] != VERSION or manifest['runtime'] != runtime():
        raise DataError('Runtime/preprocessing differs from frozen manifest; verify using its recorded environment.')
    for name, path in [('prepare_urls.py', Path(__file__)), ('url_analysis.py', ROOT / 'services/ai/url_analysis.py')]:
        if sha_file(path) != manifest['code_sha256'][name]:
            raise DataError('Pipeline code differs from frozen manifest.')
    all_ids = set()
    group_owner = {}
    record_owner = set()
    kept = {}
    counts = {}
    for split in RATIOS:
        labels = Counter()
        groups = set()
        with (directory / f'{split}.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                inspected = inspect_url(row['input_url'])
                canonical = inspected['url']['normalized_url']
                if row['normalized_url'] != canonical or row['sample_id'] != digest_text(canonical) or row['group_id'] != grouping(inspected):
                    raise DataError('Canonical URL/sample/group mismatch.')
                if row['source_label'] not in ('0', '1') or row['y'] != 1 - int(row['source_label']):
                    raise DataError('Incorrect label mapping.')
                if row['source_id'] != manifest['source']['source_id'] or row['label_schema_version'] != 'url-labels-v1':
                    raise DataError('Incorrect source or label schema.')
                if row['sample_id'] in all_ids or row['source_record'] in record_owner:
                    raise DataError('Repeated sample/record across output.')
                owner = group_owner.setdefault(row['group_id'], split)
                if owner != split:
                    raise DataError('Domain/IP group leakage between splits.')
                all_ids.add(row['sample_id']); groups.add(row['group_id']); record_owner.add(row['source_record'])
                kept[row['sample_id']] = row['source_record']
                labels[row['y']] += 1
        if not labels[0] or not labels[1]:
            raise DataError('Missing class in a split.')
        counts[split] = {'rows': sum(labels.values()), 'groups': len(groups), 'labels': {str(k): v for k, v in sorted(labels.items())}}
    report = load_json(directory / 'report.json')
    for split, stats in counts.items():
        if any(report['splits'][split][key] != value for key, value in stats.items()):
            raise DataError('Split report mismatch.')
    for name, count_key in [('quarantine.jsonl', 'quarantined_rows'), ('duplicates.jsonl', 'duplicate_rows_removed')]:
        count = 0
        with (directory / name).open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line); count += 1
                if row['source_record'] in record_owner:
                    raise DataError('Source row counted more than once.')
                record_owner.add(row['source_record'])
                if name == 'duplicates.jsonl' and kept.get(row['sample_id']) != row['kept_source_record']:
                    raise DataError('Duplicate does not point to a retained sample.')
        if count != report[count_key]:
            raise DataError('Quarantine/duplicate accounting mismatch.')
    if record_owner != set(range(1, report['input_rows'] + 1)) or len(all_ids) != report['clean_rows'] or len(group_owner) != report['unique_groups']:
        raise DataError('Input/output accounting mismatch.')
    return {'verified': True, 'clean_rows': len(all_ids), 'groups': len(group_owner), 'splits': counts,
            'sample_overlap': 0, 'domain_group_overlap': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('prepare')
    build.add_argument('--input', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('verify')
    check.add_argument('--dataset', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.input, args.output, load_json(LOCK)) if args.command == 'prepare' else verify(args.dataset)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (DataError, OSError, csv.Error, UnicodeError, KeyError, json.JSONDecodeError) as error:
        # Do not echo exception text from a CSV/URL/OS parser: it can include input or local secrets.
        message = str(error) if isinstance(error, DataError) else type(error).__name__ + ': check input files and pinned environment.'
        print('ERROR: ' + message, file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
