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

    def test_navigation_targets_exist_and_ids_are_unique(self):
        ids = re.findall(r"""\bid=["']([^"']+)["']""", self.html)
        self.assertEqual(len(ids), len(set(ids)), "HTML contains duplicate id attributes")

        targets = re.findall(r"""href=["']#([^"']+)["']""", self.html)
        self.assertTrue(targets, "Expected in-page navigation links")
        for target in targets:
            with self.subTest(target=target):
                self.assertIn(target, ids, f"Navigation target #{target} does not exist")

    def test_mobile_command_dock_and_skip_link_are_present(self):
        self.assertIn('<nav class="mobile-dock"', self.html)
        self.assertIn('class="skip-link"', self.html)
        self.assertIn('aria-label="เมนูทางลัดบนมือถือ"', self.html)
        for target in ("marketOverview", "stock-workspace", "newsDashboard", "watchlistTitle"):
            with self.subTest(target=target):
                self.assertIn(f'href="#{target}"', self.html)

    def test_feed_pagination_refresh_and_freshness_controls_are_present(self):
        for expected in (
            'id="refreshData"',
            'id="dataFreshness"',
            'id="loadMoreNews"',
            "visibleNewsLimit = 24",
            "refreshDashboardData",
            "function safeHttpUrl",
            'id="aiSourceLabel"',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.html)

    def test_news_source_labels_distinguish_gemini_from_headline_fallback(self):
        self.assertIn("summary_source === \"gemini\"", self.html)
        self.assertIn("summary_source === \"headline_fallback\"", self.html)
        self.assertIn("analysis_source === \"fallback\"", self.html)
        self.assertIn("อ้างอิงจากพาดหัว · ไม่ใช่คำแปล", self.html)

    def test_responsive_and_accessibility_styles_are_present(self):
        compact_html = self.html.replace(" ", "")
        for breakpoint in ("1100px", "760px", "560px"):
            with self.subTest(breakpoint=breakpoint):
                self.assertIn(f"max-width:{breakpoint}", compact_html)

        self.assertIn('name="viewport"', self.html)
        self.assertIn('lang="th"', self.html)
        self.assertIn("prefers-reduced-motion:reduce", compact_html)
        self.assertIn(":focus-visible", self.html)


if __name__ == "__main__":
    unittest.main()
