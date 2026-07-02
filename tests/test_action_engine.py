import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from action_engine import (  # noqa: E402
    RESEARCH_DECISIONS,
    RESEARCH_SIGNALS,
    decide_research,
)


class ResearchEngineTests(unittest.TestCase):
    def test_research_output_types_match_specification(self):
        self.assertEqual(
            RESEARCH_DECISIONS,
            {
                "核心研究標的",
                "小幅布局候選",
                "回檔布局候選",
                "續列觀察",
                "僅追蹤不投入",
                "暫不投入",
                "排除觀察",
            },
        )
        self.assertEqual(
            RESEARCH_SIGNALS,
            {"consider", "wait", "watch", "avoid"},
        )

    def test_wiwynn_uses_scores_instead_of_old_position_strategy(self):
        result = decide_research(
            total_score=87,
            valuation_score=17,
            price_risk_score=5,
            ai_relevance="高",
            research_role="高關注標的",
        )
        self.assertEqual(result.research_decision, "回檔布局候選")
        self.assertEqual(result.research_signal, "wait")

    def test_tsmc_high_score_and_low_price_score_waits_for_pullback(self):
        result = decide_research(
            total_score=84,
            valuation_score=15,
            price_risk_score=2,
            ai_relevance="高",
            research_role="核心研究標的",
        )
        self.assertEqual(result.research_decision, "回檔布局候選")
        self.assertEqual(result.research_signal, "wait")
        self.assertEqual(
            result.research_reason,
            "公司品質高，但股價或籌碼風險偏高，不追價，等待回檔或風險下降",
        )

    def test_safe_high_score_is_small_position_candidate(self):
        result = decide_research(
            total_score=88,
            valuation_score=15,
            price_risk_score=8,
            ai_relevance="高",
            research_role="高關注標的",
        )
        self.assertEqual(result.research_decision, "小幅布局候選")
        self.assertEqual(result.research_signal, "consider")
        self.assertEqual(result.signal_strength, "中")

    def test_non_high_ai_non_core_cannot_be_small_position_candidate(self):
        result = decide_research(
            total_score=90,
            valuation_score=18,
            price_risk_score=9,
            ai_relevance="中",
            research_role="觀察標的",
        )
        self.assertEqual(result.research_decision, "續列觀察")
        self.assertEqual(result.research_signal, "watch")

    def test_score_75_with_acceptable_valuation_stays_on_watchlist(self):
        result = decide_research(
            total_score=77,
            valuation_score=10,
            price_risk_score=6,
        )
        self.assertEqual(result.research_decision, "續列觀察")
        self.assertEqual(result.research_signal, "watch")
        self.assertEqual(result.signal_strength, "中")

    def test_score_60_to_74_is_weak_watch(self):
        result = decide_research(
            total_score=70,
            valuation_score=8,
            price_risk_score=6,
        )
        self.assertEqual(result.research_decision, "續列觀察")
        self.assertEqual(result.research_signal, "watch")
        self.assertEqual(result.signal_strength, "弱")

    def test_score_below_60_is_tracking_only(self):
        result = decide_research(
            total_score=55,
            valuation_score=8,
            price_risk_score=5,
        )
        self.assertEqual(result.research_decision, "僅追蹤不投入")
        self.assertEqual(result.research_signal, "watch")

    def test_yageo_low_score_and_high_risk_is_avoid(self):
        result = decide_research(
            total_score=51,
            valuation_score=4,
            price_risk_score=2,
            ai_relevance="中",
            research_role="景氣循環觀察",
        )
        self.assertEqual(result.research_decision, "暫不投入")
        self.assertEqual(result.research_signal, "avoid")

    def test_missing_scores_are_tracking_only(self):
        result = decide_research(
            total_score=None,
            valuation_score=None,
            price_risk_score=None,
        )
        self.assertEqual(result.research_decision, "僅追蹤不投入")
        self.assertEqual(result.research_signal, "watch")

    def test_outputs_never_contain_position_operation_terms(self):
        cases = (
            (87, 17, 5, "高", "高關注標的"),
            (88, 15, 8, "高", "核心研究標的"),
            (77, 10, 6, "高", "觀察標的"),
            (51, 4, 2, "中", "景氣循環觀察"),
        )
        forbidden = ("reduce", "exit", "清倉", "減碼", "續抱", "加碼")
        for total, valuation, price, relevance, role in cases:
            with self.subTest(total=total):
                result = decide_research(
                    total_score=total,
                    valuation_score=valuation,
                    price_risk_score=price,
                    ai_relevance=relevance,
                    research_role=role,
                )
                output = " ".join(result.as_dict().values())
                self.assertFalse(any(term in output for term in forbidden))


if __name__ == "__main__":
    unittest.main()
