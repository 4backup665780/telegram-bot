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
    "USD/CAD OTC": {"yahoo": "USDJPY=X", "tv_symbol": "USDJPY", "tv_exchange": "OANDA"},
    "EUR/JPY OTC": {"yahoo": "EURJPY=X", "tv_symbol": "
