import csv
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from fetch_stock_info import (  # noqa: E402
    OUTPUT_FIELDS,
    determine_confidence,
    find_local_stock,
    load_local_stocks,
    make_price_risk_reason,
    make_valuation_reason,
    suggest_growth_score,
    suggest_price_risk_score,
    suggest_valuation_score,
    upsert_suggestion,
)


class FetchStockInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.local_stocks = load_local_stocks(PROJECT_DIR / "stocks.csv")

    def test_local_stock_can_be_found_by_id_and_name(self):
        self.assertEqual(
            find_local_stock(self.local_stocks, "2330").stock_name,
            "台積電",
        )
        self.assertEqual(
            find_local_stock(self.local_stocks, "緯穎").stock_id,
            "6669",
        )

    def test_growth_score_uses_revenue_trend(self):
        self.assertEqual(suggest_growth_score(30.0, 20.0), 22)
        self.assertEqual(suggest_growth_score(None, None), 12)
        self.assertEqual(suggest_growth_score(-20.0, -15.0), 5)

    def test_valuation_and_price_risk_scores_are_bounded(self):
        self.assertEqual(suggest_valuation_score(10.0, 22), 19)
        self.assertEqual(suggest_valuation_score(100.0, 5), 2)
        self.assertEqual(suggest_price_risk_score(20.0), 9)
        self.assertEqual(suggest_price_risk_score(99.0), 2)
        self.assertEqual(suggest_price_risk_score(None), 5)

    def test_low_scores_have_specific_reasons(self):
        valuation_reason = make_valuation_reason(80.0, 15, 3)
        self.assertIn("估值過熱", valuation_reason)
        self.assertIn("不適合", valuation_reason)

        price_reason = make_price_risk_reason(
            {
                "latest": 99.0,
                "low_1y": 50.0,
                "high_1y": 100.0,
                "position_pct": 98.0,
            },
            2,
        )
        self.assertIn("52 週高點", price_reason)
        self.assertIn("追價風險高", price_reason)

    def test_missing_data_forces_low_confidence(self):
        confidence = determine_confidence(
            has_company=True,
            has_revenue=False,
            has_valuation=False,
            has_price_history=False,
            has_news=False,
            warnings=["資料不足"],
        )
        self.assertEqual(confidence, "低")

    def test_upsert_writes_only_suggestion_fields(self):
        suggestion = {
            "generated_at": "2026-07-01T12:00:00+08:00",
            "score_version": "0.5.1",
            "stock_id": "2330",
            "stock_name": "台積電",
            "confidence_level": "高",
            "suggested_industry_score": 25,
            "industry_reason": "產業理由",
            "suggested_growth_score": 22,
            "growth_reason": "成長理由",
            "suggested_ai_score": 20,
            "ai_reason": "AI 理由",
            "suggested_valuation_score": 15,
            "valuation_reason": "估值理由",
            "suggested_price_risk_score": 2,
            "price_risk_reason": "價格理由",
            "raw_metrics_summary": "原始指標",
            "source_count": 1,
            "source_urls": "https://example.com",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "suggested_scores.csv"
            upsert_suggestion(suggestion, output)
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(tuple(reader.fieldnames), OUTPUT_FIELDS)
                rows = list(reader)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["stock_id"], "2330")
            self.assertEqual(rows[0]["confidence_level"], "高")
            self.assertTrue(all("suggested_suggested" not in field for field in OUTPUT_FIELDS))


if __name__ == "__main__":
    unittest.main()
