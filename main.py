from flask import Flask
import threading, os
app = Flask(__name__)
@app.route('/')
def home():
    return "BOT RUNNING - 40 SEC ZONE - NO PRICE"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))).start()

import time
import requests
from datetime import datetime, timedelta, timezone

BD_TZ = timezone(timedelta(hours=6))
def now_bd():
    return datetime.now(BD_TZ)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

GROUP_A = {
    "EUR/USD": {"yahoo": "EURUSD=X", "tv_symbol": "EURUSD", "tv_exchange": "OANDA"},
    "GBP/USD": {"yahoo": "GBPUSD=X", "tv_symbol": "GBPUSD", "tv_exchange": "OANDA"},
    "USD/JPY": {"yahoo": "USDJPY=X", "tv_symbol": "USDJPY", "tv_exchange": "OANDA"},
    "EUR/JPY": {"yahoo": "EURJPY=X", "tv_symbol": "EURJPY", "tv_exchange": "OANDA"},
}
GROUP_B = {
    "AUD/USD": {"yahoo": "AUDUSD=X", "tv_symbol": "AUDUSD", "tv_exchange": "OANDA"},
    "USD/CAD": {"yahoo": "USDCAD=X", "tv_symbol": "USDCAD", "tv_exchange": "OANDA"},
    "GBP/JPY": {"yahoo": "GBPJPY=X", "tv_symbol": "GBPJPY", "tv_exchange": "OANDA"},
}
ALL_PAIRS = {**GROUP_A, **GROUP_B}

OTC_PAIRS = {
    "EUR/USD OTC": {"yahoo": "EURUSD=X", "tv_symbol": "EURUSD", "tv_exchange": "OANDA"},
    "GBP/USD OTC": {"yahoo": "GBPUSD=X", "tv_symbol": "GBPUSD", "tv_exchange": "OANDA"},
    "USD/JPY OTC": {"yahoo": "USDJPY=X", "tv_symbol": "USDJPY", "tv_exchange": "OANDA"},
    "AUD/USD OTC": {"yahoo": "AUDUSD=X", "tv_symbol": "AUDUSD", "tv_exchange": "OANDA"},
    "USD/CAD OTC": {"yahoo": "USDCAD=X", "tv_symbol": "USDCAD", "tv_exchange": "OANDA"},
    "EUR/JPY OTC": {"yahoo": "EURJPY=X", "tv_symbol": "EURJPY", "tv_exchange": "OANDA"},
}

sent_signals = {}
today_win = 0
today_loss = 0
last_auto_check = 0
last_update_id = 0
last_signal_minute = ""
last_heartbeat = 0
last_auto_wait_msg = 0
otc_mode_manual = False

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def is_forex_market_open():
    now = now_bd()
    if now.weekday() == 5:
        return False
    if now.weekday() == 6:
        return False
    if now.weekday() == 4 and now.hour >= 23:
        return False
    return True

def is_otc_time():
    if otc_mode_manual:
        return True
    if not is_forex_market_open():
        return True
    return False

def calc_ema(closes, period=20):
    if len(closes) < period:
        return closes[-1]
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for p in closes[period:]:
        ema = p * k + ema * (1 - k)
    return ema

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    gains = gains[-period:]
    losses = losses[-period:]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100 if avg_gain > 0 else 50
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def build_from_candles(closes, opens, highs, lows):
    if len(closes) < 35:
        return None, None
    price = float(closes[-1])
    open_price = float(opens[-1])
    high_price = float(highs[-1])
    low_price = float(lows[-1])
    rsi = float(calc_rsi(closes))
    ema20 = float(calc_ema(closes, 20))
    last_30_highs = sorted(highs[-31:-1], reverse=True)
    last_30_lows = sorted(lows[-31:-1])
    res_center = float(sum(last_30_highs[:3]) / 3)
    sup_center = float(sum(last_30_lows[:3]) / 3)
    zone_width = price * 0.0008
    tv = {
        "price": price, "open": open_price, "high": high_price, "low": low_price,
        "rsi": rsi, "ema20": ema20, "closes": closes, "opens": opens, "highs": highs, "lows": lows
    }
    sr = {
        "res_center": res_center,
        "res_top": res_center + zone_width,
        "res_bottom": res_center - zone_width,
        "sup_center": sup_center,
        "sup_top": sup_center + zone_width,
        "sup_bottom": sup_center - zone_width,
        "zone_width": zone_width,
        "range": float(res_center - sup_center),
    }
    return tv, sr

def get_data_and_sr(pair_info):
    yahoo_symbol = pair_info["yahoo"]
    tv_symbol = pair_info["tv_symbol"]
    tv_exchange = pair_info["tv_exchange"]
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        result = data.get("chart", {}).get("result", [None])[0]
        if result:
            quote = result["indicators"]["quote"][0]
            closes = [c for c in quote["close"] if c is not None]
            opens = [o for o in quote["open"] if o is not None]
            highs = [h for h in quote["high"] if h is not None]
            lows = [l for l in quote["low"] if l is not None]
            closes = closes[-50:]
            opens = opens[-50:]
            highs = highs[-50:]
            lows = lows[-50:]
            if len(closes) >= 35:
                return build_from_candles(closes, opens, highs, lows)
    except Exception as e:
        print(f"Yahoo Error {yahoo_symbol}: {e}")
    try:
        now_ts = int(time.time())
        from_ts = now_ts - 50*60
        symbol_full = f"{tv_exchange}:{tv_symbol}"
        url = f"https://udf-proxy.tradingview.com/history?symbol={symbol_full}&resolution=1&from={from_ts}&to={now_ts}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data.get("s") == "ok" and "c" in data:
            return build_from_candles(data["c"], data["o"], data["h"], data["l"])
    except Exception as e:
        print(f"TV Backup Error {tv_symbol}: {e}")
    return None, None

# ===== 40 SEC ZONE TOUCH - NO PRICE SHOW =====
def check_zone_touch(tv, sr, is_otc=False):
    price = tv["price"]
    open_p = tv["open"]
    high_p = tv["high"]
    low_p = tv["low"]
    rsi = tv["rsi"]
    closes = tv["closes"]

    if high_p == low_p:
        return None, "DATA STALE - Price নড়তেছে না"

    if is_otc and len(closes) >= 4:
        last_move = abs(closes[-1] - closes[-4]) / closes[-4] * 100 if closes[-4] != 0 else 0
        if last_move > 0.20:
            return None, "MANIPULATION - হঠাৎ স্পাইক"

    candle_range = high_p - low_p if high_p != low_p else 0.00001
    upper_wick = high_p - max(price, open_p)
    lower_wick = min(price, open_p) - low_p
    upper_wick_ratio = upper_wick / candle_range if candle_range > 0 else 0
    lower_wick_ratio = lower_wick / candle_range if candle_range > 0 else 0

    in_res_zone = (price >= sr["res_bottom"] and price <= sr["res_top"]) or (high_p >= sr["res_bottom"] and high_p <= sr["res_top"] + sr["zone_width"])
    res_wick_ok = upper_wick_ratio >= 0.15
    res_price_in_zone = price >= sr["res_bottom"]
    if in_res_zone and (res_wick_ok or res_price_in_zone):
        if 40 <= rsi <= 85:
            return "🔴 SELL", "Resistance Zone Touch + Wick Rejection"

    in_sup_zone = (price >= sr["sup_bottom"] and price <= sr["sup_top"]) or (low_p >= sr["sup_bottom"] - sr["zone_width"] and low_p <= sr["sup_top"])
    sup_wick_ok = lower_wick_ratio >= 0.15
    sup_price_in_zone = price <= sr
