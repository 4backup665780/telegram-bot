from flask import Flask
import threading, os
app = Flask(__name__)
@app.route('/')
def home():
    return "BOT RUNNING - 40 SEC ZONE TOUCH - REAL + OTC"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))).start()

import time
import requests
from datetime import datetime, timedelta, timezone

BD_TZ = timezone(timedelta(hours=6))
def now_bd():
    return datetime.now(BD_TZ)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# ===== REAL PAIRS =====
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

# ===== OTC PAIRS =====
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

    # ===== ZONE CALCULATION - গত 30 ক্যান্ডেল থেকে =====
    # Resistance Zone = সবচেয়ে উপরের High গুলা
    # Support Zone = সবচেয়ে নিচের Low গুলা
    last_30_highs = sorted(highs[-31:-1], reverse=True)
    last_30_lows = sorted(lows[-31:-1])
    # Top 3 High এর গড় = Resistance Zone Center
    res_center = float(sum(last_30_highs[:3]) / 3)
    sup_center = float(sum(last_30_lows[:3]) / 3)
    # Zone Width - Price এর 0.05%
    zone_width = price * 0.0005
    # JPY Pair এর জন্য Width বড়
    if price > 50:
        zone_width = price * 0.0005

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

# ===== 40 SEC ZONE TOUCH LOGIC - ক্লাসের নিয়ম =====
def check_zone_touch(tv, sr, is_otc=False):
    price = tv["price"]
    open_p = tv["open"]
    high_p = tv["high"]
    low_p = tv["low"]
    rsi = tv["rsi"]
    closes = tv["closes"]

    # --- OTC MANIPULATION CHECK - শেষ মুহূর্তে হঠাৎ স্পাইক ---
    if is_otc and len(closes) >= 4:
        last_move = abs(closes[-1] - closes[-4]) / closes[-4] * 100 if closes[-4] != 0 else 0
        if last_move > 0.15:
            return None, "MANIPULATION - হঠাৎ স্পাইক, Broker ঘুরাইতেছে"

    # ===== RULE 1: RESISTANCE ZONE TOUCH = DOWN =====
    # Price Resistance Zone এর ভিতরে ঢুকছে কিনা?
    in_res_zone = (price >= sr["res_bottom"] and price <= sr["res_top"]) or (high_p >= sr["res_bottom"] and high_p <= sr["res_top"] + sr["zone_width"])
    # Wick Check - উপরে লম্বা Wick আছে কিনা? High থেকে Price নিচে নেমে আসছে?
    # Candle এর Range এর 30% এর বেশি উপরে Wick থাকতে হবে
    candle_range = high_p - low_p if high_p != low_p else 0.00001
    upper_wick = high_p - max(price, open_p)
    upper_wick_ratio = upper_wick / candle_range if candle_range > 0 else 0
    res_wick_ok = upper_wick_ratio >= 0.30

    if in_res_zone and res_wick_ok:
        # RSI Confirm - Resistance এ RSI 50 এর উপরে থাকলে ভালো, 70 এর উপরে হলে Overbought
        # RSI 45-75 হলে OK
        if 45 <= rsi <= 80:
            return "🔴 SELL", f"Resistance Zone {sr['res_center']:.5f} Touch + Wick Rejection + RSI {round(rsi)}"

    # ===== RULE 2: SUPPORT ZONE TOUCH = UP =====
    in_sup_zone = (price >= sr["sup_bottom"] and price <= sr["sup_top"]) or (low_p >= sr["sup_bottom"] - sr["zone_width"] and low_p <= sr["sup_top"])
    lower_wick = min(price, open_p) - low_p
    lower_wick_ratio = lower_wick / candle_range if candle_range > 0 else 0
    sup_wick_ok = lower_wick_ratio >= 0.30

    if in_sup_zone and sup_wick_ok:
        if 20 <= rsi <= 55:
            return "🟢 BUY", f"Support Zone {sr['sup_center']:.5f} Touch + Wick Rejection + RSI {round(rsi)}"

    # ===== কোনো Zone এ নাই = WAIT =====
    return None, f"Zone Touch হয় নাই - Price {price:.5f} | Res Zone {sr['res_bottom']:.5f}-{sr['res_top']:.5f} | Sup Zone {sr['sup_bottom']:.5f}-{sr['sup_top']:.5f} | RSI {round(rsi)}"

def check_all_markets(manual=False, force_otc=False):
    global last_signal_minute, last_auto_wait_msg
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
        group_name = "OTC - 40 SEC ZONE TOUCH"
        mode_txt = "OTC"
    else:
        if manual:
            PAIRS_TO_CHECK = ALL_PAIRS
            group_name = "REAL - ALL 7 - 40 SEC ZONE"
        else:
            if now.minute % 2 == 0:
                PAIRS_TO_CHECK = GROUP_A
                group_name = "REAL - GROUP A - 40 SEC ZONE"
            else:
                PAIRS_TO_CHECK = GROUP_B
                group_name = "REAL - GROUP B - 40 SEC ZONE"
        mode_txt = "REAL"

    print(f"Checking {group_name} at {now.strftime('%H:%M:%S')}")
    start_time = time.time()
    checked = 0
    failed = 0
    wait_list = []
    best_signal = None

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
            # Zone এর Range খুব ছোট হলে FLAT - Trade নিবো না
            if sr["range"] < (0.0004 if price < 50 else 0.04):
                wait_list.append(f"{pair_name} FLAT")
                if manual:
                    send_telegram(f"⏳ {pair_name} - FLAT Zone = WAIT")
                time.sleep(0.5)
                continue

            direction, reason = check_zone_touch(tv, sr, is_otc=use_otc)
            if direction is None:
                wait_list.append(f"{pair_name} WAIT")
                if manual:
                    send_telegram(f"⏳ {pair_name} - WAIT\n{reason}\nPrice {price:.5f} | Open {tv['open']:.5f} | High {tv['high']:.5f} | Low {tv['low']:.5f}")
                time.sleep(0.5)
                continue

            # Zone Touch মিলে গেছে - Best Signal
            if best_signal is None:
                best_signal = (pair_name, symbols, direction, price, tv, sr, reason)
            # Manual হলে প্রথমটাই পাঠাই দেই, Auto হলে Best টা পরে পাঠাবো
            if manual:
                break
            else:
                continue

        except Exception as e:
            print(f"Pair Error {pair_name}: {e}")
            continue

    if best_signal:
        pair_name, symbols, direction, price, tv, sr, reason = best_signal
        tag = "✋ MANUAL" if manual else "🤖 AUTO"
        msg = f"""🕒 Entry Time: {next_candle_time} (BD Time)
📊 Asset: {pair_name}
🎯 Direction: {direction}
⏱️ Expiry: M1
🚨 {tag} - 40 SEC ZONE TOUCH ✅
💰 Price: {price:.5f}
📍 Res Zone: {sr['res_bottom']:.5f} - {sr['res_top']:.5f}
📍 Sup Zone: {sr['sup_bottom']:.5f} - {sr['sup_top']:.5f}
✅ Reason: {reason}
📩 Signal Time: {now.strftime('%H:%M:%S')}"""
        send_telegram(msg)
        sent_signals[next_candle_time] = {"pair": pair_name, "direction": direction, "pair_info": symbols, "entry_price": price, "entry_time": next_candle_time}
        last_signal_minute = next_candle_time
        return
    else:
        if manual:
            send_telegram(f"🏁 CHECK SES - Zone Touch মিলে নাই, তাই Signal দেই নাই\nChecked: {checked} | WAIT: {', '.join(wait_list)}")
        else:
            if time.time() - last_auto_wait_msg >= 600:
                last_auto_wait_msg = time.time()
                send_telegram(f"⏳ AUTO - {now.strftime('%H:%M:%S')} - Zone Touch হয় নাই, WAIT...\nMode: {mode_txt} | Checked: {checked} Pair")
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
                    send_telegram("🔍 OTC Check kortesi - 40 SEC Zone Touch...")
                    check_all_markets(manual=True, force_otc=True)
                else:
                    send_telegram("🔍 Real Check kortesi - 40 SEC Zone Touch...")
                    check_all_markets(manual=True)
            elif text == "otc":
                send_telegram("🔍 OTC Check kortesi - 40 SEC Zone Touch...")
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

send_telegram("🤖 BOT RESTARTED - 40 SEC ZONE TOUCH\n✅ REAL + OTC - 2 tar jonnoi eki niyom\n✅ 40 Sec e Zone Touch holei Signal\n✅ Resistance Touch = SELL | Support Touch = BUY\n✅ Command: signal / otc / otc on / otc off / win / loss")
print("BOT Started - 40 Sec Zone Touch")
while True:
    try:
        now = now_bd()
        use_otc_now = is_otc_time()
        # ===== 40 SEC LOGIC - 40 theke 50 sec er moddhe check =====
        if 40 <= now.second <= 50:
            if time.time() - last_auto_check >= 50:
                last_auto_check = time.time()
                print(f"AUTO CHECK 40SEC {'OTC' if use_otc_now else 'REAL'} at {now.strftime('%H:%M:%S')}")
                check_all_markets(manual=False)
        if time.time() - last_heartbeat >= 600:
            last_heartbeat = time.time()
            if use_otc_now:
                send_telegram(f"💓 BOT ALIVE - {now.strftime('%H:%M:%S')} BD Time\n✅ OTC MODE: 40 SEC Zone Touch Cholche")
            else:
                send_telegram(f"💓 BOT ALIVE - {now.strftime('%H:%M:%S')} BD Time\n✅ REAL MODE: 40 SEC Zone Touch Cholche")
        check_telegram_commands()
        check_results()
        time.sleep(1)
    except Exception as e:
        print(e)
        time.sleep(1)
