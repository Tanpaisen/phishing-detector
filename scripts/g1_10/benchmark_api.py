"""Local HTTP URL-inspection load probe. Rate-limited replies are NOT successful scans."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlsplit
from common import VERSION, SYNTHETIC, Monitor, machine, write_report, latency, sha


def target_url(url):
    p = urlsplit(url)
    if (p.scheme != 'http' or p.hostname not in ('127.0.0.1', '::1') or p.username or p.password
            or p.query or p.fragment or p.path != '/api/v1/url/inspect'):
        raise ValueError('Only a literal loopback HTTP URL with /api/v1/url/inspect is accepted.')
    return p.hostname, p.port or 80, p.path


def classify(status, body, expected):
    if status == 429: return 'rate_limited'
    if status in (408, 504): return 'http_timeout'
    if status != 200: return 'http_error'
    try: data = json.loads(body)
    except (ValueError, UnicodeError): return 'contract_error'
    if not isinstance(data, dict): return 'contract_error'
    result = data.get('url')
    if (data.get('stage') != 'URL_INSPECTION' or data.get('schema_version') != '1.0'
            or data.get('model_loaded') is not False or not isinstance(result, dict)
            or result.get('normalized_url') != expected): return 'contract_error'
    return 'success'


def summarize(records, seconds):
    counts = Counter(r[0] for r in records)
    return {'completed_attempts': len(records), 'outcomes': dict(counts),
            'http_statuses': dict(Counter(str(r[2]) for r in records if r[2] is not None)),
            'successful_inspections': counts['success'], 'success_ratio': counts['success'] / len(records),
            'attempts_per_second': len(records) / seconds,
            'successful_inspections_per_second': counts['success'] / seconds,
            'all_outcomes_latency': latency([r[1] for r in records]),
            'success_only_latency': latency([r[1] for r in records if r[0] == 'success']),
            'latency_by_outcome': {k: latency([r[1] for r in records if r[0] == k]) for k in counts}}


def probe(url, requests, concurrency, timeout):
    host, port, path = target_url(url)
    if not 1 <= requests <= 10000 or not 1 <= concurrency <= 64 or not 0 < timeout <= 60:
        raise ValueError('Invalid requests/concurrency/timeout.')
    # Synthetic inputs only. Expected normalized values do not require AI imports in the client.
    inputs = [('https://example.com', 'https://example.com'),
              ('https://EXAMPLE.org/a?x=1', 'https://example.org/a?x=1')]
    counter = iter(range(requests)); lock = threading.Lock()
    def worker():
        records = []
        connection = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            while True:
                with lock: index = next(counter, None)
                if index is None: break
                raw, expected = inputs[index % len(inputs)]
                started = time.perf_counter(); status = None
                try:
                    connection.request('POST', path, body=json.dumps({'url': raw}).encode(),
                                       headers={'Content-Type': 'application/json'})
                    response = connection.getresponse(); status = response.status
                    body = response.read(65537)
                    if len(body) > 65536:
                        outcome = 'response_too_large'; connection.close()
                    else: outcome = classify(status, body, expected)
                except (TimeoutError, socket.timeout):
                    outcome = 'transport_timeout'; connection.close()
                except (OSError, http.client.HTTPException):
                    outcome = 'transport_error'; connection.close()
                records.append((outcome, (time.perf_counter() - started) * 1000, status))
        finally: connection.close()
        return records
    with Monitor() as monitor:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            groups = list(pool.map(lambda _: worker(), range(concurrency)))
    records = [r for group in groups for r in group]
    result = summarize(records, monitor.elapsed)
    return {'stage': 'G1.10', 'version': VERSION, 'scope': 'loopback_node_to_ai_url_inspection',
            'status': 'MEASURED' if result['success_ratio'] == 1 else 'MEASURED_WITH_NON_SUCCESS_OUTCOMES',
            'config': {'requests': requests, 'concurrency': concurrency, 'socket_timeout_seconds': timeout,
                       'arrival_model': 'closed_loop_no_think_time', 'http_connection': 'reused per worker when possible',
                       'warmup_requests': 0, 'redirects_followed': False},
            'results': result, 'client_resources': monitor.report(), 'client_machine': machine(),
            'code_sha256': sha(__file__), 'production_ready': False,
            'model_inference_measured': False, 'database_measured': False,
            'server_cpu_ram_measured': False,
            'limitations': ['Client RSS is not Node/FastAPI memory. Server hardware and startup flags must be recorded separately.',
                           '429, timeouts, bad contracts and failures are excluded from successful throughput.',
                           'Existing 60 requests/minute/IP guard is left enabled; no bypass or retries.',
                           'No fixed arrival rate: this closed-loop probe is not a capacity or SLA guarantee.',
                           'Synthetic short URLs only; no URL fetch, accuracy evaluation, model inference or DB queries.',
                           'Percentiles with few successful samples are unstable. Runs can share the same rate-limit window.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:3001/api/v1/url/inspect')
    p.add_argument('--requests', type=int, default=40)
    p.add_argument('--concurrency', type=int, default=1)
    p.add_argument('--timeout', type=float, default=10)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        if a.output.exists(): raise ValueError('Output exists.')
        result = probe(a.url, a.requests, a.concurrency, a.timeout)
        write_report(a.output, result)
        print(json.dumps({'status': result['status'], 'results': result['results']}, indent=2))
    except (ValueError, OSError):
        print('ERROR: check loopback target, parameters and new output path.')
        return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
