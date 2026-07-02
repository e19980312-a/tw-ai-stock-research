#!/usr/bin/env python3
"""台股 AI 選股查詢工具 v0.9 研究決策引擎。"""

from __future__ import annotations

from dataclasses import asdict, dataclass


RESEARCH_DECISIONS = {
    "核心研究標的",
    "小幅布局候選",
    "回檔布局候選",
    "續列觀察",
    "僅追蹤不投入",
    "暫不投入",
    "排除觀察",
}
RESEARCH_SIGNALS = {"consider", "wait", "watch", "avoid"}
SIGNAL_STRENGTHS = {"強", "中", "弱"}


@dataclass(frozen=True)
class ResearchResult:
    research_decision: str
    research_signal: str
    signal_strength: str
    research_reason: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def decide_research(
    *,
    total_score: float | None,
    valuation_score: float | None,
    price_risk_score: float | None,
    ai_relevance: str = "",
    research_role: str = "",
) -> ResearchResult:
    """依公司分數、風險與研究定位產生研究輔助訊號。"""

    ai_relevance = str(ai_relevance).strip()
    research_role = str(research_role).strip()

    if (
        total_score is None
        or valuation_score is None
        or price_risk_score is None
    ):
        return ResearchResult(
            "僅追蹤不投入",
            "watch",
            "弱",
            "分數資料不足，補齊研究資料後再評估",
        )

    if valuation_score <= 5 and price_risk_score <= 4:
        return ResearchResult(
            "暫不投入",
            "avoid",
            "中",
            "估值與股價風險偏高，目前不適合追價",
        )

    if total_score >= 80 and price_risk_score <= 5:
        return ResearchResult(
            "回檔布局候選",
            "wait",
            "中",
            "公司品質高，但股價或籌碼風險偏高，不追價，等待回檔或風險下降",
        )

    if (
        total_score >= 85
        and valuation_score >= 14
        and price_risk_score >= 6
    ):
        if ai_relevance == "高" or research_role == "核心研究標的":
            return ResearchResult(
                "小幅布局候選",
                "consider",
                "中",
                "公司條件佳，估值與股價風險尚可，可列為小幅布局候選",
            )
        return ResearchResult(
            "續列觀察",
            "watch",
            "中",
            "公司條件佳，但 AI 相關性與研究定位未達布局條件，續列觀察",
        )

    if total_score >= 75 and valuation_score >= 10:
        return ResearchResult(
            "續列觀察",
            "watch",
            "中",
            "公司條件不差，但等待估值、股價或基本面條件改善",
        )

    if 60 <= total_score < 75:
        return ResearchResult(
            "續列觀察",
            "watch",
            "弱",
            "具備部分題材或基本面，但尚未達到布局門檻",
        )

    if total_score < 60:
        return ResearchResult(
            "僅追蹤不投入",
            "watch",
            "弱",
            "公司分數尚未達投入門檻，維持追蹤",
        )

    return ResearchResult(
        "續列觀察",
        "watch",
        "弱",
        "公司分數尚可，但估值條件未達布局門檻",
    )
