from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import test_url_feature_experiments as fixture
import compare_url_lightgbm as m


class LightGBMUnits(unittest.TestCase):
    def test_fixed_protocol_cpu_and_no_imbalance_double_weight(self):
        p=m.validate_protocol()
        self.assertEqual(p['params']['device_type'],'cpu')
        self.assertTrue(p['params']['deterministic'])
        self.assertFalse(p['params']['is_unbalance'])
        self.assertEqual(p['params']['scale_pos_weight'],1)
        self.assertFalse(p['early_stopping'])
        self.assertEqual(p['num_boost_round'],300)

    def test_native_fit_is_reproducible_and_prediction_does_not_fit_validation(self):
        rng=np.random.default_rng(42);x=rng.random((160,23));y=(x[:,0]>.5).astype(int);w=np.ones(160)
        evaluations={'small':(x[:40],y[:40])}
        original=m.lgb.train
        with patch.object(m.lgb,'train',wraps=original) as train:
            a,t=m.fit_lightgbm(x,y,w,evaluations,1)
            self.assertEqual(train.call_count,1)
            self.assertEqual(set(train.call_args.kwargs),{'num_boost_round'})
            self.assertEqual(train.call_args.kwargs['num_boost_round'],300)
            dataset=train.call_args.args[1]
            self.assertEqual(dataset.num_data(),160)
        b,_=m.fit_lightgbm(x,y,w,evaluations,1)
        np.testing.assert_array_equal(a['small'],b['small'])
        self.assertGreater(t['actual_boosting_iterations'],0)
        self.assertLessEqual(t['actual_boosting_iterations'],300)

    def test_invalid_weights_and_schema(self):
        x=np.zeros((4,23));y=np.array([0,1,0,1])
        for w in [np.zeros(4),np.array([1.,1.,float('nan'),1.])]:
            with self.assertRaises(m.base.TrainingError):m.fit_lightgbm(x,y,w,{},1)
        with self.assertRaises(m.base.TrainingError):m.fit_lightgbm(x[:,:18],y,np.ones(4),{},1)

    def test_paired_changes_at_different_thresholds(self):
        y=np.array([0,0,1,1]);labels={s:y for s in m.collector.SOURCES}
        rf={s:np.array([.8,.1,.7,.6]) for s in labels}
        gb={s:np.array([.2,.1,.95,.9]) for s in labels}
        rp=m.thresholds.joint_points({s:(y,rf[s]) for s in labels})
        gp=m.thresholds.joint_points({s:(y,gb[s]) for s in labels})
        r=m.compare_at_cap(labels,rf,gb,rp,gp,'0.01')
        self.assertEqual(r['minimum_source_recall_delta'],1.)
        for s in labels:
            self.assertEqual(r['sources'][s]['corrected_fn'],2)
            self.assertEqual(r['sources'][s]['introduced_fp'],0)


class LightGBMIntegration(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.FeatureExperimentTests();self.fx.setUp();self.fx.run_experiment()
        self.f=self.fx.f;self.output=self.f.root/'lightgbm'
    def tearDown(self):self.fx.tearDown()
    def run_experiment(self):
        with patch.object(m.ex.dg.ms.ev.intake,'LOCK',self.f.lock):
            return m.experiment(self.f.fixture.dataset,self.f.external,self.f.baseline,self.f.primary,
                                self.fx.fx.f.output,self.fx.output,self.output,1)

    def test_full_flow_same_train_weights_no_test_no_network_no_model_export(self):
        old_open=Path.open;old_rf=m.ex.fit_scenario;old_lgb=m.fit_lightgbm;seen={}
        def guard(p,*a,**kw):
            if p.name in ['test.jsonl','holdout.jsonl','cases.jsonl','decisions.jsonl']:
                raise AssertionError('Forbidden file read')
            return old_open(p,*a,**kw)
        def rf(x,y,w,e,workers):
            seen['rf']=(x.copy(),y.copy(),w.copy());return old_rf(x,y,w,e,workers)
        def gb(x,y,w,e,workers):
            seen['gb']=(x.copy(),y.copy(),w.copy());return old_lgb(x,y,w,e,workers)
        with (patch.object(Path,'open',guard),patch('socket.socket',side_effect=AssertionError('network')),
             patch.object(m.ex.dg.ms.ev.joblib,'load',side_effect=AssertionError('pickle')),
             patch.object(m.ex,'fit_scenario',side_effect=rf),patch.object(m,'fit_lightgbm',side_effect=gb)):
            r=self.run_experiment()
        for a,b in zip(seen['rf'],seen['gb']):np.testing.assert_array_equal(a,b)
        self.assertEqual(seen['rf'][0].shape[1],23)
        self.assertEqual(len(seen['rf'][1]),r['splits']['phiusiil_train']['rows']+r['splits']['external_train']['rows'])
        for v in r['train_weight_totals'].values():self.assertAlmostEqual(v,r['train_rows']/4)
        self.assertTrue(r['rf_reproduced_g18']);self.assertFalse(r['model_exported'])
        self.assertEqual({p.name for p in self.output.iterdir()},{'report.json','protocol.json','manifest.json'})
        self.assertNotIn('https://',(self.output/'report.json').read_text())
        def check_keys(value):
            if isinstance(value, dict):
                self.assertFalse({'input_url', 'normalized_url'} & set(value))
                for v in value.values(): check_keys(v)
            elif isinstance(value, list):
                for v in value: check_keys(v)
        check_keys(r)
        for model in r['results'].values():
            for point in model['threshold_study']['joint_cap_points']:
                for source,v in point['sources'].items():
                    self.assertLessEqual(v['confusion_matrix']['fp'],point['allowed_false_positives'][source])

    def test_g18_checksum_failure_before_fit(self):
        with (self.fx.output/'report.json').open('a') as f:f.write(' ')
        with patch.object(m.ex,'fit_scenario',side_effect=AssertionError('fit')):
            with self.assertRaises(m.base.TrainingError):self.run_experiment()
        self.assertFalse(self.output.exists())

    def test_rf_mismatch_prevents_lightgbm_and_output(self):
        with (patch.object(m.ex.dg,'reproduce',side_effect=m.base.TrainingError('mismatch')),
             patch.object(m,'fit_lightgbm',side_effect=AssertionError('fit'))):
            with self.assertRaises(m.base.TrainingError):self.run_experiment()
        self.assertFalse(self.output.exists())

    def test_failed_lightgbm_publishes_nothing(self):
        with patch.object(m,'fit_lightgbm',side_effect=m.lgb.basic.LightGBMError('failed')):
            with self.assertRaises(m.lgb.basic.LightGBMError):self.run_experiment()
        self.assertFalse(self.output.exists())

    def test_changed_protocol_rejected(self):
        p=self.f.root/'changed-protocol.json';v=m.base.load_json(m.PROTOCOL);v['params']['num_leaves']=63;m.base.write_json(p,v)
        with patch.object(m,'PROTOCOL',p),patch.object(m.ex,'fit_scenario',side_effect=AssertionError('fit')):
            with self.assertRaises(m.base.TrainingError):self.run_experiment()

    def test_version_mismatch_rejected(self):
        with patch.object(m.lgb,'__version__','other'):
            with self.assertRaises(m.base.TrainingError):self.run_experiment()

    def test_no_overwrite(self):
        self.output.mkdir()
        with self.assertRaises(m.base.TrainingError):self.run_experiment()

if __name__=='__main__':unittest.main()
