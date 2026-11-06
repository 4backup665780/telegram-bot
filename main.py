from flask import Flask
import threading, os
app = Flask(__name__)
@app.route('/')
def home():
    return "BOT RUNNING - OP-1 + SUPPORT RESISTANCE"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))).start()

import time
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from tradingview_ta import TA_Handler, Interval as TA_Interval

BD_TZ = timezone(timedelta(hours=6))
def now_bd():
    return datetime.now(BD_TZ)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
AMOUNT = 3

PAIRS = {
    "EUR/USD": {"tv_symbol": "EURUSD", "tv_exchange": "OANDA"},
    "GBP/USD": {"tv_symbol": "GBPUSD", "tv_exchange": "OANDA"},
    "USD/JPY": {"tv_symbol": "USDJPY", "tv_exchange": "OANDA"},
    "AUD/USD": {"tv_symbol": "AUDUSD", "tv_exchange": "OANDA"},
    "USD/CAD": {"tv_symbol": "USDCAD", "tv_exchange": "OANDA"},
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
        handler = TA_Handler(symbol=tv_symbol, screener="forex", exchange="OANDA", interval=TA_Interval.INTERVAL_1_MINUTE)
        analysis = handler.get_analysis()
        ind = analysis.indicators
        return {"price": float(ind["close"]), "open": float(ind["open"]), "rsi": float(ind["RSI"]), "ema20": float(ind["EMA20"])}
    except Exception as e:
        print(f"TA Error {tv_symbol}: {e}")
        return None

def get_sr_and_last_candle(tv_symbol, tv_exchange):
    # Support Resistance + Last Candel Color - TradingView History theke
    try:
        now_ts = int(time.time())
        from_ts = now_ts - 35*60
        symbol_full = f"{tv_exchange}:{tv_symbol}"
        url = f"https://udf-proxy.tradingview.com/history?symbol={symbol_full}&resolution=1&from={from_ts}&to={now_ts}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data.get("s") != "ok" or "c" not in data:
            return None
        highs = data["h"]
        lows = data["l"]
        closes = data["c"]
        opens = data["o"]
        if len(closes) < 25:
            return None
        use_highs = highs[-31:-1]
        use_lows = lows[-31:-1]
        support = min(use_lows)
        resistance = max(use_highs)
        # Last Closed Candel - Running ta bad diye ager ta
        last_close = closes[-2]
        last_open = opens[-2]
        last_green = last_close > last_open  # SOBUJ True, LAL False
        last_red = not last_green
        return {
            "support": float(support),
            "resistance": float(resistance),
            "middle": float((support + resistance)/2),
            "range_pips": float(resistance - support),
            "last_green": last_green,
            "last_red": last_red,
            "last_close": float(last_close),
            "last_open": float(last_open),
        }
    except Exception as e:
        print(f"SR Error {tv_symbol}: {e}")
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
    for pair_name, symbols in PAIRS.items():
        tv = get_tradingview_data(symbols["tv_symbol"])
        if tv is None:
            continue
        sr = get_sr_and_last_candle(symbols["tv_symbol"], symbols["tv_exchange"])
        if sr is None:
            if manual:
                send_telegram(f"❌ {pair_name} - Data Pawa Jay Nai")
            continue

        price = tv["price"]
        ema20 = tv["ema20"]
        rsi = tv["rsi"]
        support = sr["support"]
        resistance = sr["resistance"]
        last_green = sr["last_green"]
        last_red = sr["last_red"]

        # OP-1 Terms
        is_sobuj = last_green
        is_lal = last_red
        is_upore = price > ema20
        is_niche = price < ema20

        # SR Terms
        dist_support_pct = abs(price - support) / price * 100 if price != 0 else 999
        dist_resistance_pct = abs(price - resistance) / price * 100 if price != 0 else 999
        near_support = dist_support_pct <= 0.12 or price < support  # Support er kache ba venge niche
        near_resistance = dist_resistance_pct <= 0.12 or price > resistance  # Resistance er kache ba venge upore
        breakout_up = price > resistance
        breakdown_down = price < support

        # Safety Flat Check
        min_range = 0.0004 if "JPY" not in pair_name else 0.04
        if sr["range_pips"] < min_range:
            if manual:
                send_telegram(f"⏳ {pair_name} - FLAT MARKET = WAIT\nSupport {support:.5f} | Resistance {resistance:.5f}")
            continue

        direction = None
        reason = ""
        price_line = ""
        rule_name = ""

        # ===== RULE 1: SOBUJ + UPORE + RSI 40-70 + SR = BUY =====
        if is_sobuj and is_upore and 40 <= rsi <= 70 and (near_support or breakout_up):
            direction = "🟢 BUY"
            rule_name = "Rule 1: SOBUJ + UPORE + RSI 40-70 + SR"
            sr_txt = "Breakout Above Resistance" if breakout_up else f"Support {support:.5f} er kache Bounce"
            reason = f"Rule 1: Last Candel SOBUJ + Price EMA20 ({ema20:.5f}) er UPORE + RSI {round(rsi)} (40-70) + SR: {sr_txt}"
            price_line = f"Price {price:.5f} | Support {support:.5f} | Resistance {resistance:.5f}"

        # ===== RULE 2: LAL + NICHE + RSI 30-60 + SR = SELL =====
        elif is_lal and is_niche and 30 <= rsi <= 60 and (near_resistance or breakdown_down):
            direction = "🔴 SELL"
            rule_name = "Rule 2: LAL + NICHE + RSI 60-30 + SR"
            sr_txt = "Breakdown Below Support" if breakdown_down else f"Resistance {resistance:.5f} er kache Rejection"
            reason = f"Rule 2: Last Candel LAL + Price EMA20 ({ema20:.5f}) er NICHE + RSI {round(rsi)} (30-60) + SR: {sr_txt}"
            price_line = f"Price {price:.5f} | Support {support:.5f} | Resistance {resistance:.5f}"

        # ===== RULE 3: LAL + UPORE + RSI 40-70 = WAIT =====
        elif is_lal and is_upore and 40 <= rsi <= 70:
            if manual:
                send_telegram(f"⏳ {pair_name} - Rule 3: LAL + UPORE + RSI {round(rsi)} = WAIT\nPrice {price:.5f} | EMA {ema20:.5f} | Support {support:.5f} | Resistance {resistance:.5f}")
            continue

        # ===== RULE 4: SOBUJ + NICHE + RSI 30-60 = WAIT =====
        elif is_sobuj and is_niche and 30 <= rsi <= 60:
            if manual:
                send_telegram(f"⏳ {pair_name} - Rule 4: SOBUJ + NICHE + RSI {round(rsi)} = WAIT\nPrice {price:.5f} | EMA {ema20:.5f} | Support {support:.5f} | Resistance {resistance:.5f}")
            continue

        # ===== OP-1 Milse kintu SR Milenai = WAIT (Middle Zone) =====
        elif (is_sobuj and is_upore and 40 <= rsi <= 70) or (is_lal and is_niche and 30 <= rsi <= 60):
            if manual:
                send_telegram(f"⏳ {pair_name} - OP-1 Milse kintu SR Milenai = WAIT\nLast Candel {'SOBUJ' if is_sobuj else 'LAL'} + {'UPORE' if is_upore else 'NICHE'} + RSI {round(rsi)}\nPrice {price:.5f} | Support {support:.5f} | Resistance {resistance:.5f} | Middle Zone e ache")
            continue

        else:
            if manual:
                send_telegram(f"❌ {pair_name} - Kono Rule Milenai\nLast Candel {'SOBUJ' if is_sobuj else 'LAL'} | {'UPORE' if is_upore else 'NICHE'} | RSI {round(rsi)}\nPrice {price:.5f} | EMA {ema20:.5f}\nSupport {support:.5f} | Resistance {resistance:.5f}")
            continue

        tag = "✋ MANUAL" if manual else "🤖 AUTO"
        msg = f"""🚨 {tag} - OP-1 + SR MODE
📊 Asset: {pair_name}
⏱️ Expiry: M1
🎯 Direction: {direction}
💰 Price: {price_line}
🕒 Entry Time: {next_candle_time} (BD Time UTC+6)
📩 Signal Time: {now.strftime('%H:%M:%S')} - Running Candel {now.strftime('%H:%M')} er 25-30s e Analysis
⚠️ Safety: 0-10s Dekhbo, 10-20s Trade, 20s+ NO TRADE
✅ Reason: {reason}
💰 Amount: ${AMOUNT}
📌 Note: OP-1 (SOBUJ/LAL + UPORE/NICHE + RSI) + Support/Resistance Double Confirm"""
        send_telegram(msg)
        print(f"Signal OP1+SR: {pair_name} {direction} for {next_candle_time} - {rule_name}")
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
                msg = f"""📢 RESULT - {pred['entry_time']} CANDLE [OP-1 + SR]
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
                send_telegram("🔍 OP-1 + Support/Resistance Analysis kortesi... 5 Pair Check kortesi")
                check_all_markets(manual=True)
            elif text == "win":
                today_win += 1
                send_telegram(f"✅ WIN Record korsi\n📈 Total Today: {today_win} Win - {today_loss} Loss")
                if today_win >= 3:
                    send_telegram("⚠️ Rule 6: 3 Win = STOP")
            elif text == "loss":
                today_loss += 1
                send_telegram(f"❌ LOSS Record korsi\n📈 Total Today: {today_win} Win - {today_loss} Loss")
                if today_loss >= 2:
                    send_telegram("⚠️ Rule 6: 2 Loss = STOP")
    except Exception as e:
        print(f"Telegram Poll Error: {e}")

send_telegram("🤖 BOT UPDATED - OP-1 + SR MODE\n✅ Rule 1: SOBUJ + UPORE + RSI 40-70 = BUY\n✅ Rule 2: LAL + NICHE + RSI 60-30 = SELL\n✅ Rule 3: LAL + UPORE = WAIT\n✅ Rule 4: SOBUJ + NICHE = WAIT\n✅ + Support/Resistance Double Confirm")
print("BOT Started - OP-1 + SR")
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
