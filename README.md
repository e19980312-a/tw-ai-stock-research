# 台股 AI 選股查詢／研究輔助工具 v1.0.5

本工具用於查詢台股 AI 供應鏈股票、比較研究吸引力，以及判斷標的應列為布局候選、等待回檔、持續觀察或暫不投入。

本工具只整理公司研究資料、研究分數與星號清單，不連結個人交易資訊。

> 本工具僅供研究輔助，不代表投資建議，也不與實際持股連動。

## 安裝與啟動

需要 Python 3.10 以上。

```powershell
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud 部署

本目錄可直接作為 GitHub repository 根目錄部署，Community Cloud 的入口檔選擇 `app.py`。

部署前確認：

```text
app.py
requirements.txt
score_stocks.py
fetch_stock_info.py
action_engine.py
stocks.csv
decision_summary.csv
watchlist.csv
.streamlit/config.toml
```

簡要步驟：

1. 將本目錄提交並推送到 GitHub。
2. 前往 [Streamlit Community Cloud](https://share.streamlit.io/)。
3. 建立 App，選擇 GitHub repository、`main` branch 與入口檔 `app.py`。
4. 建議在 Advanced settings 選擇 Python 3.12。
5. 按下 Deploy；完成後即可分享 `https://<app-name>.streamlit.app` 網址。

完整 GitHub 指令、資料更新與網址分享方式請見 [`DEPLOY.md`](DEPLOY.md)。

> Community Cloud 不保證執行期間寫入本機檔案的資料會永久保存。
> 網頁中新增的清單或連網建議可能在重啟、休眠或重新部署後還原。
> 需要永久更新時，請在本機修改 CSV、重新產生摘要，再提交到 GitHub。

## 公開部署模式與私人研究模式

`PUBLIC_MODE` 預設為 `True`，適合直接部署到公開的 Streamlit Community Cloud。

### 公開部署模式

未設定 `PUBLIC_MODE`，或設為 `true` 時：

- 可搜尋股票、查看本地研究資料。
- 可連網產生並顯示研究建議。
- `stocks.csv` 不允許由網頁流程修改。
- 「我的清單」只保存在目前瀏覽 session，不讀寫 `watchlist.csv`。
- 不提供套用研究分數功能。
- 關閉分頁、session 結束、App 重啟或重新部署後，暫存清單可能消失。

頁面會顯示：

> 公開版僅供研究展示，操作不會永久保存。

### 私人研究模式

私人模式會恢復 `watchlist.csv` 與研究資料後端的寫入能力。啟動前設定：

PowerShell：

```powershell
$env:PUBLIC_MODE = "false"
streamlit run app.py
```

macOS／Linux：

```bash
PUBLIC_MODE=false streamlit run app.py
```

Community Cloud 的 Advanced settings → Secrets 亦可設定：

```toml
PUBLIC_MODE = false
```

私人模式只代表程式允許寫入 CSV；Community Cloud 本機檔案仍不保證永久保存。需要永久保留的內容仍應提交到 GitHub，或改接持久性資料庫。

重新產生研究摘要：

```powershell
python score_stocks.py
```

查詢單檔股票：

```powershell
python query_stock.py 2330
python query_stock.py 台積電
```

## 專案檔案

- `stocks.csv`：研究股票池、研究定位、五項人工分數與研究備註。
- `decision_summary.csv`：整理後的研究決策摘要。
- `suggested_scores.csv`：連網資料產生的輔助建議分數，不會自動修改股票池。
- `watchlist.csv`：使用者以星號加入的研究清單。
- `score_stocks.py`：計算總分、分類與研究決策。
- `action_engine.py`：研究決策規則。
- `query_stock.py`：CLI 單檔查詢。
- `app.py`：Streamlit 查詢與研究審核介面。
- `.streamlit/config.toml`：Community Cloud 與基本介面設定。
- `DEPLOY.md`：GitHub 與 Streamlit Community Cloud 部署手冊。

## stocks.csv

核心欄位：

- `data_date`
- `stock_id`
- `stock_name`
- `industry_position`
- `ai_relevance`：高／中／低
- `is_bottleneck`：是／否／部分
- `risk_notes`
- `research_role`
- `research_note`
- `industry_score`
- `growth_score`
- `ai_score`
- `valuation_score`
- `price_risk_score`
- `source`

`research_role` 可用值：

- 核心研究標的
- 高關注標的
- 觀察標的
- 景氣循環觀察
- 非主線觀察

`research_note` 只記錄研究觀點。

## watchlist.csv

固定欄位：

- `stock_id`
- `stock_name`
- `added_at`
- `note`

同一個 `stock_id` 只會保留一筆。加入與移出清單不會修改研究分數。

## 五項分數

五項分數合計 100 分：

| 欄位 | 滿分 | 說明 |
|---|---:|---|
| `industry_score` | 25 | 產業地位與競爭優勢 |
| `growth_score` | 25 | 營收與獲利成長 |
| `ai_score` | 20 | AI 長期受益程度 |
| `valuation_score` | 20 | 估值合理性 |
| `price_risk_score` | 10 | 股價位置與籌碼風險 |

任一分數缺漏時，`total_score` 為 `NA`，分類顯示「分數資料不足」。

研究分類：

| 總分 | category |
|---:|---|
| 80 以上 | 高研究吸引力 |
| 65–79 | 值得持續研究 |
| 50–64 | 觀察追蹤 |
| 50 以下 | 低優先或排除 |

## 研究決策引擎

輸出欄位：

- `research_decision`
- `research_signal`：`consider`／`wait`／`watch`／`avoid`
- `signal_strength`：強／中／弱
- `research_reason`

規則：

1. `valuation_score <= 5` 且 `price_risk_score <= 4`：
   `暫不投入／avoid／中`。
2. `total_score >= 80` 且 `price_risk_score <= 5`：
   `回檔布局候選／wait／中`。
3. `total_score >= 85`、`valuation_score >= 14` 且
   `price_risk_score >= 6`：
   `小幅布局候選／consider／中`。
4. 上述小幅布局條件若 `ai_relevance` 不是「高」，且
   `research_role` 不是「核心研究標的」，改為
   `續列觀察／watch／中`。
5. `total_score >= 75` 且 `valuation_score >= 10`：
   `續列觀察／watch／中`。
6. `total_score` 為 60–74：
   `續列觀察／watch／弱`。
7. `total_score < 60`：
   `僅追蹤不投入／watch／弱`。

## decision_summary.csv

固定輸出欄位：

1. `data_date`
2. `stock_id`
3. `stock_name`
4. `total_score`
5. `category`
6. `research_decision`
7. `research_signal`
8. `signal_strength`
9. `research_reason`
10. `research_role`
11. `industry_position`
12. `ai_relevance`
13. `is_bottleneck`
14. `industry_score`
15. `growth_score`
16. `ai_score`
17. `valuation_score`
18. `price_risk_score`
19. `risk_notes`
20. `research_note`

資料依 `total_score` 由高到低排序，缺少完整分數的股票排在最後。

## Streamlit 頁面

Streamlit 下拉選單只保留兩個日常使用頁面：

v1.0.5 新增公開部署模式；核心評分、連網抓取及資料欄位均維持不變。

### 股票研究

- 搜尋本地股票代號、公司名稱或新股票代號。
- 股票標題下依序顯示清單備註、加入／移出清單及連網更新按鈕。
- 本地有資料時，以同一張摘要卡顯示資料日期、總分、連網信心等級、研究決策、研究訊號、強度與研究理由。
- 尚無連網建議時，摘要卡的信心等級顯示「尚未連網更新」。
- 本地沒有資料時，可直接執行連網研究。
- 連網結果在同一頁顯示建議分數、理由、原始指標與資料來源。
- 公司定位、風險備註與研究備註排列在五項連網建議之前。
- 五項連網建議固定依產業地位、成長性、AI 長期受益、估值合理性、股價與籌碼風險排列。
- 研究角色保留在資料中，但不在介面呈現。
- 連網產生時間、評分版本、原始指標摘要與資料來源集中在股票研究頁底部。
- 分數比較、決策預覽與人工套用後端仍保留，日後可重新啟用。
- 以 `☆`／`★` 加入或移出我的清單，可同時填寫研究追蹤備註。

### 我的清單

- 讀取 `watchlist.csv`，並以股票代號連接 `decision_summary.csv`。
- 主表格使用中文欄名，顯示總分、五項分數、研究決策、研究訊號、強度、AI 相關性、資料日期與備註。
- 研究訊號只在介面轉換為「可研究／等待／觀察／暫避」，資料檔仍保留英文值。
- 主表格不顯示分類欄位。
- 星星只保留在清單管理區，不占用主表格欄位。
- 支援股票搜尋，以及研究決策、研究訊號、訊號強度與 AI 相關性篩選。
- 依總分由高到低排序。
- 尚未建立研究資料的新股票仍會保留，並提示回到股票研究頁產生連網建議。
- 每檔股票都可直接移出我的清單。
- 手機畫面改用直向卡片，避免寬表格造成不便。

連網資料與建議分數只供研究參考，不會自動套用。

> 本工具僅供研究輔助，不代表投資建議，也不與實際持股連動。
