from flask import Flask
import threading, os
app = Flask(__name__)
@app.route('/')
def home():
    return "BOT RUNNING - REAL MARKET ONLY"
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

sent_signals = {}
today_win = 0
today_loss = 0
last_auto_check = 0
last_update_id = 0
last_signal_minute = ""
last_heartbeat = 0
last_auto_wait_msg = 0

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg}, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def is_forex_market_open():
    now = now_bd()
    # Saturday = 5, Sunday = 6 - Market Closed
    if now.weekday() == 5:
        return False
    if now.weekday() == 6:
        return False
    # Friday 11 PM er por Market Closed
    if now.weekday() == 4 and now.hour >= 23:
        return False
    return True

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
    if len(closes) < 25:
        return None, None
    price = float(closes[-1])
    open_price = float(opens[-1])
    rsi = float(calc_rsi(closes))
    ema20 = float(calc_ema(closes, 20))
    tv = {"price": price, "open": open_price, "rsi": rsi, "ema20": ema20}
    use_highs = highs[-31:-1]
    use_lows = lows[-31:-1]
    support = float(min(use_lows))
    resistance = float(max(use_highs))
    last_close = float(closes[-2])
    last_open = float(opens[-2])
    last_green = last_close > last_open
    sr = {
        "support": support,
        "resistance": resistance,
        "middle": float((support + resistance)/2),
        "range_pips": float(resistance - support),
        "last_green": last_green,
        "last_red": not last_green,
        "last_close": last_close,
        "last_open": last_open,
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
            if len(closes) >= 25:
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

def check_all_markets(manual=False):
    global last_signal_minute, last_auto_wait_msg
    now = now_bd()

    # MARKET CLOSED HOLE SIGNAL DIBO NA
    if not is_forex_market_open():
        if manual:
            send_telegram("⛔ Real Market Closed - Sat/Sun\n✅ Market Khulbe Monday Sokal\n❌ OTC Signal OFF - OTC dibo na")
        return

    entry_dt = now + timedelta(minutes=1)
    next_candle_time = entry_dt.strftime("%H:%M")
    if not manual and next_candle_time == last_signal_minute:
        return
    if not manual and next_candle_time in sent_signals:
        return

    if manual:
        PAIRS_TO_CHECK = ALL_PAIRS
        group_name = "REAL - ALL 7"
    else:
        if now.minute % 2 == 0:
            PAIRS_TO_CHECK = GROUP_A
            group_name = "REAL - GROUP A (4 Pair)"
        else:
            PAIRS_TO_CHECK = GROUP_B
            group_name = "REAL - GROUP B (3 Pair)"

    print(f"Checking {group_name} at {now.strftime('%H:%M:%S')}")
    start_time = time.time()
    checked = 0
    failed = 0
    wait_list = []

    for pair_name, symbols in PAIRS_TO_CHECK.items():
        try:
            checked += 1
            tv, sr = get_data_and_sr(symbols)
            if tv is None or sr is None:
                failed += 1
                if manual:
                    send_telegram(f"❌ {pair_name} - Data Fail")
                time.sleep(0.8)
                continue

            price = tv["price"]
            ema20 = tv["ema20"]
            rsi = tv["rsi"]
            support = sr["support"]
            resistance = sr["resistance"]
            last_green = sr["last_green"]
            last_red = sr["last_red"]

            is_sobuj = last_green
            is_lal = last_red
            is_upore = price > ema20
            is_niche = price < ema20
            dist_support_pct = abs(price - support) / price * 100 if price != 0 else 999
            dist_resistance_pct = abs(price - resistance) / price * 100 if price != 0 else 999
            near_support = dist_support_pct <= 0.12 or price < support
            near_resistance = dist_resistance_pct <= 0.12 or price > resistance
            breakout_up = price > resistance
            breakdown_down = price < support
            sr_near_support = dist_support_pct <= 0.08 and price > support
            sr_near_resistance = dist_resistance_pct <= 0.08 and price < resistance
            min_range = 0.0004 if "JPY" not in pair_name else 0.04
            if sr["range_pips"] < min_range:
                wait_list.append(f"{pair_name} FLAT")
                if manual:
                    send_telegram(f"⏳ {pair_name} - FLAT = WAIT")
                time.sleep(0.5)
                continue

            direction = None
            reason = ""
            price_line = ""
            signal_type = ""
            if is_sobuj and is_upore and 40 <= rsi <= 70 and (near_support or breakout_up):
                direction = "🟢 BUY"
                signal_type = "STRONG - OP-1"
                sr_txt = "Breakout" if breakout_up else f"Support {support:.5f} Bounce"
                reason = f"OP-1: SOBUJ + EMA UPORE + RSI {round(rsi)} + {sr_txt}"
                price_line = f"Price {price:.5f} | S {support:.5f} | R {resistance:.5f}"
            elif is_lal and is_niche and 30 <= rsi <= 60 and (near_resistance or breakdown_down):
                direction = "🔴 SELL"
                signal_type = "STRONG - OP-1"
                sr_txt = "Breakdown" if breakdown_down else f"Resistance {resistance:.5f} Rejection"
                reason = f"OP-1: LAL + EMA NICHE + RSI {round(rsi)} + {sr_txt}"
                price_line = f"Price {price:.5f} | S {support:.5f} | R {resistance:.5f}"
            elif sr_near_support and 25 <= rsi <= 55:
                direction = "🟢 BUY"
                signal_type = "SR FALLBACK"
                reason = f"SR: Support {support:.5f} kache + RSI {round(rsi)}"
                price_line = f"Price {price:.5f} | S {support:.5f} | R {resistance:.5f}"
            elif sr_near_resistance and 45 <= rsi <= 75:
                direction = "🔴 SELL"
                signal_type = "SR FALLBACK"
                reason = f"SR: Resistance {resistance:.5f} kache + RSI {round(rsi)}"
                price_line = f"Price {price:.5f} | S {support:.5f} | R {resistance:.5f}"
            elif breakout_up and 55 <= rsi <= 75:
                direction = "🟢 BUY"
                signal_type = "SR FALLBACK"
                reason = f"Breakout R {resistance:.5f} + RSI {round(rsi)}"
                price_line = f"Price {price:.5f} | Breakout R {resistance:.5f}"
            elif breakdown_down and 25 <= rsi <= 45:
                direction = "🔴 SELL"
                signal_type = "SR FALLBACK"
                reason = f"Breakdown S {support:.5f} + RSI {round(rsi)}"
                price_line = f"Price {price:.5f} | Breakdown S {support:.5f}"
            else:
                wait_list.append(f"{pair_name} WAIT")
                if manual:
                    send_telegram(f"⏳ {pair_name} - WAIT\nLast {'SOBUJ' if is_sobuj else 'LAL'} + {'UPORE' if is_upore else 'NICHE'} + RSI {round(rsi)}\nPrice {price:.5f} | S {support:.5f} | R {resistance:.5f}")
                time.sleep(0.5)
                continue

            tag = "✋ MANUAL" if manual else "🤖 AUTO"
            # TOMAR CORRECTION ORDER - Entry Time UPORE
            msg = f"""🕒 Entry Time: {next_candle_time} (BD Time)
📊 Asset: {pair_name}
🎯 Direction: {direction}
⏱️ Expiry: M1
🚨 {tag} - {signal_type}
💰 Price: {price_line}
✅ Reason: {reason}
📩 Signal Time: {now.strftime('%H:%M:%S')}"""
            send_telegram(msg)
            sent_signals[next_candle_time] = {"pair": pair_name, "direction": direction, "pair_info": symbols, "entry_price": price, "entry_time": next_candle_time}
            last_signal_minute = next_candle_time
            return

        except Exception as e:
            print(f"Pair Error {pair_name}: {e}")
            continue

    if manual:
        elapsed = round(time.time() - start_time, 1)
        send_telegram(f"🏁 CHECK SES - {elapsed}s\nChecked: {checked} | Fail: {failed}\nWAIT: {', '.join(wait_list) if wait_list else 'Nai'}")

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
                tv, sr = get_data_and_sr(pred["pair_info"])
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
                    extra = "\n⚠️ 2 Loss = STOP"
                if today_win >= 3:
                    extra = "\n⚠️ 3 Win = STOP"
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
                if not is_forex_market_open():
                    send_telegram("⛔ Real Market Closed - Sat/Sun\n✅ Market Khulbe Monday Sokal\n❌ OTC Signal OFF")
                else:
                    send_telegram("🔍 Real Check kortesi...")
                    check_all_markets(manual=True)
            elif text == "win":
                today_win += 1
                send_telegram(f"✅ WIN Record korsi\n📈 Total: {today_win} Win - {today_loss} Loss")
                if today_win >= 3:
                    send_telegram("⚠️ 3 Win = STOP")
            elif text == "loss":
                today_loss += 1
                send_telegram(f"❌ LOSS Record korsi\n📈 Total: {today_win} Win - {today_loss} Loss")
                if today_loss >= 2:
                    send_telegram("⚠️ 2 Loss = STOP")
    except Exception as e:
        print(f"Telegram Poll Error: {e}")

send_telegram("🤖 BOT RESTARTED - REAL MARKET ONLY\n✅ OTC OFF - OTC Signal ar asbe na\n✅ Mon-Fri = Real Signal (7 Pair)\n✅ Sat/Sun = Market Closed\n✅ Command: signal / win / loss")
print("BOT Started - Real Only")
while True:
    try:
        now = now_bd()
        # MARKET OPEN THAKLEI AUTO CHECK CHOLBE
        if is_forex_market_open():
            if 20 <= now.second <= 40:
                if time.time() - last_auto_check >= 50:
                    last_auto_check = time.time()
                    print(f"AUTO CHECK REAL at {now.strftime('%H:%M:%S')}")
                    check_all_markets(manual=False)
            if time.time() - last_heartbeat >= 600:
                last_heartbeat = time.time()
                send_telegram(f"💓 BOT ALIVE - {now.strftime('%H:%M:%S')} BD Time\n✅ REAL MODE: Cholche - 7 Pair Rotation\n⏳ Signal mille nijei pathabo")
        else:
            # MARKET CLOSED HOLE 1 GHONTA POR POR EKTA MSG
            if time.time() - last_heartbeat >= 3600:
                last_heartbeat = time.time()
                send_telegram(f"💤 MARKET CLOSED - {now.strftime('%H:%M:%S')} BD Time\n❌ OTC OFF - Signal dibo na\n✅ Market Khulbe Monday Sokal")
        check_telegram_commands()
        check_results()
        time.sleep(1)
    except Exception as e:
        print(e)
        time.sleep(1)
