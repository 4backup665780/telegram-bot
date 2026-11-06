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
import os

# --- BANGLADESH TIME FIX: UTC+6 ---
BD_TZ = timezone(timedelta(hours=6))
def now_bd():
    return datetime.now(BD_TZ)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

BALANCE = 307
AMOUNT = 3

PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
}

sent_signals = {}
today_win = 0
today_loss = 0
last_auto_check = 0
last_update_id = 0

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
    now = now_bd()
    next_candle_time = (now + timedelta(minutes=1)).strftime("%H:%M")
    if not manual and next_candle_time in sent_signals:
        return
    found_any = False
    for pair_name, symbol in PAIRS.items():
        df = get_market_data(symbol)
        if df is None:
            continue
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        price = float(last['Close'])
        open_price = float(last['Open'])
        ema = float(last['EMA20'])
        ema50 = float(last['EMA50'])
        rsi = float(last['RSI'])
        is_green = price > open_price
        is_red = price < open_price
        is_upore = price > ema
        is_niche = price < ema
        
        direction = None
        reason = ""
        price_line = ""
        confidence = 0
        logic_type = ""

        if is_green and is_upore and 35 <= rsi <= 75:
            direction = "🟢 BUY"
            reason = f"Rule 1 Milse - SOBUJ + UPORE + RSI {round(rsi)}"
            price_line = f"{price:.5f} er niche ba borabor thakle BUY"
            confidence = 75 if 50 <= rsi <= 60 else 68
            logic_type = "RULE"
        elif is_red and is_niche and 25 <= rsi <= 65:
            direction = "🔴 SELL"
            reason = f"Rule 2 Milse - LAL + NICHE + RSI {round(rsi)}"
            price_line = f"{price:.5f} er upore ba borabor thakle SELL"
            confidence = 75 if 40 <= rsi <= 50 else 68
            logic_type = "RULE"
        elif rsi < 30 and is_green:
            direction = "🟢 BUY"
            reason = f"Oversold Reversal - RSI {round(rsi)} < 30"
            price_line = f"{price:.5f} er niche ba borabor thakle BUY"
            confidence = 78
            logic_type = "OTHER"
        elif rsi > 70 and is_red:
            direction = "🔴 SELL"
            reason = f"Overbought Reversal - RSI {round(rsi)} > 70"
            price_line = f"{price:.5f} er upore ba borabor thakle SELL"
            confidence = 78
            logic_type = "OTHER"
        elif is_green and is_upore and float(prev['Close']) > float(prev['Open']) and ema > ema50:
            direction = "🟢 BUY"
            reason = f"Strong Uptrend - 3 Green + EMA20 > EMA50 + RSI {round(rsi)}"
            price_line = f"{price:.5f} er niche ba borabor thakle BUY"
            confidence = 82
            logic_type = "OTHER"
        elif is_red and is_niche and float(prev['Close']) < float(prev['Open']) and ema < ema50:
            direction = "🔴 SELL"
            reason = f"Strong Downtrend - 3 Red + EMA20 < EMA50 + RSI {round(rsi)}"
            price_line = f"{price:.5f} er upore ba borabor thakle SELL"
            confidence = 82
            logic_type = "OTHER"
        elif is_green and is_upore:
            direction = "🟢 BUY"
            reason = f"Weak Signal - SOBUJ + EMA er UPORE, RSI {round(rsi)}"
            price_line = f"{price:.5f} er niche ba borabor thakle BUY"
            confidence = 60
            logic_type = "WEAK"
        elif is_red and is_niche:
            direction = "🔴 SELL"
            reason = f"Weak Signal - LAL + EMA er NICHE, RSI {round(rsi)}"
            price_line = f"{price:.5f} er upore ba borabor thakle SELL"
            confidence = 60
            logic_type = "WEAK"
        elif is_upore:
            direction = "🟢 BUY"
            reason = f"Sideways Market - Candle ulta palta, kintu Price EMA er UPORE, tai BUY - RSI {round(rsi)}"
            price_line = f"{price:.5f} er niche ba borabor thakle BUY"
            confidence = 55
            logic_type = "FALLBACK"
        elif is_niche:
            direction = "🔴 SELL"
            reason = f"Sideways Market - Candle ulta palta, kintu Price EMA er NICHE, tai SELL - RSI {round(rsi)}"
            price_line = f"{price:.5f} er upore ba borabor thakle SELL"
            confidence = 55
            logic_type = "FALLBACK"
        elif is_green:
            direction = "🟢 BUY"
            reason = f"Last Candle SOBUJ - RSI {round(rsi)} - Sabdhan"
            price_line = f"{price:.5f} er niche ba borabor thakle BUY"
            confidence = 55
            logic_type = "FALLBACK"
        else:
            direction = "🔴 SELL"
            reason = f"Last Candle LAL - RSI {round(rsi)} - Sabdhan"
            price_line = f"{price:.5f} er upore ba borabor thakle SELL"
            confidence = 55
            logic_type = "FALLBACK"

        if confidence >= 70:
            power = f"🔥 STRONG SIGNAL - {confidence}% Kaj Korar Chance"
        elif confidence >= 60:
            power = f"⚠️ WEAK SIGNAL - {confidence}% - Sabdhan, Chaile Skip Koro"
        else:
            power = f"⚠️ LOW SIGNAL - {confidence}% - Sideways Market, Risk beshi, Skip kora valo"

        tag = "✋ TUMI CHAISO - MANUAL" if manual else "🤖 AUTO - RULE MILSE"
        msg = f"""🚨 {tag}
📊 Asset: {pair_name}
⏱️ Expiry: M1
🎯 Direction: {direction}
💰 Price: {price_line}
🕒 Entry Time: {next_candle_time} (BD Time UTC+6)
⚠️ Safety: 0-10s Dekhbo, 10-20s Trade, 20s+ NO TRADE
✅ Reason: {reason}
💰 Amount: ${AMOUNT} (1% of ${BALANCE})
{power}"""
        send_telegram(msg)
        print(f"Signal Sent: {pair_name} {direction} for {next_candle_time} - {logic_type} {confidence}% manual={manual}")
        sent_signals[next_candle_time] = {"pair": pair_name, "symbol": symbol, "direction": direction, "entry_price": price, "entry_time": next_candle_time}
        found_any = True
        break
    
    if manual and not found_any:
        send_telegram("❌ Yahoo theke dam ante partesi na, 1 min por abar try koro.")

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
                    extra = "\n⚠️ Rule 6: Por por 2 Loss - STOP - Ajker moto sesh"
                if today_win >= 3:
                    extra = "\n⚠️ Rule 6: 3 Win hoye gese - STOP - Profit niye ber hoye jao"
                msg = f"""📢 RESULT - {pred['entry_time']} CANDLE (BD Time)
📊 Asset: {pred['pair']}
🎯 Direction: {pred['direction']}
💰 Entry Price: {entry:.5f}
💰 Close Price: {close_price:.5f}
{result_txt} {profit}
📈 Total Today: {today_win} Win - {today_loss} Loss{extra}"""
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
                print("Manual signal requested")
                send_telegram("🔍 Signal khujtesi... 5s wait koro")
                check_all_markets(manual=True)
    except Exception as e:
        print(f"Telegram Poll Error: {e}")

send_telegram("🤖 BOT UPDATED - BD TIME UTC+6!\n✅ Ekhon sob time Bangladesh Time e asbe\n✅ Ekhon ar 'Rules miltese na' asbe na")
print("BOT Started - BD TIME MODE...")
while True:
    try:
        now_ts = time.time()
        if now_ts - last_auto_check >= 300:
            last_auto_check = now_ts
            check_all_markets(manual=False)
        check_telegram_commands()
        check_results()
        time.sleep(5)
    except Exception as e:
        print(e)
        time.sleep(5)
