# Streamlit Community Cloud 部署手冊

本專案可直接部署為「台股 AI 選股查詢／研究輔助工具」。

> 本工具僅供研究輔助，不代表投資建議，也不與實際持股連動。

## 部署模式

### 公開部署模式（預設）

未設定 `PUBLIC_MODE` 時，系統預設 `PUBLIC_MODE=True`：

- 可查詢本地研究資料。
- 可連網產生研究建議。
- 新股票可產生 `research_candidates.csv` 初步研究卡。
- 不允許套用研究分數或修改 `stocks.csv`。
- 「我的清單」只存在個別使用者的 Streamlit session，不寫入 `watchlist.csv`。
- 頁面會標示「公開版僅供研究展示，操作不會永久保存。」

公開部署不需要在 Community Cloud 設定任何 Secrets。

### 私人研究模式

本機私人使用時可設定環境變數：

```bash
PUBLIC_MODE=false streamlit run app.py
```

PowerShell：

```powershell
$env:PUBLIC_MODE = "false"
streamlit run app.py
```

若部署為受限存取的 Community Cloud App，可在 Advanced settings → Secrets 設定：

```toml
PUBLIC_MODE = false
```

私人模式會恢復 `watchlist.csv` 與研究資料後端的寫入能力，但 Community Cloud 本機檔案仍不保證持久保存。

私人模式也會顯示「加入正式研究資料庫」按鈕；確認後才會備份並更新 `stocks.csv` 與 `decision_summary.csv`。

## 1. 部署目錄

請將目前這一層目錄作為 GitHub repository 根目錄。至少需要包含：

```text
.streamlit/
└── config.toml
app.py
requirements.txt
score_stocks.py
fetch_stock_info.py
action_engine.py
stocks.csv
decision_summary.csv
research_candidates.csv
watchlist.csv
```

程式沒有寫死 Windows 或 macOS 的本機絕對路徑。CSV 與 Python 腳本都以 `app.py` 所在目錄為基準尋找，因此從 repository 根目錄啟動即可。

## 2. 推送到 GitHub

先在 GitHub 建立一個空白 repository，例如 `tw-ai-stock-research`，不要預先加入 README 或其他檔案。

在本專案根目錄執行：

```bash
git init
git branch -M main
git add .
git commit -m "Prepare Streamlit Community Cloud deployment"
git remote add origin https://github.com/<你的帳號>/<repository>.git
git push -u origin main
```

請把 `<你的帳號>` 與 `<repository>` 換成實際名稱。若目錄已經是 Git repository，只需正常 `git add`、`git commit`、`git push`，不必再次執行 `git init` 或新增 remote。

推送前建議確認沒有提交 API 金鑰、密碼、Cookie 或其他私人資料。本專案目前不需要 Streamlit secrets。

## 3. 在 Streamlit Community Cloud 部署

1. 前往 [share.streamlit.io](https://share.streamlit.io/) 並登入。
2. 連結用來存放本專案的 GitHub 帳號。
3. 在工作區按 **Create app**。
4. 選擇 **Yup, I have an app**。
5. 填入：
   - Repository：`<你的帳號>/<repository>`
   - Branch：`main`
   - Main file path：`app.py`
6. 可在 **Advanced settings** 將 Python 版本選為 `3.12`。
7. 公開版不需填 Secrets；私人研究模式可填入 `PUBLIC_MODE = false`。
8. 可選擇容易記憶的 App URL，然後按 **Deploy**。

Community Cloud 會從 GitHub repository 取得檔案，依 `requirements.txt` 建立 Python 環境，再執行 `streamlit run app.py`。

## 4. 更新研究資料

永久更新研究股票池或摘要時，建議在本機處理：

```bash
python score_stocks.py
```

確認下列檔案內容正確：

- `stocks.csv`
- `decision_summary.csv`
- `watchlist.csv`（若要更新部署時的預設清單）
- `suggested_scores.csv`（若要更新部署時的預設連網建議）
- `research_candidates.csv`（若要保留新股票初步研究卡）

再提交到 GitHub：

```bash
git add stocks.csv decision_summary.csv watchlist.csv suggested_scores.csv research_candidates.csv
git commit -m "Update research data"
git push
```

Community Cloud 通常會在 GitHub 更新後自動重新部署。若畫面沒有更新，可從 App 管理頁選擇 **Reboot app**。

## 5. 雲端 CSV 寫入限制

Community Cloud 不保證本機檔案儲存的持久性。網頁執行期間產生或修改的內容，例如：

- `watchlist.csv`
- `suggested_scores.csv`
- `research_candidates.csv`
- 備份 CSV

可能在 App 重啟、休眠、重新部署或平台重建環境後消失，並回到 GitHub repository 內的版本。

此外，同一個公開 App 的訪客會共用伺服器端檔案。若「我的清單」屬於私人用途，建議使用私人 repository／限制觀看權限，或日後改接具持久性的資料庫或雲端儲存。

v1.1 公開模式下，「我的清單」仍只使用個別 session；`suggested_scores.csv` 與 `research_candidates.csv` 是連網研究的暫時輸出，可能因 App 重啟或其他研究請求而更新，不應視為永久資料庫。

## 6. 分享公開網址

部署完成後，App 會取得固定網址：

```text
https://<你的-app-subdomain>.streamlit.app
```

若 App 設為公開，可直接複製此網址分享。若使用私人 repository 或限制觀看權限，需在 Streamlit Community Cloud 的 Sharing 設定加入可觀看的使用者。

也可在 GitHub README 加入按鈕：

```markdown
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://<你的-app-subdomain>.streamlit.app)
```

## 7. 部署失敗時

1. 先查看 Community Cloud 右側 Logs。
2. 確認入口檔為 `app.py`。
3. 確認 `requirements.txt` 與 `app.py` 在 repository 根目錄。
4. 確認 CSV 已提交到 GitHub，且檔名大小寫完全相同。
5. 若更新依賴或資料後狀態未刷新，從 App 管理頁執行 Reboot。

官方文件：

- [File organization](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization)
- [App dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies)
- [Deploy your app](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy)
- [Share your app](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app)
