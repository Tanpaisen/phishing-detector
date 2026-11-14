"""Validate design documents and synthetic examples; does not test running APIs."""
import copy
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / 'packages/contracts'
report = {'kind': 'design-contract-validation', 'documents': {}, 'cases': []}
for name in ['public', 'internal']:
    doc = json.loads((CONTRACTS / f'{name}.openapi.json').read_text(encoding="utf-8"))
    validate(doc)
    ops = [op for item in doc['paths'].values() for method, op in item.items()
           if method in {'get', 'post', 'put', 'patch', 'delete'}]
    assert all(op.get('x-implementation-status') in {'planned', 'implemented'} for op in ops)
    assert len({op['operationId'] for op in ops}) == len(ops)
    report['documents'][name] = {'operations': len(ops), 'implemented_markers': sum(op['x-implementation-status'] == 'implemented' for op in ops)}
    if name == 'public':
        public = doc

cases = json.loads((CONTRACTS / 'examples.json').read_text(encoding="utf-8"))
for case in cases:
    schema = {'$ref': '#/components/schemas/' + case['schema'], 'components': public['components']}
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(case['value']))
    assert bool(errors) != case['valid'], f"Unexpected validation for {case['name']}: {[e.message for e in errors]}"
    report['cases'].append({'name': case['name'], 'passed': True})
report['cases_passed'] = len(cases)
print(json.dumps(report, ensure_ascii=False, indent=2))
