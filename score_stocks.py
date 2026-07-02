#!/usr/bin/env python3
"""台股 AI 選股查詢與研究分數整合器 v0.9。"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from action_engine import decide_research


SCORE_LIMITS = {
    "industry_score": 25.0,
    "growth_score": 25.0,
    "ai_score": 20.0,
    "valuation_score": 20.0,
    "price_risk_score": 10.0,
}

VERSION = "0.9"
RESEARCH_ROLES = {
    "核心研究標的",
    "高關注標的",
    "觀察標的",
    "景氣循環觀察",
    "非主線觀察",
}

REQUIRED_FIELDS = (
    "data_date",
    "stock_id",
    "stock_name",
    "industry_position",
    "ai_relevance",
    "is_bottleneck",
    "risk_notes",
    "research_role",
    "research_note",
    *SCORE_LIMITS.keys(),
)

OUTPUT_FIELDS = (
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
)

MISSING_TOKENS = {"", "NA", "N/A", "NULL", "NONE", "-", "--"}


class InputError(ValueError):
    """輸入 CSV 不符合規格。"""


@dataclass(frozen=True)
class Stock:
    data_date: str
    stock_id: str
    stock_name: str
    industry_position: str
    ai_relevance: str
    is_bottleneck: str
    risk_notes: str
    research_role: str
    research_note: str
    industry_score: float | None
    growth_score: float | None
    ai_score: float | None
    valuation_score: float | None
    price_risk_score: float | None


def require_text(row: dict[str, str], field: str, row_number: int) -> str:
    value = (row.get(field) or "").strip()
    if not value:
        raise InputError(f"第 {row_number} 列：{field} 不得空白")
    return value


def require_date(row: dict[str, str], field: str, row_number: int) -> str:
    value = require_text(row, field, row_number)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"第 {row_number} 列：{field} 必須是 YYYY-MM-DD") from exc
    return value


def parse_optional_score(
    row: dict[str, str],
    field: str,
    row_number: int,
    maximum: float,
) -> float | None:
    raw = (row.get(field) or "").strip()
    if raw.upper() in MISSING_TOKENS:
        return None

    try:
        value = float(raw)
    except ValueError as exc:
        raise InputError(
            f"第 {row_number} 列：{field} 必須是 0–{maximum:g}、空白或 NA"
        ) from exc

    if not math.isfinite(value):
        raise InputError(f"第 {row_number} 列：{field} 必須是有限數字")
    if not 0.0 <= value <= maximum:
        raise InputError(f"第 {row_number} 列：{field} 必須介於 0–{maximum:g}")
    return value


def stock_from_row(row: dict[str, str], row_number: int) -> Stock:
    ai_relevance = require_text(row, "ai_relevance", row_number)
    if ai_relevance not in {"高", "中", "低"}:
        raise InputError(f"第 {row_number} 列：ai_relevance 必須是 高 / 中 / 低")

    is_bottleneck = require_text(row, "is_bottleneck", row_number)
    if is_bottleneck not in {"是", "否", "部分"}:
        raise InputError(f"第 {row_number} 列：is_bottleneck 必須是 是 / 否 / 部分")

    research_role = require_text(row, "research_role", row_number)
    if research_role not in RESEARCH_ROLES:
        raise InputError(
            f"第 {row_number} 列：research_role 必須是 "
            + " / ".join(sorted(RESEARCH_ROLES))
        )

    return Stock(
        data_date=require_date(row, "data_date", row_number),
        stock_id=require_text(row, "stock_id", row_number),
        stock_name=require_text(row, "stock_name", row_number),
        industry_position=require_text(row, "industry_position", row_number),
        ai_relevance=ai_relevance,
        is_bottleneck=is_bottleneck,
        risk_notes=(row.get("risk_notes") or "").strip(),
        research_role=research_role,
        research_note=(row.get("research_note") or "").strip(),
        industry_score=parse_optional_score(
            row, "industry_score", row_number, SCORE_LIMITS["industry_score"]
        ),
        growth_score=parse_optional_score(
            row, "growth_score", row_number, SCORE_LIMITS["growth_score"]
        ),
        ai_score=parse_optional_score(
            row, "ai_score", row_number, SCORE_LIMITS["ai_score"]
        ),
        valuation_score=parse_optional_score(
            row, "valuation_score", row_number, SCORE_LIMITS["valuation_score"]
        ),
        price_risk_score=parse_optional_score(
            row, "price_risk_score", row_number, SCORE_LIMITS["price_risk_score"]
        ),
    )


def read_stocks(path: Path) -> list[Stock]:
    if not path.exists():
        raise InputError(f"找不到輸入檔：{path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = tuple(reader.fieldnames or ())
        missing = [field for field in REQUIRED_FIELDS if field not in headers]
        if missing:
            raise InputError(f"輸入 CSV 缺少欄位：{', '.join(missing)}")
        stocks = [
            stock_from_row(row, row_number)
            for row_number, row in enumerate(reader, start=2)
        ]

    if not stocks:
        raise InputError("輸入 CSV 沒有任何股票資料")

    seen: set[str] = set()
    duplicates: set[str] = set()
    for stock in stocks:
        if stock.stock_id in seen:
            duplicates.add(stock.stock_id)
        seen.add(stock.stock_id)
    if duplicates:
        raise InputError(f"stock_id 不得重複：{', '.join(sorted(duplicates))}")
    return stocks


def classify(total_score: float) -> str:
    if total_score >= 80.0:
        return "高研究吸引力"
    if total_score >= 65.0:
        return "值得持續研究"
    if total_score >= 50.0:
        return "觀察追蹤"
    return "低優先或排除"


def display_score(value: float | None) -> int | float | str:
    if value is None:
        return "NA"
    if value.is_integer():
        return int(value)
    return round(value, 2)


def score_stock(stock: Stock) -> dict[str, str | int | float]:
    scores = {
        "industry_score": stock.industry_score,
        "growth_score": stock.growth_score,
        "ai_score": stock.ai_score,
        "valuation_score": stock.valuation_score,
        "price_risk_score": stock.price_risk_score,
    }
    missing = [field for field, value in scores.items() if value is None]

    if missing:
        total_score: int | float | str = "NA"
        total_for_research: float | None = None
        category = "分數資料不足"
    else:
        total = sum(value for value in scores.values() if value is not None)
        total_score = int(total) if total.is_integer() else round(total, 2)
        total_for_research = total
        category = classify(total)

    research_result = decide_research(
        total_score=total_for_research,
        valuation_score=stock.valuation_score,
        price_risk_score=stock.price_risk_score,
        ai_relevance=stock.ai_relevance,
        research_role=stock.research_role,
    )

    return {
        "data_date": stock.data_date,
        "stock_id": stock.stock_id,
        "stock_name": stock.stock_name,
        "total_score": total_score,
        "category": category,
        **research_result.as_dict(),
        "research_role": stock.research_role,
        "industry_position": stock.industry_position,
        "ai_relevance": stock.ai_relevance,
        "is_bottleneck": stock.is_bottleneck,
        "industry_score": display_score(stock.industry_score),
        "growth_score": display_score(stock.growth_score),
        "ai_score": display_score(stock.ai_score),
        "valuation_score": display_score(stock.valuation_score),
        "price_risk_score": display_score(stock.price_risk_score),
        "risk_notes": stock.risk_notes,
        "research_note": stock.research_note,
    }


def write_results(
    rows: Iterable[dict[str, str | int | float]],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def sort_results(
    rows: Iterable[dict[str, str | int | float]],
) -> list[dict[str, str | int | float]]:
    return sorted(
        rows,
        key=lambda row: (
            row["total_score"] == "NA",
            -float(row["total_score"]) if row["total_score"] != "NA" else 0.0,
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="讀取台股 AI 研究分數，輸出研究吸引力與決策摘要。"
    )
    script_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "--input",
        type=Path,
        default=script_dir / "stocks.csv",
        help="輸入 CSV 路徑（預設：程式目錄下 stocks.csv）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "decision_summary.csv",
        help="輸出 CSV 路徑（預設：程式目錄下 decision_summary.csv）",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        stocks = read_stocks(args.input.resolve())
        results = sort_results(score_stock(stock) for stock in stocks)
        write_results(results, args.output.resolve())
    except (InputError, OSError, csv.Error) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1

    scored_count = sum(row["total_score"] != "NA" for row in results)
    print(
        f"完成（v{VERSION}）：已讀取 {len(stocks)} 檔股票；"
        f"已評分 {scored_count} 檔"
    )
    print(f"輸出：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
