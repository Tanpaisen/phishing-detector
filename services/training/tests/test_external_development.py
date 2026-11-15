import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import evaluate_external_development as ev
import train_url_baselines as base
import test_url_baselines as fixtures
from common import save_manifest,write_rows,prep
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier


class ExternalEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.TrainingTests();self.fixture.setUp();self.root=self.fixture.root
        self.baseline=self.root/'baseline';base.train(self.fixture.dataset,self.baseline,1)
        self.primary=self.root/'primary.csv';self.primary.write_text('synthetic primary for tests only',encoding='utf-8')
        self.lock=self.root/'source-lock.json'
        self.source={'sha256':base.sha(self.primary),'source_id':'synthetic','source_page':'https://example.com/source',
                     'doi':'synthetic','label_map':{'legitimate':0,'phishing':1}}
        base.write_json(self.lock,self.source)
        self.external=self.root/'external';self.external.mkdir()
        records=[]
        for i in range(200):
            raw=f'https://external{i}.net/'+('login-'*4 if i%2 else 'home')
            data=base.inspect_url(raw);group=prep.grouping(data)
            if ev.intake.role(group)!='development':continue
            records.append({'input_url':raw,'normalized_url':data['url']['normalized_url'],
                'sample_id':prep.digest_text(data['url']['normalized_url']),'group_id':group,
                'source_record':i+1,'source_id':'synthetic','source_label':'phishing' if i%2 else 'legitimate','y':i%2,
                'role':'development','scheme':'https','url_length':data['features']['url_length']})
            if len(records)==40:break
        self.records=records
        write_rows(self.external/'development.jsonl',records)
        from collections import Counter
        stats={'rows':len(records),'groups':len({r['group_id'] for r in records}),
               'labels':dict(Counter(str(r['y']) for r in records))}
        base.write_json(self.external/'report.json',{'base_url_overlap_after_filter':0,'base_domain_overlap_after_filter':0,
                       'development_holdout_group_overlap':0,'splits':{'development':stats}})
        model_manifest=base.load_json(self.baseline/'manifest.json')
        save_manifest(self.external,{'version':ev.intake.VERSION,'source':self.source,'runtime':prep.runtime(),
            'code_sha256':base.sha(Path(ev.intake.__file__)),
            'base_dataset_manifest_sha256':model_manifest['dataset_manifest_sha256']})

    def tearDown(self):self.fixture.tearDown()

    def evaluate(self):
        with patch.object(ev.intake,'LOCK',self.lock):
            return ev.evaluate(self.external,self.baseline,self.primary,self.root/'result','mendeley-v3',1)

    def test_no_fit_no_train_validation_holdout_or_test_reads(self):
        original_open=Path.open
        def guard(path,*a,**kw):
            if path.name in ('train.jsonl','validation.jsonl','test.jsonl','holdout.jsonl'):
                raise AssertionError('Do not access frozen splits during external scoring')
            return original_open(path,*a,**kw)
        hashes={p.name:base.sha(p) for p in self.baseline.iterdir()}
        with patch.object(Path,'open',guard),patch.object(LogisticRegression,'fit',side_effect=AssertionError('No fitting')),patch.object(RandomForestClassifier,'fit',side_effect=AssertionError('No fitting')),patch('socket.socket',side_effect=AssertionError('Offline')):
            r=self.evaluate()
        self.assertEqual(r['rows'],40)
        self.assertFalse(r['model_fit_performed']);self.assertFalse(r['external_holdout_file_opened'])
        self.assertEqual(set(r['results']),set(ev.MODEL_NAMES))
        self.assertTrue(r['provenance']['primary_byte_match'])
        self.assertFalse(r['provenance']['origin_authenticated_by_software'])
        self.assertEqual(hashes,{p.name:base.sha(p) for p in self.baseline.iterdir()})
        text=(self.root/'result/report.json').read_text(encoding='utf-8')
        self.assertNotIn('https://external',text)

    def test_primary_mismatch_stops_before_model_load(self):
        self.primary.write_text('wrong',encoding='utf-8')
        with patch.object(ev.joblib,'load',side_effect=AssertionError('Never deserialize on bad provenance')):
            with self.assertRaisesRegex(base.TrainingError,'Primary file'):self.evaluate()
        self.assertFalse((self.root/'result').exists())

    def test_corrupt_artifact_stops_before_load(self):
        p=self.baseline/'random_forest.joblib'
        with p.open('ab') as f:f.write(b'corrupt')
        with patch.object(ev.joblib,'load',side_effect=AssertionError('Do not deserialize corrupt model')):
            with self.assertRaisesRegex(base.TrainingError,'checksum'):self.evaluate()

    def test_mutated_development_checksum_rejected(self):
        with (self.external/'development.jsonl').open('a',encoding='utf-8') as f:f.write('{}\n')
        with self.assertRaisesRegex(base.TrainingError,'checksum'):self.evaluate()

    def test_role_injection_rejected_even_with_rehashed_file(self):
        changed=copy.deepcopy(self.records);changed[0]['role']='holdout'
        write_rows(self.external/'development.jsonl',changed)
        m=base.load_json(self.external/'manifest.json');m['files']['development.jsonl']=base.sha(self.external/'development.jsonl')
        base.write_json(self.external/'manifest.json',m)
        with self.assertRaisesRegex(base.TrainingError,'role'):self.evaluate()

    def test_bundle_metadata_rejected(self):
        original=ev.joblib.load
        def load(path):
            b=original(path);b['positive_label']=0;return b
        with patch.object(ev.joblib,'load',side_effect=load):
            with self.assertRaisesRegex(base.TrainingError,'bundle'):self.evaluate()

    def test_wrong_runtime_stops_before_load(self):
        m=base.load_json(self.baseline/'manifest.json');m['runtime']['python_version']='0'
        base.write_json(self.baseline/'manifest.json',m)
        with patch.object(ev.joblib,'load',side_effect=AssertionError('No incompatible load')):
            with self.assertRaisesRegex(base.TrainingError,'environment'):self.evaluate()

    def test_refuses_existing_output(self):
        (self.root/'result').mkdir()
        with self.assertRaisesRegex(base.TrainingError,'new output'):self.evaluate()

    def test_slice_zero_denominators(self):
        r=ev.slice_metrics(np.array([1,1]),np.array([.8,.2]),np.array([True,True]))
        self.assertIsNone(r['fpr']);self.assertEqual(r['recall'],.5)
        r=ev.slice_metrics(np.array([0,1]),np.array([.8,.2]),np.array([False,False]))
        self.assertEqual(r['rows'],0);self.assertIsNone(r['precision']);self.assertIsNone(r['recall'])

if __name__=='__main__':unittest.main()

# Audit helper tests are discovered by unittest; these do not inspect any real test set.
class StructureAuditTests(unittest.TestCase):
    def test_structure_counts_preserve_slash_distinction(self):
        from audit_url_structure import structure_counts
        r=structure_counts([{'input_url':'https://example.com','y':0},
                            {'input_url':'https://example.com/','y':0},
                            {'input_url':'http://example.net/a','y':1}])
        self.assertEqual(r['0']['empty_path'],1);self.assertEqual(r['0']['slash_only_path'],1)
        self.assertEqual(r['0']['exactly_two_slashes'],1);self.assertEqual(r['1']['non_root_path'],1)

    def test_primary_label_mapping_and_record_bounds(self):
        from audit_url_structure import verify_primary_rows
        primary=[{'url':'https://example.com','status':'legitimate'}]
        row={'source_record':1,'input_url':'https://example.com','source_label':'legitimate','y':0}
        self.assertEqual(verify_primary_rows([row],primary),1)
        for change in [{'source_record':0},{'y':1},{'source_label':'phishing'}]:
            with self.subTest(change=change):
                with self.assertRaises(base.TrainingError):verify_primary_rows([{**row,**change}],primary)
