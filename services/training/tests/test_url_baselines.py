import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import train_url_baselines as training
from phishing_core.url_features import extract_features, FEATURE_NAMES, schema
from url_analysis import inspect_url, URLInputError
import numpy as np
import joblib


class FeatureTests(unittest.TestCase):
    def test_feature_definitions_and_order(self):
        raw = 'https://Sub.Example.com:443/A%20B?x=12&Y=3#Top'
        values = dict(zip(FEATURE_NAMES, extract_features(raw, inspect_url)))
        self.assertEqual(len(values), 18)
        self.assertEqual(values['url_length'], len(raw))
        self.assertEqual(values['hostname_length'], 15)
        self.assertEqual(values['subdomain_count'], 1)
        self.assertEqual(values['path_length'], 6)
        self.assertEqual(values['query_length'], 8)
        self.assertEqual(values['fragment_length'], 3)
        self.assertEqual(values['percent_escape_count'], 1)
        self.assertEqual(values['has_explicit_port'], 1)
        self.assertEqual(values['digit_count'], 8)
        self.assertEqual(values['equals_count'], 2)

    def test_invalid_url_not_silently_imputed(self):
        with self.assertRaises(URLInputError):
            extract_features('javascript:alert(1)', inspect_url)

    def test_input_representation_preserved_and_offline(self):
        with patch('socket.socket', side_effect=AssertionError('No network allowed')):
            unicode_values = extract_features('https://bücher.de/', inspect_url)
            ascii_values = extract_features('https://xn--bcher-kva.de/', inspect_url)
        self.assertNotEqual(unicode_values[0], ascii_values[0])
        self.assertEqual(unicode_values[1], ascii_values[1])
        self.assertEqual(extract_features(' https://example.com/?# ', inspect_url),
                         extract_features('https://example.com/?#', inspect_url))

    def test_unknown_preprocessing_rejected(self):
        def wrong(raw):
            inspected = inspect_url(raw); inspected['preprocessing_version']='unknown'; return inspected
        with self.assertRaises(ValueError):
            extract_features('https://example.com', wrong)


class TrainingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.dataset = self.root/'dataset'; self.dataset.mkdir()
        stats = {}
        for split, offset, count in [('train',0,40),('validation',40,20)]:
            records=[]
            for i in range(offset,offset+count):
                records.append({'input_url': f'https://sample{i}.com/' + ('login-'*4 if i%2 else 'home'),
                                'source_label':str(1-i%2),'y':i%2,'sample_id':f'sample{i}','group_id':f'group{i}'})
            with (self.dataset/f'{split}.jsonl').open('w',encoding='utf-8') as stream:
                for record in records: stream.write(json.dumps(record)+'\n')
            stats[split]={'rows':count,'groups':count,'labels':{'0':count//2,'1':count//2}}
        training.write_json(self.dataset/'report.json',{'splits':stats})
        resources=inspect_url('https://example.com/')
        manifest={'status':'FROZEN','pipeline_version':'url-dataset-v1',
                  'runtime':{'preprocessing_version':resources['preprocessing_version'],**resources['resources']},
                  'source':training.load_json(training.ROOT/'scripts/g1/source-lock.json'),
                  'code_sha256':{'prepare_urls.py':training.sha(training.ROOT/'scripts/g1/prepare_urls.py'),
                                 'url_analysis.py':training.sha(training.ROOT/'services/ai/url_analysis.py')},
                  'files':{p.name:training.sha(p) for p in self.dataset.iterdir()}}
        manifest['files']['test.jsonl']='0'*64
        training.write_json(self.dataset/'manifest.json',manifest)
        # Deliberately absent test.jsonl: G1.2 must not require it.

    def tearDown(self): self.temp.cleanup()

    def test_full_training_never_opens_test_and_exports_both_models(self):
        original_open=Path.open
        def guarded_open(path,*args,**kwargs):
            if path.name=='test.jsonl': raise AssertionError('Final test must remain untouched')
            return original_open(path,*args,**kwargs)
        with patch.object(Path,'open',guarded_open):
            report=training.train(self.dataset,self.root/'models',1)
        self.assertFalse(report['final_test_opened'])
        self.assertEqual(set(report['results']),{'logistic_regression','random_forest'})
        self.assertEqual(report['status'],'CANDIDATE_ONLY')
        self.assertEqual(training.load_json(self.root/'models/feature-schema.json'),schema())

    def test_scaler_fits_train_only_and_roundtrip(self):
        xt=np.asarray([[i + (j % 3) for j in range(len(FEATURE_NAMES))] for i in range(40)],dtype=float); yt=np.asarray([i%2 for i in range(40)])
        xv=xt[:20]+10000; yv=yt[:20]
        target=self.root/'fit';target.mkdir()
        training.fit_and_compare(xt,yt,xv,yv,target,1)
        model=joblib.load(target/'logistic_regression.joblib')['model']
        np.testing.assert_allclose(model.named_steps['scale'].mean_,xt.mean(axis=0))
        self.assertNotAlmostEqual(model.named_steps['scale'].mean_[0],np.vstack([xt,xv]).mean(axis=0)[0])

    def test_wrong_checksum_and_runtime_stop_before_fit(self):
        with (self.dataset/'train.jsonl').open('a',encoding='utf-8') as stream: stream.write('{}\n')
        with patch.object(training,'fit_and_compare',side_effect=AssertionError('Fit must not run')):
            with self.assertRaisesRegex(training.TrainingError,'checksum'):
                training.train(self.dataset,self.root/'models')
        self.assertFalse((self.root/'models').exists())
        manifest=training.load_json(self.dataset/'manifest.json');manifest['runtime']['python_version']='0.0.0'
        training.write_json(self.dataset/'manifest.json',manifest)
        with self.assertRaisesRegex(training.TrainingError,'same Python'):
            training.validate_manifest(self.dataset)

    def test_final_test_split_refused(self):
        with self.assertRaises(training.TrainingError): training.load_split(self.dataset,'test',{})

    def test_confusion_matrix_positive_class_and_no_threshold_tuning(self):
        result=training.metrics(np.array([0,0,1,1]),np.array([.1,.6,.4,.9]))
        self.assertEqual(result['confusion_matrix'],{'tn':1,'fp':1,'fn':1,'tp':1})
        self.assertEqual(result['threshold'],.5)
        self.assertEqual(result['recall'],.5); self.assertEqual(result['fpr'],.5)
        with self.assertRaises(training.TrainingError):training.metrics(np.array([0,1]),np.array([float('nan'),.5]))

    def test_domain_overlap_stops_training(self):
        records=[json.loads(line) for line in (self.dataset/'validation.jsonl').read_text(encoding='utf-8').splitlines()]
        records[0]['group_id']='group0'
        with (self.dataset/'validation.jsonl').open('w',encoding='utf-8') as stream:
            for record in records:stream.write(json.dumps(record)+'\n')
        manifest=training.load_json(self.dataset/'manifest.json');manifest['files']['validation.jsonl']=training.sha(self.dataset/'validation.jsonl')
        training.write_json(self.dataset/'manifest.json',manifest)
        with patch.object(training,'fit_and_compare',side_effect=AssertionError('No training on leaked groups')):
            with self.assertRaisesRegex(training.TrainingError,'leakage'):
                training.train(self.dataset,self.root/'models')

    def test_failed_fit_cleans_staging_and_no_overwrite(self):
        with patch.object(training,'fit_and_compare',side_effect=training.TrainingError('synthetic failure')):
            with self.assertRaises(training.TrainingError):training.train(self.dataset,self.root/'models')
        self.assertFalse((self.root/'models').exists())
        self.assertFalse(list(self.root.glob('.baseline-staging-*')))
        (self.root/'models').mkdir()
        with self.assertRaisesRegex(training.TrainingError,'exists'):
            training.train(self.dataset,self.root/'models')

if __name__=='__main__':unittest.main()
