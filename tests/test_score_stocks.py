import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from score_stocks import (  # noqa: E402
    InputError,
    OUTPUT_FIELDS,
    classify,
    read_stocks,
    score_stock,
    sort_results,
    stock_from_row,
)


def make_row(**overrides):
    row = {
        "data_date": "2026-07-01",
        "stock_id": "TEST01",
        "stock_name": "測試公司",
        "industry_position": "測試角色",
        "ai_relevance": "高",
        "is_bottleneck": "是",
        "risk_notes": "測試風險",
        "research_role": "高關注標的",
        "research_note": "測試研究備註",
        "industry_score": "25",
        "growth_score": "25",
        "ai_score": "20",
        "valuation_score": "20",
        "price_risk_score": "10",
    }
    row.update(overrides)
    return row


class ScoreStocksTests(unittest.TestCase):
    def test_decision_summary_column_order(self):
        self.assertEqual(
            OUTPUT_FIELDS,
            (
                "data_date",
                "stock_id",
                "stock_name",
                "total_score",
                "category",
                "research_decision",
                "research_signal",
                "signal_strength",
                "research_reason",
                "research_role",
                "industry_position",
                "ai_relevance",
                "is_bottleneck",
                "industry_score",
                "growth_score",
                "ai_score",
                "valuation_score",
                "price_risk_score",
                "risk_notes",
                "research_note",
            ),
        )

    def test_removed_position_fields_are_not_exported(self):
        removed = {
            "holding_status",
            "current_shares",
            "last_trade_note",
            "manual_override",
            "target_action",
            "strategy_note",
            "position_role",
            "action_decision",
            "add_reduce_signal",
        }
        self.assertTrue(removed.isdisjoint(OUTPUT_FIELDS))

    def test_complete_scores_reach_100(self):
        result = score_stock(stock_from_row(make_row(), 2))
        self.assertEqual(result["total_score"], 100)
        self.assertEqual(result["category"], "高研究吸引力")
        self.assertEqual(result["research_decision"], "小幅布局候選")
        self.assertEqual(result["research_signal"], "consider")

    def test_missing_score_is_not_imputed(self):
        result = score_stock(
            stock_from_row(make_row(valuation_score="NA"), 2)
        )
        self.assertEqual(result["total_score"], "NA")
        self.assertEqual(result["category"], "分數資料不足")
        self.assertEqual(result["research_decision"], "僅追蹤不投入")

    def test_score_range_is_validated(self):
        with self.assertRaises(InputError):
            stock_from_row(make_row(industry_score="26"), 2)

    def test_research_role_is_validated(self):
        with self.assertRaises(InputError):
            stock_from_row(make_row(research_role="核心持股"), 2)

    def test_missing_total_is_sorted_last(self):
        complete = score_stock(stock_from_row(make_row(stock_id="A"), 2))
        missing = score_stock(
            stock_from_row(make_row(stock_id="B", ai_score="NA"), 3)
        )
        results = sort_results([missing, complete])
        self.assertEqual([row["stock_id"] for row in results], ["A", "B"])

    def test_classification_boundaries(self):
        self.assertEqual(classify(80.0), "高研究吸引力")
        self.assertEqual(classify(79.99), "值得持續研究")
        self.assertEqual(classify(65.0), "值得持續研究")
        self.assertEqual(classify(64.99), "觀察追蹤")
        self.assertEqual(classify(50.0), "觀察追蹤")
        self.assertEqual(classify(49.99), "低優先或排除")

    def test_watchlist_has_12_scored_stocks(self):
        stocks = read_stocks(PROJECT_DIR / "stocks.csv")
        results = sort_results(score_stock(stock) for stock in stocks)
        self.assertEqual(len(results), 12)
        self.assertTrue(all(row["total_score"] != "NA" for row in results))

        wiwynn = next(row for row in results if row["stock_id"] == "6669")
        self.assertEqual(wiwynn["research_decision"], "回檔布局候選")
        self.assertEqual(wiwynn["research_signal"], "wait")

        tsmc = next(row for row in results if row["stock_id"] == "2330")
        self.assertEqual(tsmc["research_role"], "核心研究標的")
        self.assertEqual(tsmc["research_decision"], "回檔布局候選")


if __name__ == "__main__":
    unittest.main()
