import backtrader as bt
import yfinance as yf
import pandas as pd
import datetime
from collections import deque

# ==========================================
# 參數設定區 (User Configuration)
# ==========================================
TIMEFRAME = "15m"           # 回到 15 分鐘 (最佳勝率)
LOOKBACK_DAYS = 60        # 擴展至 2 年歷史數據
RISK_PCT = 0.05            # 提高風險至 2%
MNQ_POINT_VALUE = 2        # MNQ 每點價值 $2
MNQ_MARGIN = 2000          # MNQ 保證金要求 (約略值)
START_CASH = 50000         # 提高初始資金至 5萬
MAX_CONTRACTS = 3          # 最大持倉限制
COMMISSION_PER_CONTRACT = 2.0  # 更實際的來回成本 (2點)
MAX_CONSECUTIVE_LOSSES = 3  # 連續虧損停損機制
MIN_TRADES_FOR_STATS = 30   # 最少交易次數才顯示統計
# ==========================================

class SMC_Strategy_Optimized(bt.Strategy):
    params = (
        ('ema_period', 50),
        ('atr_period', 14),
        ('extension_threshold', 3.0),
        ('swing_lookback', 3),
        ('rr_ratio', 2.5),             # 回復最佳設定 2.5
        ('min_atr_filter', 1.0),
        ('use_sma_filter', False),
    )

    def __init__(self):
        # 技術指標
        self.ema = bt.indicators.EMA(self.data.close, period=self.params.ema_period)
        self.sma200 = bt.indicators.SMA(self.data.close, period=200)  # 長期趨勢線
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        
        # Swing Points
        self.swing_low = None
        self.swing_high = None
        self.swing_low_bar = None  # 記錄發生時間
        
        # 風險控管
        self.order = None
        self.consecutive_losses = 0
        self.trade_history = deque(maxlen=10)  # 最近10筆交易
        
        # 統計數據
        self.total_trades = 0
        self.winning_trades = 0
        self.entry_price = None
        self.stop_loss = None
        self.loss_cooldown_counter = 0  # 冷靜期計數器
        
        # SMC State Variables
        self.choch_level = None
        self.awaiting_choch = False
        
    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f'{dt.isoformat()}, {txt}')

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(f'買入執行: 價格 {order.executed.price:.2f}, 數量 {order.executed.size}')
                self.entry_price = order.executed.price
            elif order.issell():
                self.log(f'賣出執行: 價格 {order.executed.price:.2f}')
                
        elif order.status in [order.Canceled]:
            self.log(f'管理訂單取消 (OCO): {order.status}')
        elif order.status in [order.Margin, order.Rejected]:
            self.log(f'訂單失敗: {order.status}')
        
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        
        self.total_trades += 1
        pnl = trade.pnl
        
        # 記錄交易結果
        if pnl > 0:
            self.winning_trades += 1
            self.consecutive_losses = 0
            self.log(f'交易獲利: {pnl:.2f}')
        else:
            self.consecutive_losses += 1
            self.log(f'交易虧損: {pnl:.2f} (連續虧損: {self.consecutive_losses})')
        
        self.trade_history.append(pnl)

    def is_trading_hours(self):
        """過濾低流動性時段 (UTC 時間)"""
        current_time = self.data.datetime.datetime(0)
        hour = current_time.hour
        
        # 避開亞洲盤低流動性時段 (UTC 18:00-23:00 約為台灣凌晨2點-7點)
        if 18 <= hour <= 23:
            return False
        
        # 避開週末
        if current_time.weekday() >= 5:
            return False
        
        return True

    def check_risk_limits(self):
        """檢查風險控管條件"""
        # 1. 連續虧損保護
        if self.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            self.loss_cooldown_counter += 1
            if self.loss_cooldown_counter > 20:  # 冷靜 20 根 K 線 (約 5 小時)
                self.consecutive_losses = 0
                self.loss_cooldown_counter = 0
                self.log('ℹ️ 冷靜期結束,恢復交易')
            else:
                self.log(f'⚠️ 連續虧損暫停中 (冷靜期 {self.loss_cooldown_counter}/20)')
                return False
        
        # 2. 帳戶虧損保護 (低於初始資金 30%)
        current_value = self.broker.getvalue()
        if current_value < START_CASH * 0.7:
            self.log(f'⚠️ 帳戶虧損超過 30%,停止交易')
            return False
        
        return True

    def calculate_position_size(self, entry_price, stop_loss):
        """改進的倉位計算"""
        risk_per_share = entry_price - stop_loss
        if risk_per_share <= 0:
            return 0
        
        # 可用資金 (扣除保證金緩衝)
        available_cash = self.broker.getcash()
        account_value = self.broker.getvalue()
        
        # 計算理論倉位
        risk_amount = account_value * RISK_PCT
        theoretical_size = risk_amount / (risk_per_share * MNQ_POINT_VALUE)
        
        # 保證金檢查
        max_contracts_by_margin = int(available_cash / (MNQ_MARGIN * 1.2))
        
        # 取最小值
        final_size = min(
            int(theoretical_size),
            MAX_CONTRACTS,
            max_contracts_by_margin
        )
        
        if final_size == 0:
            self.log(f'⚠️ [風險計算細節] 資金: ${account_value:.0f}, 風險預算: ${risk_amount:.0f}, 單口風險: ${risk_per_share * MNQ_POINT_VALUE:.0f} (止損距: {risk_per_share:.2f}點)')
            self.log(f'   理論口數: {theoretical_size:.2f}, 保證金限制口數: {max_contracts_by_margin}')

        return max(final_size, 1) if final_size > 0 else 0

    def next(self):
        # 訂單檢查
        if self.order:
            return
        
        # 風險控管檢查
        if not self.check_risk_limits():
            return
        
        # 時段過濾
        if not self.is_trading_hours():
            return
        
        # ATR 過濾 (避免盤整)
        if self.atr[0] < self.params.min_atr_filter:
            return
        
        # =====================================
        # Swing Point 識別 (改進版)
        # =====================================
        if len(self.data) > 11:
            past_lows = self.data.low.get(ago=-10, size=11)
            past_highs = self.data.high.get(ago=-10, size=11)
            
            # 確認中間點是否為極值
            if past_lows[5] == min(past_lows):
                new_low = past_lows[5]
                # 只在發現更低的低點時更新
                if self.swing_low is None or new_low < self.swing_low:
                    self.swing_low = new_low
                    self.swing_low_bar = len(self.data) - 5
            
            if past_highs[5] == max(past_highs):
                self.swing_high = past_highs[5]
        
        if self.swing_low is None or self.swing_high is None:
            return
        
        # 確保 Swing Low 不是太舊 (最多 50 根 K 線)
        if len(self.data) - self.swing_low_bar > 50:
            return
        
        # =====================================
        # SMC 交易邏輯 (Liquidity Sweep -> CHoCH -> FVG)
        # =====================================
        
        # 1. 識別流動性掃蕩 (Liquidity Sweep)
        sweep_signal = (self.data.low[0] < self.swing_low and 
                      self.data.close[0] > self.swing_low)
        
        if sweep_signal and not self.position and not self.awaiting_choch:
            # 觸發 CHoCH 等待模式
            # 尋找最近的小高點作為 CHoCH 突破位
            past_highs = self.data.high.get(ago=0, size=5)
            if past_highs:
                self.choch_level = max(past_highs)
                self.awaiting_choch = True
                self.log(f'👀 發現掃蕩,等待 CHoCH 突破: {self.choch_level:.2f}')
                return # 等待確認

        # 2. 等待 CHoCH 確認
        if self.awaiting_choch:
            # 如果價格跌破更低的低點, 取消等待 (結構失效)
            if self.data.low[0] < self.swing_low:
                 self.awaiting_choch = False
                 self.log('❌ 結構失效 (破底), 取消等待 CHoCH')
                 return
            
            # 檢查是否突破 CHoCH
            if self.data.close[0] > self.choch_level:
                self.log(f'✅ CHoCH 確認! 突破 {self.choch_level:.2f}')
                self.awaiting_choch = False # Reset state
                
                # 3. FVG 確認 (選擇性)
                # 檢查這根 K 線或前一根是否形成 FVG
                # FVG: High[i-2] < Low[i] (Bullish FVG)
                fvg_detected = False
                if len(self.data) > 3:
                     # Check current gap
                     if self.data.low[0] > self.data.high[-2]:
                         fvg_detected = True
                     # Check previous gap
                     elif self.data.low[-1] > self.data.high[-3]:
                         fvg_detected = True
                
                if fvg_detected:
                    self.log('💎 發現 FVG, 進場做多!')
                    entry_price = self.data.close[0]
                    # 止損放在當前波動低點
                    stop_loss = self.data.low[0] - self.atr[0]
                    
                    size = self.calculate_position_size(entry_price, stop_loss)
                    if size > 0:
                        risk = entry_price - stop_loss
                        tp_price = entry_price + (risk * self.params.rr_ratio)
                        
                        self.log(f'📈 做多訊號 (SMC): 入場 {entry_price:.2f}, 止損 {stop_loss:.2f}, 止盈 {tp_price:.2f}, 數量 {size}')

                        # 使用 Bracket Order 自動管理 OCO
                        self.buy_bracket(
                            size=size,
                            price=entry_price,
                            stopprice=stop_loss,
                            limitprice=tp_price
                        )
                else:
                    self.log('⚠️ CHoCH 但無 FVG, 跳過交易')
        
        # 移除舊邏輯所需的 variables
        # extension = abs(self.data.close[0] - self.ema[0])
        # is_overextended = extension > (self.params.extension_threshold * self.atr[0])


# ==========================================
# 執行引擎
# ==========================================
if __name__ == '__main__':
    cerebro = bt.Cerebro()
    
    # 1. 下載數據 (擴展至 2 年)
    print(f"📊 正在下載 {TIMEFRAME} 數據 (過去 {LOOKBACK_DAYS} 天)...")
    try:
        data_df = yf.download(
            tickers="NQ=F",
            period=f"{LOOKBACK_DAYS}d",
            interval=TIMEFRAME,
            progress=False
        )
        
        if isinstance(data_df.columns, pd.MultiIndex):
            data_df.columns = data_df.columns.get_level_values(0)
        
        data_df = data_df.dropna()
        
        if len(data_df) < 100:
            print("⚠️ 數據不足,請降低 LOOKBACK_DAYS 或更換數據源")
            exit()
        
        print(f"✅ 成功載入 {len(data_df)} 根 K 線")
        
    except Exception as e:
        print(f"❌ 數據下載失敗: {e}")
        exit()
    
    # 載入數據
    data = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data)
    
    # 2. 策略與資金設定
    cerebro.addstrategy(SMC_Strategy_Optimized)
    cerebro.broker.setcash(START_CASH)
    cerebro.broker.setcommission(
        commission=COMMISSION_PER_CONTRACT,
        margin=MNQ_MARGIN,
        mult=MNQ_POINT_VALUE
    )
    
    # 3. 分析器
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.02)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
    
    # 4. 執行回測
    print(f"\n{'='*60}")
    print(f"🚀 開始回測 - 初始資金: ${START_CASH:,.2f}")
    print(f"{'='*60}\n")
    
    results = cerebro.run()
    strat = results[0]
    
    # 5. 結果分析
    final_value = cerebro.broker.getvalue()
    pnl = final_value - START_CASH
    returns = (pnl / START_CASH) * 100
    
    print(f"\n{'='*60}")
    print(f"📊 回測結果")
    print(f"{'='*60}")
    print(f"最終資金: ${final_value:,.2f}")
    print(f"總損益: ${pnl:,.2f} ({returns:+.2f}%)")
    
    # Drawdown
    dd_info = strat.analyzers.drawdown.get_analysis()
    print(f"最大回撤: {dd_info.max.drawdown:.2f}%")
    print(f"最大回撤期間: {dd_info.max.len} 根K線")
    
    # 交易統計
    trade_info = strat.analyzers.trades.get_analysis()
    total = trade_info.total.closed if 'total' in trade_info and 'closed' in trade_info.total else 0
    won = trade_info.won.total if 'won' in trade_info and 'total' in trade_info.won else 0
    lost = trade_info.lost.total if 'lost' in trade_info and 'total' in trade_info.lost else 0
    
    print(f"\n交易統計:")
    print(f"  總交易次數: {total}")
    
    if total >= MIN_TRADES_FOR_STATS:
        win_rate = (won / total * 100) if total > 0 else 0
        print(f"  勝率: {win_rate:.1f}% ({won}勝 / {lost}敗)")
        
        if 'won' in trade_info and trade_info.won.total > 0:
            avg_win = trade_info.won.pnl.average
            print(f"  平均獲利: ${avg_win:.2f}")
        
        if 'lost' in trade_info and trade_info.lost.total > 0:
            avg_loss = trade_info.lost.pnl.average
            print(f"  平均虧損: ${avg_loss:.2f}")
            
            if avg_loss != 0:
                profit_factor = abs(avg_win * won / (avg_loss * lost))
                print(f"  獲利因子: {profit_factor:.2f}")
        
        # Sharpe Ratio
        sharpe = strat.analyzers.sharpe.get_analysis()
        if sharpe and 'sharperatio' in sharpe and sharpe['sharperatio'] is not None:
            print(f"  Sharpe Ratio: {sharpe['sharperatio']:.2f}")
    else:
        print(f"  ⚠️ 交易次數不足 ({total} < {MIN_TRADES_FOR_STATS}),統計結果參考性低")
    
    print(f"{'='*60}\n")
    
    # 6. 風險提示
    print("⚠️ 重要提醒:")
    print("1. 此為歷史數據回測,不代表未來績效")
    print("2. 實際交易會有滑點、斷線、流動性風險")
    print("3. 建議先用模擬帳戶測試至少 3 個月")
    print("4. 初期僅投入總資金的 10-20%")
    print("5. MNQ 保證金需求約 $2,000/口,請確保資金充足\n")
    
    # 7. 繪圖
    cerebro.plot(style='candlestick', volume=False)