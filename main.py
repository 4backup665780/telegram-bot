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
        sorted_highs = sorted(highs, reverse=True)
        sorted_lows = sorted(lows)
        res_center = sum(sorted_highs[:3]) / 3
        sup_center = sum(sorted_lows[:3]) / 3
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
    box = get_5min_box(pair_info["yahoo"])
    tv = get_1min_data(pair_info["yahoo"], pair_info["tv_symbol"], pair_info["tv_exchange"])
    if box is None or tv is None:
        return None, None
    return tv, box

def check_box_touch(tv, box, is_otc=False):
    price = tv["price"]
    open_p = tv["open"]
    high_p = tv["high"]
    low_p = tv["low"]
    rsi = tv["rsi"]
    closes = tv["closes"]
    if high_p == low_p:
        return None, "DATA STALE"
    if is_otc and len(closes) >= 4:
        last_move = abs(closes[-1] - closes[-4]) / closes[-4] * 100 if closes[-4] != 0 else 0
        if last_move > 0.25:
            return None, "MANIPULATION"
    candle_range = high_p - low_p if high_p != low_p else 0.00001
    upper_wick = high_p - max(price, open_p)
    lower_wick = min(price, open_p) - low_p
    upper_wick_ratio = upper_wick / candle_range if candle_range > 0 else 0
    lower_wick_ratio = lower_wick / candle_range if candle_range > 0 else 0
    in_res_box = (price >= box["res_bottom"] and price <= box["res_top"]) or (high_p >= box["res_bottom"] and high_p <= box["res_top"] + box["box_width"])
    if in_res_box and upper_wick_ratio >= 0.10:
        if 35 <= rsi <= 88:
            return "🔴 SELL", "5MIN Resistance Box Touch + Wick Rejection"
    in_sup_box = (price >= box["sup_bottom"] and price <= box["sup_top"]) or (low_p >= box["sup_bottom"] - box["box_width"] and low_p <= box["sup_top"])
    if in_sup_box and lower_wick_ratio >= 0.10:
        if 12 <= rsi <= 65:
            return "🟢 BUY", "5MIN Support Box Touch + Wick Rejection"
    dist_to_res = abs(price - box["res_center"]) / price * 100 if price != 0 else 99
    dist_to_sup = abs(price - box["sup_center"]) / price * 100 if price != 0 else 99
    if dist_to_res < 0.12 and rsi >= 50 and upper_wick_ratio >= 0.05:
        return "🔴 SELL", "Near 5MIN Resistance Box + Wick"
    if dist_to_sup < 0.12 and rsi <= 50 and lower_wick_ratio >= 0.05:
        return "🟢 BUY", "Near 5MIN Support Box + Wick"
    return None, "5MIN Box Touch hoy nai"

def check_all_markets(manual=False, force_otc=False):
    global last_signal_minute
    now = now_bd()
    entry_dt = now + timedelta(minutes=1)
    next_candle_time = entry_dt.strftime("%H:%M")
    if not manual and next_candle_time == last_signal_minute:
        return
    if not manual and next_candle_time in sent_signals:
        return
    use_otc = force_otc or is_otc_time()
    if use_otc:
        PAIRS_TO_CHECK = OTC_PAIRS
        group_name = "OTC - 5MIN BOX"
    else:
        if manual:
            PAIRS_TO_CHECK = ALL_PAIRS
            group_name = "REAL - ALL 7"
        else:
            if now.minute % 2 == 0:
                PAIRS_TO_CHECK = GROUP_A
                group_name = "REAL - GROUP A"
            else:
                PAIRS_TO_CHECK = GROUP_B
                group_name = "REAL - GROUP B"
    print(f"Checking {group_name} 5MIN BOX at {now.strftime('%H:%M:%S')}")
    checked = 0
    best_signal = None
    for pair_name, symbols in PAIRS_TO_CHECK.items():
        try:
            checked += 1
            tv, box = get_box_and_1min(symbols)
            if tv is None or box is None:
                if manual:
                    send_telegram(f"❌ {pair_name} - Data Fail")
                time.sleep(0.8)
                continue
            direction, reason = check_box_touch(tv, box, is_otc=use_otc)
            if direction is None:
                if manual:
                    send_telegram(f"⏳ {pair_name} - WAIT\n{reason}")
                time.sleep(0.5)
                continue
            if best_signal is None:
                best_signal = (pair_name, symbols, direction, tv["price"], tv, box, reason)
            if manual:
                break
            else:
                continue
        except Exception as e:
            print(f"Pair Error {pair_name}: {e}")
            continue
    if best_signal:
        pair_name, symbols, direction, price, tv, box, reason = best_signal
        tag = "✋ MANUAL" if manual else "🤖 AUTO"
        msg = f"""🕒 Entry Time: {next_candle_time} (BD Time)
📊 Asset: {pair_name}
🎯 Direction: {direction}
⏱️ Expiry: M1
🚨 {tag} - 5MIN BOX + 1MIN 40SEC TOUCH ✅
✅ Reason: {reason}
📩 Signal Time: {now.strftime('%H:%M:%S')}"""
        send_telegram(msg)
        sent_signals[next_candle_time] = {"pair": pair_name, "direction": direction, "pair_info": symbols, "entry_price": price, "entry_time": next_candle_time}
        last_signal_minute = next_candle_time
        return
    else:
        if manual:
            send_telegram(f"🏁 CHECK SES - 5MIN Box Touch mile nai, tai Signal dei nai\nChecked: {checked}")
        else:
            print(f"No Signal - 5MIN Box Touch hoy nai")
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
                tv, box = get_box_and_1min(pred["pair_info"])
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
{result_txt} {profit}
📈 Total: {today_win} Win - {today_loss} Loss{extra}"""
                send_telegram(msg)
                to_remove.append(candle_time)
        except Exception as e:
            print(f"Result Error: {e}")
    for k in to_remove:
        del sent_signals[k]

def check_telegram_commands():
    global last_update_id, today_win, today_loss, otc_mode_manual
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
                if is_otc_time():
                    send_telegram("🔍 OTC Check kortesi - 5MIN BOX + 1MIN Touch...")
                    check_all_markets(manual=True, force_otc=True)
                else:
                    send_telegram("🔍 Real Check kortesi - 5MIN BOX + 1MIN Touch...")
                    check_all_markets(manual=True)
            elif text == "otc":
                send_telegram("🔍 OTC Check kortesi - 5MIN BOX + 1MIN Touch...")
                check_all_markets(manual=True, force_otc=True)
            elif text == "otc on":
                otc_mode_manual = True
                send_telegram("✅ OTC MODE ON")
            elif text == "otc off":
                otc_mode_manual = False
                send_telegram("✅ OTC MODE OFF - Real Mode")
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

send_telegram("🤖 BOT RESTARTED - 5MIN BOX + 1MIN 40SEC\n✅ 5MIN Candle theke BOX banabe\n✅ 1MIN Candle e BOX Touch hole Signal\n✅ NO PRICE - NO FLAT - NO WAIT SPAM\n✅ Command: signal / otc / win / loss")
print("BOT Started - 5MIN BOX + 1MIN Touch")
while True:
    try:
        now = now_bd()
        use_otc_now = is_otc_time()
        if 40 <= now.second <= 50:
            if time.time() - last_auto_check >= 50:
                last_auto_check = time.time()
                print(f"AUTO CHECK 40SEC {'OTC' if use_otc_now else 'REAL'} 5MIN BOX at {now.strftime('%H:%M:%S')}")
                check_all_markets(manual=False)
        if time.time() - last_heartbeat >= 3600:
            last_heartbeat = time.time()
            send_telegram(f"💓 BOT ALIVE - {now.strftime('%H:%M:%S')} BD Time\n✅ {'OTC' if use_otc_now else 'REAL'} MODE - 5MIN BOX Cholche")
        check_telegram_commands()
        check_results()
        time.sleep(1)
    except Exception as e:
        print(e)
        time.sleep(1)
