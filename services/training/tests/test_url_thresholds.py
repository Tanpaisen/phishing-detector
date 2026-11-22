import json
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
import test_url_feature_experiments as fixture
import collect_url_validation_scores as collect
import analyze_url_thresholds as study
from common import base,rows,write_rows

class ThresholdUnitTests(unittest.TestCase):
    def test_exact_integer_budgets(self):
        self.assertEqual([study.allowed_fp(c,472) for c in study.CAPS],[0,2,4,9,23])
        self.assertEqual(study.allowed_fp('0.01',100),1)
        with self.assertRaises(base.TrainingError):study.allowed_fp('1.1',10)
    def test_inclusive_threshold_and_ties(self):
        y=np.array([0,1]);s=np.array([.5,.5]);p=study.point(y,s,.5)
        self.assertEqual(p['confusion_matrix'],{'tn':0,'fp':1,'fn':0,'tp':1})
        result=study.joint_points({k:(y,s) for k in study.SOURCES},('0',))['joint_cap_points'][0]
        self.assertGreater(result['threshold'],.5)
        self.assertEqual(result['status'],'NO_POSITIVE_PREDICTIONS_ON_OBSERVED_VALIDATION')
        self.assertIsNone(result['sources'][study.SOURCES[0]]['precision'])
    def test_score_one_reject_all_sentinel(self):
        y=np.array([0,1]);s=np.array([1.,1.])
        p=study.joint_points({k:(y,s) for k in study.SOURCES},('0',))['joint_cap_points'][0]
        self.assertTrue(p['threshold_above_score_range']);self.assertGreater(p['threshold'],1)
    def test_each_source_constraint_not_pooled(self):
        a=(np.array([0]*100+[1]*10),np.array([.1]*100+[.95]*10))
        b=(np.array([0]*10+[1]*10),np.array([.9]+[.1]*9+[.8]*10))
        p=study.joint_points(dict(zip(study.SOURCES,[a,b])),('0.01',))['joint_cap_points'][0]
        self.assertEqual(p['threshold'],.95)
        self.assertEqual(p['sources'][study.SOURCES[1]]['recall'],0)
    def test_random_tied_scores_match_bruteforce_minimum(self):
        rng=np.random.default_rng(42)
        for _ in range(10):
            data={k:(np.r_[0,1,rng.integers(0,2,20)],rng.choice([0.,.2,.5,.8,1.],22)) for k in study.SOURCES}
            all_s=np.concatenate([s for y,s in data.values()]);candidates=np.unique(np.r_[0.,all_s,np.nextafter(max(all_s),np.inf)])
            for p in study.joint_points(data,('0','0.2','0.5'))['joint_cap_points']:
                feasible=[]
                for t in candidates:
                    ok=all(study.point(y,s,t)['confusion_matrix']['fp']<=study.allowed_fp(p['empirical_fpr_cap'],int(sum(y==0))) for y,s in data.values())
                    if ok:feasible.append(t)
                self.assertEqual(p['threshold'],min(feasible))
    def test_invalid_scores_labels_and_sources(self):
        for y,s in [(np.array([0,1]),np.array([np.nan,.5])),(np.array([0,1]),np.array([.2,1.1])),(np.array([0,0]),np.array([.2,.8])),(np.array([False,True]),np.array([.2,.8]))]:
            with self.assertRaises(base.TrainingError):study.validate_arrays(y,s)
        with self.assertRaises(base.TrainingError):study.joint_points({})

class ThresholdIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.FeatureExperimentTests();self.fx.setUp();self.fx.run_experiment();self.f=self.fx.f
        self.packet=self.f.root/'scores';self.output=self.f.root/'thresholds'
    def tearDown(self):self.fx.tearDown()
    def collect(self):
        with patch.object(collect.ex.dg.ms.ev.intake,'LOCK',self.f.lock):
            return collect.collect(self.f.fixture.dataset,self.f.external,self.f.baseline,self.f.primary,self.fx.fx.f.output,self.fx.output,self.packet,1)
    def test_full_collection_and_analysis_offline_no_final_sets_or_pickle(self):
        original=Path.open
        def guard(p,*a,**kw):
            if p.name in ['test.jsonl','holdout.jsonl','cases.jsonl','decisions-template.jsonl']:raise AssertionError('Forbidden data')
            return original(p,*a,**kw)
        with patch.object(Path,'open',guard),patch('socket.socket',side_effect=AssertionError('Network')),patch.object(collect.ex.dg.ms.ev.joblib,'load',side_effect=AssertionError('Pickle')):
            r=self.collect()
            self.assertTrue(r['reproduced_g18'])
            with patch.object(base,'estimators',side_effect=AssertionError('Analyzer must not fit')):report=study.analyze(self.packet,self.output)
        self.assertIsNone(report['deployment_threshold']);self.assertFalse(report['model_activated'])
        values=list(rows(self.packet/'validation-scores.jsonl'))
        self.assertEqual(len(values),sum(s['rows'] for s in r['sources'].values()))
        self.assertNotIn('https://',(self.packet/'validation-scores.jsonl').read_text())
        for result in report['results'].values():
            for p in result['joint_cap_points']:
                for source,m in p['sources'].items():self.assertLessEqual(m['confusion_matrix']['fp'],p['allowed_false_positives'][source])
    def test_g18_hash_mismatch_stops_before_fit(self):
        with (self.fx.output/'report.json').open('a') as f:f.write(' ')
        with patch.object(collect.ex,'fit_scenario',side_effect=AssertionError('Fit')):
            with self.assertRaises(base.TrainingError):self.collect()
        self.assertFalse(self.packet.exists())
    def test_reproduction_failure_publishes_no_scores(self):
        with patch.object(collect.ex.dg,'reproduce',side_effect=base.TrainingError('Mismatch')):
            with self.assertRaises(base.TrainingError):self.collect()
        self.assertFalse(self.packet.exists())
    def test_score_corruption_rejected(self):
        self.collect()
        with (self.packet/'validation-scores.jsonl').open('a') as f:f.write('{}\n')
        with self.assertRaises(base.TrainingError):study.analyze(self.packet,self.output)
        self.assertFalse(self.output.exists())
    def test_rehashed_duplicate_and_boolean_labels_rejected(self):
        self.collect();p=self.packet/'validation-scores.jsonl';original=list(rows(p))
        for kind in ['duplicate','boolean']:
            values=[{**v} for v in original]
            if kind=='duplicate':values[1]['sample_id']=values[0]['sample_id']
            else:values[0]['y']=True
            write_rows(p,values);m=base.load_json(self.packet/'manifest.json');m['files'][p.name]=base.sha(p);base.write_json(self.packet/'manifest.json',m)
            with self.assertRaises(base.TrainingError):study.analyze(self.packet,self.output)
    def test_outputs_cannot_be_overwritten(self):
        self.packet.mkdir()
        with self.assertRaises(base.TrainingError):self.collect()
        self.output.mkdir()
        with self.assertRaises(base.TrainingError):study.analyze(self.packet,self.output)
    def test_changed_protocol_rejected(self):
        p=self.f.root/'bad-protocol.json';r=base.load_json(study.PROTOCOL);r['empirical_fpr_caps']=['0.9'];base.write_json(p,r)
        with patch.object(study,'PROTOCOL',p):
            with self.assertRaises(base.TrainingError):study.analyze(self.packet,self.output)

if __name__=='__main__':unittest.main()
