import backtrader as bt
import yfinance as yf
import pandas as pd
from collections import deque

# ==========================================
# 參數設定區
# ==========================================
TIMEFRAME = "15m"
START_CASH = 50000
RISK_PCT = 0.02             
MNQ_POINT_VALUE = 2
MNQ_MARGIN = 2000
COMMISSION_PER_CONTRACT = 2.0

class SMC_KillZone_Strategy(bt.Strategy):
    params = (
        ('ema_trend', 200),     
        ('atr_period', 14),
        ('rr_ratio', 2.0),      
        ('lookback_swing', 20),  # 修正：擴大到 20 根 (5小時高低點)
        ('min_atr', 5.0),        # 修正：波動率濾網，ATR小於5點不交易
    )

    def __init__(self):
        # 指標
        self.ema200 = bt.indicators.EMA(self.data.close, period=self.params.ema_trend)
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        self.rsi = bt.indicators.RSI(self.data.close, period=14)
        
        # 關鍵高低點
        self.highest = bt.indicators.Highest(self.data.high, period=self.params.lookback_swing)
        self.lowest = bt.indicators.Lowest(self.data.low, period=self.params.lookback_swing)
        
        self.order = None

    def log(self, txt, dt=None):
        dt = dt or self.datas[0].datetime.datetime(0)
        print(f'{dt.isoformat()}, {txt}')

    def is_kill_zone(self):
        """
        ICT Kill Zone (紐約時段)
        yfinance 數據通常是 UTC 時間
        紐約開盤 09:30 ET 約為 14:30 UTC (夏令時) 或 13:30 (冬令時)
        這裡我們設定一個寬鬆的活躍區間：UTC 13:00 - 20:00
        """
        current_hour = self.data.datetime.time(0).hour
        # 只在 UTC 13點(美股盤前) 到 20點(美股午後) 交易
        if 13 <= current_hour <= 20:
            return True
        return False

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        if order.status in [order.Completed]:
            dir = "BUY" if order.isbuy() else "SELL"
            self.log(f'{dir} 成交 @ {order.executed.price:.2f}')
            self.order = None

    def calculate_size(self, stop_loss_dist):
        if stop_loss_dist <= 0: return 0
        account_value = self.broker.getvalue()
        risk_amt = account_value * RISK_PCT
        contract_risk = stop_loss_dist * MNQ_POINT_VALUE
        size = int(risk_amt / contract_risk)
        max_margin = int(self.broker.getcash() / MNQ_MARGIN)
        return min(size, 3, max_margin) # 限制最大 3 口

    def next(self):
        if self.order or self.position: return 

        # ---------------------------
        # 濾網 1: 時間 (Kill Zone)
        # ---------------------------
        if not self.is_kill_zone():
            return

        # ---------------------------
        # 濾網 2: 波動率 (Volatility)
        # ---------------------------
        if self.atr[0] < self.params.min_atr:
            return

        # ---------------------------
        # 策略邏輯
        # ---------------------------
        trend_bullish = self.data.close[0] > self.ema200[0]
        trend_bearish = self.data.close[0] < self.ema200[0]
        
        # 比較 "前一根" 的 20K 高低點，看 "當前" 是否刺穿
        prev_low_n = self.lowest[-1]
        prev_high_n = self.highest[-1]
        
        # 發生獵殺 (Sweep) 且 收盤收回
        sweep_low = (self.data.low[0] < prev_low_n) and (self.data.close[0] > prev_low_n)
        sweep_high = (self.data.high[0] > prev_high_n) and (self.data.close[0] < prev_high_n)

        # 🟢 進場做多
        if trend_bullish and sweep_low:
            # 確認 K 線是陽線 (收盤 > 開盤) 增加勝率
            if self.data.close[0] > self.data.open[0]:
                sl_dist = 1.5 * self.atr[0] # 給予更大呼吸空間
                stop_price = self.data.low[0] - sl_dist
                take_profit = self.data.close[0] + (sl_dist * self.params.rr_ratio)
                
                size = self.calculate_size(self.data.close[0] - stop_price)
                if size > 0:
                    self.log(f'🚀 紐約戰區做多 | Sweep @ {self.data.low[0]:.2f}')
                    self.buy_bracket(size=size, price=self.data.close[0], stopprice=stop_price, limitprice=take_profit)

        # 🔴 進場做空
        elif trend_bearish and sweep_high:
            # 確認 K 線是陰線
            if self.data.close[0] < self.data.open[0]:
                sl_dist = 1.5 * self.atr[0]
                stop_price = self.data.high[0] + sl_dist
                take_profit = self.data.close[0] - (sl_dist * self.params.rr_ratio)
                
                size = self.calculate_size(stop_price - self.data.close[0])
                if size > 0:
                    self.log(f'📉 紐約戰區做空 | Sweep @ {self.data.high[0]:.2f}')
                    self.sell_bracket(size=size, price=self.data.close[0], stopprice=stop_price, limitprice=take_profit)

# ==========================================
# 執行區
# ==========================================
if __name__ == '__main__':
    cerebro = bt.Cerebro()
    
    # 重新下載數據
    print(f"📊 正在下載數據 (只過濾高質量時段)...")
    data_df = yf.download("NQ=F", period="59d", interval="15m", progress=False)
    
    if isinstance(data_df.columns, pd.MultiIndex):
        data_df.columns = data_df.columns.get_level_values(0)
    data_df = data_df.dropna()
    
    data = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data)
    
    cerebro.addstrategy(SMC_KillZone_Strategy)
    cerebro.broker.setcash(START_CASH)
    cerebro.broker.setcommission(commission=COMMISSION_PER_CONTRACT, margin=MNQ_MARGIN, mult=MNQ_POINT_VALUE)
    
    # 加入分析器
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe', riskfreerate=0.02)
    
    print(f"🚀 開始 V4 (ICT Kill Zone) 回測...")
    results = cerebro.run()
    strat = results[0]
    
    # ==========================
    # 績效報告
    # ==========================
    final_val = cerebro.broker.getvalue()
    pnl = final_val - START_CASH
    return_pct = (pnl / START_CASH) * 100
    
    print(f"\n{'='*50}")
    print(f"📊 最終績效報告")
    print(f"{'='*50}")
    print(f"💰 初始資金: ${START_CASH:,.2f}")
    print(f"🏁 最終資金: ${final_val:,.2f}")
    print(f"📈 總損益: ${pnl:,.2f} ({return_pct:+.2f}%)")
    
    # 交易統計
    trade_an = strat.analyzers.trades.get_analysis()
    
    # 檢查是否有交易產生
    if trade_an.get('total', {}).get('total', 0) > 0:
        total_trades = trade_an.total.closed
        won_trades = trade_an.won.total
        lost_trades = trade_an.lost.total
        win_rate = (won_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 獲利因子 (Profit Factor)
        total_won = trade_an.won.pnl.total
        total_lost = trade_an.lost.pnl.total
        profit_factor = abs(total_won / total_lost) if total_lost != 0 else float('inf')
        
        avg_win = trade_an.won.pnl.average if won_trades > 0 else 0
        avg_loss = trade_an.lost.pnl.average if lost_trades > 0 else 0
        
        print(f"\n🔸 交易統計:")
        print(f"   總交易次數: {total_trades}")
        print(f"   勝率: {win_rate:.1f}% ({won_trades}勝 / {lost_trades}敗)")
        print(f"   獲利因子 (PF): {profit_factor:.2f}")
        print(f"   平均獲利: ${avg_win:.2f}")
        print(f"   平均虧損: ${avg_loss:.2f}")
        
        # 回撤分析
        drawdown = strat.analyzers.drawdown.get_analysis()
        max_dd = drawdown.max.drawdown
        max_dd_len = drawdown.max.len
        print(f"\n📉 風險指標:")
        print(f"   最大回撤: {max_dd:.2f}%")
        print(f"   回撤期間: {max_dd_len} 根K線")
        
        # 夏普比率
        sharpe = strat.analyzers.sharpe.get_analysis()
        if sharpe['sharperatio'] is not None:
            print(f"   夏普比率: {sharpe['sharperatio']:.2f}")
    else:
        print("\n⚠️ 無交易產生")

    print(f"{'='*50}")
    
    # 繪圖
    # cerebro.plot(style='candlestick', volume=False)
