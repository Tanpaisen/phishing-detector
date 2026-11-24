"""Performance helpers. Reports contain aggregate measurements, never submitted URLs."""
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import threading
import time
import psutil

ROOT = Path(__file__).resolve().parents[2]
VERSION = 'url-performance-v1'
SYNTHETIC = (
    'https://example.com', 'http://example.org/a/b?x=1&y=2',
    'https://LOGIN.Example.co.uk/Login?A=1#Section',
    'https://www.example.com/a%20b?q=%E1%BB%87',
    'https://xn--bcher-kva.de/path', 'https://example.com:8443/hello',
    'https://example.org/' + 'a' * 512 + '?q=' + 'x' * 512,
    'https://example.com/đăng-nhập?x=1',
)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def write_report(path, data):
    # Exclusive create: never overwrite another run; encoding explicit on Windows.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def latency(values):
    if not values: return None
    values = sorted(values)
    def q(p): return values[max(0, math.ceil(p * len(values)) - 1)]
    return {'n': len(values), 'p50_ms': q(.50), 'p95_ms': q(.95),
            'p99_ms': q(.99), 'max_ms': values[-1],
            'quantile_method': 'nearest_rank'}


def machine():
    return {'python': platform.python_version(), 'os': platform.system(),
            'machine': platform.machine(), 'logical_cpus': os.cpu_count(),
            'physical_cpus': psutil.cpu_count(logical=False),
            'total_ram_bytes': psutil.virtual_memory().total,
            'psutil': psutil.__version__}


class Monitor:
    """Sample current-process RSS, not child/server RAM. Sampling can miss brief peaks."""
    def __enter__(self):
        self.process = psutil.Process()
        self.initial = self.peak = self.process.memory_info().rss
        self.before_cpu = sum(self.process.cpu_times()[:2])
        self.stop = threading.Event()
        def sample():
            while not self.stop.wait(.02):
                self.peak = max(self.peak, self.process.memory_info().rss)
        self.thread = threading.Thread(target=sample, daemon=True)
        self.thread.start()
        self.started = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = time.perf_counter() - self.started
        self.stop.set(); self.thread.join()
        self.peak = max(self.peak, self.process.memory_info().rss)
        self.cpu = sum(self.process.cpu_times()[:2]) - self.before_cpu

    def report(self):
        return {'wall_seconds': self.elapsed, 'process_cpu_seconds': self.cpu,
                'rss_initial_bytes': self.initial, 'rss_sampled_peak_bytes': self.peak,
                'rss_increase_bytes': max(0, self.peak - self.initial),
                'rss_sampling_interval_ms': 20,
                'scope': 'current process only; sampled RSS is not guaranteed absolute peak'}
