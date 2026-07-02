#!/usr/bin/env python3
"""台股 AI 選股查詢與研究輔助工具 v1.0 Streamlit 介面。"""

from __future__ import annotations

import hashlib
import html
import importlib
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

import action_engine as action_engine_module


# Streamlit 會在同一個 Python 行程內重跑頁面，需同步重載本機研究規則。
action_engine_module = importlib.reload(action_engine_module)
ResearchResult = action_engine_module.ResearchResult
decide_research = action_engine_module.decide_research


APP_VERSION = "1.0.5"
APP_DIR = Path(__file__).resolve().parent
SUMMARY_PATH = APP_DIR / "decision_summary.csv"
SUGGESTED_PATH = APP_DIR / "suggested_scores.csv"
STOCKS_PATH = APP_DIR / "stocks.csv"
WATCHLIST_PATH = APP_DIR / "watchlist.csv"
APPLY_LOG_PATH = APP_DIR / "apply_log.csv"
SCORE_SCRIPT = APP_DIR / "score_stocks.py"
FETCH_SCRIPT = APP_DIR / "fetch_stock_info.py"


def environment_flag(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        try:
            raw_value = st.secrets.get(name)
        except StreamlitSecretNotFoundError:
            raw_value = None
    if raw_value is None:
        return default
    return str(raw_value).strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
    }


PUBLIC_MODE = environment_flag("PUBLIC_MODE", default=True)
PUBLIC_MODE_NOTICE = "公開版僅供研究展示，操作不會永久保存。"
PUBLIC_WATCHLIST_SESSION_KEY = "public_mode_watchlist"

PAGES = (
    "股票研究",
    "我的清單",
)

DECISION_COLUMNS = [
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
]

DASHBOARD_COLUMNS = [
    "stock_id",
    "stock_name",
    "total_score",
    "category",
    "research_decision",
    "research_signal",
    "signal_strength",
    "valuation_score",
    "price_risk_score",
]

DECISION_SCORE_COLUMNS = [
    "total_score",
    "industry_score",
    "growth_score",
    "ai_score",
    "valuation_score",
    "price_risk_score",
]

SUGGESTED_COLUMNS = [
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
]

SUGGESTED_SCORE_COLUMNS = [
    "suggested_industry_score",
    "suggested_growth_score",
    "suggested_ai_score",
    "suggested_valuation_score",
    "suggested_price_risk_score",
]

CURRENT_SCORE_COLUMNS = [
    "industry_score",
    "growth_score",
    "ai_score",
    "valuation_score",
    "price_risk_score",
]

RESEARCH_CONTEXT_COLUMNS = [
    "ai_relevance",
    "research_role",
    "research_note",
]

WATCHLIST_COLUMNS = [
    "stock_id",
    "stock_name",
    "added_at",
    "note",
]

WATCHLIST_VIEW_COLUMNS = [
    "stock_id",
    "stock_name",
    "total_score",
    "industry_score",
    "growth_score",
    "ai_score",
    "valuation_score",
    "price_risk_score",
    "research_decision",
    "research_signal",
    "signal_strength",
    "ai_relevance",
    "data_date",
    "note",
]

WATCHLIST_TABLE_LABELS = {
    "stock_id": "股票代號",
    "stock_name": "公司名稱",
    "total_score": "總分",
    "industry_score": "產業地位分數",
    "growth_score": "成長性分數",
    "ai_score": "AI 長期受益分數",
    "valuation_score": "估值合理性分數",
    "price_risk_score": "股價與籌碼風險分數",
    "research_decision": "研究決策",
    "research_signal": "研究訊號",
    "signal_strength": "強度",
    "ai_relevance": "AI 相關性",
    "data_date": "資料日期",
    "note": "備註",
}

RESEARCH_SIGNAL_LABELS = {
    "consider": "可研究",
    "wait": "等待",
    "watch": "觀察",
    "avoid": "暫避",
}

APPLY_LOG_COLUMNS = [
    "applied_at",
    "stock_id",
    "stock_name",
    "original_industry_score",
    "new_industry_score",
    "original_growth_score",
    "new_growth_score",
    "original_ai_score",
    "new_ai_score",
    "original_valuation_score",
    "new_valuation_score",
    "original_price_risk_score",
    "new_price_risk_score",
    "original_total_score",
    "new_total_score",
    "original_category",
    "new_category",
    "confidence_level",
    "reason_summary",
    "backup_filename",
]

APPLY_LOG_SCORE_COLUMNS = [
    "original_industry_score",
    "new_industry_score",
    "original_growth_score",
    "new_growth_score",
    "original_ai_score",
    "new_ai_score",
    "original_valuation_score",
    "new_valuation_score",
    "original_price_risk_score",
    "new_price_risk_score",
    "original_total_score",
    "new_total_score",
]

SUGGESTED_TO_CURRENT = {
    "suggested_industry_score": "industry_score",
    "suggested_growth_score": "growth_score",
    "suggested_ai_score": "ai_score",
    "suggested_valuation_score": "valuation_score",
    "suggested_price_risk_score": "price_risk_score",
}

SCORE_LIMITS = {
    "industry_score": 25.0,
    "growth_score": 25.0,
    "ai_score": 20.0,
    "valuation_score": 20.0,
    "price_risk_score": 10.0,
}

REVIEW_SCORE_ROWS = [
    (
        "產業地位",
        "industry_score",
        "suggested_industry_score",
        "industry_reason",
    ),
    (
        "成長性",
        "growth_score",
        "suggested_growth_score",
        "growth_reason",
    ),
    (
        "AI 長期受益",
        "ai_score",
        "suggested_ai_score",
        "ai_reason",
    ),
    (
        "估值合理性",
        "valuation_score",
        "suggested_valuation_score",
        "valuation_reason",
    ),
    (
        "股價與籌碼風險",
        "price_risk_score",
        "suggested_price_risk_score",
        "price_risk_reason",
    ),
]

COLUMN_LABELS = {
    "stock_id": "股票代號",
    "stock_name": "公司名稱",
    "total_score": "總分",
    "category": "分類",
    "research_decision": "研究決策",
    "research_signal": "研究訊號",
    "signal_strength": "訊號強度",
    "research_role": "研究定位",
    "valuation_score": "估值分數",
    "price_risk_score": "價格風險",
}

NOT_FOUND_MESSAGE = "找不到此股票，請確認股票名稱或代號是否已加入 stocks.csv"
SAFETY_NOTICE = "本工具僅供研究輔助，不代表投資建議，也不與實際持股連動"
REVIEW_WARNING = SAFETY_NOTICE
APPLY_LOCK = threading.Lock()
WATCHLIST_LOCK = threading.Lock()


@st.cache_data(show_spinner=False)
def load_decision_summary(path_text: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    frame = pd.read_csv(
        Path(path_text),
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")
    missing = [column for column in DECISION_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"decision_summary.csv 缺少欄位：{', '.join(missing)}")

    frame = frame[DECISION_COLUMNS].copy()
    for column in DECISION_SCORE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(
        "total_score",
        ascending=False,
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def load_suggested_scores(path_text: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    frame = pd.read_csv(
        Path(path_text),
        dtype=str,
        encoding="utf-8-sig",
    ).fillna("")
    missing = [column for column in SUGGESTED_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"suggested_scores.csv 缺少欄位：{', '.join(missing)}")

    frame = frame[SUGGESTED_COLUMNS].copy()
    for column in SUGGESTED_SCORE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


@st.cache_data(show_spinner=False)
def load_stocks(path_text: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    frame = pd.read_csv(
        Path(path_text),
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    required = ["stock_id", "stock_name", *CURRENT_SCORE_COLUMNS]
    missing = [column for column in required if column not in frame]
    if missing:
        raise ValueError(f"stocks.csv 缺少欄位：{', '.join(missing)}")
    if frame["stock_id"].astype(str).str.strip().duplicated().any():
        raise ValueError("stocks.csv 的 stock_id 不得重複")

    for column in CURRENT_SCORE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


@st.cache_data(show_spinner=False)
def load_watchlist(path_text: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    frame = pd.read_csv(
        Path(path_text),
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    missing = [column for column in WATCHLIST_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"watchlist.csv 缺少欄位：{', '.join(missing)}")

    frame = frame[WATCHLIST_COLUMNS].copy()
    frame["stock_id"] = frame["stock_id"].astype(str).str.strip()
    if (frame["stock_id"] == "").any():
        raise ValueError("watchlist.csv 的 stock_id 不得空白")
    if frame["stock_id"].duplicated().any():
        raise ValueError("watchlist.csv 的 stock_id 不得重複")
    return frame


@st.cache_data(show_spinner=False)
def load_apply_log(path_text: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    frame = pd.read_csv(
        Path(path_text),
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )
    missing = [column for column in APPLY_LOG_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"apply_log.csv 缺少欄位：{', '.join(missing)}")

    frame = frame[APPLY_LOG_COLUMNS].copy()
    for column in APPLY_LOG_SCORE_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(
        "applied_at",
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)


def clear_data_caches() -> None:
    load_decision_summary.clear()
    load_suggested_scores.clear()
    load_stocks.clear()
    load_watchlist.clear()
    load_apply_log.clear()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_script(
    script: Path,
    *arguments: str,
) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=APP_DIR,
        env=environment,
        capture_output=True,
        check=False,
    )


def process_error(completed: subprocess.CompletedProcess[bytes]) -> str:
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    stdout = completed.stdout.decode("utf-8", errors="replace").strip()
    return stderr or stdout or "未知錯誤"


def fetched_stock_id(completed: subprocess.CompletedProcess[bytes]) -> str:
    output = completed.stdout.decode("utf-8", errors="replace")
    match = re.search(r"完成（v[^）]+）：\s*([0-9A-Za-z.-]+)", output)
    return match.group(1) if match else ""


class SuggestionApplyError(RuntimeError):
    """建議分數無法安全套用。"""


class ResearchFetchError(RuntimeError):
    """連網研究建議無法安全產生。"""


class WatchlistError(RuntimeError):
    """我的清單無法安全更新。"""


def _read_watchlist_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=WATCHLIST_COLUMNS)
    try:
        frame = pd.read_csv(
            path,
            dtype=str,
            encoding="utf-8-sig",
            keep_default_na=False,
        )
    except (OSError, pd.errors.ParserError) as exc:
        raise WatchlistError(f"無法讀取 watchlist.csv：{exc}") from exc
    missing = [column for column in WATCHLIST_COLUMNS if column not in frame]
    if missing:
        raise WatchlistError(
            f"watchlist.csv 缺少欄位：{', '.join(missing)}"
        )
    frame = frame[WATCHLIST_COLUMNS].copy()
    frame["stock_id"] = frame["stock_id"].astype(str).str.strip()
    if (frame["stock_id"] == "").any():
        raise WatchlistError("watchlist.csv 的 stock_id 不得空白")
    if frame["stock_id"].duplicated().any():
        raise WatchlistError("watchlist.csv 的 stock_id 不得重複")
    return frame


def _write_watchlist_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            prefix=".watchlist_",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            frame[WATCHLIST_COLUMNS].to_csv(
                handle,
                index=False,
                lineterminator="\n",
            )
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as exc:
        raise WatchlistError(f"無法更新 watchlist.csv：{exc}") from exc
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def _read_session_watchlist() -> pd.DataFrame:
    rows = st.session_state.get(PUBLIC_WATCHLIST_SESSION_KEY, [])
    frame = pd.DataFrame(rows, columns=WATCHLIST_COLUMNS).fillna("")
    if frame.empty:
        return pd.DataFrame(columns=WATCHLIST_COLUMNS)
    frame["stock_id"] = frame["stock_id"].astype(str).str.strip()
    return frame.drop_duplicates("stock_id", keep="last").reset_index(
        drop=True
    )


def _write_session_watchlist(frame: pd.DataFrame) -> None:
    st.session_state[PUBLIC_WATCHLIST_SESSION_KEY] = frame[
        WATCHLIST_COLUMNS
    ].fillna("").to_dict("records")


def add_to_watchlist(
    stock_id: str,
    stock_name: str,
    *,
    note: str = "",
    path: Path = WATCHLIST_PATH,
    now: datetime | None = None,
) -> bool:
    """加入單一股票；公開版只更新目前 session。"""

    normalized_id = stock_id.strip()
    normalized_name = stock_name.strip()
    if not normalized_id:
        raise WatchlistError("stock_id 不得空白")
    if not normalized_name:
        raise WatchlistError("stock_name 不得空白")

    with WATCHLIST_LOCK:
        frame = (
            _read_session_watchlist()
            if PUBLIC_MODE
            else _read_watchlist_csv(path)
        )
        if normalized_id in set(frame["stock_id"]):
            return False
        added_at = (now or datetime.now().astimezone()).isoformat(
            timespec="seconds"
        )
        new_row = pd.DataFrame(
            [
                {
                    "stock_id": normalized_id,
                    "stock_name": normalized_name,
                    "added_at": added_at,
                    "note": note.strip(),
                }
            ],
            columns=WATCHLIST_COLUMNS,
        )
        updated = pd.concat([frame, new_row], ignore_index=True)
        if PUBLIC_MODE:
            _write_session_watchlist(updated)
        else:
            _write_watchlist_csv(updated, path)
        return True


def remove_from_watchlist(
    stock_id: str,
    *,
    path: Path = WATCHLIST_PATH,
) -> bool:
    """移出單一股票；公開版只更新目前 session。"""

    normalized_id = stock_id.strip()
    if not normalized_id:
        raise WatchlistError("stock_id 不得空白")

    with WATCHLIST_LOCK:
        frame = (
            _read_session_watchlist()
            if PUBLIC_MODE
            else _read_watchlist_csv(path)
        )
        keep = frame["stock_id"] != normalized_id
        if keep.all():
            return False
        updated = frame.loc[keep].reset_index(drop=True)
        if PUBLIC_MODE:
            _write_session_watchlist(updated)
        else:
            _write_watchlist_csv(updated, path)
        return True


def generate_research_suggestion(
    query: str,
    *,
    stocks_path: Path = STOCKS_PATH,
    suggested_path: Path = SUGGESTED_PATH,
    fetch_script: Path = FETCH_SCRIPT,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """執行連網研究腳本，並確認研究股票池未被修改。"""

    normalized_query = query.strip()
    if not normalized_query:
        raise ResearchFetchError("請先輸入股票代號或名稱。")
    if not stocks_path.exists():
        raise ResearchFetchError(f"找不到 stocks.csv：{stocks_path}")

    before_hash = file_hash(stocks_path)
    fetch_runner = runner or run_script
    if PUBLIC_MODE:
        try:
            with tempfile.TemporaryDirectory(
                prefix="public_stock_research_"
            ) as temporary_dir:
                safe_stocks_path = Path(temporary_dir) / "stocks.csv"
                shutil.copy2(stocks_path, safe_stocks_path)
                completed = fetch_runner(
                    fetch_script,
                    normalized_query,
                    "--stocks",
                    str(safe_stocks_path),
                    "--output",
                    str(suggested_path),
                )
        except OSError as exc:
            raise ResearchFetchError(
                f"無法建立公開研究用暫存資料：{exc}"
            ) from exc
    else:
        completed = fetch_runner(
            fetch_script,
            normalized_query,
            "--stocks",
            str(stocks_path),
            "--output",
            str(suggested_path),
        )
    after_hash = file_hash(stocks_path)
    if before_hash != after_hash:
        raise ResearchFetchError(
            "安全檢查失敗：stocks.csv 在連網研究期間發生變動，"
            "請立即人工檢查。"
        )
    if completed.returncode != 0:
        raise ResearchFetchError(
            f"研究建議產生失敗：{process_error(completed)}"
        )
    if not suggested_path.exists() or suggested_path.stat().st_size == 0:
        raise ResearchFetchError(
            "研究腳本未產生有效的 suggested_scores.csv。"
        )
    return completed


def _load_apply_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        raise SuggestionApplyError(f"找不到 {label}：{path.name}")
    try:
        return pd.read_csv(
            path,
            dtype=str,
            encoding="utf-8-sig",
            keep_default_na=False,
        )
    except (OSError, pd.errors.ParserError) as exc:
        raise SuggestionApplyError(f"無法讀取 {label}：{exc}") from exc


def _validated_suggested_scores(row: pd.Series) -> dict[str, str]:
    values: dict[str, str] = {}
    for suggested_column, current_column in SUGGESTED_TO_CURRENT.items():
        raw = str(row.get(suggested_column, "")).strip()
        try:
            value = float(raw)
        except ValueError as exc:
            raise SuggestionApplyError(
                f"{suggested_column} 缺漏或不是數字，不能套用"
            ) from exc
        maximum = SCORE_LIMITS[current_column]
        if not math.isfinite(value) or not 0.0 <= value <= maximum:
            raise SuggestionApplyError(
                f"{suggested_column} 必須介於 0–{maximum:g}"
            )
        values[current_column] = f"{value:g}"
    return values


def _score_state(row: pd.Series) -> tuple[dict[str, str], str, str]:
    scores: dict[str, str] = {}
    numeric_values: list[float] = []
    complete = True
    for column in CURRENT_SCORE_COLUMNS:
        raw = str(row.get(column, "")).strip()
        try:
            value = float(raw)
        except ValueError:
            scores[column] = ""
            complete = False
            continue
        if not math.isfinite(value):
            scores[column] = ""
            complete = False
            continue
        scores[column] = f"{value:g}"
        numeric_values.append(value)

    if not complete or len(numeric_values) != len(CURRENT_SCORE_COLUMNS):
        return scores, "", "分數資料不足"

    total = sum(numeric_values)
    if total >= 80:
        category = "高研究吸引力"
    elif total >= 65:
        category = "值得持續研究"
    elif total >= 50:
        category = "觀察追蹤"
    else:
        category = "低優先或排除"
    return scores, f"{total:g}", category


def _reason_summary(row: pd.Series) -> str:
    parts = []
    for label, _, _, reason_column in REVIEW_SCORE_ROWS:
        reason = " ".join(
            research_wording(row.get(reason_column, "")).split()
        )
        parts.append(f"{label}：{reason or '理由資料不足'}")
    return "｜".join(parts)


def _existing_apply_log(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=APPLY_LOG_COLUMNS)
    frame = _load_apply_csv(path, "apply_log.csv")
    missing = [column for column in APPLY_LOG_COLUMNS if column not in frame]
    if missing:
        raise SuggestionApplyError(
            f"apply_log.csv 缺少欄位：{', '.join(missing)}"
        )
    return frame[APPLY_LOG_COLUMNS].copy()


def _restore_file(path: Path, original: bytes | None) -> None:
    if original is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(original)


def apply_suggestion_to_stocks(
    stock_id: str,
    *,
    stocks_path: Path = STOCKS_PATH,
    suggested_path: Path = SUGGESTED_PATH,
    summary_path: Path = SUMMARY_PATH,
    apply_log_path: Path = APPLY_LOG_PATH,
    score_script: Path = SCORE_SCRIPT,
    now: datetime | None = None,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] | None = None,
) -> Path:
    """備份後只更新指定股票，成功重評分並寫入套用紀錄。"""

    if PUBLIC_MODE:
        raise SuggestionApplyError(
            "公開部署模式不允許修改 stocks.csv 或套用研究分數。"
        )

    target_id = stock_id.strip()
    if not target_id:
        raise SuggestionApplyError("stock_id 不得空白")

    with APPLY_LOCK:
        stocks = _load_apply_csv(stocks_path, "stocks.csv")
        suggestions = _load_apply_csv(suggested_path, "suggested_scores.csv")

        required_stock_columns = ["stock_id", *CURRENT_SCORE_COLUMNS]
        required_suggested_columns = [
            "stock_id",
            *SUGGESTED_TO_CURRENT.keys(),
        ]
        missing_stocks = [
            column for column in required_stock_columns if column not in stocks
        ]
        missing_suggestions = [
            column
            for column in required_suggested_columns
            if column not in suggestions
        ]
        if missing_stocks:
            raise SuggestionApplyError(
                f"stocks.csv 缺少欄位：{', '.join(missing_stocks)}"
            )
        if missing_suggestions:
            raise SuggestionApplyError(
                "suggested_scores.csv 缺少欄位："
                + ", ".join(missing_suggestions)
            )

        stock_matches = stocks.index[
            stocks["stock_id"].astype(str).str.strip() == target_id
        ].tolist()
        suggestion_matches = suggestions.index[
            suggestions["stock_id"].astype(str).str.strip() == target_id
        ].tolist()
        if len(stock_matches) != 1:
            raise SuggestionApplyError(
                f"stocks.csv 必須恰好有一筆 stock_id={target_id}"
            )
        if len(suggestion_matches) != 1:
            raise SuggestionApplyError(
                f"suggested_scores.csv 必須恰好有一筆 stock_id={target_id}"
            )

        stock_row = stocks.loc[stock_matches[0]]
        suggestion_row = suggestions.loc[suggestion_matches[0]]
        updates = _validated_suggested_scores(suggestion_row)
        original_scores, original_total, original_category = _score_state(
            stock_row
        )
        operation_time = now or datetime.now().astimezone()
        timestamp = operation_time.strftime("%Y%m%d_%H%M%S")
        backup_path = stocks_path.with_name(
            f"stocks_backup_{timestamp}.csv"
        )
        if backup_path.exists():
            raise SuggestionApplyError(
                f"備份檔已存在：{backup_path.name}，請稍後再試"
            )

        try:
            shutil.copy2(stocks_path, backup_path)
        except OSError as exc:
            raise SuggestionApplyError(f"無法建立備份：{exc}") from exc

        updated = stocks.copy()
        stock_index = stock_matches[0]
        for column, value in updates.items():
            updated.at[stock_index, column] = value

        other_rows = stocks.index != stock_index
        if not updated.loc[other_rows].equals(stocks.loc[other_rows]):
            raise SuggestionApplyError("安全檢查失敗：偵測到其他股票被修改")

        temporary_stocks: Path | None = None
        temporary_summary: Path | None = None
        temporary_log: Path | None = None
        stocks_replaced = False
        summary_replaced = False
        log_replaced = False
        summary_original = (
            summary_path.read_bytes() if summary_path.exists() else None
        )
        log_original = (
            apply_log_path.read_bytes() if apply_log_path.exists() else None
        )
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8-sig",
                newline="",
                prefix=".stocks_",
                suffix=".tmp",
                dir=stocks_path.parent,
                delete=False,
            ) as handle:
                temporary_stocks = Path(handle.name)
                updated.to_csv(handle, index=False, lineterminator="\n")

            os.replace(temporary_stocks, stocks_path)
            temporary_stocks = None
            stocks_replaced = True

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".decision_summary_",
                suffix=".tmp",
                dir=summary_path.parent,
                delete=False,
            ) as handle:
                temporary_summary = Path(handle.name)

            score_runner = runner or run_script
            completed = score_runner(
                score_script,
                "--input",
                str(stocks_path),
                "--output",
                str(temporary_summary),
            )
            if completed.returncode != 0:
                raise SuggestionApplyError(
                    f"重新評分失敗：{process_error(completed)}"
                )
            if not temporary_summary.exists() or temporary_summary.stat().st_size == 0:
                raise SuggestionApplyError("重新評分未產生有效的決策摘要")

            new_summary = _load_apply_csv(
                temporary_summary,
                "重新評分結果",
            )
            summary_matches = new_summary.index[
                new_summary["stock_id"].astype(str).str.strip() == target_id
            ].tolist()
            if len(summary_matches) != 1:
                raise SuggestionApplyError(
                    f"重新評分結果必須恰好有一筆 stock_id={target_id}"
                )
            new_summary_row = new_summary.loc[summary_matches[0]]
            new_scores, calculated_total, calculated_category = _score_state(
                new_summary_row
            )
            new_total = str(
                new_summary_row.get("total_score", calculated_total)
            ).strip()
            new_category = str(
                new_summary_row.get("category", calculated_category)
            ).strip()

            log_row: dict[str, str] = {
                "applied_at": operation_time.isoformat(timespec="seconds"),
                "stock_id": target_id,
                "stock_name": str(stock_row.get("stock_name", "")).strip(),
                "original_total_score": original_total,
                "new_total_score": new_total,
                "original_category": original_category,
                "new_category": new_category,
                "confidence_level": str(
                    suggestion_row.get("confidence_level", "")
                ).strip(),
                "reason_summary": _reason_summary(suggestion_row),
                "backup_filename": backup_path.name,
            }
            for column in CURRENT_SCORE_COLUMNS:
                log_row[f"original_{column}"] = original_scores[column]
                log_row[f"new_{column}"] = new_scores[column]

            apply_log = pd.concat(
                [
                    _existing_apply_log(apply_log_path),
                    pd.DataFrame([log_row], columns=APPLY_LOG_COLUMNS),
                ],
                ignore_index=True,
            )
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8-sig",
                newline="",
                prefix=".apply_log_",
                suffix=".tmp",
                dir=apply_log_path.parent,
                delete=False,
            ) as handle:
                temporary_log = Path(handle.name)
                apply_log.to_csv(handle, index=False, lineterminator="\n")

            os.replace(temporary_summary, summary_path)
            temporary_summary = None
            summary_replaced = True
            os.replace(temporary_log, apply_log_path)
            temporary_log = None
            log_replaced = True
            return backup_path
        except Exception as exc:
            if stocks_replaced:
                shutil.copy2(backup_path, stocks_path)
            if summary_replaced:
                _restore_file(summary_path, summary_original)
            if log_replaced:
                _restore_file(apply_log_path, log_original)
            if isinstance(exc, SuggestionApplyError):
                raise
            raise SuggestionApplyError(f"套用建議分數失敗：{exc}") from exc
        finally:
            for temporary_path in (
                temporary_stocks,
                temporary_summary,
                temporary_log,
            ):
                if temporary_path and temporary_path.exists():
                    temporary_path.unlink()


def read_decision_frame() -> pd.DataFrame | None:
    if not SUMMARY_PATH.exists():
        st.error("找不到 decision_summary.csv，請先重新產生摘要。")
        return None
    try:
        return load_decision_summary(
            str(SUMMARY_PATH),
            SUMMARY_PATH.stat().st_mtime_ns,
        )
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"無法讀取 decision_summary.csv：{exc}")
        return None


def read_suggested_frame() -> pd.DataFrame | None:
    if not SUGGESTED_PATH.exists():
        return None
    try:
        return load_suggested_scores(
            str(SUGGESTED_PATH),
            SUGGESTED_PATH.stat().st_mtime_ns,
        )
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"無法讀取 suggested_scores.csv：{exc}")
        return None


def read_stocks_frame() -> pd.DataFrame | None:
    if not STOCKS_PATH.exists():
        st.error("找不到 stocks.csv。")
        return None
    try:
        return load_stocks(
            str(STOCKS_PATH),
            STOCKS_PATH.stat().st_mtime_ns,
        )
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"無法讀取 stocks.csv：{exc}")
        return None


def read_watchlist_frame() -> pd.DataFrame | None:
    if PUBLIC_MODE:
        return _read_session_watchlist()

    if not WATCHLIST_PATH.exists():
        try:
            _write_watchlist_csv(
                pd.DataFrame(columns=WATCHLIST_COLUMNS),
                WATCHLIST_PATH,
            )
        except WatchlistError as exc:
            st.error(str(exc))
            return None
    try:
        return load_watchlist(
            str(WATCHLIST_PATH),
            WATCHLIST_PATH.stat().st_mtime_ns,
        )
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"無法讀取 watchlist.csv：{exc}")
        return None


def read_apply_log_frame() -> pd.DataFrame | None:
    if not APPLY_LOG_PATH.exists():
        st.error("找不到 apply_log.csv。")
        return None
    try:
        return load_apply_log(
            str(APPLY_LOG_PATH),
            APPLY_LOG_PATH.stat().st_mtime_ns,
        )
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"無法讀取 apply_log.csv：{exc}")
        return None


def find_exact_stock(frame: pd.DataFrame, query: str) -> pd.DataFrame:
    key = query.strip().casefold()
    if not key:
        return frame.iloc[0:0]
    stock_ids = frame["stock_id"].astype(str).str.strip().str.casefold()
    stock_names = frame["stock_name"].astype(str).str.strip().str.casefold()
    return frame[(stock_ids == key) | (stock_names == key)]


def find_stock_matches(frame: pd.DataFrame, query: str) -> pd.DataFrame:
    exact = find_exact_stock(frame, query)
    if not exact.empty:
        return exact
    return filter_dashboard(frame, query)


def filter_dashboard(frame: pd.DataFrame, query: str) -> pd.DataFrame:
    key = query.strip().casefold()
    if not key:
        return frame
    stock_ids = frame["stock_id"].astype(str).str.casefold()
    stock_names = frame["stock_name"].astype(str).str.casefold()
    return frame[
        stock_ids.str.contains(key, regex=False)
        | stock_names.str.contains(key, regex=False)
    ]


def filter_research_summary(
    frame: pd.DataFrame,
    *,
    query: str = "",
    research_decisions: tuple[str, ...] = (),
    research_signals: tuple[str, ...] = (),
    signal_strengths: tuple[str, ...] = (),
    ai_relevances: tuple[str, ...] = (),
    score_range: tuple[float, float] = (0.0, 100.0),
) -> pd.DataFrame:
    """套用搜尋與研究條件，並維持總分由高到低排序。"""

    filtered = filter_dashboard(frame, query)
    for column, selected in (
        ("research_decision", research_decisions),
        ("research_signal", research_signals),
        ("signal_strength", signal_strengths),
        ("ai_relevance", ai_relevances),
    ):
        if selected:
            filtered = filtered[filtered[column].isin(selected)]

    minimum, maximum = score_range
    filtered = filtered[
        filtered["total_score"].between(minimum, maximum, inclusive="both")
    ]
    return filtered.sort_values(
        "total_score",
        ascending=False,
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)


def filter_options(frame: pd.DataFrame, column: str) -> list[str]:
    values = {
        str(value).strip()
        for value in frame[column]
        if str(value).strip()
    }
    return sorted(values)


def research_signal_label(value: object) -> str:
    text = str(value)
    return RESEARCH_SIGNAL_LABELS.get(text, text)


def build_watchlist_view(
    watchlist: pd.DataFrame,
    summary: pd.DataFrame,
) -> pd.DataFrame:
    """以我的清單為主表，補上現有研究摘要。"""

    research_columns = [
        "stock_id",
        "stock_name",
        "total_score",
        "industry_score",
        "growth_score",
        "ai_score",
        "valuation_score",
        "price_risk_score",
        "research_decision",
        "research_signal",
        "signal_strength",
        "ai_relevance",
        "data_date",
    ]
    research = summary[research_columns].copy().rename(
        columns={"stock_name": "research_stock_name"}
    )
    merged = watchlist.merge(
        research,
        on="stock_id",
        how="left",
        validate="one_to_one",
    )
    merged["stock_name"] = merged["research_stock_name"].where(
        merged["research_stock_name"].fillna("").astype(str).str.strip() != "",
        merged["stock_name"],
    )
    merged["_sort_score"] = pd.to_numeric(
        merged["total_score"],
        errors="coerce",
    )
    merged = merged.sort_values(
        "_sort_score",
        ascending=False,
        na_position="last",
        kind="stable",
    )
    missing_text = "尚未建立研究資料"
    for column in (
        "total_score",
        "industry_score",
        "growth_score",
        "ai_score",
        "valuation_score",
        "price_risk_score",
        "research_decision",
        "research_signal",
        "signal_strength",
        "ai_relevance",
        "data_date",
    ):
        merged[column] = merged[column].where(
            merged[column].notna()
            & (merged[column].astype(str).str.strip() != ""),
            missing_text,
        )
    return merged[WATCHLIST_VIEW_COLUMNS].reset_index(drop=True)


def filter_watchlist_view(
    frame: pd.DataFrame,
    *,
    query: str = "",
    research_decisions: tuple[str, ...] = (),
    research_signals: tuple[str, ...] = (),
    signal_strengths: tuple[str, ...] = (),
    ai_relevances: tuple[str, ...] = (),
) -> pd.DataFrame:
    filtered = filter_dashboard(frame, query)
    for column, selected in (
        ("research_decision", research_decisions),
        ("research_signal", research_signals),
        ("signal_strength", signal_strengths),
        ("ai_relevance", ai_relevances),
    ):
        if selected:
            filtered = filtered[filtered[column].isin(selected)]
    return filtered.reset_index(drop=True)


def format_score(value: object) -> str:
    if pd.isna(value) or value == "":
        return "NA"
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def research_wording(value: object) -> str:
    legacy_position_term = "不適合大幅" + "加" + "碼"
    return str(value).replace(
        legacy_position_term,
        "宜等待回檔或風險改善",
    )


def render_score_cards(cards: list[tuple[str, object]]) -> None:
    for index in range(0, len(cards), 2):
        pair = cards[index : index + 2]
        columns = st.columns(len(pair))
        for column, (label, value) in zip(columns, pair):
            with column:
                with st.container(border=True):
                    st.metric(label, format_score(value))


def render_stock_detail(
    row: pd.Series,
    *,
    show_title: bool = True,
) -> None:
    with st.container(border=True):
        if show_title:
            st.subheader(f"{row['stock_id']}　{row['stock_name']}")
        st.caption(f"資料日期：{row['data_date']}")
        total_column, category_column = st.columns(2)
        total_column.metric("總分", format_score(row["total_score"]))
        category_column.metric("分類", row["category"] or "—")
        st.success(
            f"研究決策：{row['research_decision'] or '—'}｜"
            f"{row['research_signal'] or '—'}｜"
            f"強度 {row['signal_strength'] or '—'}"
        )
        st.write(f"**研究理由：** {row['research_reason'] or '—'}")

    st.markdown("#### 五項分數")
    render_score_cards(
        [
            ("產業地位", row["industry_score"]),
            ("成長性", row["growth_score"]),
            ("AI 長期受益", row["ai_score"]),
            ("估值合理性", row["valuation_score"]),
            ("股價與籌碼風險", row["price_risk_score"]),
        ]
    )

    with st.container(border=True):
        st.markdown("#### 公司定位")
        st.write(f"**產業位置：** {row['industry_position'] or '—'}")
        st.write(f"**AI 相關性：** {row['ai_relevance'] or '—'}")
        st.write(f"**是否瓶頸環節：** {row['is_bottleneck'] or '—'}")

    with st.container(border=True):
        st.markdown("#### 研究定位")
        st.write(f"**研究角色：** {row['research_role'] or '—'}")
        st.write(f"**研究備註：** {row['research_note'] or '—'}")

    with st.expander("風險備註", expanded=False):
        st.write(f"**風險備註：** {row['risk_notes'] or '—'}")


def render_research_summary(
    local_row: pd.Series | None,
    suggestion_row: pd.Series | None,
) -> None:
    """將本地研究結論與連網信心等級合併為單一摘要卡。"""

    with st.container(border=True):
        data_date = (
            local_row["data_date"] if local_row is not None else "尚未建立研究資料"
        )
        total_score = (
            format_score(local_row["total_score"])
            if local_row is not None
            else "—"
        )
        confidence_level = (
            suggestion_row["confidence_level"] or "—"
            if suggestion_row is not None
            else "尚未連網更新"
        )
        signal_strength = (
            local_row["signal_strength"] or "—"
            if local_row is not None
            else "—"
        )
        research_decision = (
            local_row["research_decision"] or "尚未建立研究資料"
            if local_row is not None
            else "尚未建立研究資料"
        )
        research_signal = (
            research_signal_label(local_row["research_signal"])
            if local_row is not None
            else "—"
        )
        research_reason = (
            local_row["research_reason"] or "尚未建立研究資料"
            if local_row is not None
            else "尚未建立研究資料"
        )

        st.caption(f"資料日期：{data_date}")
        score_column, confidence_column, strength_column = st.columns(3)
        score_column.metric("總分", total_score)
        confidence_column.metric("信心等級", confidence_level)
        strength_column.metric("強度", signal_strength)
        st.success(
            f"研究決策：{research_decision}｜"
            f"研究訊號：{research_signal}"
        )
        st.write(f"**研究理由：** {research_reason}")


def render_research_context(row: pd.Series) -> None:
    """顯示公司定位與風險、研究備註。"""

    with st.container(border=True):
        st.markdown("#### 公司定位")
        st.write(f"**產業位置：** {row['industry_position'] or '—'}")
        st.write(f"**AI 相關性：** {row['ai_relevance'] or '—'}")
        st.write(f"**是否瓶頸環節：** {row['is_bottleneck'] or '—'}")

    with st.container(border=True):
        st.markdown("#### 風險與研究備註")
        st.write(f"**風險備註：** {row['risk_notes'] or '—'}")
        st.write(f"**研究備註：** {row['research_note'] or '—'}")


def source_links(source_text: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    for index, raw_url in enumerate(source_text.split(" | "), start=1):
        url = raw_url.strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        path_label = parsed.path.rstrip("/").split("/")[-1]
        label = parsed.netloc + (f"／{path_label}" if path_label else "")
        links.append((f"來源 {index}：{label}", url))
    return links


def render_suggested_detail(row: pd.Series) -> None:
    suggestion_cards = [
        (
            "產業地位建議",
            row["suggested_industry_score"],
            row["industry_reason"],
        ),
        (
            "成長性建議",
            row["suggested_growth_score"],
            row["growth_reason"],
        ),
        (
            "AI 長期受益建議",
            row["suggested_ai_score"],
            row["ai_reason"],
        ),
        (
            "估值合理性建議",
            row["suggested_valuation_score"],
            row["valuation_reason"],
        ),
        (
            "股價與籌碼風險建議",
            row["suggested_price_risk_score"],
            row["price_risk_reason"],
        ),
    ]
    for label, value, reason in suggestion_cards:
        with st.container(border=True):
            st.metric(label, format_score(value))
            st.write(research_wording(reason) or "理由資料不足")


def render_suggested_appendix(row: pd.Series) -> None:
    """將原始指標與資料來源集中放在研究頁底部。"""

    with st.expander("原始指標摘要", expanded=False):
        st.write(f"**產生時間：** {row['generated_at'] or '—'}")
        st.write(f"**評分版本：** {row['score_version'] or '—'}")
        st.write(row["raw_metrics_summary"] or "無")

    with st.expander("資料來源", expanded=False):
        links = source_links(row["source_urls"])
        if not links:
            st.write("未提供可用來源連結")
        for label, url in links:
            st.markdown(f"- [{label}]({url})")


def build_review_frame(
    stocks: pd.DataFrame,
    suggestions: pd.DataFrame,
) -> pd.DataFrame:
    current = stocks[
        [
            "stock_id",
            "stock_name",
            *CURRENT_SCORE_COLUMNS,
            *RESEARCH_CONTEXT_COLUMNS,
        ]
    ].copy()
    current = current.rename(columns={"stock_name": "current_stock_name"})

    proposed = suggestions.copy()
    proposed = proposed.drop_duplicates("stock_id", keep="last")
    proposed = proposed.rename(
        columns={"stock_name": "suggested_stock_name"}
    )
    merged = proposed.merge(
        current,
        on="stock_id",
        how="left",
        validate="one_to_one",
    )
    merged["stock_name"] = merged["current_stock_name"].where(
        merged["current_stock_name"].astype(str).str.strip() != "",
        merged["suggested_stock_name"],
    )
    return merged[
        merged["current_stock_name"].notna()
        & (merged["current_stock_name"].astype(str).str.strip() != "")
    ].reset_index(drop=True)


def review_comparison(row: pd.Series) -> pd.DataFrame:
    records = []
    for label, current_column, suggested_column, _ in REVIEW_SCORE_ROWS:
        current = row[current_column]
        suggested = row[suggested_column]
        difference = (
            float(suggested) - float(current)
            if not pd.isna(current) and not pd.isna(suggested)
            else math.nan
        )
        records.append(
            {
                "評分項目": label,
                "目前分數": current,
                "建議分數": suggested,
                "變動": difference,
            }
        )
    return pd.DataFrame(records)


def review_research_preview(
    row: pd.Series,
    *,
    use_suggested_scores: bool,
) -> ResearchResult:
    values: dict[str, float | None] = {}
    for current_column in CURRENT_SCORE_COLUMNS:
        source_column = (
            next(
                suggested
                for suggested, current in SUGGESTED_TO_CURRENT.items()
                if current == current_column
            )
            if use_suggested_scores
            else current_column
        )
        raw = row[source_column]
        values[current_column] = (
            None if pd.isna(raw) or raw == "" else float(raw)
        )
    total_score = (
        sum(value for value in values.values() if value is not None)
        if all(value is not None for value in values.values())
        else None
    )
    return decide_research(
        total_score=total_score,
        valuation_score=values["valuation_score"],
        price_risk_score=values["price_risk_score"],
        ai_relevance=row.get("ai_relevance", ""),
        research_role=row.get("research_role", ""),
    )


def render_watchlist_control(
    stock_id: str,
    stock_name: str,
    watchlist: pd.DataFrame,
) -> None:
    in_list = stock_id in set(watchlist["stock_id"].astype(str))
    star = "★" if in_list else "☆"
    st.subheader(f"{star} {stock_id}　{stock_name}")

    current_note = ""
    if in_list:
        matching_rows = watchlist.loc[
            watchlist["stock_id"].astype(str) == stock_id
        ]
        if not matching_rows.empty:
            current_note = str(matching_rows.iloc[-1]["note"])

    note = st.text_input(
        "清單備註",
        value=current_note,
        placeholder="可選填研究追蹤重點",
        key=f"watchlist_note_{stock_id}",
        disabled=in_list,
    )

    if in_list:
        if st.button(
            "移出我的清單",
            key=f"remove_research_{stock_id}",
            width="stretch",
        ):
            try:
                removed = remove_from_watchlist(stock_id)
            except WatchlistError as exc:
                st.error(str(exc))
            else:
                clear_data_caches()
                if removed:
                    st.session_state["research_page_message"] = (
                        f"{stock_id} {stock_name} 已移出我的清單。"
                    )
                st.rerun()
        return

    if st.button(
        "加入我的清單",
        key=f"add_research_{stock_id}",
        type="secondary",
        width="stretch",
    ):
        try:
            added = add_to_watchlist(
                stock_id,
                stock_name,
                note=note,
            )
        except WatchlistError as exc:
            st.error(str(exc))
        else:
            clear_data_caches()
            st.session_state["research_page_message"] = (
                f"{stock_id} {stock_name} "
                + ("已加入我的清單。" if added else "已在我的清單中。")
            )
            st.rerun()


def render_review_workflow(suggestion_row: pd.Series) -> None:
    if PUBLIC_MODE:
        st.info("公開部署模式不提供套用研究分數功能。")
        return

    stocks = read_stocks_frame()
    if stocks is None:
        return
    try:
        review = build_review_frame(
            stocks,
            suggestion_row.to_frame().T,
        )
    except (KeyError, ValueError, pd.errors.MergeError) as exc:
        st.error(f"無法建立審核比較資料：{exc}")
        return
    if review.empty:
        st.info(
            "研究建議已建立，但本地研究資料尚未建立；"
            "目前可先加入我的清單持續追蹤。"
        )
        return

    row = review.iloc[0]
    selected_id = str(row["stock_id"])
    st.markdown("### 目前分數 vs 建議分數")
    comparison = review_comparison(row)
    mobile_rows = []
    for _, comparison_row in comparison.iterrows():
        mobile_rows.append(
            f'<article class="mobile-review-card">'
            f"<strong>{html.escape(str(comparison_row['評分項目']))}</strong>"
            f'<div class="mobile-review-card__scores">'
            f"<span>目前 {html.escape(format_score(comparison_row['目前分數']))}</span>"
            f"<span>建議 {html.escape(format_score(comparison_row['建議分數']))}</span>"
            f"<span>變動 {html.escape(format_score(comparison_row['變動']))}</span>"
            f"</div>"
            f"</article>"
        )
    st.markdown(
        '<div class="mobile-review">' + "".join(mobile_rows) + "</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        comparison,
        hide_index=True,
        width="stretch",
        column_config={
            "評分項目": st.column_config.TextColumn("評分項目"),
            "目前分數": st.column_config.NumberColumn(
                "目前分數",
                format="%.0f",
            ),
            "建議分數": st.column_config.NumberColumn(
                "建議分數",
                format="%.0f",
            ),
            "變動": st.column_config.NumberColumn("變動", format="%+.0f"),
        },
    )

    current_research = review_research_preview(
        row,
        use_suggested_scores=False,
    )
    suggested_research = review_research_preview(
        row,
        use_suggested_scores=True,
    )
    st.markdown("### 套用後研究決策預覽")
    st.info(
        f"目前：{current_research.research_decision}／"
        f"{current_research.research_signal}／"
        f"{current_research.signal_strength}"
        "　→　"
        f"套用後：{suggested_research.research_decision}／"
        f"{suggested_research.research_signal}／"
        f"{suggested_research.signal_strength}"
    )
    st.write(f"**套用後研究理由：** {suggested_research.research_reason}")
    st.caption(
        "人工確認後只更新這檔股票的五項研究分數；"
        "系統會先備份 stocks.csv，再重新產生 decision_summary.csv。"
    )
    if st.button(
        "套用到研究評分資料",
        type="primary",
        width="stretch",
    ):
        try:
            with st.spinner("正在備份、套用研究分數並重新評分…"):
                backup_path = apply_suggestion_to_stocks(selected_id)
        except SuggestionApplyError as exc:
            st.error(str(exc))
        else:
            clear_data_caches()
            st.session_state["research_page_message"] = (
                f"{selected_id} {row['stock_name']} 的研究分數已套用；"
                f"備份檔：{backup_path.name}；"
                "decision_summary.csv 已重新產生。"
            )
            st.rerun()


def render_stock_research_page() -> None:
    st.header("股票研究")
    success_message = st.session_state.pop("research_page_message", "")
    if success_message:
        st.success(success_message)

    query = st.text_input(
        "搜尋股票",
        placeholder="例如：2330、台積電",
        key="stock_research_query",
    ).strip()
    if not query:
        st.caption(
            "輸入本地股票或新股票代號，開始查看研究資料與連網建議。"
        )
        return

    summary = read_decision_frame()
    if summary is None:
        return
    local_matches = find_stock_matches(summary, query)
    local_row: pd.Series | None = None
    if len(local_matches) == 1:
        local_row = local_matches.iloc[0]
    elif len(local_matches) > 1:
        choices = local_matches["stock_id"].astype(str).tolist()
        name_by_id = dict(
            zip(local_matches["stock_id"], local_matches["stock_name"])
        )
        selected_id = st.selectbox(
            "選擇本地研究股票",
            choices,
            format_func=lambda value: f"{value}　{name_by_id[value]}",
            key="local_research_match",
        )
        local_row = local_matches.loc[
            local_matches["stock_id"].astype(str) == selected_id
        ].iloc[0]

    watchlist = read_watchlist_frame()
    if watchlist is None:
        return

    suggestions = read_suggested_frame()
    suggestion_row: pd.Series | None = None
    if suggestions is not None and not suggestions.empty:
        suggestion_lookup = (
            str(local_row["stock_id"]) if local_row is not None else query
        )
        suggestion_matches = find_stock_matches(
            suggestions,
            suggestion_lookup,
        )
        if (
            len(suggestion_matches) != 1
            and st.session_state.get("last_research_query") == query
        ):
            suggestion_matches = find_exact_stock(
                suggestions,
                st.session_state.get("last_research_stock_id", ""),
            )
        if len(suggestion_matches) == 1:
            suggestion_row = suggestion_matches.iloc[0]

    display_row = local_row if local_row is not None else suggestion_row
    if display_row is not None:
        render_watchlist_control(
            str(display_row["stock_id"]),
            str(display_row["stock_name"]),
            watchlist,
        )

    fetch_label = (
        "連網更新研究建議"
        if local_row is not None
        else "連網產生研究建議"
    )
    fetch_query = (
        str(local_row["stock_id"]) if local_row is not None else query
    )
    if st.button(
        fetch_label,
        type="primary",
        width="stretch",
    ):
        try:
            with st.spinner("正在擷取公開資料並產生研究建議…"):
                completed = generate_research_suggestion(fetch_query)
        except ResearchFetchError as exc:
            st.error(str(exc))
        else:
            load_suggested_scores.clear()
            st.session_state["last_research_query"] = query
            st.session_state["last_research_stock_id"] = (
                fetched_stock_id(completed) or fetch_query
            )
            st.session_state["research_page_message"] = (
                "研究建議已產生；請閱讀建議分數與理由。"
            )
            st.rerun()

    if local_row is None:
        st.info("本地研究資料尚未建立，可使用連網研究產生建議分數")

    render_research_summary(local_row, suggestion_row)
    if local_row is not None:
        render_research_context(local_row)
    if suggestion_row is None:
        st.caption("尚未產生這檔股票的連網研究建議。")
    else:
        render_suggested_detail(suggestion_row)
        render_suggested_appendix(suggestion_row)


def render_watchlist_page() -> None:
    st.header("我的清單")
    success_message = st.session_state.pop("watchlist_page_message", "")
    if success_message:
        st.success(success_message)

    watchlist = read_watchlist_frame()
    if watchlist is None:
        return
    if watchlist.empty:
        st.info("尚未加入任何股票，請到股票研究頁按星星加入我的清單。")
        return
    summary = read_decision_frame()
    if summary is None:
        return

    view = build_watchlist_view(watchlist, summary)
    query = st.text_input(
        "搜尋我的清單",
        placeholder="輸入股票代號、名稱或部分關鍵字",
        key="watchlist_search",
    )
    with st.expander("篩選條件", expanded=False):
        decisions = tuple(
            st.multiselect(
                "研究決策",
                filter_options(view, "research_decision"),
                key="watchlist_decision_filter",
            )
        )
        signal_values = filter_options(view, "research_signal")
        signal_by_label = {
            research_signal_label(value): value for value in signal_values
        }
        selected_signal_labels = st.multiselect(
            "研究訊號",
            list(signal_by_label),
            key="watchlist_signal_filter",
        )
        signals = tuple(
            signal_by_label[label] for label in selected_signal_labels
        )
        strengths = tuple(
            st.multiselect(
                "訊號強度",
                filter_options(view, "signal_strength"),
                key="watchlist_strength_filter",
            )
        )
        relevances = tuple(
            st.multiselect(
                "AI 相關性",
                filter_options(view, "ai_relevance"),
                key="watchlist_ai_filter",
            )
        )
    filtered = filter_watchlist_view(
        view,
        query=query,
        research_decisions=decisions,
        research_signals=signals,
        signal_strengths=strengths,
        ai_relevances=relevances,
    )
    if filtered.empty:
        st.warning("沒有符合搜尋與篩選條件的股票。")
        return

    missing_text = "尚未建立研究資料"
    if (filtered["research_decision"] == missing_text).any():
        st.info("部分股票尚未建立研究資料，可回到股票研究頁連網產生研究建議。")

    mobile_cards = []
    for _, row in filtered.iterrows():
        mobile_cards.append(
            f'<article class="mobile-stock-card">'
            f'<div class="mobile-stock-card__top">'
            f"<strong>★ {html.escape(str(row['stock_id']))}　"
            f"{html.escape(str(row['stock_name']))}</strong>"
            f'<span class="mobile-stock-card__score">'
            f"{html.escape(format_score(row['total_score']))}</span>"
            f"</div>"
            f'<div class="mobile-stock-card__decision">'
            f"<strong>{html.escape(str(row['research_decision']))}</strong>"
            f"<span>{html.escape(research_signal_label(row['research_signal']))}／"
            f"{html.escape(str(row['signal_strength']))}</span>"
            f"</div>"
            f'<div class="mobile-stock-card__metrics">'
            f"<span>估值 {html.escape(format_score(row['valuation_score']))}</span>"
            f"<span>價格風險 {html.escape(format_score(row['price_risk_score']))}</span>"
            f"</div>"
            f"</article>"
        )
    st.markdown(
        '<div class="mobile-watchlist">'
        + "".join(mobile_cards)
        + "</div>",
        unsafe_allow_html=True,
    )
    display_table = filtered[WATCHLIST_VIEW_COLUMNS].copy()
    display_table["research_signal"] = display_table[
        "research_signal"
    ].map(research_signal_label)
    display_table = display_table.rename(columns=WATCHLIST_TABLE_LABELS)
    st.dataframe(
        display_table,
        hide_index=True,
        width="stretch",
        height=min(650, 38 * (len(display_table) + 1)),
    )

    st.markdown("### 清單管理")
    for _, row in filtered.iterrows():
        stock_id = str(row["stock_id"])
        stock_name = str(row["stock_name"])
        with st.container(border=True):
            label_column, button_column = st.columns([3, 2])
            label_column.write(f"★ **{stock_id}　{stock_name}**")
            if button_column.button(
                "移出我的清單",
                key=f"remove_watchlist_{stock_id}",
                width="stretch",
            ):
                try:
                    removed = remove_from_watchlist(stock_id)
                except WatchlistError as exc:
                    st.error(str(exc))
                else:
                    clear_data_caches()
                    if removed:
                        st.session_state["watchlist_page_message"] = (
                            f"{stock_id} {stock_name} 已移出我的清單。"
                        )
                    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="台股 AI 選股查詢／研究輔助",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1100px;
            padding-top: 1rem;
            padding-bottom: 2rem;
        }
        .mobile-watchlist,
        .mobile-review {
            display: none;
        }
        @media (max-width: 640px) {
            .block-container {
                padding-left: 0.75rem;
                padding-right: 0.75rem;
            }
            h1 {
                font-size: 2rem !important;
            }
            [data-testid="stDataFrame"] {
                display: none;
            }
            .mobile-watchlist {
                display: grid;
                gap: 0.75rem;
            }
            .mobile-review {
                display: grid;
                gap: 0.6rem;
            }
            .mobile-review-card {
                border: 1px solid rgba(128, 128, 128, 0.35);
                border-radius: 0.75rem;
                padding: 0.8rem;
                background: rgba(128, 128, 128, 0.06);
            }
            .mobile-review-card__scores {
                display: flex;
                flex-wrap: wrap;
                gap: 0.4rem;
                margin-top: 0.5rem;
            }
            .mobile-review-card__scores span {
                border-radius: 999px;
                padding: 0.2rem 0.55rem;
                background: rgba(128, 128, 128, 0.18);
            }
            .mobile-stock-card {
                border: 1px solid rgba(128, 128, 128, 0.35);
                border-radius: 0.75rem;
                padding: 0.85rem;
                background: rgba(128, 128, 128, 0.06);
            }
            .mobile-stock-card__top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 0.5rem;
            }
            .mobile-stock-card__score {
                border-radius: 999px;
                padding: 0.15rem 0.55rem;
                background: #ff4b4b;
                color: white;
                white-space: nowrap;
            }
            .mobile-stock-card__category {
                margin-top: 0.45rem;
                font-weight: 600;
            }
            .mobile-stock-card__decision {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 0.5rem;
                margin-top: 0.45rem;
                padding: 0.45rem 0.6rem;
                border-radius: 0.55rem;
                background: rgba(28, 131, 225, 0.14);
            }
            .mobile-stock-card__decision span {
                white-space: nowrap;
                font-size: 0.85rem;
            }
            .mobile-stock-card__metrics {
                display: flex;
                flex-wrap: wrap;
                gap: 0.45rem;
                margin-top: 0.65rem;
                font-size: 0.9rem;
            }
            .mobile-stock-card__metrics span {
                border-radius: 999px;
                padding: 0.2rem 0.55rem;
                background: rgba(128, 128, 128, 0.18);
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("台股 AI 選股查詢／研究輔助")
    st.caption(
        f"v{APP_VERSION}｜公開部署模式"
    )
    st.warning(SAFETY_NOTICE)
    if PUBLIC_MODE:
        st.info(PUBLIC_MODE_NOTICE)

    page = st.selectbox("功能頁面", PAGES)
    st.divider()

    if page == PAGES[0]:
        render_stock_research_page()
    else:
        render_watchlist_page()


if __name__ == "__main__":
    main()
