#!/usr/bin/env python3
"""台股 AI 選股監控 v0.5：抓取公開資料並產生建議分數。"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence
from zoneinfo import ZoneInfo


VERSION = "0.5.1"

TWSE_COMPANY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TWSE_REVENUE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
TWSE_VALUATION_URL = (
    "https://www.twse.com.tw/exchangeReport/BWIBBU_d"
    "?response=json&selectType=ALL"
)
TPEX_COMPANY_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
TPEX_REVENUE_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"
TPEX_VALUATION_URL = (
    "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/"
    "pera_result.php?l=zh-tw&o=json&s=0"
)
TPEX_PRICE_URL = (
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
)
YAHOO_CHART_TEMPLATE = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    "?range=1y&interval=1d"
)
GOOGLE_NEWS_TEMPLATE = (
    "https://news.google.com/rss/search?"
    "q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
)

OUTPUT_FIELDS = (
    "generated_at",
    "score_version",
    "stock_id",
    "stock_name",
    "confidence_level",
    "suggested_industry_score",
    "industry_reason",
    "suggested_growth_score",
    "growth_reason",
    "suggested_ai_score",
    "ai_reason",
    "suggested_valuation_score",
    "valuation_reason",
    "suggested_price_risk_score",
    "price_risk_reason",
    "raw_metrics_summary",
    "source_count",
    "source_urls",
)

AI_KEYWORDS = (
    "AI",
    "人工智慧",
    "伺服器",
    "資料中心",
    "雲端",
    "HPC",
    "高速運算",
    "ASIC",
    "先進製程",
    "先進封裝",
    "CoWoS",
    "HBM",
    "液冷",
    "散熱",
    "光通訊",
    "PCB",
    "銅箔基板",
    "記憶體",
    "晶圓",
    "封裝",
    "變壓器",
)


class FetchError(RuntimeError):
    """公開資料抓取或輸入解析失敗。"""


@dataclass(frozen=True)
class LocalStock:
    stock_id: str
    stock_name: str
    industry_position: str
    ai_relevance: str
    is_bottleneck: str
    risk_notes: str


@dataclass(frozen=True)
class CompanyMatch:
    stock_id: str
    stock_name: str
    market: str
    record: dict[str, Any]
    local: LocalStock | None


def http_get(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; TaiwanAIStockMonitor/0.5; "
                "+https://www.twse.com.tw/)"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_json(url: str, timeout: int) -> Any:
    return json.loads(http_get(url, timeout).decode("utf-8-sig"))


def fetch_text(url: str, timeout: int) -> str:
    return http_get(url, timeout).decode("utf-8-sig", errors="replace")


def safe_fetch_json(
    url: str,
    timeout: int,
    warnings: list[str],
) -> Any:
    try:
        return fetch_json(url, timeout)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        warnings.append(f"無法讀取 {url}：{exc}")
        return None


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" 　-")


def parse_float(value: Any) -> float | None:
    text = clean_text(value).replace(",", "")
    if not text or text.upper() in {"-", "N/A", "NA", "NULL"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_local_stocks(path: Path) -> list[LocalStock]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "stock_id",
            "stock_name",
            "industry_position",
            "ai_relevance",
            "is_bottleneck",
            "risk_notes",
        }
        if not required.issubset(set(reader.fieldnames or ())):
            return []
        return [
            LocalStock(
                stock_id=clean_text(row.get("stock_id")),
                stock_name=clean_text(row.get("stock_name")),
                industry_position=clean_text(row.get("industry_position")),
                ai_relevance=clean_text(row.get("ai_relevance")),
                is_bottleneck=clean_text(row.get("is_bottleneck")),
                risk_notes=clean_text(row.get("risk_notes")),
            )
            for row in reader
        ]


def find_local_stock(
    stocks: Iterable[LocalStock],
    query: str,
) -> LocalStock | None:
    key = query.strip().casefold()
    for stock in stocks:
        if key in {stock.stock_id.casefold(), stock.stock_name.casefold()}:
            return stock
    return None


def company_record_id(record: dict[str, Any]) -> str:
    return clean_text(
        record.get("公司代號")
        or record.get("SecuritiesCompanyCode")
        or record.get("Code")
    )


def company_record_name(record: dict[str, Any]) -> str:
    return clean_text(
        record.get("公司簡稱")
        or record.get("CompanyAbbreviation")
        or record.get("公司名稱")
        or record.get("CompanyName")
    )


def resolve_company(
    query: str,
    local_stocks: list[LocalStock],
    twse_companies: list[dict[str, Any]],
    tpex_companies: list[dict[str, Any]],
) -> CompanyMatch:
    local = find_local_stock(local_stocks, query)
    key = (local.stock_id if local else query).strip().casefold()

    for market, records in (
        ("TWSE", twse_companies),
        ("TPEx", tpex_companies),
    ):
        for record in records:
            record_id = company_record_id(record)
            record_name = company_record_name(record)
            if key in {record_id.casefold(), record_name.casefold()}:
                return CompanyMatch(
                    stock_id=record_id,
                    stock_name=local.stock_name if local else record_name,
                    market=market,
                    record=record,
                    local=local,
                )

    if local:
        return CompanyMatch(
            stock_id=local.stock_id,
            stock_name=local.stock_name,
            market="UNKNOWN",
            record={},
            local=local,
        )
    raise FetchError("找不到此股票，請確認名稱或代號")


def find_record(
    records: Iterable[dict[str, Any]],
    stock_id: str,
) -> dict[str, Any] | None:
    for record in records:
        if company_record_id(record) == stock_id:
            return record
    return None


def fetch_revenue_info(
    stock_id: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    record = find_record(records, stock_id) or {}
    return {
        "data_month": clean_text(record.get("資料年月")),
        "monthly_yoy": parse_float(record.get("營業收入-去年同月增減(%)")),
        "cumulative_yoy": parse_float(
            record.get("累計營業收入-前期比較增減(%)")
        ),
    }


def fetch_valuation_info(
    match: CompanyMatch,
    twse_data: Any,
    tpex_data: Any,
) -> dict[str, float | str | None]:
    if match.market == "TWSE" and isinstance(twse_data, dict):
        for row in twse_data.get("data", []):
            if clean_text(row[0]) == match.stock_id:
                return {
                    "price": parse_float(row[2]),
                    "pe_ratio": parse_float(row[5]),
                    "pb_ratio": parse_float(row[6]),
                    "date": clean_text(twse_data.get("date")),
                }

    if match.market == "TPEx" and isinstance(tpex_data, dict):
        tables = tpex_data.get("tables") or []
        if tables:
            for row in tables[0].get("data", []):
                if clean_text(row[0]) == match.stock_id:
                    return {
                        "price": None,
                        "pe_ratio": parse_float(row[2]),
                        "pb_ratio": parse_float(row[6]),
                        "date": clean_text(tables[0].get("date")),
                    }
    return {"price": None, "pe_ratio": None, "pb_ratio": None, "date": ""}


def fetch_tpex_price(
    stock_id: str,
    records: Any,
) -> float | None:
    if not isinstance(records, list):
        return None
    for record in records:
        if clean_text(record.get("SecuritiesCompanyCode")) == stock_id:
            return parse_float(record.get("Close"))
    return None


def fetch_price_history(
    match: CompanyMatch,
    timeout: int,
    warnings: list[str],
) -> tuple[dict[str, float | None], str]:
    suffixes = [".TW"] if match.market == "TWSE" else [".TWO"]
    if match.market == "UNKNOWN":
        suffixes = [".TW", ".TWO"]

    for suffix in suffixes:
        symbol = f"{match.stock_id}{suffix}"
        url = YAHOO_CHART_TEMPLATE.format(symbol=symbol)
        data = safe_fetch_json(url, timeout, warnings)
        try:
            result = data["chart"]["result"][0]
            closes = [
                float(value)
                for value in result["indicators"]["quote"][0]["close"]
                if value is not None
            ]
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if not closes:
            continue

        latest = closes[-1]
        low = min(closes)
        high = max(closes)
        position = (
            50.0 if high <= low else 100.0 * (latest - low) / (high - low)
        )
        return {
            "latest": latest,
            "low_1y": low,
            "high_1y": high,
            "position_pct": position,
        }, url

    return {
        "latest": None,
        "low_1y": None,
        "high_1y": None,
        "position_pct": None,
    }, ""


def strip_html(value: str) -> str:
    return clean_text(html.unescape(re.sub(r"<[^>]+>", " ", value)))


def fetch_news(
    stock_name: str,
    timeout: int,
    warnings: list[str],
) -> tuple[list[dict[str, str]], str]:
    query = urllib.parse.quote_plus(f"{stock_name} 股票")
    url = GOOGLE_NEWS_TEMPLATE.format(query=query)
    try:
        root = ET.fromstring(fetch_text(url, timeout))
    except (OSError, ET.ParseError, urllib.error.URLError) as exc:
        warnings.append(f"無法讀取新聞 RSS：{exc}")
        return [], url

    news: list[dict[str, str]] = []
    for item in root.findall("./channel/item")[:5]:
        news.append(
            {
                "title": strip_html(item.findtext("title") or ""),
                "link": clean_text(item.findtext("link")),
                "published": clean_text(item.findtext("pubDate")),
            }
        )
    return news, url


def find_ai_keywords(text: str) -> list[str]:
    folded = text.casefold()
    return [
        keyword
        for keyword in AI_KEYWORDS
        if keyword.casefold() in folded
    ]


def suggest_industry_score(local: LocalStock | None) -> int:
    if local is None:
        return 15
    score = {"是": 23, "部分": 19, "否": 14}.get(
        local.is_bottleneck,
        15,
    )
    score += {"高": 2, "中": 1, "低": 0}.get(local.ai_relevance, 0)
    return min(25, score)


def suggest_growth_score(
    monthly_yoy: float | None,
    cumulative_yoy: float | None,
) -> int:
    values = [
        value
        for value in (monthly_yoy, cumulative_yoy)
        if value is not None
    ]
    if not values:
        return 12
    trend = sum(values) / len(values)
    if trend >= 40:
        return 24
    if trend >= 25:
        return 22
    if trend >= 15:
        return 20
    if trend >= 8:
        return 17
    if trend >= 0:
        return 14
    if trend >= -10:
        return 10
    return 5


def suggest_ai_score(
    local: LocalStock | None,
    keyword_count: int,
) -> int:
    relevance = local.ai_relevance if local else ""
    base = {"高": 14, "中": 9, "低": 4}.get(relevance, 6)
    return min(20, base + min(keyword_count, 6))


def suggest_valuation_score(
    pe_ratio: float | None,
    growth_score: int,
) -> int:
    if pe_ratio is None or pe_ratio <= 0:
        return 10
    if pe_ratio <= 12:
        score = 18
    elif pe_ratio <= 18:
        score = 16
    elif pe_ratio <= 25:
        score = 14
    elif pe_ratio <= 35:
        score = 12
    elif pe_ratio <= 50:
        score = 9
    elif pe_ratio <= 75:
        score = 6
    else:
        score = 3
    if growth_score >= 20:
        score += 1
    elif growth_score <= 9:
        score -= 1
    return max(0, min(20, score))


def suggest_price_risk_score(position_pct: float | None) -> int:
    if position_pct is None:
        return 5
    if position_pct <= 25:
        return 9
    if position_pct <= 45:
        return 8
    if position_pct <= 60:
        return 7
    if position_pct <= 75:
        return 6
    if position_pct <= 85:
        return 5
    if position_pct <= 92:
        return 4
    if position_pct <= 97:
        return 3
    return 2


def format_number(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "NA"
    return f"{value:.{digits}f}"


def unique_urls(urls: Iterable[str]) -> list[str]:
    result: list[str] = []
    for url in urls:
        if url and url not in result:
            result.append(url)
    return result


def determine_confidence(
    *,
    has_company: bool,
    has_revenue: bool,
    has_valuation: bool,
    has_price_history: bool,
    has_news: bool,
    warnings: list[str],
) -> str:
    available = sum(
        (
            has_company,
            has_revenue,
            has_valuation,
            has_price_history,
            has_news,
        )
    )
    if available == 5 and not warnings:
        return "高"
    if (
        available >= 4
        and has_company
        and (has_revenue or has_valuation)
        and has_price_history
    ):
        return "中"
    return "低"


def make_industry_reason(
    local: LocalStock | None,
    score: int,
) -> str:
    if local is None:
        return (
            f"stocks.csv 無既有產業定位與瓶頸標記，採中性 {score}/25；"
            "需人工確認產業地位。"
        )
    return (
        f"瓶頸環節標記為「{local.is_bottleneck or '未填'}」，"
        f"AI 相關性為「{local.ai_relevance or '未填'}」，"
        f"依質化規則建議 {score}/25。"
    )


def make_growth_reason(
    revenue: dict[str, Any],
    score: int,
) -> str:
    monthly = revenue["monthly_yoy"]
    cumulative = revenue["cumulative_yoy"]
    values = [value for value in (monthly, cumulative) if value is not None]
    if not values:
        return (
            f"月營收年增與累計年增資料不足，採中性 {score}/25；"
            "信心偏低，需人工補資料。"
        )
    trend = sum(values) / len(values)
    return (
        f"{revenue['data_month'] or '最新期'}單月營收年增 "
        f"{format_number(monthly)}%，累計年增 "
        f"{format_number(cumulative)}%，可用指標平均 "
        f"{trend:.1f}%，依成長區間建議 {score}/25。"
    )


def make_ai_reason(
    local: LocalStock | None,
    keywords: list[str],
    score: int,
) -> str:
    relevance = local.ai_relevance if local else "未評"
    if not keywords:
        return (
            f"既有 AI 相關性為「{relevance}」，公開文字未偵測到明確 "
            f"AI 關鍵字，建議 {score}/20；需人工查核。"
        )
    return (
        f"既有 AI 相關性為「{relevance}」，公開資料與新聞偵測到 "
        f"{len(keywords)} 個關鍵字：{'、'.join(keywords)}；"
        f"建議 {score}/20。"
    )


def make_valuation_reason(
    pe_ratio: float | None,
    growth_score: int,
    score: int,
) -> str:
    if pe_ratio is None or pe_ratio <= 0:
        return (
            f"本益比資料不足或不適用，採中性 {score}/20；"
            "不得視為估值合理。"
        )
    if pe_ratio <= 12:
        band = "12 倍以下，估值相對低"
    elif pe_ratio <= 18:
        band = "12–18 倍，估值仍可接受"
    elif pe_ratio <= 25:
        band = "18–25 倍，估值略高"
    elif pe_ratio <= 35:
        band = "25–35 倍，估值偏高"
    elif pe_ratio <= 50:
        band = "35–50 倍，已反映較多樂觀預期"
    elif pe_ratio <= 75:
        band = "50–75 倍，估值明顯偏高"
    else:
        band = "高於 75 倍，估值過熱"

    adjustment = ""
    if growth_score >= 20:
        adjustment = "；成長分數較高，規則加 1 分"
    elif growth_score <= 9:
        adjustment = "；成長分數偏低，規則減 1 分"
    warning = (
        "，不適合僅因題材追價" if score <= 9 else ""
    )
    return (
        f"本益比 {pe_ratio:.2f} 倍，落在「{band}」區間"
        f"{adjustment}，建議 {score}/20{warning}。"
    )


def make_price_risk_reason(
    price_history: dict[str, float | None],
    score: int,
) -> str:
    latest = price_history["latest"]
    high = price_history["high_1y"]
    position = price_history["position_pct"]
    if latest is None or high is None or position is None:
        return (
            f"近一年價格區間資料不足，採中性 {score}/10；"
            "無法判斷是否接近 52 週高點。"
        )

    distance_from_high = (
        0.0 if high <= 0 else max(0.0, (high - latest) / high * 100.0)
    )
    if score <= 2:
        assessment = "極度接近 52 週高點，追價風險高"
    elif score <= 4:
        assessment = "位於近一年高檔，適合控制部位"
    elif score <= 6:
        assessment = "股價位置偏高，宜等待回檔或風險改善"
    elif score <= 8:
        assessment = "股價位置中性，可持續觀察"
    else:
        assessment = "股價位置相對安全"
    return (
        f"現價 {latest:.2f}，近一年高點 {high:.2f}，"
        f"區間位置 {position:.1f}%，距高點約 {distance_from_high:.1f}%；"
        f"{assessment}，建議 {score}/10。"
    )


def build_suggestion(
    match: CompanyMatch,
    revenue: dict[str, Any],
    valuation: dict[str, float | str | None],
    price_history: dict[str, float | None],
    news: list[dict[str, str]],
    warnings: list[str],
    source_urls: list[str],
) -> dict[str, str | int]:
    local_text = ""
    if match.local:
        local_text = " ".join(
            (
                match.local.industry_position,
                match.local.risk_notes,
                match.local.ai_relevance,
            )
        )
    basic_text = " ".join(clean_text(value) for value in match.record.values())
    news_text = " ".join(item["title"] for item in news)
    keywords = find_ai_keywords(f"{local_text} {basic_text} {news_text}")

    industry_score = suggest_industry_score(match.local)
    growth_score = suggest_growth_score(
        revenue["monthly_yoy"],
        revenue["cumulative_yoy"],
    )
    ai_score = suggest_ai_score(match.local, len(keywords))
    valuation_score = suggest_valuation_score(
        valuation["pe_ratio"],
        growth_score,
    )
    price_risk_score = suggest_price_risk_score(
        price_history["position_pct"]
    )

    company_full_name = clean_text(
        match.record.get("公司名稱")
        or match.record.get("CompanyName")
        or match.stock_name
    )
    industry_code = clean_text(
        match.record.get("產業別")
        or match.record.get("SecuritiesIndustryCode")
    )
    website = clean_text(
        match.record.get("網址")
        or match.record.get("WebAddress")
    )

    all_urls = unique_urls(
        [
            *source_urls,
            website,
            *(item["link"] for item in news[:3]),
        ]
    )
    confidence = determine_confidence(
        has_company=bool(match.record),
        has_revenue=(
            revenue["monthly_yoy"] is not None
            or revenue["cumulative_yoy"] is not None
        ),
        has_valuation=valuation["pe_ratio"] is not None,
        has_price_history=price_history["position_pct"] is not None,
        has_news=bool(news),
        warnings=warnings,
    )
    raw_metrics = [
        f"market={match.market}",
        f"company={company_full_name}",
        f"industry_code={industry_code or 'NA'}",
        f"revenue_month={revenue['data_month'] or 'NA'}",
        f"monthly_yoy_pct={format_number(revenue['monthly_yoy'])}",
        f"cumulative_yoy_pct={format_number(revenue['cumulative_yoy'])}",
        f"latest_price={format_number(price_history['latest'], 2)}",
        f"low_1y={format_number(price_history['low_1y'], 2)}",
        f"high_1y={format_number(price_history['high_1y'], 2)}",
        f"price_position_pct={format_number(price_history['position_pct'])}",
        f"pe_ratio={format_number(valuation['pe_ratio'], 2)}",
        f"pb_ratio={format_number(valuation['pb_ratio'], 2)}",
        f"ai_keywords={'、'.join(keywords) if keywords else 'NA'}",
        f"news_count={len(news)}",
    ]
    if warnings:
        raw_metrics.append("warnings=" + "｜".join(warnings))

    return {
        "generated_at": datetime.now(
            ZoneInfo("Asia/Taipei")
        ).isoformat(timespec="seconds"),
        "score_version": VERSION,
        "stock_id": match.stock_id,
        "stock_name": match.stock_name,
        "confidence_level": confidence,
        "suggested_industry_score": industry_score,
        "industry_reason": make_industry_reason(
            match.local,
            industry_score,
        ),
        "suggested_growth_score": growth_score,
        "growth_reason": make_growth_reason(revenue, growth_score),
        "suggested_ai_score": ai_score,
        "ai_reason": make_ai_reason(match.local, keywords, ai_score),
        "suggested_valuation_score": valuation_score,
        "valuation_reason": make_valuation_reason(
            valuation["pe_ratio"],
            growth_score,
            valuation_score,
        ),
        "suggested_price_risk_score": price_risk_score,
        "price_risk_reason": make_price_risk_reason(
            price_history,
            price_risk_score,
        ),
        "raw_metrics_summary": "；".join(raw_metrics),
        "source_count": len(all_urls),
        "source_urls": " | ".join(all_urls),
    }


def write_suggestions(
    rows: Iterable[dict[str, str | int]],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def migrate_legacy_row(row: dict[str, str]) -> dict[str, str | int]:
    legacy_reason = (
        "舊版資料未保存此分數理由，信心標示為低；"
        "請重新執行 fetch_stock_info.py 更新。"
    )
    source_urls = clean_text(row.get("source_urls"))
    source_count = len(
        [url for url in source_urls.split(" | ") if clean_text(url)]
    )
    return {
        "generated_at": clean_text(row.get("generated_at")),
        "score_version": clean_text(row.get("score_version")) or "legacy",
        "stock_id": clean_text(row.get("stock_id")),
        "stock_name": clean_text(row.get("stock_name")),
        "confidence_level": "低",
        "suggested_industry_score": clean_text(
            row.get("suggested_industry_score")
        ),
        "industry_reason": clean_text(row.get("industry_reason"))
        or legacy_reason,
        "suggested_growth_score": clean_text(
            row.get("suggested_growth_score")
        ),
        "growth_reason": clean_text(row.get("growth_reason"))
        or legacy_reason,
        "suggested_ai_score": clean_text(row.get("suggested_ai_score")),
        "ai_reason": clean_text(row.get("ai_reason")) or legacy_reason,
        "suggested_valuation_score": clean_text(
            row.get("suggested_valuation_score")
        ),
        "valuation_reason": clean_text(row.get("valuation_reason"))
        or legacy_reason,
        "suggested_price_risk_score": clean_text(
            row.get("suggested_price_risk_score")
        ),
        "price_risk_reason": clean_text(row.get("price_risk_reason"))
        or legacy_reason,
        "raw_metrics_summary": clean_text(row.get("raw_metrics_summary"))
        or clean_text(row.get("evidence_summary"))
        or "舊版未保存原始指標",
        "source_count": clean_text(row.get("source_count"))
        or source_count,
        "source_urls": source_urls,
    }


def upsert_suggestion(
    suggestion: dict[str, str | int],
    path: Path,
) -> None:
    rows: list[dict[str, str | int]] = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = tuple(reader.fieldnames or ())
            existing_rows = [dict(row) for row in reader]
            if all(field in headers for field in OUTPUT_FIELDS):
                rows = existing_rows
            else:
                rows = [
                    migrate_legacy_row(row)
                    for row in existing_rows
                    if clean_text(row.get("stock_id"))
                ]

    rows = [
        row
        for row in rows
        if clean_text(row.get("stock_id")) != str(suggestion["stock_id"])
    ]
    rows.append(suggestion)
    rows.sort(key=lambda row: clean_text(row.get("stock_id")))
    write_suggestions(rows, path)


def fetch_suggestion(
    query: str,
    stocks_path: Path,
    timeout: int,
) -> dict[str, str | int]:
    warnings: list[str] = []
    twse_companies = safe_fetch_json(TWSE_COMPANY_URL, timeout, warnings)
    tpex_companies = safe_fetch_json(TPEX_COMPANY_URL, timeout, warnings)
    twse_list = twse_companies if isinstance(twse_companies, list) else []
    tpex_list = tpex_companies if isinstance(tpex_companies, list) else []

    match = resolve_company(
        query,
        load_local_stocks(stocks_path),
        twse_list,
        tpex_list,
    )

    revenue_url = (
        TWSE_REVENUE_URL if match.market == "TWSE" else TPEX_REVENUE_URL
    )
    revenue_data = safe_fetch_json(revenue_url, timeout, warnings)
    revenue_records = revenue_data if isinstance(revenue_data, list) else []
    revenue = fetch_revenue_info(match.stock_id, revenue_records)

    twse_valuation = safe_fetch_json(TWSE_VALUATION_URL, timeout, warnings)
    tpex_valuation = safe_fetch_json(TPEX_VALUATION_URL, timeout, warnings)
    valuation = fetch_valuation_info(
        match,
        twse_valuation,
        tpex_valuation,
    )

    price_history, price_url = fetch_price_history(match, timeout, warnings)
    if price_history["latest"] is None and valuation["price"] is not None:
        price_history["latest"] = float(valuation["price"])
    if match.market == "TPEx" and price_history["latest"] is None:
        tpex_prices = safe_fetch_json(TPEX_PRICE_URL, timeout, warnings)
        price_history["latest"] = fetch_tpex_price(match.stock_id, tpex_prices)

    news, news_url = fetch_news(match.stock_name, timeout, warnings)

    source_urls = [
        TWSE_COMPANY_URL if match.market == "TWSE" else TPEX_COMPANY_URL,
        revenue_url,
        TWSE_VALUATION_URL
        if match.market == "TWSE"
        else TPEX_VALUATION_URL,
        price_url,
        news_url,
    ]
    return build_suggestion(
        match,
        revenue,
        valuation,
        price_history,
        news,
        warnings,
        source_urls,
    )


def build_parser() -> argparse.ArgumentParser:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "抓取公開資料並產生建議分數；不會覆蓋 stocks.csv。"
        )
    )
    parser.add_argument(
        "query",
        nargs="+",
        help="股票代號或名稱，例如 2330、台積電、緯穎",
    )
    parser.add_argument(
        "--stocks",
        type=Path,
        default=script_dir / "stocks.csv",
        help="本機觀察清單路徑",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=script_dir / "suggested_scores.csv",
        help="建議分數輸出路徑",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="單一網路請求逾時秒數",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    query = " ".join(args.query).strip()
    try:
        suggestion = fetch_suggestion(
            query,
            args.stocks,
            max(3, args.timeout),
        )
        upsert_suggestion(suggestion, args.output)
    except (FetchError, OSError, csv.Error) as exc:
        print(f"錯誤：{exc}", file=sys.stderr)
        return 1

    print(f"完成（v{VERSION}）：{suggestion['stock_id']} {suggestion['stock_name']}")
    print(
        "建議分數："
        f"產業 {suggestion['suggested_industry_score']}、"
        f"成長 {suggestion['suggested_growth_score']}、"
        f"AI {suggestion['suggested_ai_score']}、"
        f"估值 {suggestion['suggested_valuation_score']}、"
        f"價格風險 {suggestion['suggested_price_risk_score']}"
    )
    print(f"輸出：{args.output.resolve()}")
    print("stocks.csv 未被修改；請人工確認後再採用建議分數。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
