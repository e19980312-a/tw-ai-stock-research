import re
import tomllib
import unittest
from pathlib import Path

import app


PROJECT_DIR = Path(__file__).resolve().parents[1]
REQUIRED_ROOT_FILES = {
    "app.py",
    "requirements.txt",
    "score_stocks.py",
    "fetch_stock_info.py",
    "action_engine.py",
    "stocks.csv",
    "decision_summary.csv",
    "watchlist.csv",
}


class CommunityCloudDeploymentTests(unittest.TestCase):
    def test_required_files_are_in_project_root(self):
        missing = [
            filename
            for filename in sorted(REQUIRED_ROOT_FILES)
            if not (PROJECT_DIR / filename).is_file()
        ]
        self.assertEqual(missing, [])

    def test_required_python_packages_are_declared(self):
        requirements = (PROJECT_DIR / "requirements.txt").read_text(
            encoding="utf-8"
        )
        package_names = {
            re.split(r"[<>=!~\[]", line.strip(), maxsplit=1)[0].lower()
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertTrue(
            {"streamlit", "pandas", "requests", "tzdata"}.issubset(
                package_names
            )
        )

    def test_runtime_csv_paths_are_project_relative(self):
        csv_paths = (
            app.SUMMARY_PATH,
            app.SUGGESTED_PATH,
            app.STOCKS_PATH,
            app.WATCHLIST_PATH,
            app.APPLY_LOG_PATH,
        )
        self.assertTrue(
            all(path.parent.resolve() == PROJECT_DIR for path in csv_paths)
        )

    def test_source_has_no_machine_specific_absolute_path(self):
        windows_absolute = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
        unix_home = re.compile(r"/(?:Users|home)/[^/\s]+/")
        for filename in (
            "app.py",
            "score_stocks.py",
            "fetch_stock_info.py",
            "action_engine.py",
        ):
            source = (PROJECT_DIR / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertIsNone(windows_absolute.search(source))
                self.assertIsNone(unix_home.search(source))

    def test_streamlit_config_is_cloud_ready(self):
        config_path = PROJECT_DIR / ".streamlit" / "config.toml"
        self.assertTrue(config_path.is_file())
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        self.assertTrue(config["server"]["headless"])
        self.assertEqual(config["client"]["toolbarMode"], "minimal")
        self.assertFalse(config["browser"]["gatherUsageStats"])


if __name__ == "__main__":
    unittest.main()
