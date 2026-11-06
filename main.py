from flask import Flask
import threading, os
app = Flask(__name__)
@app.route('/')
def home():
    return "BOT IS RUNNING"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))).start()

import time
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone

BD_TZ = timezone(timedelta(hours=6))
def now_bd():
    return datetime.now(BD_TZ)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
BALANCE = 307
AMOUNT = 3
PAIRS = {"EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X"}
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

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_market_data(symbol):
    try:
        df = yf.download(symbol, period="1d", interval="1m", progress=False)
        if df.empty or len(df) < 25:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df['EMA20'] = df['Close'].ewm(span=20).mean()
        df['EMA50'] = df['Close'].ewm(span=50).mean()
        df['RSI'] = calculate_rsi(df['Close'])
        return df
    except Exception as e:
        print(f"Yahoo Error {symbol}: {e}")
        return None

def check_all_markets(manual=False):
    global last_signal_minute
    now = now_bd()
    entry_dt = now + timedelta(minutes=1)
    next_candle_time = entry_dt.strftime("%H:%M")
    if not manual and next_candle_time == last_signal_minute:
        return
    if not manual and next_candle_time in sent_signals:
        return
    for pair_name, symbol in PAIRS.items():
        df = get_market_data(symbol)
        if df is None:
            continue
        last_10 = df.tail(10)
        last = df.iloc[-1]
        price = float(last['Close'])
        ema = float(last['EMA20'])
        rsi = float(last['RSI'])
        is_upore = price > ema
        is_niche = price < ema
        green_count = 0
        red_count = 0
        for i in range(len(last_10)):
            row = last_10.iloc[i]
            if float(row['Close']) > float(row['Open']):
                green_count += 1
            else:
                red_count += 1
        last_green = float(last['Close']) > float(last['Open'])
        last_red = float(last['Close']) < float(last['Open'])
        direction = None
        reason = ""
        price_line = ""
        rule_name = ""
        # PRIORITY 1: OP-1 RULE 1 BUY
        if green_count >= 6 and is_upore and 40 <= rsi <= 70:
            direction = "🟢 BUY"
            rule_name = "OP-1 Rule 1"
            reason = f"OP-1: 10 Candel e {green_count} SOBUJ + UPORE + RSI {round(rsi)} (40-70)"
            price_line = f"{price:.5f} er niche ba borabor thakle BUY"
        # PRIORITY 2: OP-1 RULE 2 SELL
        elif red_count >= 6 and is_niche and 30 <= rsi <= 60:
            direction = "🔴 SELL"
            rule_name = "OP-1 Rule 2"
            reason = f"OP-1: 10 Candel e {red_count} LAL + NICHE + RSI {round(rsi)} (30-60)"
            price_line = f"{price:.5f} er upore ba borabor thakle SELL"
        # PRIORITY 3: EXTRA STRONG
        elif green_count >= 9 and is_upore:
            direction = "🟢 BUY"
            rule_name = "EXTRA STRONG"
            reason = f"EXTRA STRONG: 10 Candel e {green_count}/10 SOBUJ + UPORE + RSI {round(rsi)}"
            price_line = f"{price:.5f} er niche ba borabor thakle BUY"
        elif red_count >= 9 and is_niche:
            direction = "🔴 SELL"
            rule_name = "EXTRA STRONG"
            reason = f"EXTRA STRONG: 10 Candel e {red_count}/10 LAL + NICHE + RSI {round(rsi)}"
            price_line = f"{price:.5f} er upore ba borabor thakle SELL"
        # PRIORITY 4: WAIT
        elif last_red and is_upore and 40 <= rsi <= 70:
            if manual:
                send_telegram(f"⏳ {pair_name} - Rule 3: LAL + UPORE = WAIT")
            continue
        elif last_green and is_niche and 30 <= rsi <= 60:
            if manual:
                send_telegram(f"⏳ {pair_name} - Rule 4: SOBUJ + NICHE = WAIT")
            continue
        else:
            if manual:
                send_telegram(f"❌ {pair_name} - Kono Rule Milenai - 10 Candel: {green_count} SOBUJ / {red_count} LAL, RSI {round(rsi)}")
            continue
        tag = "✋ MANUAL" if manual else "🤖 AUTO"
        msg = f"""🚨 {tag}
📊 Asset: {pair_name}
⏱️ Expiry: M1
🎯 Direction: {direction}
💰 Price: {price_line}
🕒 Entry Time: {next_candle_time} (BD Time UTC+6)
📩 Signal Time: {now.strftime('%H:%M:%S')} - Running Candel {now.strftime('%H:%M')} er 25-30s e Analysis
⚠️ Safety: 0-10s Dekhbo, 10-20s Trade, 20s+ NO TRADE
✅ Reason: {reason} - {rule_name}
💰 Amount: ${AMOUNT}"""
        send_telegram(msg)
        print(f"Signal: {pair_name} {direction} for {next_candle_time} - {rule_name}")
        sent_signals[next_candle_time] = {"pair": pair_name, "symbol": symbol, "direction": direction, "entry_price": price, "entry_time": next_candle_time}
        last_signal_minute = next_candle_time
        return

def check_results():
    global today_win, today_loss
    now = now_bd()
    if now.second < 2 or now.second > 10:
        return
    to_remove = []
    for candle_time, pred in list(sent_signals.items()):
        try:
            candle_dt = datetime.strptime(candle_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day, tzinfo=BD_TZ)
            diff = (now - candle_dt).total_seconds()
            if diff >= 60 and diff < 180:
                df = get_market_data(pred["symbol"])
                if df is None:
                    continue
                close_price = float(df.iloc[-1]['Close'])
                entry = pred["entry_price"]
                is_win = False
                if "BUY" in pred["direction"] and close_price > entry:
                    is_win = True
                if "SELL" in pred["direction"] and close_price < entry:
                    is_win = True
                if is_win:
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
                msg = f"""📢 RESULT - {pred['entry_time']} CANDLE
📊 Asset: {pred['pair']}
🎯 Direction: {pred['direction']}
💰 Entry: {entry:.5f} -> Close: {close_price:.5f}
{result_txt} {profit}
📈 Total: {today_win} Win - {today_loss} Loss{extra}"""
                send_telegram(msg)
                to_remove.append(candle_time)
        except Exception as e:
            print(f"Result Error: {e}")
    for k in to_remove:
        del sent_signals[k]

def check_telegram_commands():
    global last_update_id
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
                send_telegram("🔍 OP-1 + Extra Strong Analysis kortesi...")
                check_all_markets(manual=True)
    except Exception as e:
        print(f"Telegram Poll Error: {e}")

send_telegram("🤖 BOT UPDATED - OP-1 + EXTRA STRONG\n✅ OP-1 Rule 1/2 + Extra 9/10\n✅ 25-30s Signal, Entry Next Candle")
print("BOT Started - OP-1 + EXTRA STRONG")
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
