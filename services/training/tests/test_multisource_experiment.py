import csv
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import test_external_development as fixture
import train_multisource_experiment as ms
from common import base

class MultiSourceTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.ExternalEvaluationTests();self.f.setUp()
        primary=[{'url':'https://unused.net','status':'legitimate'} for _ in range(max(r['source_record'] for r in self.f.records))]
        for r in self.f.records:primary[r['source_record']-1]={'url':r['input_url'],'status':r['source_label']}
        with self.f.primary.open('w',encoding='utf-8',newline='') as stream:
            w=csv.DictWriter(stream,fieldnames=['url','status']);w.writeheader();w.writerows(primary)
        self.f.source['sha256']=base.sha(self.f.primary);base.write_json(self.f.lock,self.f.source)
        m=base.load_json(self.f.external/'manifest.json');m['source']=self.f.source
        base.write_json(self.f.external/'manifest.json',m)
        self.output=self.f.root/'mixed'
    def tearDown(self):self.f.tearDown()
    def run_experiment(self):
        with patch.object(ms.ev.intake,'LOCK',self.f.lock):
            return ms.experiment(self.f.fixture.dataset,self.f.external,self.f.baseline,self.f.primary,self.output,1)
    def test_full_run_offline_no_final_sets_or_pickle(self):
        orig=Path.open
        def guard(p,*a,**kw):
            if p.name in ['test.jsonl','holdout.jsonl']:raise AssertionError('Final set read')
            return orig(p,*a,**kw)
        with patch.object(Path,'open',guard),patch('socket.socket',side_effect=AssertionError('Network')),patch.object(ms.ev.joblib,'load',side_effect=AssertionError('No model load')):
            r=self.run_experiment()
        self.assertEqual(len(r['results']),3)
        self.assertEqual(r['splits']['external_train']['rows']+r['splits']['external_reused_validation']['rows'],40)
        self.assertFalse(r['model_exported'])
        self.assertNotIn('https://external',(self.output/'report.json').read_text(encoding='utf-8'))
    def test_corrupt_source_stops_before_fit(self):
        self.f.primary.write_text('bad',encoding='utf-8')
        with patch.object(ms,'fit_models',side_effect=AssertionError('Fit called')):
            with self.assertRaises(base.TrainingError):self.run_experiment()
        self.assertFalse(self.output.exists())
    def test_failed_fit_does_not_publish(self):
        with patch.object(ms,'fit_models',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):self.run_experiment()
        self.assertFalse(self.output.exists())
    def test_no_overwrite(self):
        self.output.mkdir()
        with self.assertRaises(base.TrainingError):self.run_experiment()

class SplitAndWeightTests(unittest.TestCase):
    def test_group_assignment_order_and_label_independent(self):
        meta=[{'group_id':str(i//2)} for i in range(100)]
        y=np.array([i%2 for i in range(100)])
        a=ms.partition(meta,y)
        self.assertTrue(np.array_equal(a,ms.partition(meta,1-y)))
        self.assertTrue(np.array_equal(a,ms.partition(meta[::-1],y[::-1])[::-1]))
        self.assertTrue(np.array_equal(a[::2],a[1::2]))
    def test_weights_equalize_source_label_mass(self):
        y=np.array([0,0,0,1,0,1,1]);s=np.array([0,0,0,0,1,1,1]);w=ms.weights_for(y,s)
        for source in [0,1]:
            for label in [0,1]:self.assertAlmostEqual(w[(s==source)&(y==label)].sum(),len(y)/4)
    def test_weighted_fit_routes_train_weights_to_scaler_and_classifier(self):
        class Estimator:
            classes_ = np.array([0,1])
            def __init__(self):self.parameters={};self.calls=[]
            def set_params(self,**kwargs):self.parameters.update(kwargs)
            def fit(self,x,y,**kwargs):self.calls.append((x.copy(),y.copy(),kwargs))
            def predict_proba(self,x):return np.tile([.4,.6],(len(x),1))
        models={name:Estimator() for name in ms.ev.MODEL_NAMES}
        xt=np.zeros((4,len(base.FEATURE_NAMES)));xv=np.ones((2,len(base.FEATURE_NAMES)))
        yt=np.array([0,1,0,1]);yv=np.array([0,1]);weights=np.array([1.,2.,3.,4.])
        with patch.object(base,'estimators',return_value=models):
            ms.fit_models(xt,yt,{'validation':(xv,yv)},1,weights)
        for name,model in models.items():
            self.assertEqual(len(model.calls),1)
            self.assertTrue(np.array_equal(model.calls[0][0],xt))
            self.assertTrue(np.array_equal(model.calls[0][1],yt))
            self.assertTrue(all(v is None for v in model.parameters.values()))
            expected=['scale__sample_weight','classifier__sample_weight'] if name=='logistic_regression' else ['sample_weight']
            self.assertEqual(set(model.calls[0][2]),set(expected))
            for key in expected:self.assertTrue(np.array_equal(model.calls[0][2][key],weights))

    def test_leakage_and_missing_classes_rejected(self):
        with self.assertRaises(base.TrainingError):ms.assert_disjoint({'a'},{'g'},{'b'},{'g'})
        with self.assertRaises(base.TrainingError):ms.partition([{'group_id':'a'}],np.array([0]))
        with self.assertRaises(base.TrainingError):ms.weights_for(np.array([0,1]),np.array([0,0]))

if __name__=='__main__':unittest.main()
