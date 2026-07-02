import os
import subprocess
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from streamlit.testing.v1 import AppTest

import app as app_module


PROJECT_DIR = Path(__file__).resolve().parents[1]


def element_tree_text(element) -> str:
    """Collect labels and values from one rendered top-level element."""

    parts = []
    for attribute in ("label", "value"):
        value = getattr(element, attribute, None)
        if value not in (None, ""):
            parts.append(str(value))
    for child in getattr(element, "children", {}).values():
        parts.append(element_tree_text(child))
    return "\n".join(parts)


@contextmanager
def temporary_project_watchlist(rows):
    path = PROJECT_DIR / "watchlist.csv"
    original = path.read_bytes() if path.exists() else None
    pd.DataFrame(rows, columns=app_module.WATCHLIST_COLUMNS).to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
        lineterminator="\n",
    )
    app_module.clear_data_caches()
    try:
        yield
    finally:
        if original is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(original)
        app_module.clear_data_caches()


@contextmanager
def temporary_public_mode(enabled):
    original_mode = app_module.PUBLIC_MODE
    original_environment = os.environ.get("PUBLIC_MODE")
    os.environ["PUBLIC_MODE"] = "true" if enabled else "false"
    app_module.PUBLIC_MODE = enabled
    try:
        yield
    finally:
        app_module.PUBLIC_MODE = original_mode
        if original_environment is None:
            os.environ.pop("PUBLIC_MODE", None)
        else:
            os.environ["PUBLIC_MODE"] = original_environment


class StreamlitAppTests(unittest.TestCase):
    def make_app(self) -> AppTest:
        app = AppTest.from_file(
            str(PROJECT_DIR / "app.py"),
            default_timeout=20,
        )
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_navigation_only_has_v1_pages(self):
        self.assertEqual(app_module.APP_VERSION, "1.0.5")
        self.assertTrue(app_module.PUBLIC_MODE)
        self.assertEqual(app_module.PAGES, ("股票研究", "我的清單"))
        app = self.make_app()
        self.assertEqual(app.selectbox[0].label, "功能頁面")
        self.assertEqual(list(app.selectbox[0].options), list(app_module.PAGES))
        self.assertTrue(
            any(
                app_module.PUBLIC_MODE_NOTICE in item.value
                for item in app.info
            )
        )

    def test_stock_research_page_searches_local_stock(self):
        with temporary_project_watchlist([]):
            app = self.make_app()
            self.assertEqual(app.text_input[0].label, "搜尋股票")
            self.assertEqual(
                app.text_input[0].placeholder,
                "例如：2330、台積電",
            )
            app.text_input[0].input("2330").run()
            self.assertFalse(app.exception)
            self.assertTrue(
                any(
                    "☆ 2330" in item.value and "台積電" in item.value
                    for item in app.subheader
                )
            )
            page_text = "\n".join(item.value for item in app.markdown)
            self.assertNotIn("本地研究資料", page_text)
            self.assertNotIn("連網研究建議", page_text)
            self.assertNotIn("研究定位", page_text)
            self.assertNotIn("研究角色", page_text)
            self.assertIn("研究理由", page_text)
            self.assertTrue(
                any(button.label == "加入我的清單" for button in app.button)
            )
            self.assertTrue(
                any(
                    button.label == "連網更新研究建議"
                    for button in app.button
                )
            )
            self.assertEqual(app.text_input[1].label, "清單備註")
            self.assertEqual(
                [button.label for button in app.button[:2]],
                ["加入我的清單", "連網更新研究建議"],
            )
            metric_labels = {metric.label for metric in app.metric}
            self.assertNotIn("分類", metric_labels)
            self.assertTrue(
                {
                    "產業地位",
                    "成長性",
                    "AI 長期受益",
                    "估值合理性",
                    "股價與籌碼風險",
                }.isdisjoint(metric_labels)
            )

    def test_new_stock_can_start_network_research(self):
        app = self.make_app()
        app.text_input[0].input("2308").run()
        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                "本地研究資料尚未建立" in item.value
                for item in app.info
            )
        )
        self.assertTrue(
            any(
                button.label == "連網產生研究建議"
                for button in app.button
            )
        )
        self.assertTrue(
            any("2308" in item.value for item in app.subheader)
        )

    def test_summary_shows_no_network_update_without_suggestion(self):
        app = self.make_app()
        app.text_input[0].input("3324").run()
        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["信心等級"], "尚未連網更新")

    def test_stock_research_page_hides_comparison_and_apply_controls(self):
        app = self.make_app()
        app.text_input[0].input("2330").run()
        self.assertFalse(app.exception)
        self.assertFalse(app.dataframe)
        page_markdown = [item.value for item in app.markdown]
        page_text = "\n".join(page_markdown)
        self.assertNotIn("目前分數 vs 建議分數", page_text)
        self.assertNotIn("套用後研究決策預覽", page_text)
        self.assertFalse(
            any(
                button.label == "套用到研究評分資料"
                for button in app.button
            )
        )
        self.assertIn("公司定位", page_text)
        self.assertIn("風險與研究備註", page_text)
        self.assertNotIn("研究定位", page_text)
        self.assertEqual(
            [expander.label for expander in app.expander[-2:]],
            ["原始指標摘要", "資料來源"],
        )
        metric_labels = [metric.label for metric in app.metric]
        self.assertEqual(
            metric_labels[:3],
            ["總分", "信心等級", "強度"],
        )
        self.assertEqual(
            metric_labels[3:],
            [
                "產業地位建議",
                "成長性建議",
                "AI 長期受益建議",
                "估值合理性建議",
                "股價與籌碼風險建議",
            ],
        )
        self.assertEqual(len(app.subheader), 1)
        self.assertIn("2330　台積電", app.subheader[0].value)

        top_level = {
            index: element_tree_text(element)
            for index, element in app.main.children.items()
        }

        def top_index(text):
            return next(
                index
                for index, content in top_level.items()
                if text in content
            )

        self.assertEqual(
            top_index("總分"),
            top_index("信心等級"),
        )
        self.assertEqual(
            top_index("信心等級"),
            top_index("強度"),
        )
        self.assertLess(top_index("公司定位"), top_index("產業地位建議"))
        self.assertLess(
            top_index("風險與研究備註"),
            top_index("產業地位建議"),
        )
        suggestion_order = [
            top_index(label)
            for label in (
                "產業地位建議",
                "成長性建議",
                "AI 長期受益建議",
                "估值合理性建議",
                "股價與籌碼風險建議",
                "原始指標摘要",
                "資料來源",
            )
        ]
        self.assertEqual(suggestion_order, sorted(suggestion_order))

    def test_watchlist_page_shows_starred_stock(self):
        rows = [
            {
                "stock_id": "2330",
                "stock_name": "台積電",
                "added_at": "2026-07-02T10:00:00+08:00",
                "note": "核心研究",
            }
        ]
        with temporary_public_mode(False), temporary_project_watchlist(rows):
            app = self.make_app()
            app.selectbox[0].select("我的清單").run()
            self.assertFalse(app.exception)
            table = app.dataframe[0].value
            self.assertEqual(
                list(table.columns),
                list(app_module.WATCHLIST_TABLE_LABELS.values()),
            )
            self.assertNotIn("星號", table.columns)
            self.assertNotIn("分類", table.columns)
            self.assertEqual(str(table.iloc[0]["股票代號"]), "2330")
            self.assertEqual(table.iloc[0]["研究訊號"], "等待")
            self.assertNotIn(
                table.iloc[0]["研究訊號"],
                {"consider", "wait", "watch", "avoid"},
            )
            self.assertTrue(
                any(
                    button.label == "移出我的清單"
                    for button in app.button
                )
            )

    def test_watchlist_page_handles_stock_without_research_data(self):
        rows = [
            {
                "stock_id": "9999",
                "stock_name": "新研究股票",
                "added_at": "2026-07-02T10:00:00+08:00",
                "note": "等待建立資料",
            }
        ]
        with temporary_public_mode(False), temporary_project_watchlist(rows):
            app = self.make_app()
            app.selectbox[0].select("我的清單").run()
            self.assertFalse(app.exception)
            table = app.dataframe[0].value
            self.assertEqual(
                table.iloc[0]["研究決策"],
                "尚未建立研究資料",
            )
            self.assertTrue(
                any(
                    "可回到股票研究頁連網產生研究建議"
                    in item.value
                    for item in app.info
                )
            )

    def test_empty_watchlist_message(self):
        with temporary_project_watchlist([]):
            app = self.make_app()
            app.selectbox[0].select("我的清單").run()
            self.assertTrue(
                any(
                    "尚未加入任何股票，請到股票研究頁按星星加入我的清單。"
                    in item.value
                    for item in app.info
                )
            )

    def test_rendered_pages_use_research_language(self):
        forbidden = (
            "加碼",
            "減碼",
            "清倉",
            "持股",
            "股數",
            "成本",
            "reduce",
            "exit",
        )
        rows = [
            {
                "stock_id": "2330",
                "stock_name": "台積電",
                "added_at": "2026-07-02T10:00:00+08:00",
                "note": "研究追蹤",
            }
        ]
        with temporary_public_mode(False), temporary_project_watchlist(rows):
            for page in app_module.PAGES:
                with self.subTest(page=page):
                    app = self.make_app()
                    app.selectbox[0].select(page).run()
                    if page == "股票研究":
                        app.text_input[0].input("2330").run()
                    text_parts = []
                    for collection_name in (
                        "title",
                        "header",
                        "subheader",
                        "markdown",
                        "caption",
                        "warning",
                        "info",
                        "success",
                    ):
                        text_parts.extend(
                            str(item.value)
                            for item in getattr(app, collection_name)
                        )
                    rendered = "\n".join(text_parts).replace(
                        app_module.SAFETY_NOTICE,
                        "",
                    )
                    for term in forbidden:
                        self.assertNotIn(term, rendered)


class WatchlistWorkflowTests(unittest.TestCase):
    def test_private_mode_add_does_not_duplicate_and_remove_works(self):
        with temporary_public_mode(False), TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "watchlist.csv"
            added = app_module.add_to_watchlist(
                "2330",
                "台積電",
                note="研究追蹤",
                path=path,
                now=datetime(2026, 7, 2, 10, 0, 0),
            )
            duplicate = app_module.add_to_watchlist(
                "2330",
                "台積電",
                path=path,
                now=datetime(2026, 7, 2, 10, 1, 0),
            )
            frame = pd.read_csv(
                path,
                dtype=str,
                encoding="utf-8-sig",
                keep_default_na=False,
            )
            self.assertTrue(added)
            self.assertFalse(duplicate)
            self.assertEqual(len(frame), 1)
            self.assertEqual(frame.iloc[0]["note"], "研究追蹤")

            self.assertTrue(
                app_module.remove_from_watchlist("2330", path=path)
            )
            self.assertFalse(
                app_module.remove_from_watchlist("2330", path=path)
            )
            empty = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
            self.assertTrue(empty.empty)

    def test_watchlist_view_sorts_and_preserves_new_stock(self):
        watchlist = pd.DataFrame(
            [
                {
                    "stock_id": "9999",
                    "stock_name": "新研究股票",
                    "added_at": "2026-07-02T10:00:00+08:00",
                    "note": "新股票",
                },
                {
                    "stock_id": "2330",
                    "stock_name": "台積電",
                    "added_at": "2026-07-02T10:01:00+08:00",
                    "note": "既有資料",
                },
            ],
            columns=app_module.WATCHLIST_COLUMNS,
        )
        summary = app_module.load_decision_summary(
            str(PROJECT_DIR / "decision_summary.csv"),
            (PROJECT_DIR / "decision_summary.csv").stat().st_mtime_ns,
        )
        view = app_module.build_watchlist_view(watchlist, summary)
        self.assertEqual(view.iloc[0]["stock_id"], "2330")
        missing = view.loc[view["stock_id"] == "9999"].iloc[0]
        self.assertEqual(missing["industry_score"], "尚未建立研究資料")
        self.assertEqual(missing["research_decision"], "尚未建立研究資料")

    def test_new_stock_network_research_creates_suggested_csv(self):
        with temporary_public_mode(True), TemporaryDirectory() as temporary_dir:
            temp_dir = Path(temporary_dir)
            stocks_path = temp_dir / "stocks.csv"
            suggested_path = temp_dir / "suggested_scores.csv"
            stocks_path.write_bytes((PROJECT_DIR / "stocks.csv").read_bytes())
            original = stocks_path.read_bytes()

            def fake_runner(*arguments):
                stocks_index = arguments.index("--stocks") + 1
                output_index = arguments.index("--output") + 1
                temporary_stocks = Path(arguments[stocks_index])
                self.assertNotEqual(temporary_stocks, stocks_path)
                temporary_stocks.write_text(
                    "public mode temporary copy",
                    encoding="utf-8",
                )
                Path(arguments[output_index]).write_bytes(
                    (PROJECT_DIR / "suggested_scores.csv").read_bytes()
                )
                return subprocess.CompletedProcess(
                    args=arguments,
                    returncode=0,
                    stdout="完成（v0.5.1）：2308 台達電\n".encode("utf-8"),
                    stderr=b"",
                )

            completed = app_module.generate_research_suggestion(
                "2308",
                stocks_path=stocks_path,
                suggested_path=suggested_path,
                fetch_script=PROJECT_DIR / "fetch_stock_info.py",
                runner=fake_runner,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertTrue(suggested_path.exists())
            self.assertEqual(original, stocks_path.read_bytes())
            self.assertEqual(app_module.fetched_stock_id(completed), "2308")

    def test_private_mode_apply_still_creates_backup_and_summary(self):
        with temporary_public_mode(False), TemporaryDirectory() as temporary_dir:
            temp_dir = Path(temporary_dir)
            paths = {
                filename: temp_dir / filename
                for filename in (
                    "stocks.csv",
                    "suggested_scores.csv",
                    "apply_log.csv",
                )
            }
            for filename, destination in paths.items():
                destination.write_bytes((PROJECT_DIR / filename).read_bytes())
            summary_path = temp_dir / "decision_summary.csv"
            original = paths["stocks.csv"].read_bytes()

            backup = app_module.apply_suggestion_to_stocks(
                "2330",
                stocks_path=paths["stocks.csv"],
                suggested_path=paths["suggested_scores.csv"],
                summary_path=summary_path,
                apply_log_path=paths["apply_log.csv"],
                score_script=PROJECT_DIR / "score_stocks.py",
                now=datetime(2026, 7, 2, 12, 34, 56),
            )
            self.assertEqual(original, backup.read_bytes())
            self.assertTrue(summary_path.exists())

    def test_public_mode_watchlist_is_session_only(self):
        with temporary_public_mode(True), temporary_project_watchlist([]):
            watchlist_path = PROJECT_DIR / "watchlist.csv"
            original = watchlist_path.read_bytes()

            app = StreamlitAppTests().make_app()
            app.text_input[0].input("2330").run()
            add_button = next(
                button
                for button in app.button
                if button.label == "加入我的清單"
            )
            add_button.click().run()

            self.assertEqual(original, watchlist_path.read_bytes())
            app.selectbox[0].select("我的清單").run()
            table = app.dataframe[0].value
            self.assertEqual(str(table.iloc[0]["股票代號"]), "2330")

    def test_public_mode_rejects_stocks_write(self):
        with temporary_public_mode(True), TemporaryDirectory() as temporary_dir:
            temp_dir = Path(temporary_dir)
            stocks_path = temp_dir / "stocks.csv"
            suggested_path = temp_dir / "suggested_scores.csv"
            apply_log_path = temp_dir / "apply_log.csv"
            stocks_path.write_bytes((PROJECT_DIR / "stocks.csv").read_bytes())
            suggested_path.write_bytes(
                (PROJECT_DIR / "suggested_scores.csv").read_bytes()
            )
            apply_log_path.write_bytes(
                (PROJECT_DIR / "apply_log.csv").read_bytes()
            )
            original = stocks_path.read_bytes()

            with self.assertRaisesRegex(
                app_module.SuggestionApplyError,
                "公開部署模式不允許修改 stocks.csv",
            ):
                app_module.apply_suggestion_to_stocks(
                    "2330",
                    stocks_path=stocks_path,
                    suggested_path=suggested_path,
                    summary_path=temp_dir / "decision_summary.csv",
                    apply_log_path=apply_log_path,
                    score_script=PROJECT_DIR / "score_stocks.py",
                )

            self.assertEqual(original, stocks_path.read_bytes())
            self.assertEqual(
                list(temp_dir.glob("stocks_backup_*.csv")),
                [],
            )


if __name__ == "__main__":
    unittest.main()
