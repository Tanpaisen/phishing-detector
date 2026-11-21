"""G1.8 additive lexical hypotheses; no labels, vocabulary fitting, network or URL rewriting."""
from collections.abc import Callable
import math
import re
from urllib.parse import urlsplit
from . import url_features as legacy

VERSION = 'url-structural-extensions-v1'
HOST_NAMES = ('has_www_subdomain', 'non_www_subdomain_depth', 'max_hostname_label_length',
              'hostname_digit_ratio', 'hostname_hyphen_ratio')
PATH_NAMES = ('path_segment_count', 'path_max_segment_length', 'query_field_count',
              'path_percent_encoded_ratio', 'query_percent_encoded_ratio')
SCENARIOS = ('baseline', 'baseline_plus_hostname', 'baseline_plus_path_query')


def schema(scenario):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown feature scenario.')
    extra = () if scenario == 'baseline' else HOST_NAMES if scenario == 'baseline_plus_hostname' else PATH_NAMES
    return {**legacy.schema(), 'version': legacy.SCHEMA_VERSION if not extra else VERSION + ':' + scenario,
            'base_version': legacy.SCHEMA_VERSION, 'feature_names': list(legacy.FEATURE_NAMES + extra),
            'extension_definitions': {
                'hostname': 'ASCII IDNA hostname from frozen inspector; IP hosts get five zeros. Dot-separated nonempty labels. '
                            'Only a leading www label in the PSL subdomain is removed for depth. Ratios use full ASCII hostname length including dots; ASCII digits only.',
                'path_query': 'Original path/query, no percent decoding or Unicode normalization. Segments: nonempty slash-separated path parts. '
                              'Fields: nonempty ampersand-separated query parts, including flags and repeated keys. Semicolon is not a separator. '
                              'Encoded ratio = 3 * count of valid %HH triplets / original component length; empty component gives zero.'}}


def extract_all(raw: str, inspector: Callable[[str], dict]):
    inspected = inspector(raw)
    if inspected['preprocessing_version'] != legacy.PREPROCESSING_VERSION:
        raise ValueError('Unsupported preprocessing version.')
    baseline = legacy.extract_features(raw, lambda _: inspected)
    url = inspected['url']
    host = url['hostname_ascii']
    if url['is_ip']:
        hostname = [0.] * len(HOST_NAMES)
    else:
        sublabels = [p for p in (url['subdomain'] or '').split('.') if p]
        www = bool(sublabels and sublabels[0] == 'www')
        hostname = [float(www), float(len(sublabels) - int(www)),
                    float(max((len(p) for p in host.split('.') if p), default=0)),
                    sum('0' <= c <= '9' for c in host) / len(host), host.count('-') / len(host)]
    parts = urlsplit(raw.strip(' '))
    segments = [p for p in parts.path.split('/') if p]
    encoded = lambda s: 3 * len(re.findall(r'%[0-9a-fA-F]{2}', s)) / len(s) if s else 0.
    path_query = [float(len(segments)), float(max(map(len, segments), default=0)),
                  float(sum(bool(p) for p in parts.query.split('&'))), encoded(parts.path), encoded(parts.query)]
    if not all(math.isfinite(v) and v >= 0 for v in hostname + path_query):
        raise ValueError('Invalid extension features.')
    return {'baseline': baseline, 'baseline_plus_hostname': baseline + hostname,
            'baseline_plus_path_query': baseline + path_query}
