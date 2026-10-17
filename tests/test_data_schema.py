import json
from pathlib import Path
import unittest


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class PublishedDataSchemaTests(unittest.TestCase):
    def load_json(self, filename):
        with (DATA_DIR / filename).open(encoding="utf-8") as data_file:
            return json.load(data_file)

    def test_published_json_files_are_valid_json(self):
        filenames = (
            "market_prices.json",
            "market_sentiment.json",
            "market_summary.json",
            "news.json",
            "stock_analysis.json",
            "trending_topics.json",
        )
        for filename in filenames:
            with self.subTest(filename=filename):
                self.assertTrue((DATA_DIR / filename).is_file())
                self.load_json(filename)

    def test_market_prices_has_dashboard_shape(self):
        market_data = self.load_json("market_prices.json")

        self.assertIsInstance(market_data, dict)
        self.assertIsInstance(market_data.get("quotes"), list)
        self.assertIsInstance(market_data.get("stocks"), dict)
        for quote in market_data["quotes"]:
            self.assertIsInstance(quote, dict)
            self.assertIsInstance(quote.get("symbol"), str)
            self.assertIsInstance(quote.get("price"), (int, float))
            self.assertIsInstance(quote.get("change_percent"), (int, float))

    def test_stock_analysis_matches_dashboard_schema(self):
        analyses = self.load_json("stock_analysis.json")

        self.assertIsInstance(analyses, list)
        for analysis in analyses:
            self.assertIsInstance(analysis, dict)
            self.assertIsInstance(analysis.get("ticker"), str)
            self.assertIsInstance(analysis.get("last_updated"), str)
            self.assertIsInstance(analysis.get("summary"), str)
            self.assertIsInstance(analysis.get("analysis_points"), list)
            self.assertTrue(all(isinstance(point, str) for point in analysis["analysis_points"]))
