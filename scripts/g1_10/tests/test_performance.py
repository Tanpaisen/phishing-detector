import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common
import benchmark_api as api
import benchmark_local as local


class UnitTests(unittest.TestCase):
    def test_quantiles_and_empty(self):
        self.assertIsNone(common.latency([]))
        self.assertEqual(common.latency(list(range(1, 101)))['p95_ms'], 95)
        self.assertEqual(common.latency([2])['p99_ms'], 2)

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'report.json'; common.write_report(p, {'x': 1})
            with self.assertRaises(FileExistsError): common.write_report(p, {'x': 2})
            self.assertEqual(json.loads(p.read_text()), {'x': 1})

    def test_loopback_and_path_only(self):
        self.assertEqual(api.target_url('http://127.0.0.1:3001/api/v1/url/inspect')[1], 3001)
        for url in ['https://example.com/api/v1/url/inspect', 'http://localhost/api/v1/url/inspect',
                    'http://u:p@127.0.0.1/api/v1/url/inspect', 'http://127.0.0.1/api/v1/url/inspect?x=1',
                    'http://127.0.0.1/internal/v1/url/inspect']:
            with self.assertRaises(ValueError): api.target_url(url)

    def test_status_and_response_contract(self):
        self.assertEqual(api.classify(429,b'', ''), 'rate_limited')
        self.assertEqual(api.classify(504,b'', ''), 'http_timeout')
        for data in [b'null',b'[]',b'{}',b'bad']:
            self.assertEqual(api.classify(200,data, 'x'), 'contract_error')
        body={'stage':'URL_INSPECTION','schema_version':'1.0','model_loaded':False,'url':{'normalized_url':'x'}}
        self.assertEqual(api.classify(200,json.dumps(body).encode(),'x'),'success')
        self.assertEqual(api.classify(200,json.dumps(body).encode(),'y'),'contract_error')
        body['model_loaded']=True
        self.assertEqual(api.classify(200,json.dumps(body).encode(),'x'),'contract_error')

    def test_failures_not_counted_as_throughput(self):
        r=api.summarize([('success',10,200),('rate_limited',1,429),('transport_timeout',100,None)],2)
        self.assertEqual(r['attempts_per_second'],1.5)
        self.assertEqual(r['successful_inspections_per_second'],.5)
        self.assertEqual(r['success_only_latency']['n'],1)
        r=api.summarize([('http_error',1,503)],1)
        self.assertIsNone(r['success_only_latency'])

    def test_train_only_no_replay_and_line_bound(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'train.jsonl';p.write_text(json.dumps({'input_url':'https://example.com'})+'\n')
            self.assertEqual(len(list(local.source(1,p))),1)
            with self.assertRaises(ValueError): list(local.source(2,p))
            with self.assertRaises(ValueError): list(local.train_urls(Path(d)/'test.jsonl'))
            p.write_text('x'*(local.MAX_LINE+1))
            with self.assertRaises(ValueError): list(local.train_urls(p))

    def test_synthetic_stream_offline_and_no_raw_output(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            r=local.run(25,'features')
        self.assertEqual(r['valid'],25)
        self.assertEqual(r['invalid'],0)
        self.assertNotIn('https://',json.dumps(r))
        self.assertFalse(r['training_measured'])
        self.assertGreater(r['timing']['rss_sampled_peak_bytes'],0)

    def test_rejected_urls_are_not_successes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'train.jsonl';p.write_text(json.dumps({'input_url':'not a URL'})+'\n')
            r=local.run(1,'inspection',p)
            self.assertEqual(r['invalid'],1)
            self.assertEqual(r['successful_rows_per_second'],0)
            self.assertIsNone(r['first_1000_successful_call_latency'])

    def test_http_integration_and_no_redirect(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(302);self.send_header('Location','http://example.com');self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            r=api.probe(f'http://127.0.0.1:{server.server_port}/api/v1/url/inspect',6,2,1)
            self.assertEqual(r['results']['http_statuses'],{'302':6})
            self.assertEqual(r['results']['successful_inspections'],0)
        finally: server.shutdown();server.server_close();thread.join()

    def test_http_timeout_is_not_success(self):
        with patch('benchmark_api.http.client.HTTPConnection') as connection:
            connection.return_value.request.side_effect = TimeoutError()
            r = api.probe('http://127.0.0.1:3001/api/v1/url/inspect', 3, 1, .1)
        self.assertEqual(r['results']['outcomes'], {'transport_timeout': 3})
        self.assertIsNone(r['results']['success_only_latency'])

    def test_http_connection_failure_has_report(self):
        # Closed ephemeral ports can time out or be reused on different OSes.
        # Inject refusal deterministically; real HTTP is covered above.
        with patch('benchmark_api.http.client.HTTPConnection') as connection:
            connection.return_value.request.side_effect = ConnectionRefusedError()
            r = api.probe('http://127.0.0.1:3001/api/v1/url/inspect', 2, 1, .1)
        self.assertEqual(r['results']['outcomes'], {'transport_error': 2})
        self.assertEqual(r['results']['successful_inspections'], 0)
        self.assertIsNone(r['results']['success_only_latency'])
        self.assertEqual(connection.return_value.request.call_count, 2)
        self.assertTrue(connection.return_value.close.called)

if __name__=='__main__': unittest.main()
