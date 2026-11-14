"""Lexical features only; no DNS, webpage, label or source-derived statistics."""
from collections.abc import Callable
import math
import re
from urllib.parse import urlsplit

SCHEMA_VERSION = 'url-lexical-v1'
PREPROCESSING_VERSION = 'url-inspection-v1'
FEATURE_NAMES = (
    'url_length', 'hostname_length', 'subdomain_count', 'digit_count',
    'is_ip', 'is_https', 'path_length', 'query_length', 'fragment_length',
    'hyphen_count', 'dot_count', 'slash_count', 'equals_count', 'ampersand_count',
    'percent_escape_count', 'has_query', 'has_fragment', 'has_explicit_port',
)


def schema() -> dict:
    return {'version': SCHEMA_VERSION, 'preprocessing_version': PREPROCESSING_VERSION,
            'dtype': 'float64', 'feature_names': list(FEATURE_NAMES),
            'missing_policy': 'Reject invalid URL; no imputation.',
            'length_unit': 'Python Unicode code points; encoded percent sequences are not decoded.',
            'input': 'Original input_url, not normalized_url; outer ASCII spaces removed by the inspector.'}


def extract_features(raw: str, inspector: Callable[[str], dict]) -> list[float]:
    """Use the SAME inspector as inference; callback avoids duplicating the frozen parser.

    Caller supplies services.ai.url_analysis.inspect_url. Invalid inputs propagate its
    validation error. Neither IDs, labels, domain strings nor source metadata enter X.
    """
    inspected = inspector(raw)
    if inspected['preprocessing_version'] != PREPROCESSING_VERSION:
        raise ValueError('Unsupported URL preprocessing version.')
    value = raw.strip(' ')
    parts = urlsplit(value)
    features, url = inspected['features'], inspected['url']
    row = [features['url_length'], features['hostname_length'], features['subdomain_count'],
           features['digit_count'], url['is_ip'], url['scheme'] == 'https',
           len(parts.path), len(parts.query), len(parts.fragment),
           value.count('-'), value.count('.'), value.count('/'), value.count('='), value.count('&'),
           len(re.findall(r'%[0-9a-fA-F]{2}', value)), features['has_query'], features['has_fragment'],
           url['port'] is not None]
    result = [float(item) for item in row]
    if len(result) != len(FEATURE_NAMES) or not all(math.isfinite(item) and item >= 0 for item in result):
        raise ValueError('Invalid feature vector.')
    return result
