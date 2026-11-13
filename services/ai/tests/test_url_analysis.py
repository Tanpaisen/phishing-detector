import os
import unittest
from unittest.mock import patch

os.environ["AI_SERVICE_TOKEN"] = "test-only-token-not-for-production-123456"

from fastapi.testclient import TestClient
from main import app
from url_analysis import URLInputError, inspect_url


class URLAnalysisTests(unittest.TestCase):
    def test_preserves_case_encoding_and_empty_delimiters(self):
        result = inspect_url("  HTTPS://EXAMPLE.COM.:443/Login?A=%2F&A=2#Token  ")
        self.assertEqual(result["url"]["normalized_url"], "https://example.com:443/Login?A=%2F&A=2#Token")
        for tail in ("?", "#", "?#", "/%252F?q=%252F#A"):
            self.assertEqual(inspect_url("https://example.com" + tail)["url"]["normalized_url"], "https://example.com" + tail)

    def test_psl_and_actual_domain(self):
        cases = {
            "https://login.example.co.uk": ("example.co.uk", "login"),
            "https://bank.com.attacker.com/login/bank.com": ("attacker.com", "bank.com"),
            "https://alice.github.io": ("alice.github.io", ""),
        }
        for url, (domain, subdomain) in cases.items():
            with self.subTest(url=url):
                data = inspect_url(url)["url"]
                self.assertEqual(data["registered_domain"], domain)
                self.assertEqual(data["subdomain"], subdomain)

    def test_idna_equivalence(self):
        a = inspect_url("https://bücher.de/ĐăngNhập")
        b = inspect_url("https://xn--bcher-kva.de/ĐăngNhập")
        self.assertEqual(a["url"]["normalized_url"], b["url"]["normalized_url"])
        self.assertEqual(a["url"]["hostname_unicode"], "bücher.de")
        self.assertTrue(a["features"]["has_unicode_input"])
        self.assertTrue(a["features"]["has_punycode_hostname"])

    def test_unicode_path_is_not_unicode_hostname(self):
        result = inspect_url("https://example.com/đăng-nhập")
        self.assertTrue(result["features"]["has_unicode_input"])
        self.assertFalse(result["features"]["has_unicode_hostname"])
        self.assertFalse(result["features"]["has_format_characters_in_hostname"])

    def test_preserves_hostname_before_idna_mapping(self):
        host = "exam\u200bple.com"
        result = inspect_url("https://" + host)
        self.assertEqual(result["url"]["hostname_ascii"], "example.com")
        self.assertEqual(result["url"]["hostname_input"], host)
        self.assertTrue(result["features"]["has_format_characters_in_hostname"])

    def test_public_ips(self):
        for url in ("https://8.8.8.8/path", "https://[2606:4700:4700::1111]:443/?"):
            with self.subTest(url=url):
                data = inspect_url(url)["url"]
                self.assertTrue(data["is_ip"])
                self.assertIsNone(data["registered_domain"])

    def test_rejects_invalid_or_unsupported_input(self):
        cases = [
            "", " " * 4, "https://example.com/" + "a" * 4096,
            "example.com", "ftp://example.com", "javascript:alert(1)",
            "https:///path", "https://user:password@example.com",
            "https://example.com\\@evil.com", "https://exa\nmple.com",
            "\thttps://example.com", "https://example.com/a b", "https://example.com/\x00",
            "https://example.com/%GG", "https://example.com/%",
            "https://%65xample.com", "https://bad..com", "https://-bad.com",
            "https://example.com:", "https://example.com:0", "https://example.com:65536",
            "https://example.com:abc", "https://example.com:１２３",
            "https://[::1]suffix", "https://[fe80::1%25eth0]", "https://[8.8.8.8]",
            "https://localhost", "https://server.local", "https://com",
            "https://127.0.0.1", "https://192.168.1.1", "https://100.64.0.1",
            "https://224.0.0.1", "https://[::1]", "https://[::ffff:127.0.0.1]",
            "https://127.1", "https://2130706433", "https://0x7f000001",
            "https://0177.0.0.1", "https://１２７.０.０.１",
        ]
        for url in cases:
            with self.subTest(url=url), self.assertRaises(URLInputError):
                inspect_url(url)

    def test_offline_first_use(self):
        # Fresh extractor ensures the initial PSL load cannot hide a network call.
        import tldextract
        extractor = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=(), include_psl_private_domains=True)
        with patch("url_analysis.EXTRACTOR", extractor), \
             patch("socket.getaddrinfo", side_effect=AssertionError("DNS forbidden")), \
             patch("socket.socket.connect", side_effect=AssertionError("Network forbidden")), \
             patch("requests.sessions.Session.request", side_effect=AssertionError("HTTP forbidden")):
            result = inspect_url("https://login.example.co.uk/path")
            self.assertEqual(result["url"]["registered_domain"], "example.co.uk")
            self.assertNotIn("risk_level", result)
            self.assertNotIn("model_score", result)


class APIContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {"X-Service-Token": os.environ["AI_SERVICE_TOKEN"]}

    def test_authentication(self):
        for headers in ({}, {"X-Service-Token": "wrong"}):
            self.assertEqual(self.client.post("/internal/v1/url/inspect", json={"url": "https://example.com"}, headers=headers).status_code, 401)

    def test_success_without_model(self):
        response = self.client.post("/internal/v1/url/inspect", json={"url": "https://example.com"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["model_loaded"])
        self.assertEqual(self.client.get("/internal/v1/ready", headers=self.headers).status_code, 503)

    def test_no_sensitive_input_in_errors(self):
        for body in ({"url": "https://user:SECRET@example.com"}, {"url": 123, "otp": "SECRET"}, {"url": ["SECRET"]}):
            with self.subTest(body=body):
                response = self.client.post("/internal/v1/url/inspect", json=body, headers=self.headers)
                self.assertEqual(response.status_code, 422)
                self.assertNotIn("SECRET", response.text)


if __name__ == "__main__":
    unittest.main()
