import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from query_stock import (  # noqa: E402
    DISPLAY_FIELDS,
    find_stock,
    format_stock,
    load_decision_summary,
)


class QueryStockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_decision_summary(PROJECT_DIR / "decision_summary.csv")

    def test_find_by_stock_id(self):
        result = find_stock(self.rows, "2330")
        self.assertIsNotNone(result)
        self.assertEqual(result["stock_name"], "台積電")

    def test_find_by_stock_name(self):
        result = find_stock(self.rows, "緯穎")
        self.assertIsNotNone(result)
        self.assertEqual(result["stock_id"], "6669")

    def test_unknown_stock_returns_none(self):
        self.assertIsNone(find_stock(self.rows, "不存在公司"))

    def test_formatted_result_contains_all_fields(self):
        result = find_stock(self.rows, "台積電")
        output = format_stock(result)
        for field in DISPLAY_FIELDS:
            self.assertIn(f"{field}:", output)


if __name__ == "__main__":
    unittest.main()
