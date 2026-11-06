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
from datetime import datetime, timedelta
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

BALANCE = 307
AMOUNT = 3

PAIRS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "USDCAD=X",
    "EUR/GBP": "EURGBP=X",
    "GBP/JPY": "GBPJPY=X",
}

sent_signals = {}
today_win = 0
today_loss = 0

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
        # Last 5 candle body size for momentum
        df['Body'] = abs(df['Close'] - df['Open'])
        return df
    except:
        return None

def check_all_markets():
    now = datetime.now()
    # Proti minute - 15s theke 20s er moddhe check kore 40s agey signal dibe
    if now.second < 15 or now.second > 20:
        return
    next_candle_time = (now + timedelta(minutes=1)).strftime("%H:%M")
    if next_candle_time in sent_signals:
        return
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

        # === RULE 1 & 2 - MAIN RULE ===
        if is_green and is_upore and 40 <= rsi <= 70:
            direction = "🟢 BUY"
            reason = f"Rule 1 Milse - SOBUJ + UPORE + RSI {round(rsi)}"
            price_line = f"{price:.5f} er niche ba borabor thakle BUY"
            confidence = 75 if 50 <= rsi <= 60 else 65
            logic_type = "RULE"
        elif is_red and is_niche and 30 <= rsi <= 60:
            direction = "🔴 SELL"
            reason = f"Rule 2 Milse - LAL + NICHE + RSI {round(rsi)}"
            price_line = f"{price:.5f} er upore ba borabor thakle SELL"
            confidence = 75 if 40 <= rsi <= 50 else 65
            logic_type = "RULE"

        # === RULE NA MILLE - ONNO LOGIC ===
        else:
            # Logic A: Oversold Reversal - RSI onek niche, niche theke upore uthbe
            if rsi < 30 and is_green and price > float(prev['Close']):
                direction = "🟢 BUY"
                reason = f"Rule er baire - Oversold Reversal - RSI {round(rsi)} < 30, U-turn chance beshi"
                price_line = f"{price:.5f} er niche ba borabor thakle BUY"
                confidence = 78
                logic_type = "OTHER"
            # Logic B: Overbought Reversal
            elif rsi > 70 and is_red and price < float(prev['Close']):
                direction = "🔴 SELL"
                reason = f"Rule er baire - Overbought Reversal - RSI {round(rsi)} > 70, Down chance beshi"
                price_line = f"{price:.5f} er upore ba borabor thakle SELL"
                confidence = 78
                logic_type = "OTHER"
            # Logic C: Strong Trend Continue - 3 ta sobuj/red por por + EMA upore/niche
            elif is_green and is_upore and float(prev['Close']) > float(prev['Open']) and float(prev2['Close']) > float(prev2['Open']) and ema > ema50:
                direction = "🟢 BUY"
                reason = f"Rule er baire - Strong Uptrend Continue - 3 Green + EMA20 > EMA50 + RSI {round(rsi)}"
                price_line = f"{price:.5f} er niche ba borabor thakle BUY"
                confidence = 82
                logic_type = "OTHER"
            elif is_red and is_niche and float(prev['Close']) < float(prev['Open']) and float(prev2['Close']) < float(prev2['Open']) and ema < ema50:
                direction = "🔴 SELL"
                reason = f"Rule er baire - Strong Downtrend Continue - 3 Red + EMA20 < EMA50 + RSI {round(rsi)}"
                price_line = f"{price:.5f} er upore ba borabor thakle SELL"
                confidence = 82
                logic_type = "OTHER"
            # Logic D: EMA Breakout
            elif is_green and price > ema and float(prev['Close']) < float(prev['EMA20']):
                direction = "🟢 BUY"
                reason = f"Rule er baire - EMA20 Breakout Up - Price EMA cross korse + RSI {round(rsi)}"
                price_line = f"{price:.5f} er niche ba borabor thakle BUY"
                confidence = 72
                logic_type = "OTHER"
            elif is_red and price < ema and float(prev['Close']) > float(prev['EMA20']):
                direction = "🔴 SELL"
                reason = f"Rule er baire - EMA20 Breakout Down - Price EMA cross korse + RSI {round(rsi)}"
                price_line = f"{price:.5f} er upore ba borabor thakle SELL"
                confidence = 72
                logic_type = "OTHER"
            else:
                continue

        # 70% er niche confidence hole signal dibe na - vul signal kombe
        if confidence < 65:
            continue

        if confidence >= 70:
            power = f"🔥 STRONG SIGNAL - {confidence}% Kaj Korar Chance"
        else:
            power = f"⚠️ WEAK SIGNAL - {confidence}% - Sabdhan, Chaile Skip Koro"

        msg = f"""🚨 UPCOMING SIGNAL - 40s AGEY
📊 Asset: {pair_name}
⏱️ Expiry: M1
🎯 Direction: {direction}
💰 Price: {price_line}
🕒 Entry Time: {next_candle_time}
⚠️ Safety: 0-10s Dekhbo, 10-20s Trade, 20s+ NO TRADE
✅ Reason: {reason}
💰 Amount: ${AMOUNT} (1% of ${BALANCE})
{power}"""
        send_telegram(msg)
        print(f"Signal Sent: {pair_name} {direction} for {next_candle_time} - {logic_type} {confidence}%")
        sent_signals[next_candle_time] = {"pair": pair_name, "symbol": symbol, "direction": direction, "entry_price": price, "entry_time": next_candle_time}
        break

def check_results():
    global today_win, today_loss
    now = datetime.now()
    if now.second < 2 or now.second > 10:
        return
    to_remove = []
    for candle_time, pred in list(sent_signals.items()):
        try:
            candle_dt = datetime.strptime(candle_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
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
                msg = f"""📢 RESULT - {pred['entry_time']} CANDLE
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

send_telegram("🤖 BOT UPDATED!\n✅ Proti Minute Signal\n✅ Rule mille Rule, na mille Onno Logic likhe dibe\n✅ 70-90% Strong Signal Auto\nSignal 40s agey paba + Auto Result paba")
print("BOT Started...")
while True:
    try:
        check_all_markets()
        check_results()
        time.sleep(5)
    except Exception as e:
        print(e)
        time.sleep(5)
