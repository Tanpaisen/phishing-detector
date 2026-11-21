from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import test_multisource_diagnostics as fixture
import train_url_feature_experiments as ex
from common import base
from phishing_core import url_feature_extensions as f

class ExtensionTests(unittest.TestCase):
    def test_host_psl_www_and_ratios(self):
        host='www.a1-b.example.co.uk';r=f.extract_all('https://'+host+'/a',base.inspect_url)
        self.assertEqual(r['baseline_plus_hostname'][-5:], [1.,1.,7.,1/len(host),1/len(host)])
        r=f.extract_all('https://www.blogspot.com/',base.inspect_url)
        self.assertEqual(r['baseline_plus_hostname'][-5:-3],[0.,0.])
        r=f.extract_all('https://www.tenant.blogspot.com/',base.inspect_url)
        self.assertEqual(r['baseline_plus_hostname'][-5:-3],[1.,0.])
    def test_path_query_no_decoding_or_empty_fields(self):
        path='/a//b%2Fc/';query='x=%26&flag&x=2&&'
        r=f.extract_all('https://example.com'+path+'?'+query+'#ignored',base.inspect_url)
        self.assertEqual(r['baseline_plus_path_query'][-5:],[2.,5.,3.,3/len(path),3/len(query)])
        r=f.extract_all('https://example.com/?a=1;b=2',base.inspect_url)
        self.assertEqual(r['baseline_plus_path_query'][-5:],[0.,0.,1.,0.,0.])
    def test_ip_empty_components_and_idna(self):
        for host in ['8.8.8.8','[2606:4700:4700::1111]']:
            r=f.extract_all('https://'+host,base.inspect_url)
            self.assertEqual(r['baseline_plus_hostname'][-5:],[0.]*5)
            self.assertEqual(r['baseline_plus_path_query'][-5:],[0.]*5)
        a=f.extract_all('https://www.bücher.de/',base.inspect_url)
        b=f.extract_all('https://www.xn--bcher-kva.de/',base.inspect_url)
        self.assertEqual(a['baseline_plus_hostname'][-5:],b['baseline_plus_hostname'][-5:])
    def test_baseline_preserved_offline_and_no_mutation(self):
        raw=' https://WWW.Example.com/A%2fb?q=1#X '
        inspected=base.inspect_url(raw)
        import copy
        original=copy.deepcopy(inspected)
        with patch('socket.socket',side_effect=AssertionError('Network')):
            r=f.extract_all(raw,lambda _:inspected)
        self.assertEqual(inspected,original)
        self.assertEqual(r['baseline'],base.extract_features(raw,base.inspect_url))
        for name in f.SCENARIOS:self.assertEqual(r[name][:18],r['baseline'])
        self.assertEqual([len(r[k]) for k in f.SCENARIOS],[18,23,23])
    def test_invalid_input_version_and_scenario(self):
        with self.assertRaises(ValueError):f.extract_all('javascript:alert(1)',base.inspect_url)
        ins=base.inspect_url('https://example.com');ins['preprocessing_version']='unknown'
        with self.assertRaises(ValueError):f.extract_all('https://example.com',lambda _:ins)
        with self.assertRaises(ValueError):f.schema('combined')
    def test_paired_changes_account_for_fp_fn(self):
        y=np.array([0,0,1,1]);b=np.array([.8,.2,.2,.8]);n=np.array([.2,.8,.8,.2])
        self.assertEqual(ex.paired_changes(y,b,n),{'corrected_fp':1,'introduced_fp':1,'corrected_fn':1,'introduced_fn':1})
    def test_test_split_refused(self):
        with self.assertRaises(base.TrainingError):ex.load_base(Path('/does-not-exist'),'test',{})

class FeatureExperimentTests(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.DiagnosticTests();self.fx.setUp();self.f=self.fx.f.f
        self.output=self.f.root/'features'
    def tearDown(self):self.fx.tearDown()
    def run_experiment(self):
        with patch.object(ex.dg.ms.ev.intake,'LOCK',self.f.lock):
            return ex.experiment(self.f.fixture.dataset,self.f.external,self.f.baseline,self.f.primary,self.fx.f.output,self.output,1)
    def test_full_offline_fit_inputs_and_baseline_reproduction(self):
        orig_open=Path.open;original_fit=ex.fit_scenario;calls=[]
        def guard(p,*a,**kw):
            if p.name in ['test.jsonl','holdout.jsonl','cases.jsonl']:raise AssertionError('Forbidden file read')
            return orig_open(p,*a,**kw)
        def fit(x,y,w,e,workers):
            calls.append((x.copy(),y.copy(),w.copy()))
            return original_fit(x,y,w,e,workers)
        with patch.object(Path,'open',guard),patch('socket.socket',side_effect=AssertionError('Network')),patch.object(ex.dg.ms.ev.joblib,'load',side_effect=AssertionError('Pickle')),patch.object(ex,'fit_scenario',side_effect=fit):
            r=self.run_experiment()
        self.assertTrue(r['baseline_reproduced_g16']);self.assertFalse(r['model_exported'])
        self.assertEqual([a[0].shape[1] for a in calls],[18,23,23])
        self.assertEqual(len(calls[0][1]),r['splits']['phiusiil_train']['rows']+r['splits']['external_train']['rows'])
        for x,y,w in calls:
            np.testing.assert_array_equal(x[:,:18],calls[0][0]);np.testing.assert_array_equal(y,calls[0][1]);np.testing.assert_array_equal(w,calls[0][2])
        self.assertNotIn('https://external',(self.output/'report.json').read_text())
    def test_checksum_failure_before_fit(self):
        with (self.f.external/'development.jsonl').open('a') as stream:stream.write('{}\n')
        with patch.object(ex,'fit_scenario',side_effect=AssertionError('Fit called')):
            with self.assertRaises(base.TrainingError):self.run_experiment()
        self.assertFalse(self.output.exists())
    def test_baseline_mismatch_stops_extensions_and_publication(self):
        with patch.object(ex.dg,'reproduce',side_effect=base.TrainingError('Mismatch')),patch.object(ex,'fit_scenario',wraps=ex.fit_scenario) as fit:
            with self.assertRaises(base.TrainingError):self.run_experiment()
            self.assertEqual(fit.call_count,1)
        self.assertFalse(self.output.exists())
    def test_no_overwrite(self):
        self.output.mkdir()
        with self.assertRaises(base.TrainingError):self.run_experiment()
    def test_changed_protocol_refused(self):
        p=self.f.root/'protocol.json';v=base.load_json(ex.PROTOCOL);v['threshold']=.8;base.write_json(p,v)
        with patch.object(ex,'PROTOCOL',p),patch.object(ex,'fit_scenario',side_effect=AssertionError('Fit')):
            with self.assertRaises(base.TrainingError):self.run_experiment()

if __name__=='__main__':unittest.main()
