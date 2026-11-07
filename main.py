from flask import Flask
import threading, os
app = Flask(__name__)
@app.route('/')
def home():
    return "BOT RUNNING - 5MIN BOX + 1MIN 40SEC TOUCH"
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

# ===== STEP 1: 5 MIN CANDLE THEKE BOX BANAO - CLASS ER NIYOM =====
def get_5min_box(yahoo_symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=5m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        result = data.get("chart", {}).get("result", [None])[0]
        if not result:
            return None
        quote = result["indicators"]["quote"][0]
        highs = [h for h in quote["high"] if h is not None]
        lows = [l for l in quote["low"] if l is not None]
        closes = [c for c in quote["close"] if c is not None]
        if len(highs) < 10 or len(lows) < 10:
            return None
        highs = highs[-30:]
        lows = lows[-30:]
        closes = closes[-30:]
        last_price = closes[-1]
        # 5 MIN ER SOBCHE UPORE 3 TA HIGH = RESISTANCE BOX
        # 5 MIN ER SOBCHE NICHE 3 TA LOW = SUPPORT BOX
        sorted_highs = sorted(highs, reverse=True)
        sorted_lows = sorted(lows)
        res_center = sum(sorted_highs[:3]) / 3
        sup_center = sum(sorted_lows[:3]) / 3
        # BOX WIDTH - 5 MIN er jonno boro - 0.15%
        box_width = last_price * 0.0015
        # JPY pair hole width ektu boro
        if last_price > 50:
            box_width = last_price * 0.0015
        box = {
            "res_center": float(res_center),
            "res_top": float(res_center + box_width),
            "res_bottom": float(res_center - box_width),
            "sup_center": float(sup_center),
            "sup_top": float(sup_center + box_width),
            "sup_bottom": float(sup_center - box_width),
            "box_width": float(box_width),
            "range": float(res_center - sup_center),
        }
        return box
    except Exception as e:
        print(f"5MIN Box Error {yahoo_symbol}: {e}")
        return None

# ===== STEP 2: 1 MIN CANDLE THEKE CURRENT PRICE + WICK + RSI =====
def get_1min_data(yahoo_symbol, tv_symbol, tv_exchange):
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
            if len(closes) >= 20:
                tv = {
                    "price": float(closes[-1]),
                    "open": float(opens[-1]),
                    "high": float(highs[-1]),
                    "low": float(lows[-1]),
                    "rsi": float(calc_rsi(closes)),
                    "closes": closes,
                    "opens": opens,
                    "highs": highs,
                    "lows": lows,
                }
                return tv
    except Exception as e:
        print(f"1MIN Error {yahoo_symbol}: {e}")
    return None

def get_box_and_1min(pair_info):
    # Age 5 MIN BOX anbo
    box = get_5min_box(pair_info["yahoo"])
    # Tarpor 1 MIN data
