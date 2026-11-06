# === PRIORITY 1: OP-1 RULE 1 - BUY ===
if green_count >= 6 and is_upore and 40 <= rsi <= 70:
    direction = "🟢 BUY"
    rule_name = "OP-1 Rule 1"
    reason = f"OP-1: 10 Candel e {green_count} SOBUJ + UPORE + RSI {round(rsi)} (40-70)"
    price_line = f"{price:.5f} er niche ba borabor thakle BUY"

# === PRIORITY 2: OP-1 RULE 2 - SELL ===
elif red_count >= 6 and is_niche and 30 <= rsi <= 60:
    direction = "🔴 SELL"
    rule_name = "OP-1 Rule 2"
    reason = f"OP-1: 10 Candel e {red_count} LAL + NICHE + RSI {round(rsi)} (30-60)"
    price_line = f"{price:.5f} er upore ba borabor thakle SELL"

# === PRIORITY 3: EXTRA STRONG - OP-1 er bahire kintu market douRacche ===
elif green_count >= 9 and is_upore:
    direction = "🟢 BUY"
    rule_name = "EXTRA STRONG"
    reason = f"EXTRA STRONG: 10 Candel e {green_count}/10 SOBUJ + UPORE + RSI {round(rsi)} - Market ekdike douracche, miss kora jabe na"
    price_line = f"{price:.5f} er niche ba borabor thakle BUY"

elif red_count >= 9 and is_niche:
    direction = "🔴 SELL"
    rule_name = "EXTRA STRONG"
    reason = f"EXTRA STRONG: 10 Candel e {red_count}/10 LAL + NICHE + RSI {round(rsi)} - Market ekdike douracche, miss kora jabe na"
    price_line = f"{price:.5f} er upore ba borabor thakle SELL"

# === PRIORITY 4: RULE 3 / 4 - WAIT ===
elif last_red and is_upore and 40 <= rsi <= 70:
    continue # WAIT
elif last_green and is_niche and 30 <= rsi <= 60:
    continue # WAIT
else:
    continue # NO SIGNAL
