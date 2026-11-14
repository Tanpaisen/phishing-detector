import copy
import csv
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_urls as pipeline
import download_source


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rows = [{'URL': f'https://sample{i}.com/Login?A=1#Section', 'label': str(i % 2)} for i in range(60)]

    def tearDown(self):
        self.temp.cleanup()

    def source(self, rows=None):
        source = self.root / 'source.csv'
        with source.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['URL', 'label'])
            writer.writeheader(); writer.writerows(self.rows if rows is None else rows)
        lock = {'source_id': 'synthetic-test', 'csv_sha256': pipeline.sha_file(source),
                'preprocessing': pipeline.load_json(pipeline.LOCK)['preprocessing']}
        return source, lock

    def run_pipeline(self, rows=None, name='dataset'):
        source, lock = self.source(rows)
        output = self.root / name
        report = pipeline.prepare(source, output, lock)
        return output, report

    def records(self, output):
        return {split: [json.loads(line) for line in (output / f'{split}.jsonl').read_text(encoding='utf-8').splitlines()] for split in pipeline.RATIOS}

    def test_end_to_end_no_network_and_label_mapping(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            output, report = self.run_pipeline()
            checked = pipeline.verify(output)
        self.assertEqual(checked['clean_rows'], 60)
        self.assertEqual(report['quarantined_rows'], 0)
        for rows in self.records(output).values():
            self.assertEqual({row['y'] for row in rows}, {0, 1})
            for row in rows:
                self.assertEqual(row['y'], 1-int(row['source_label']))
                self.assertIn('/Login?A=1#Section', row['normalized_url'])

    def test_domain_private_suffix_and_ip_grouping(self):
        rows = self.rows + [{'URL': url, 'label': '0'} for url in [
            'https://a.tenant.blogspot.com/a', 'https://b.tenant.blogspot.com/b',
            'https://other.blogspot.com/a', 'https://8.8.8.8/a', 'http://8.8.8.8/b',
            'https://a.example.co.uk/a', 'http://b.example.co.uk/b']]
        output, _ = self.run_pipeline(rows)
        found = {r['input_url']: (split, r['group_id']) for split, records in self.records(output).items() for r in records}
        self.assertEqual(found[rows[-7]['URL']], found[rows[-6]['URL']])
        self.assertNotEqual(found[rows[-7]['URL']][1], found[rows[-5]['URL']][1])
        self.assertEqual(found[rows[-4]['URL']], found[rows[-3]['URL']])
        self.assertEqual(found[rows[-2]['URL']], found[rows[-1]['URL']])

    def test_conflicts_duplicates_invalid_and_accounting(self):
        rows = self.rows + [dict(self.rows[0]), {'URL': self.rows[1]['URL'], 'label': '0'},
            {'URL': 'https://user:password@example.com/', 'label': '0'},
            {'URL': 'https://example.com/', 'label': 'spam'},
            {'URL': 'https://bücher.de/a', 'label': '1'}, {'URL': 'https://xn--bcher-kva.de/a', 'label': '1'},
            {'URL': 'https://case.com/Login', 'label': '1'}, {'URL': 'https://case.com/login', 'label': '1'}]
        output, report = self.run_pipeline(rows)
        self.assertEqual(report['conflicting_canonical_urls'], 1)
        self.assertEqual(report['duplicate_rows_removed'], 2)
        self.assertEqual(report['quarantined_rows'], 4)
        self.assertEqual(report['input_rows'], report['clean_rows'] + 6)
        quarantine = (output / 'quarantine.jsonl').read_text(encoding='utf-8')
        self.assertNotIn('password', quarantine)
        self.assertNotIn('https://', quarantine)
        kept = [r for records in self.records(output).values() for r in records]
        self.assertEqual(sum(r['normalized_url'].startswith('https://case.com/') for r in kept), 2)

    def test_reproducible_bytes_and_order_independent_assignment(self):
        first, _ = self.run_pipeline(name='first')
        second, _ = self.run_pipeline(name='second')
        for path in first.iterdir():
            self.assertEqual(path.read_bytes(), (second/path.name).read_bytes())
        shuffled = copy.deepcopy(self.rows); random.Random(13).shuffle(shuffled)
        third, _ = self.run_pipeline(shuffled, 'third')
        def assignment(output):
            return {r['sample_id']: split for split, rows in self.records(output).items() for r in rows}
        self.assertEqual(assignment(first), assignment(third))

    def test_bad_checksum_and_preprocessing_do_not_publish(self):
        source, lock = self.source()
        bad = copy.deepcopy(lock); bad['csv_sha256'] = '0'*64
        with self.assertRaises(pipeline.DataError):
            pipeline.prepare(source, self.root/'bad', bad)
        bad = copy.deepcopy(lock); bad['preprocessing']['psl_sha256'] = '0'*64
        with self.assertRaises(pipeline.DataError):
            pipeline.prepare(source, self.root/'bad', bad)
        self.assertFalse((self.root/'bad').exists())

    def test_refuses_overwrite_and_insufficient_groups(self):
        output, _ = self.run_pipeline()
        source, lock = self.source()
        with self.assertRaises(pipeline.DataError):
            pipeline.prepare(source, output, lock)
        with self.assertRaises(pipeline.DataError):
            self.run_pipeline(self.rows[:2], 'small')
        self.assertFalse((self.root/'small').exists())

    def test_corruption_detected(self):
        output, _ = self.run_pipeline()
        with (output/'train.jsonl').open('a', encoding='utf-8') as stream:
            stream.write('{}\n')
        with self.assertRaisesRegex(pipeline.DataError, 'Checksum'):
            pipeline.verify(output)

    def test_leakage_detected_even_if_file_hashes_recomputed(self):
        output, _ = self.run_pipeline()
        records = self.records(output)
        donor = records['train'][0]
        injected = copy.deepcopy(donor)
        injected['input_url'] = donor['input_url'] + 'changed'
        injected['normalized_url'] = injected['input_url']
        injected['sample_id'] = pipeline.digest_text(injected['input_url'])
        injected['source_record'] = 9999
        records['test'].append(injected)
        pipeline.write_jsonl(output/'test.jsonl', records['test'])
        manifest = pipeline.load_json(output/'manifest.json')
        manifest['files']['test.jsonl'] = pipeline.sha_file(output/'test.jsonl')
        pipeline.write_json(output/'manifest.json', manifest)
        with self.assertRaisesRegex(pipeline.DataError, 'leakage'):
            pipeline.verify(output)

    def test_failed_final_verification_removes_staging(self):
        source, lock = self.source()
        with patch.object(pipeline, 'verify', side_effect=pipeline.DataError('synthetic failure')):
            with self.assertRaises(pipeline.DataError):
                pipeline.prepare(source, self.root/'failed', lock)
        self.assertFalse((self.root/'failed').exists())
        self.assertFalse(list(self.root.glob('.url-data-staging-*')))

    def test_missing_columns(self):
        source=self.root/'missing.csv'; source.write_text('wrong,label\na,0\n',encoding='utf-8')
        lock={'source_id':'test','csv_sha256':pipeline.sha_file(source),'preprocessing':{}}
        with self.assertRaisesRegex(pipeline.DataError, 'columns'):
            pipeline.prepare(source,self.root/'bad',lock)

    def test_download_reuses_matching_source_without_network(self):
        target=self.root/'phiusiil.csv'; target.write_bytes(b'synthetic')
        fake_lock={'csv_sha256':pipeline.sha_file(target)}
        with patch.object(download_source.json,'loads',return_value=fake_lock), patch('urllib.request.urlopen',side_effect=AssertionError('No download expected')):
            self.assertEqual(download_source.download(self.root)['status'],'already_verified')

if __name__ == '__main__':
    unittest.main()
