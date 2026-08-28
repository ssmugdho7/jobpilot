"""Tests for Facebook Graph API scraper."""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import load_fb_post_search_config
from app.scrapers.fb_graph_api import (
    _get_access_token,
    _search_pages,
    _get_page_posts,
    _is_job_post,
    _has_bd_location,
    _extract_title,
    _extract_location,
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
        self.assertIn("search_queries", cfg)
        self.assertIsInstance(cfg["search_queries"], list)

    def test_config_search_queries_are_strings(self):
        cfg = load_fb_post_search_config()
        for query in cfg.get("search_queries", []):
            self.assertIsInstance(query, str)
            self.assertTrue(len(query) > 0)


class TestAccessToken(unittest.TestCase):
    @patch.dict(os.environ, {"FACEBOOK_ACCESS_TOKEN": "test-token-123"})
    def test_get_token_from_env(self):
        token = _get_access_token()
        self.assertEqual(token, "test-token-123")

    @patch.dict(os.environ, {"FACEBOOK_ACCESS_TOKEN": ""})
    @patch("app.scrapers.fb_graph_api.load_fb_post_search_config")
    def test_get_token_from_config(self, mock_cfg):
        mock_cfg.return_value = {"access_token": "config-token-456"}
        token = _get_access_token()
        self.assertEqual(token, "config-token-456")

    @patch.dict(os.environ, {"FACEBOOK_ACCESS_TOKEN": ""})
    @patch("app.scrapers.fb_graph_api.load_fb_post_search_config")
    def test_get_token_empty_when_not_set(self, mock_cfg):
        mock_cfg.return_value = {}
        token = _get_access_token()
        self.assertEqual(token, "")


class TestJobPostDetection(unittest.TestCase):
    def test_is_job_post_with_hiring(self):
        self.assertTrue(_is_job_post("We are hiring a web developer in Dhaka"))

    def test_is_job_post_with_vacancy(self):
        self.assertTrue(_is_job_post("Vacancy for software engineer"))

    def test_is_job_post_with_job_keyword(self):
        self.assertTrue(_is_job_post("Job opening at our Dhaka office"))

    def test_is_not_job_post(self):
        self.assertFalse(_is_job_post("Happy birthday to our team!"))

    def test_is_not_job_post_empty(self):
        self.assertFalse(_is_job_post(""))


class TestLocationDetection(unittest.TestCase):
    def test_has_bd_location_dhaka(self):
        self.assertTrue(_has_bd_location("Position in Dhaka, Bangladesh"))

    def test_has_bd_location_chittagong(self):
        self.assertTrue(_has_bd_location("Office located in Chittagong"))

    def test_has_bd_location_bangladesh(self):
        self.assertTrue(_has_bd_location("Remote position in Bangladesh"))

    def test_no_bd_location(self):
        self.assertFalse(_has_bd_location("Office in Mumbai, India"))


class TestTitleExtraction(unittest.TestCase):
    def test_title_from_first_line(self):
        title = _extract_title("Hiring web developer\nApply now")
        self.assertEqual(title, "Hiring web developer")

    def test_title_truncates_long(self):
        long_title = "A" * 150
        title = _extract_title(long_title)
        self.assertTrue(len(title) <= 100)

    def test_title_fallback(self):
        title = _extract_title("")
        self.assertEqual(title, "Facebook Job Post")


class TestLocationExtraction(unittest.TestCase):
    def test_location_dhaka(self):
        loc = _extract_location("Position in Dhaka")
        self.assertIn("Dhaka", loc)

    def test_location_bangladesh(self):
        loc = _extract_location("Remote job in Bangladesh")
        self.assertIn("Bangladesh", loc)

    def test_location_default(self):
        loc = _extract_location("Some post without location")
        self.assertEqual(loc, "Bangladesh")


class TestSearchPages(unittest.TestCase):
    @patch("app.scrapers.fb_graph_api.requests.get")
    def test_search_returns_pages(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "123", "name": "Tech Jobs BD", "about": "Job posts"}
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        pages = _search_pages("jobs bangladesh", "test-token")
        self.assertIsInstance(pages, list)
        self.assertTrue(len(pages) > 0)
        self.assertEqual(pages[0]["id"], "123")

    @patch("app.scrapers.fb_graph_api.requests.get")
    def test_search_returns_empty_on_error(self, mock_get):
        mock_get.side_effect = Exception("API error")
        pages = _search_pages("test", "token")
        self.assertEqual(pages, [])


class TestGetPagePosts(unittest.TestCase):
    @patch("app.scrapers.fb_graph_api.requests.get")
    def test_get_posts_returns_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"id": "post_1", "message": "Hiring developer", "created_time": "2026-08-28T10:00:00+0000"}
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        posts = _get_page_posts("page_123", "token")
        self.assertIsInstance(posts, list)
        self.assertTrue(len(posts) > 0)

    @patch("app.scrapers.fb_graph_api.requests.get")
    def test_get_posts_returns_empty_on_error(self, mock_get):
        mock_get.side_effect = Exception("API error")
        posts = _get_page_posts("page_123", "token")
        self.assertEqual(posts, [])


class TestGetEnabled(unittest.TestCase):
    @patch("app.scrapers.fb_graph_api.is_fb_post_search_enabled")
    def test_returns_true_when_enabled(self, mock_enabled):
        mock_enabled.return_value = True
        self.assertTrue(get_enabled())

    @patch("app.scrapers.fb_graph_api.is_fb_post_search_enabled")
    def test_returns_false_when_disabled(self, mock_enabled):
        mock_enabled.return_value = False
        self.assertFalse(get_enabled())


class TestFetchFbPosts(unittest.TestCase):
    @patch("app.scrapers.fb_graph_api.is_fb_post_search_enabled", return_value=False)
    def test_returns_empty_when_disabled(self, _mock):
        results = fetch_fb_posts(verbose=False)
        self.assertEqual(results, [])

    @patch("app.scrapers.fb_graph_api.is_fb_post_search_enabled", return_value=True)
    @patch("app.scrapers.fb_graph_api._get_access_token", return_value="")
    def test_returns_empty_without_token(self, _mock_token, _mock_enabled):
        results = fetch_fb_posts(verbose=False)
        self.assertEqual(results, [])

    @patch("app.scrapers.fb_graph_api.is_fb_post_search_enabled", return_value=True)
    @patch("app.scrapers.fb_graph_api._get_access_token", return_value="test-token")
    @patch("app.scrapers.fb_graph_api.load_fb_post_search_config")
    @patch("app.scrapers.fb_graph_api._search_pages")
    @patch("app.scrapers.fb_graph_api._get_page_posts")
    def test_returns_job_dicts(self, mock_posts, mock_search, mock_cfg, _mock_token, _mock_enabled):
        mock_cfg.return_value = {
            "search_queries": ["jobs bangladesh"],
            "max_pages_per_run": 1,
            "posts_per_page": 5,
            "max_age_days": 3,
        }
        mock_search.return_value = [{"id": "page1", "name": "Tech Jobs BD"}]
        mock_posts.return_value = [
            {"id": "post1", "message": "Hiring web developer in Dhaka", "created_time": "2026-08-28T10:00:00+0000", "link": ""}
        ]

        results = fetch_fb_posts(verbose=False)
        self.assertIsInstance(results, list)
        if results:
            job = results[0]
            self.assertEqual(job["source_site"], "facebook_graph_api")
            self.assertIn("posting_url", job)
            self.assertIn("title", job)

    @patch("app.scrapers.fb_graph_api.is_fb_post_search_enabled", return_value=True)
    @patch("app.scrapers.fb_graph_api._get_access_token", return_value="test-token")
    @patch("app.scrapers.fb_graph_api.load_fb_post_search_config")
    @patch("app.scrapers.fb_graph_api._search_pages")
    @patch("app.scrapers.fb_graph_api._get_page_posts")
    def test_deduplicates_by_post_id(self, mock_posts, mock_search, mock_cfg, _mock_token, _mock_enabled):
        mock_cfg.return_value = {
            "search_queries": ["q1", "q2"],
            "max_pages_per_run": 2,
            "posts_per_page": 5,
            "max_age_days": 3,
        }
        mock_search.return_value = [
            {"id": "page1", "name": "Jobs BD"},
            {"id": "page2", "name": "Hiring BD"},
        ]
        # Same post from both pages
        mock_posts.return_value = [
            {"id": "post1", "message": "Hiring developer in Bangladesh", "created_time": "2026-08-28T10:00:00+0000", "link": ""}
        ]

        results = fetch_fb_posts(verbose=False)
        # Should deduplicate
        post_ids = [r.get("posting_url") for r in results]
        self.assertEqual(len(post_ids), len(set(post_ids)))


if __name__ == "__main__":
    unittest.main()
