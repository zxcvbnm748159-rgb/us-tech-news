import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import fetch_market_data, fetch_news


class MarketDataTests(unittest.TestCase):
    def test_fetch_stock_data_calculates_quote_and_builds_timeframes(self):
        now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        history = [
            {"time": int((now - timedelta(days=offset)).timestamp()), "price": 100 + offset, "volume": 1000}
            for offset in range(2200, -1, -1)
        ]
        intraday = [
            {"time": int(now.timestamp()), "price": 125.0, "volume": 2000},
        ]
        meta = {
            "regularMarketPrice": 125.0,
            "chartPreviousClose": 100.0,
            "currency": "USD",
            "regularMarketTime": 1_800_000_000,
            "preMarketPrice": 124.0,
            "postMarketPrice": 126.5,
            "fiftyTwoWeekHigh": 150.0,
            "epsTrailingTwelveMonths": 4.25,
        }
        with patch.object(fetch_market_data, "fetch_chart", side_effect=[
            (meta, history), (meta, intraday), (meta, history[::30]),
        ]):
            stock = fetch_market_data.fetch_stock_data("NVDA", now)

        self.assertEqual(stock["quote"]["price"], 125.0)
        self.assertEqual(stock["quote"]["change"], 25.0)
        self.assertEqual(stock["quote"]["change_percent"], 25.0)
        self.assertEqual(stock["quote"]["post_market_price"], 126.5)
        self.assertEqual(stock["metrics"]["fifty_two_week_high"], 150.0)
        self.assertEqual(stock["metrics"]["eps"], 4.25)
        self.assertEqual(set(stock["history"]), {"1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "MAX"})
        self.assertEqual(len(stock["history"]["1D"]), 1)
        self.assertGreater(len(stock["history"]["MAX"]), len(stock["history"]["5Y"]))

    def test_missing_after_hours_and_financial_metadata_stays_unavailable(self):
        now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        history = [
            {"time": int(now.timestamp()), "price": 100.0, "volume": 1000},
            {"time": int((now + timedelta(minutes=5)).timestamp()), "price": 101.0, "volume": 1200},
        ]
        meta = {"regularMarketPrice": 101.0, "chartPreviousClose": 100.0}
        with patch.object(fetch_market_data, "fetch_chart", side_effect=[
            (meta, history), (meta, history), (meta, history),
        ]):
            stock = fetch_market_data.fetch_stock_data("NVDA", now)

        self.assertIsNone(stock["quote"]["pre_market_price"])
        self.assertIsNone(stock["quote"]["post_market_price"])
        self.assertIsNone(stock["metrics"]["market_cap"])
        self.assertIsNone(stock["metrics"]["eps"])
        self.assertEqual(stock["metrics"]["volume"], 1200)


class NewsAlertTests(unittest.TestCase):
    def test_trending_topics_count_recent_unique_articles_and_aliases(self):
        now = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
        articles = [
            {
                "ticker": "NVDA",
                "title": "New AI GPU accelerator announced",
                "link": "https://example.com/ai",
                "published": "",
                "fetched_at": (now - timedelta(days=1)).isoformat(),
            },
            {
                "ticker": "TSLA",
                "title": "Robotaxi begins autonomous driving test",
                "link": "https://example.com/robotaxi",
                "published": "",
                "fetched_at": (now - timedelta(days=3)).isoformat(),
            },
            {
                "ticker": "TSLA",
                "title": "Old robotaxi headline",
                "link": "https://example.com/old",
                "published": "",
                "fetched_at": (now - timedelta(days=8)).isoformat(),
            },
        ]
        trending = fetch_news.build_trending_topics(articles + [articles[0]], now)
        topics = {topic["label"]: topic for topic in trending["topics"]}

        self.assertEqual(trending["source_count"], 2)
        self.assertEqual(topics["AI Chip"]["count"], 1)
        self.assertIn("GPU", topics["AI Chip"]["search_terms"])
        self.assertEqual(topics["Robotaxi"]["count"], 1)
        self.assertEqual(topics["TSLA"]["count"], 1)

    def test_market_sentiment_score_excludes_neutral_news(self):
        sentiment = fetch_news.calculate_market_sentiment([
            {"sentiment": "positive"},
            {"sentiment": "positive"},
            {"sentiment": "positive"},
            {"sentiment": "negative"},
            {"sentiment": "neutral"},
        ])

        self.assertEqual(sentiment["score"], 75)
        self.assertEqual(sentiment["label"], "Bullish")
        self.assertEqual(sentiment["counts"], {"positive": 3, "negative": 1, "neutral": 1})
        self.assertEqual(sentiment["total"], 5)

    def test_market_sentiment_with_only_neutral_articles_has_no_score(self):
        sentiment = fetch_news.calculate_market_sentiment([
            {"sentiment": "neutral"},
            {"sentiment": "unknown"},
        ])

        self.assertIsNone(sentiment["score"])
        self.assertEqual(sentiment["label"], "No data")
        self.assertEqual(sentiment["total"], 2)

    def test_daily_sentiment_accumulates_unique_articles_for_today(self):
        today = datetime.now(timezone.utc).isoformat()
        first = {
            "link": "https://example.com/first",
            "sentiment": "positive",
            "published": "",
            "fetched_at": today,
        }
        second = {
            "link": "https://example.com/second",
            "sentiment": "negative",
            "published": "",
            "fetched_at": today,
        }
        with tempfile.TemporaryDirectory() as directory:
            sentiment_path = Path(directory) / "sentiment.json"
            with patch.object(fetch_news, "SENTIMENT_FILE", str(sentiment_path)):
                fetch_news.update_daily_market_sentiment([first, first])
                fetch_news.update_daily_market_sentiment([second])
            sentiment = json.loads(sentiment_path.read_text(encoding="utf-8"))

        self.assertEqual(sentiment["score"], 50)
        self.assertEqual(sentiment["total"], 2)
        self.assertEqual(len(sentiment["articles"]), 2)

    def test_high_impact_alerts_send_once_per_configured_channel(self):
        items = [
            {
                "ticker": "NVDA",
                "title": "Major product launch",
                "link": "https://example.com/news",
                "impact_level": "high",
                "impact_direction": "positive",
                "impact_reason": "เปิดตัวผลิตภัณฑ์สำคัญ",
            },
            {
                "ticker": "AAPL",
                "title": "Routine update",
                "link": "https://example.com/other",
                "impact_level": "medium",
                "impact_direction": "negative",
            },
        ]
        secrets = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_CHAT_ID": "test-chat",
            "DISCORD_WEBHOOK_URL": "https://discord.example/webhook",
        }
        with patch.dict(os.environ, secrets, clear=True):
            with patch.object(fetch_news, "post_json", side_effect=[{"ok": True}, {}]) as send:
                fetch_news.notify_high_impact(items)
                fetch_news.notify_high_impact(items)

        self.assertEqual(send.call_count, 2)
        self.assertEqual(items[0]["notifications_sent"], ["telegram", "discord"])
        self.assertNotIn("notifications_sent", items[1])

    def test_published_time_is_parsed_as_timezone_aware(self):
        published = fetch_news.parse_news_datetime({
            "published": "Fri, 16 Oct 2026 12:57:29 +0000",
        })

        self.assertIsNotNone(published)
        self.assertIsNotNone(published.tzinfo)
        self.assertEqual(published.isoformat(), "2026-10-16T12:57:29+00:00")

    def test_daily_summary_uses_only_news_from_today(self):
        today = {
            "ticker": "NVDA",
            "title": "New AI chip",
            "published": "",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        yesterday = {
            "ticker": "AAPL",
            "title": "Older news",
            "published": "",
            "fetched_at": "2020-01-01T00:00:00+00:00",
        }
        client = SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(
                text=json.dumps({"summary_th": "ภาพรวมข่าวเป็นบวก\nNVDA และชิปโดดเด่น\nติดตามความเสี่ยงด้านการแข่งขัน"})
            ),
        ))
        with tempfile.TemporaryDirectory() as directory:
            summary_path = Path(directory) / "summary.json"
            with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True):
                with patch.object(fetch_news.genai, "Client", return_value=client):
                    with patch.object(fetch_news, "SUMMARY_FILE", str(summary_path)):
                        fetch_news.generate_daily_summary([today, yesterday])
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(len(summary["summary_th"].splitlines()), 3)
        self.assertIn("ความเสี่ยง", summary["summary_th"])
        self.assertEqual(summary["source_count"], 1)


if __name__ == "__main__":
    unittest.main()
