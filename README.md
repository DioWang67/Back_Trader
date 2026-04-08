# SMC 回測系統（Python 3.11）

本專案實作 **Liquidity Sweep + BOS + FVG Pullback** 的 SMC 規則化策略，並提供可直接在 Google Colab 執行的模組化架構。

## 專案結構

- `data_loader.py`：下載與讀取資料（TAIFEX 公開資料 + CSV 載入）
- `indicators.py`：EMA / swing / FVG 計算
- `strategy.py`：策略條件判斷（Sweep + BOS + FVG Pullback）
- `risk.py`：固定風險倉位與最大回撤檢查
- `backtest.py`：逐 K 回測、滑價、手續費、雙向交易
- `metrics.py`：績效指標
- `main.py`：執行入口
- `tests/test_backtest.py`：5 類測試案例
- `config.py`：可調整參數

## 安裝方式

```bash
python -m pip install -U pip
python -m pip install pandas requests
```

## 執行方式

```bash
python main.py
```

## 策略說明（嚴格規則）

1. 趨勢濾網：
   - `EMA50 > EMA200` 為多頭
   - `EMA50 < EMA200` 為空頭
2. Sweep：
   - `high[i] > high[i-1] 且 close[i] < high[i-1]` → 掃高
   - `low[i] < low[i-1] 且 close[i] > low[i-1]` → 掃低
3. BOS：
   - 多頭：`close[i] > 最近 swing high`
   - 空頭：`close[i] < 最近 swing low`
4. FVG：
   - 多頭：`low[i] > high[i-2]`
   - 空頭：`high[i] < low[i-2]`
5. 進場：Sweep + BOS + 回踩 FVG + 趨勢同向
6. 出場：
   - 停損：sweep 極值
   - 停利：`RR = 2`
7. 風控：
   - 每筆風險 1%
   - 最大回撤 25% 停止交易
   - 同時最多 2 筆持倉

## 如何替換資料

### 方案 A：自動下載 TAIFEX
在 `main.py` 使用 `download_txf_data()`。

### 方案 B：改用本地 CSV
改用 `load_csv("你的檔案.csv")`，欄位需包含：
- `datetime, open, high, low, close, volume`

## Google Colab

可直接貼上：

```python
!pip -q install pandas requests
!python main.py
```

## 測試

```bash
python -m unittest discover -s tests -p 'test_*.py'
```
