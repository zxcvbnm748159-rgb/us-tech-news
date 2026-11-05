import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_FILE = ROOT / "index.html"


class FrontendContractTests(unittest.TestCase):
    def setUp(self):
        self.html = HTML_FILE.read_text(encoding="utf-8")

    def test_news_sort_controls_and_impact_badges_are_present(self):
        for expected in (
            'id="newsSort"',
            'value="recent"',
            'value="impact"',
            'value="positive"',
            'value="negative"',
            "impact-tag",
            "impactRank",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.html)

    def test_original_dashboard_feature_hooks_remain_present(self):
        for expected in (
            'id="stockChart"',
            'id="watchlistList"',
            'id="portfolioHoldings"',
            'id="comparisonGrid"',
            'id="trendingList"',
            'id="newsDialog"',
            'id="personalNote"',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.html)

    def test_inline_javascript_passes_node_syntax_check(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed in this environment")

        match = re.search(r"<script>(.*?)</script>", self.html, re.DOTALL)
        self.assertIsNotNone(match, "Expected one inline application script")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", encoding="utf-8"
        ) as script_file:
            script_file.write(match.group(1))
            script_file.flush()
            result = subprocess.run(
                [node, "--check", script_file.name],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
