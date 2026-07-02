#!/usr/bin/env python3
"""依股票代號或名稱查詢 decision_summary.csv。"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable, Sequence


DISPLAY_FIELDS = (
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

NOT_FOUND_MESSAGE = "找不到此股票，請確認股票名稱或代號是否已加入 stocks.csv"


class QueryError(ValueError):
    """查詢資料檔無法使用。"""


def load_decision_summary(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise QueryError(f"找不到決策摘要檔：{path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = tuple(reader.fieldnames or ())
        missing = [field for field in DISPLAY_FIELDS if field not in headers]
        if missing:
            raise QueryError(
                f"decision_summary.csv 缺少欄位：{', '.join(missing)}"
            )
        rows = list(reader)

    if not rows:
        raise QueryError("decision_summary.csv 沒有任何股票資料")
    return rows


def find_stock(
    rows: Iterable[dict[str, str]],
    query: str,
) -> dict[str, str] | None:
    key = query.strip().casefold()
    if not key:
        return None

    for row in rows:
        stock_id = (row.get("stock_id") or "").strip().casefold()
        stock_name = (row.get("stock_name") or "").strip().casefold()
        if key == stock_id or key == stock_name:
            return row
    return None


def format_stock(row: dict[str, str]) -> str:
    return "\n".join(f"{field}: {row.get(field, '')}" for field in DISPLAY_FIELDS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="以股票代號或公司名稱查詢台股 AI 決策摘要。"
    )
    script_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "query",
        nargs="+",
        help="股票代號或公司名稱，例如 2330、台積電、緯穎",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=script_dir / "decision_summary.csv",
        help="決策摘要 CSV 路徑",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    query = " ".join(args.query).strip()

    try:
        rows = load_decision_summary(args.file)
    except (QueryError, OSError) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 2

    result = find_stock(rows, query)
    if result is None:
        print(NOT_FOUND_MESSAGE)
        return 1

    print(format_stock(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
