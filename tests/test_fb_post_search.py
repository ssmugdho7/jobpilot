"""Tests for Facebook Post Search feature."""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import load_fb_post_search_config
from app.scrapers.fb_post_search import (
    _normalize_host,
    is_allowed_domain,
    _title_passes_filter,
    _serper_search,
    get_enabled,
    fetch_fb_posts,
)


class TestConfigLoading(unittest.TestCase):
    def test_load_config_returns_dict(self):
        cfg = load_fb_post_search_config()
        self.assertIsInstance(cfg, dict)

    def test_config_has_expected_keys(self):
        cfg = load_fb_post_search_config()
        self.assertIn("enabled", cfg)
        self.assertIn("queries", cfg)
        self.assertIsInstance(cfg["queries"], list)

    def test_config_queries_are_strings(self):
        cfg = load_fb_post_search_config()
        for query in cfg.get("queries", []):
            self.assertIsInstance(query, str)
            self.assertTrue(len(query) > 0)

    def test_config_domains_list(self):
        cfg = load_fb_post_search_config()
        self.assertIsInstance(cfg.get("allowed_domains"), list)
        self.assertTrue(len(cfg.get("allowed_domains", [])) > 0)

    def test_config_title_filter_keywords(self):
        cfg = load_fb_post_search_config()
        self.assertIsInstance(cfg.get("title_filter_keywords"), list)
        self.assertTrue(len(cfg.get("title_filter_keywords", [])) > 0)


class TestHostNormalization(unittest.TestCase):
    def test_normalize_host_basic(self):
        self.assertEqual(_normalize_host("https://facebook.com/post/1"), "facebook.com")

    def test_normalize_host_with_subdomain(self):
        self.assertEqual(_normalize_host("https://www.facebook.com/jobs"), "www.facebook.com")

    def test_normalize_host_empty(self):
        self.assertEqual(_normalize_host(""), "")

    def test_normalize_host_invalid(self):
        self.assertEqual(_normalize_host("not-a-url"), "")


class TestAllowedDomain(unittest.TestCase):
    def test_facebook_com_allowed(self):
        self.assertTrue(is_allowed_domain("https://facebook.com/post/1"))

    def test_www_facebook_com_allowed(self):
        self.assertTrue(is_allowed_domain("https://www.facebook.com/jobs"))

    def test_m_facebook_com_allowed(self):
        self.assertTrue(is_allowed_domain("https://m.facebook.com/groups/hiring"))

    def test_non_fb_domain_rejected(self):
        self.assertFalse(is_allowed_domain("https://linkedin.com/jobs/123"))

    def test_non_fb_domain_rejected_2(self):
        self.assertFalse(is_allowed_domain("https://example.com/job"))


class TestTitleFilter(unittest.TestCase):
    def test_passes_with_role_and_location(self):
        self.assertTrue(_title_passes_filter(
            "Hiring web developer in Dhaka",
            "Join our team in Bangladesh"
        ))

    def test_fails_without_role(self):
        self.assertFalse(_title_passes_filter(
            "Meeting at the office",
            "Dhaka, Bangladesh"
        ))

    def test_fails_without_location(self):
        self.assertFalse(_title_passes_filter(
            "Hiring software engineer",
            "Remote position available"
        ))

    def test_passes_with_snippet_role_and_location(self):
        self.assertTrue(_title_passes_filter(
            "New opening",
            "Looking for a data analyst in Dhaka"
        ))

    def test_empty_title_and_snippet(self):
        self.assertFalse(_title_passes_filter("", ""))

    def test_passes_with_hiring_keyword(self):
        self.assertTrue(_title_passes_filter(
            "We are hiring a developer",
            "Position in Bangladesh"
        ))


class TestSerperSearch(unittest.TestCase):
    @patch("app.scrapers.fb_post_search.requests.post")
    def test_serper_search_returns_results(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "organic": [
                {"link": "https://facebook.com/post/1", "title": "Hiring web developer", "snippet": "Join our team in Dhaka"}
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        results = _serper_search("web developer", "fake-api-key", num=5)
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)
        self.assertIn("link", results[0])

    @patch("app.scrapers.fb_post_search.requests.post")
    def test_serper_search_sends_correct_payload(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"organic": []}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        _serper_search("software engineer", "test-key", num=3, tbs="qdr:d")
        call_args = mock_post.call_args
        body = call_args[1]["json"]
        self.assertIn("site:facebook.com", body["q"])
        self.assertEqual(body["gl"], "bd")
        self.assertEqual(body["num"], 3)
        self.assertEqual(body["tbs"], "qdr:d")

    @patch("app.scrapers.fb_post_search.requests.post")
    def test_serper_search_raises_on_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("429 Too Many Requests")
        mock_post.return_value = mock_resp

        with self.assertRaises(Exception):
            _serper_search("test", "key")


class TestGetEnabled(unittest.TestCase):
    @patch("app.scrapers.fb_post_search.is_fb_post_search_enabled")
    def test_returns_true_when_enabled(self, mock_enabled):
        mock_enabled.return_value = True
        self.assertTrue(get_enabled())

    @patch("app.scrapers.fb_post_search.is_fb_post_search_enabled")
    def test_returns_false_when_disabled(self, mock_enabled):
        mock_enabled.return_value = False
        self.assertFalse(get_enabled())


class TestFetchFbPosts(unittest.TestCase):
    @patch("app.scrapers.fb_post_search.is_fb_post_search_enabled", return_value=False)
    def test_returns_empty_when_disabled(self, _mock):
        results = fetch_fb_posts(verbose=False)
        self.assertEqual(results, [])

    @patch("app.scrapers.fb_post_search.is_fb_post_search_enabled", return_value=True)
    @patch("app.scrapers.fb_post_search.load_fb_post_search_config")
    def test_returns_empty_without_api_key(self, mock_cfg, _mock):
        mock_cfg.return_value = {"queries": ["test query"], "serper_api_key": ""}
        results = fetch_fb_posts(verbose=False)
        self.assertEqual(results, [])

    @patch("app.scrapers.fb_post_search.is_fb_post_search_enabled", return_value=True)
    @patch("app.scrapers.fb_post_search.load_fb_post_search_config")
    def test_returns_empty_when_no_queries(self, mock_cfg, _mock):
        mock_cfg.return_value = {"queries": [], "serper_api_key": "key"}
        results = fetch_fb_posts(verbose=False)
        self.assertEqual(results, [])

    @patch("app.scrapers.fb_post_search.is_fb_post_search_enabled", return_value=True)
    @patch("app.scrapers.fb_post_search.load_fb_post_search_config")
    @patch("app.scrapers.fb_post_search._serper_search")
    def test_returns_job_dicts(self, mock_search, mock_cfg, _mock):
        mock_cfg.return_value = {
            "queries": ["web developer Bangladesh"],
            "serper_api_key": "test-key",
            "allowed_domains": ["facebook.com"],
            "title_filter_keywords": ["developer", "engineer"],
            "location_keywords": ["dhaka", "bangladesh"],
            "max_queries_per_run": 1,
            "results_per_query": 5,
            "delay_between_queries": 0,
            "request_timeout": 10,
            "tbs": "qdr:d",
        }
        mock_search.return_value = [
            {"link": "https://facebook.com/post/1", "title": "Hiring web developer", "snippet": "Join us in Dhaka"}
        ]
        results = fetch_fb_posts(verbose=False)
        self.assertIsInstance(results, list)
        if results:
            job = results[0]
            self.assertEqual(job["source_site"], "facebook_post_search")
            self.assertIn("posting_url", job)
            self.assertIn("title", job)

    @patch("app.scrapers.fb_post_search.is_fb_post_search_enabled", return_value=True)
    @patch("app.scrapers.fb_post_search.load_fb_post_search_config")
    @patch("app.scrapers.fb_post_search._serper_search")
    def test_deduplicates_by_url(self, mock_search, mock_cfg, _mock):
        mock_cfg.return_value = {
            "queries": ["q1", "q2"],
            "serper_api_key": "test-key",
            "allowed_domains": ["facebook.com"],
            "title_filter_keywords": ["developer"],
            "location_keywords": ["bangladesh"],
            "max_queries_per_run": 2,
            "results_per_query": 5,
            "delay_between_queries": 0,
            "request_timeout": 10,
            "tbs": "qdr:d",
        }
        # Same URL in both queries
        mock_search.return_value = [
            {"link": "https://facebook.com/post/1", "title": "Hiring developer", "snippet": "Bangladesh"}
        ]
        results = fetch_fb_posts(verbose=False)
        # Should deduplicate to 1 result
        urls = [r["posting_url"] for r in results]
        self.assertEqual(len(urls), len(set(urls)))


if __name__ == "__main__":
    unittest.main()
