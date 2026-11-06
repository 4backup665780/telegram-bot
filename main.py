from flask import Flask
import threading, os
app = Flask(__name__)
@app.route('/')
def home():
    return "BOT IS RUNNING - TRADINGVIEW MODE 5 PAIRS"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))).start()

import time
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone
from tradingview_ta import TA_Handler, Interval, Exchange

BD_TZ = timezone(timedelta(hours=6))
def now_bd():
    return datetime.now(BD_TZ)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
BALANCE = 307
AMOUNT = 3

# 5 PAIRS - Real Market TradingView
PAIRS = {
    "EUR/USD": {"tv_symbol": "EURUSD", "yahoo": "EURUSD=X"},
    "GBP/USD": {"tv_symbol": "GBPUSD", "yahoo": "GBPUSD=X"},
    "USD/JPY": {"tv_symbol": "USDJPY", "yahoo": "USDJPY=X"},
    "AUD/USD": {"tv_symbol": "AUDUSD", "yahoo": "AUDUSD=X"},
    "USD/CAD": {"tv_symbol": "USDCAD", "yahoo": "USDCAD=X"},
}

sent_signals = {}
today_win = 0
today_loss = 0
last_auto_check = 0
last_update_id = 0
last_signal_minute = ""

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_tradingview_data(tv_symbol):
    try:
        handler = TA_Handler(
            symbol=tv_symbol,
            screener="forex",
            exchange="OANDA",
            interval=Interval.INTERVAL_1_MINUTE
        )
        analysis = handler.get_analysis()
        ind = analysis.indicators
        return {
            "price": float(ind["close"]),
            "open": float(ind["open"]),
            "rsi": float(ind["RSI"]),
            "ema20": float(ind["EMA20"]),
            "ema50": float(ind["EMA50"]),
        }
    except Exception as e:
        print(f"TradingView Error {tv_symbol}: {e}")
        return None

def get_candle_count(yahoo_symbol):
    try:
        df = yf.download(yahoo_symbol, period="1d", interval="1m", progress=False)
        if df.empty or len(df) < 11:
            return 0, 0, True
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        last_10 = df.tail(10)
        green = 0
        red = 0
        for i in range(len(last_10)):
            row = last_10.iloc[i]
            if float(row['Close']) > float(row['Open']):
                green += 1
            else:
                red += 1
        last = df.iloc[-1]
        last_green = float(last['Close']) > float(last['Open'])
        return green, red, last_green
    except Exception as e:
        print(f"Candle Count Error: {e}")
        return 0, 0, True

def check_all_markets(manual=False):
    global last_signal_minute
    now = now_bd()
    entry_dt = now + timedelta(minutes=1)
    next_candle_time = entry_dt.strftime("%H:%M")
    if not manual and next_candle_time == last_signal_minute:
        return
    if not manual and next_candle_time in sent_signals:
        return
    for pair_name, symbols in PAIRS.items():
        tv = get_tradingview_data(symbols["tv_symbol"])
        if tv is None:
            continue
        price = tv["price"]
        ema = tv["ema20"]
        rsi = tv["rsi"]
        is_upore = price > ema
        is_niche = price < ema
        green_count, red_count, last_green = get_candle_count(symbols["yahoo"])
        last_red = not last_green
        direction = None
        reason = ""
        price_line = ""
        rule_name = ""
        # PRIORITY 1: OP-1 RULE 1 BUY
        if green_count >= 6 and is_upore and 40 <= rsi <= 70:
            direction = "🟢 BUY"
            rule_name = "OP-1 Rule 1 [TradingView]"
            reason = f"OP-1: TradingView 10 Candel e {green_count} SOBUJ + UPORE (EMA {ema:.5f}) + RSI {round(rsi)} (40-70)"
            price_line = f"TradingView Price {price:.5f} - Quotex e ei dam er kachakachi dekhle BUY"
        # PRIORITY 2: OP-1 RULE 2 SELL
        elif red_count >= 6 and is_niche and 30 <= rsi <= 60:
            direction = "🔴 SELL"
            rule_name = "OP-1 Rule 2 [TradingView]"
            reason = f"OP-1: TradingView 10 Candel e {red_count} LAL + NICHE (EMA {ema:.5f}) + RSI {round(rsi)} (30-60)"
            price_line = f"TradingView Price {price:.5f} - Quotex e ei dam er kachakachi dekhle SELL"
        # PRIORITY 3: EXTRA STRONG
        elif green_count >= 9 and is_upore:
            direction = "🟢 BUY"
            rule_name = "EXTRA STRONG [TradingView]"
            reason = f"EXTRA STRONG: TradingView 10 Candel e {green_count}/10 SOBUJ + UPORE + RSI {round(rsi)}"
            price_line = f"TradingView Price {price:.5f} - Quotex e ei dam er kachakachi dekhle BUY"
        elif red_count >= 9 and is_niche:
            direction = "🔴 SELL"
            rule_name = "EXTRA STRONG [TradingView]"
            reason = f"EXTRA STRONG: TradingView 10 Candel e {red_count}/10 LAL + NICHE + RSI {round(rsi)}"
            price_line = f"TradingView Price {price:.5f} - Quotex e ei dam er kachakachi dekhle SELL"
        # PRIORITY 4: WAIT
        elif last_red and is_upore and 40 <= rsi <= 70:
            if manual:
                send_telegram(f"⏳ {pair_name} - Rule 3: LAL + UPORE = WAIT [TradingView RSI {round(rsi)}]")
            continue
        elif last_green and is_niche and 30 <= rsi <= 60:
            if manual:
                send_telegram(f"⏳ {pair_name} - Rule 4: SOBUJ + NICHE = WAIT [TradingView RSI {round(rsi)}]")
            continue
        else:
            if manual:
                send_telegram(f"❌ {pair_name} - Kono Rule Milenai [TradingView]\n10 Candel: {green_count} SOBUJ / {red_count} LAL\nRSI {round(rsi)} | Price {price:.5f} | EMA {ema:.5f}")
            continue
        tag = "✋ MANUAL" if manual else "🤖 AUTO"
        msg = f"""🚨 {tag} - TradingView Mode 5 Pairs
📊 Asset: {pair_name}
⏱️ Expiry: M1
🎯 Direction: {direction}
💰 Price: {price_line}
🕒 Entry Time: {next_candle_time} (BD Time UTC+6)
📩 Signal Time: {now.strftime('%H:%M:%S')} - Running Candel {now.strftime('%H:%M')} er 25-30s e Analysis
⚠️ Safety: 0-10s Dekhbo, 10-20s Trade, 20s+ NO TRADE
✅ Reason: {reason}
💰 Amount: ${AMOUNT}
📌 Note: Price TradingView er, Quotex e 1-2 pips alada hote pare"""
        send_telegram(msg)
        print(f"Signal TV: {pair_name} {direction} for {next_candle_time} - {rule_name}")
        sent_signals[next_candle_time] = {"pair": pair_name, "direction": direction, "tv_symbol": symbols["tv_symbol"], "entry_price": price, "entry_time": next_candle_time}
        last_signal_minute = next_candle_time
        return

def check_results():
    global today_win, today_loss
    now = now_bd()
    if not (5 <= now.second <= 20):
        return
    to_remove = []
    for candle_time, pred in list(sent_signals.items()):
        try:
            candle_dt = datetime.strptime(candle_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day, tzinfo=BD_TZ)
            diff = (now - candle_dt).total_seconds()
            if diff >= 65 and diff < 180:
                tv = get_tradingview_data(pred["tv_symbol"])
                if tv is None:
                    continue
                close_price = tv["price"]
                entry = pred["entry_price"]
                is_win_tv = False
                if "BUY" in pred["direction"] and close_price > entry:
                    is_win_tv = True
                if "SELL" in pred["direction"] and close_price < entry:
                    is_win_tv = True
                if is_win_tv:
                    today_win += 1
                    result_txt = "✅ RESULT: WIN ✅"
                    profit = "+$2.40"
                else:
                    today_loss += 1
                    result_txt = "❌ RESULT: LOSS ❌"
                    profit = "-$3.00"
                extra = ""
                if today_loss >= 2:
                    extra = "\n⚠️ Rule 6: 2 Loss = STOP"
                if today_win >= 3:
                    extra = "\n⚠️ Rule 6: 3 Win = STOP"
                msg = f"""📢 RESULT - {pred['entry_time']} CANDLE [TradingView]
📊 Asset: {pred['pair']}
🎯 Direction: {pred['direction']}
💰 Entry: {entry:.5f} -> Close: {close_price:.5f} (TradingView)
{result_txt} {profit}
📈 Total: {today_win} Win - {today_loss} Loss{extra}
📌 Note: Eta TradingView Result. Quotex e alada hole 'win' / 'loss' likhe thik kore dao"""
                send_telegram(msg)
                to_remove.append(candle_time)
        except Exception as e:
            print(f"Result Error: {e}")
    for k in to_remove:
        del sent_signals[k]

def check_telegram_commands():
    global last_update_id, today_win, today_loss
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={last_update_id+1}&timeout=2"
        r = requests.get(url, timeout=5).json()
        if not r.get("ok"):
            return
        for upd in r.get("result", []):
            last_update_id = upd["update_id"]
            msg_data = upd.get("message", {})
            text = (msg_data.get("text") or "").strip().lower()
            if text == "signal":
                send_telegram("🔍 TradingView 5 Pairs theke OP-1 + Extra Strong Analysis kortesi...")
                check_all_markets(manual=True)
            elif text == "win":
                today_win += 1
                send_telegram(f"✅ WIN Record korsi (Manual Correction)\n📈 Total Today: {today_win} Win - {today_loss} Loss")
                if today_win >= 3:
                    send_telegram("⚠️ Rule 6: 3 Win = STOP")
            elif text == "loss":
                today_loss += 1
                send_telegram(f"❌ LOSS Record korsi (Manual Correction)\n📈 Total Today: {today_win} Win - {today_loss} Loss")
                if today_loss >= 2:
                    send_telegram("⚠️ Rule 6: 2 Loss = STOP")
    except Exception as e:
        print(f"Telegram Poll Error: {e}")

send_telegram("🤖 BOT UPDATED - TRADINGVIEW 5 PAIRS\n✅ EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CAD\n✅ RSI/EMA TradingView OANDA theke\n✅ OP-1 + Extra Strong + Result Comparison")
print("BOT Started - TRADINGVIEW 5 PAIRS")
while True:
    try:
        now = now_bd()
        if 25 <= now.second <= 30:
            if time.time() - last_auto_check >= 50:
                last_auto_check = time.time()
                check_all_markets(manual=False)
        check_telegram_commands()
        check_results()
        time.sleep(1)
    except Exception as e:
        print(e)
        time.sleep(1)
