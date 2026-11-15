import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RADAR_JS = ROOT / "scripts" / "market-radar.js"


class MarketRadarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise unittest.SkipTest("Node.js is required to test the browser radar logic")

    def run_radar(self, market, news, now):
        script = r"""
const radar = require(process.argv[1]);
const market = JSON.parse(process.argv[2]);
const news = JSON.parse(process.argv[3]);
const now = Number(process.argv[4]);
process.stdout.write(JSON.stringify(radar.calculateRadarSignals(market, news, now)));
"""
        result = subprocess.run(
            [self.node, "-e", script, str(RADAR_JS), json.dumps(market),
             json.dumps(news), str(now)],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_large_price_move_creates_transparent_price_signal(self):
        now = 1_800_007_200_000
        market = {
            "updated_at": "2027-01-15T10:00:00Z",
            "quotes": [{"symbol": "NVDA", "change_percent": -5.4}],
            "stocks": {},
        }
        signals = self.run_radar(market, [], now)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["ticker"], "NVDA")
        self.assertEqual(signals[0]["score"], 50)
        self.assertEqual(signals[0]["events"][0]["type"], "price")
        self.assertEqual(signals[0]["severity"], "medium")

    def test_high_volume_and_high_impact_news_combine_and_cap_score(self):
        now = 1_800_007_200_000
        bars = [{"time": i, "volume": 100} for i in range(13)]
        bars.append({"time": 14, "volume": 400})
        market = {
            "updated_at": "2027-01-15T10:00:00Z",
            "quotes": [{"symbol": "NVDA", "change_percent": 5.5}],
            "stocks": {"NVDA": {"history": {"1D": bars}}},
        }
        news = [{
            "ticker": "NVDA", "impact_level": "high", "impact_source": "gemini",
            "title": "High impact report", "published": "2027-01-15T09:30:00Z",
        }]
        signals = self.run_radar(market, news, now)
        self.assertEqual(signals[0]["score"], 100)
        self.assertEqual(signals[0]["severity"], "high")
        self.assertEqual(
            {event["type"] for event in signals[0]["events"]},
            {"price", "volume", "news"},
        )
        self.assertIn("Gemini", signals[0]["events"][-1]["detail"])

    def test_stale_market_data_suppresses_price_and_volume_but_keeps_news(self):
        now = 1_800_007_200_000
        market = {
            "updated_at": "2027-01-15T06:00:00Z",
            "quotes": [{"symbol": "AAPL", "change_percent": 8.0}],
            "stocks": {"AAPL": {"history": {"1D": [
                {"time": i, "volume": 100} for i in range(14)
            ]}}},
        }
        news = [{
            "ticker": "AAPL", "impact_level": "medium", "impact_source": "rules",
            "title": "Relevant news", "published": "2027-01-15T09:30:00Z",
        }]
        signals = self.run_radar(market, news, now)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["score"], 15)
        self.assertEqual([event["type"] for event in signals[0]["events"]], ["news"])

    def test_old_or_undated_news_does_not_create_a_signal(self):
        now = 1_800_007_200_000
        market = {"updated_at": "2027-01-15T10:00:00Z", "quotes": [], "stocks": {}}
        news = [
            {"ticker": "MSFT", "impact_level": "high", "published": "2027-01-10T10:00:00Z"},
            {"ticker": "AAPL", "impact_level": "high", "title": "No timestamp"},
        ]
        self.assertEqual(self.run_radar(market, news, now), [])

    def test_volume_baseline_uses_median_of_previous_twelve_bars(self):
        now = 1_800_007_200_000
        bars = [{"time": i, "volume": 100} for i in range(12)]
        bars += [{"time": 13, "volume": 10000}, {"time": 14, "volume": 250}]
        market = {
            "updated_at": "2027-01-15T10:00:00Z",
            "quotes": [{"symbol": "TSLA", "change_percent": 0.2}],
            "stocks": {"TSLA": {"history": {"1D": bars}}},
        }
        signals = self.run_radar(market, [], now)
        self.assertEqual(signals[0]["volumeRatio"], 2.5)
        self.assertEqual(signals[0]["score"], 25)


if __name__ == "__main__":
    unittest.main()
