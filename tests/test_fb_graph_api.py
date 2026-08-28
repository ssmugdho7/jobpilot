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
        self.assertIn("pages", cfg)
        self.assertIsInstance(cfg["pages"], list)

    def test_config_has_pages(self):
        cfg = load_fb_post_search_config()
        self.assertTrue(len(cfg["pages"]) > 0)

    def test_config_pages_have_required_fields(self):
        cfg = load_fb_post_search_config()
        for page in cfg.get("pages", []):
            self.assertIn("id", page)
            self.assertIn("name", page)
            self.assertIn("type", page)


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
        job_keywords = ["hiring", "vacancy", "job", "developer", "software engineer"]
        self.assertTrue(_is_job_post("We are hiring a web developer in Dhaka", job_keywords))

    def test_is_job_post_with_vacancy(self):
        job_keywords = ["hiring", "vacancy", "job", "developer"]
        self.assertTrue(_is_job_post("Vacancy for software engineer", job_keywords))

    def test_is_not_job_post(self):
        job_keywords = ["hiring", "vacancy", "job", "developer"]
        self.assertFalse(_is_job_post("Happy birthday to our team!", job_keywords))

    def test_is_not_job_post_empty(self):
        job_keywords = ["hiring", "vacancy", "job", "developer"]
        self.assertFalse(_is_job_post("", job_keywords))


class TestLocationDetection(unittest.TestCase):
    def test_has_bd_location_dhaka(self):
        location_keywords = ["dhaka", "bangladesh", "chittagong"]
        self.assertTrue(_has_bd_location("Position in Dhaka, Bangladesh", location_keywords))

    def test_has_bd_location_bangladesh(self):
        location_keywords = ["dhaka", "bangladesh", "chittagong"]
        self.assertTrue(_has_bd_location("Remote job in Bangladesh", location_keywords))

    def test_no_bd_location(self):
        location_keywords = ["dhaka", "bangladesh", "chittagong"]
        self.assertFalse(_has_bd_location("Office in Mumbai, India", location_keywords))


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
        location_keywords = ["dhaka", "bangladesh", "chittagong"]
        loc = _extract_location("Position in Dhaka", location_keywords)
        self.assertIn("Dhaka", loc)

    def test_location_bangladesh(self):
        location_keywords = ["dhaka", "bangladesh", "chittagong"]
        loc = _extract_location("Remote job in Bangladesh", location_keywords)
        self.assertIn("Bangladesh", loc)

    def test_location_default(self):
        location_keywords = ["dhaka", "bangladesh", "chittagong"]
        loc = _extract_location("Some post without location", location_keywords)
        self.assertEqual(loc, "Bangladesh")


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

        posts = _get_page_posts("page_123", "token", "page")
        self.assertIsInstance(posts, list)
        self.assertTrue(len(posts) > 0)

    @patch("app.scrapers.fb_graph_api.requests.get")
    def test_get_posts_group_uses_feed(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": []}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        _get_page_posts("group_123", "token", "group")
        call_url = mock_get.call_args[0][0]
        self.assertIn("/feed", call_url)

    @patch("app.scrapers.fb_graph_api.requests.get")
    def test_get_posts_returns_empty_on_error(self, mock_get):
        mock_get.side_effect = Exception("API error")
        posts = _get_page_posts("page_123", "token", "page")
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
    @patch("app.scrapers.fb_graph_api._get_page_posts")
    def test_returns_job_dicts(self, mock_posts, mock_cfg, _mock_token, _mock_enabled):
        mock_cfg.return_value = {
            "pages": [{"id": "page1", "name": "Tech Jobs BD", "type": "page"}],
            "job_keywords": ["hiring", "developer"],
            "location_keywords": ["dhaka", "bangladesh"],
            "max_age_days": 3,
            "posts_per_page": 5,
        }
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
    @patch("app.scrapers.fb_graph_api._get_page_posts")
    def test_deduplicates_by_post_id(self, mock_posts, mock_cfg, _mock_token, _mock_enabled):
        mock_cfg.return_value = {
            "pages": [
                {"id": "page1", "name": "Jobs BD", "type": "page"},
                {"id": "page2", "name": "Hiring BD", "type": "page"},
            ],
            "job_keywords": ["hiring", "developer"],
            "location_keywords": ["bangladesh"],
            "max_age_days": 3,
            "posts_per_page": 5,
        }
        # Same post from both pages
        mock_posts.return_value = [
            {"id": "post1", "message": "Hiring developer in Bangladesh", "created_time": "2026-08-28T10:00:00+0000", "link": ""}
        ]

        results = fetch_fb_posts(verbose=False)
        # Should deduplicate
        post_ids = [r.get("posting_url") for r in results]
        self.assertEqual(len(post_ids), len(set(post_ids)))

    @patch("app.scrapers.fb_graph_api.is_fb_post_search_enabled", return_value=True)
    @patch("app.scrapers.fb_graph_api._get_access_token", return_value="test-token")
    @patch("app.scrapers.fb_graph_api.load_fb_post_search_config")
    @patch("app.scrapers.fb_graph_api._get_page_posts")
    def test_filters_non_job_posts(self, mock_posts, mock_cfg, _mock_token, _mock_enabled):
        mock_cfg.return_value = {
            "pages": [{"id": "page1", "name": "Tech Jobs BD", "type": "page"}],
            "job_keywords": ["hiring", "developer"],
            "location_keywords": ["bangladesh"],
            "max_age_days": 3,
            "posts_per_page": 5,
        }
        mock_posts.return_value = [
            {"id": "post1", "message": "Happy birthday team!", "created_time": "2026-08-28T10:00:00+0000", "link": ""},
            {"id": "post2", "message": "Hiring developer in Bangladesh", "created_time": "2026-08-28T11:00:00+0000", "link": ""},
        ]

        results = fetch_fb_posts(verbose=False)
        # Should only keep the job post
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
