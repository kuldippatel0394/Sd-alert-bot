# “””

SUPPLY & DEMAND TELEGRAM ALERT BOT
Based on Nathan Williams’ Strategy
Profitable Empire Forex Education Group

# Monitors: EURJPY, EURUSD, GBPUSD, USDJPY
Runs on: Any free cloud server (Render, Railway, etc.)
Alerts:  Directly to your Telegram

“””

import os
import time
import requests
from datetime import datetime, timezone
import yfinance as yf
import pandas as pd
import numpy as np

# —————————————————––

# CONFIGURATION — Fill these in before deploying

# —————————————————––

TELEGRAM_BOT_TOKEN = os.environ.get(“TELEGRAM_BOT_TOKEN”, “YOUR_BOT_TOKEN_HERE”)
TELEGRAM_CHAT_ID   = os.environ.get(“TELEGRAM_CHAT_ID”,   “YOUR_CHAT_ID_HERE”)

PAIRS = {
“EURJPY”: “EURJPY=X”,
“EURUSD”: “EURUSD=X”,
“GBPUSD”: “GBPUSD=X”,
“USDJPY”: “USDJPY=X”,
}

# —————————————————––

# STRATEGY SETTINGS

# —————————————————––

ZONE_LOOKBACK    = 100   # Candles to look back for zones
ZONE_STRENGTH    = 3     # Confirming candles needed
RETEST_PIPS      = 0.0010  # How close price must be for retest alert
SCAN_INTERVAL    = 60    # How often to scan in seconds (60 = every minute)
ALERT_COOLDOWN   = 300   # Seconds before re-alerting same zone (5 mins)

# —————————————————––

# STATE TRACKING

# —————————————————––

zone_store     = {}   # Stores detected zones per pair
last_alert     = {}   # Tracks last alert time per zone to avoid spam
alerted_breaks = set()  # Tracks breakouts already alerted

# —————————————————––

# TELEGRAM FUNCTIONS

# —————————————————––

def send_telegram(message: str):
“”“Send a message to your Telegram chat.”””
url = f”https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage”
payload = {
“chat_id”:    TELEGRAM_CHAT_ID,
“text”:       message,
“parse_mode”: “HTML”,
}
try:
r = requests.post(url, data=payload, timeout=10)
if r.status_code != 200:
print(f”Telegram error: {r.text}”)
except Exception as e:
print(f”Failed to send Telegram message: {e}”)

def send_startup_message():
msg = (
“🤖 <b>Supply & Demand Alert Bot Started!</b>\n\n”
“📊 Monitoring pairs:\n”
“• EURJPY\n• EURUSD\n• GBPUSD\n• USDJPY\n\n”
“📡 Scanning Daily + 4H zones\n”
“⚡ You’ll get alerts for:\n”
“  1️⃣ Zone Breakouts\n”
“  2️⃣ Retests (your entry signal)\n\n”
“✅ Bot is live. Waiting for setups…”
)
send_telegram(msg)

# —————————————————––

# DATA FETCHING

# —————————————————––

def get_candles(ticker: str, interval: str, period: str) -> pd.DataFrame:
“”“Fetch OHLC candle data using yfinance.”””
try:
df = yf.download(ticker, interval=interval, period=period, progress=False)
df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
df = df[[“Open”, “High”, “Low”, “Close”]].dropna()
return df
except Exception as e:
print(f”Data fetch error for {ticker} ({interval}): {e}”)
return pd.DataFrame()

# —————————————————––

# ZONE DETECTION

# —————————————————––

def is_supply_zone(df: pd.DataFrame, idx: int) -> bool:
“””
Supply zone: strong bearish candle followed by continued downward move.
Based on Nathan’s concept — area where price dropped sharply from.
“””
if idx < ZONE_STRENGTH or idx >= len(df) - ZONE_STRENGTH:
return False

```
candle     = df.iloc[idx]
body       = abs(candle["Close"] - candle["Open"])
candle_range = candle["High"] - candle["Low"]

if candle_range == 0:
    return False

# Must be bearish with body > 50% of range
if candle["Close"] >= candle["Open"]:
    return False
if body < candle_range * 0.5:
    return False

# Check momentum: subsequent candles moved down
down_count = 0
for j in range(1, ZONE_STRENGTH + 1):
    future = df.iloc[idx - j] if (idx - j) >= 0 else None
    if future is not None and future["Close"] < future["Open"]:
        down_count += 1

# Check base: candles before were small (consolidation)
avg_body_before = np.mean([
    abs(df.iloc[idx + j]["Close"] - df.iloc[idx + j]["Open"])
    for j in range(1, ZONE_STRENGTH + 1)
    if (idx + j) < len(df)
])

return down_count >= ZONE_STRENGTH - 1 and (avg_body_before == 0 or body > avg_body_before * 1.5)
```

def is_demand_zone(df: pd.DataFrame, idx: int) -> bool:
“””
Demand zone: strong bullish candle followed by continued upward move.
Based on Nathan’s concept — area where price rallied sharply from.
“””
if idx < ZONE_STRENGTH or idx >= len(df) - ZONE_STRENGTH:
return False

```
candle       = df.iloc[idx]
body         = abs(candle["Close"] - candle["Open"])
candle_range = candle["High"] - candle["Low"]

if candle_range == 0:
    return False

# Must be bullish with body > 50% of range
if candle["Close"] <= candle["Open"]:
    return False
if body < candle_range * 0.5:
    return False

# Check momentum: subsequent candles moved up
up_count = 0
for j in range(1, ZONE_STRENGTH + 1):
    future = df.iloc[idx - j] if (idx - j) >= 0 else None
    if future is not None and future["Close"] > future["Open"]:
        up_count += 1

# Check base: candles before were small (consolidation)
avg_body_before = np.mean([
    abs(df.iloc[idx + j]["Close"] - df.iloc[idx + j]["Open"])
    for j in range(1, ZONE_STRENGTH + 1)
    if (idx + j) < len(df)
])

return up_count >= ZONE_STRENGTH - 1 and (avg_body_before == 0 or body > avg_body_before * 1.5)
```

def scan_zones(pair: str, ticker: str):
“””
Scan Daily and 4H charts for Supply and Demand zones.
Returns a list of zone dicts.
“””
zones = []

```
for interval, label, period in [("1d", "D1", "6mo"), ("4h", "H4", "60d")]:
    df = get_candles(ticker, interval, period)
    if df.empty or len(df) < ZONE_LOOKBACK:
        continue

    df = df.tail(ZONE_LOOKBACK).reset_index(drop=True)

    for i in range(ZONE_STRENGTH, len(df) - ZONE_STRENGTH):
        # Supply Zone
        if is_supply_zone(df, i):
            top    = df.iloc[i]["High"]
            bottom = max(df.iloc[i]["Open"], df.iloc[i]["Close"]) - RETEST_PIPS
            zones.append({
                "type":     "SUPPLY",
                "tf":       label,
                "top":      top,
                "bottom":   bottom,
                "broken":   False,
                "break_idx": None,
            })

        # Demand Zone
        if is_demand_zone(df, i):
            bottom = df.iloc[i]["Low"]
            top    = min(df.iloc[i]["Open"], df.iloc[i]["Close"]) + RETEST_PIPS
            zones.append({
                "type":   "DEMAND",
                "tf":     label,
                "top":    top,
                "bottom": bottom,
                "broken": False,
                "break_idx": None,
            })

# Deduplicate zones that are very close to each other
deduped = []
for z in zones:
    duplicate = False
    for d in deduped:
        if abs(z["top"] - d["top"]) < RETEST_PIPS * 2:
            duplicate = True
            break
    if not duplicate:
        deduped.append(z)

return deduped
```

# —————————————————––

# BREAKOUT & RETEST DETECTION

# —————————————————––

def check_interactions(pair: str, ticker: str, zones: list):
“””
Check current price against all zones.
Alert on breakouts and retests.
“””
# Get latest price
df_live = get_candles(ticker, “5m”, “1d”)
if df_live.empty:
return

```
current_price = float(df_live["Close"].iloc[-1])
now           = time.time()

for i, zone in enumerate(zones):
    zone_id     = f"{pair}_{zone['tf']}_{zone['type']}_{round(zone['top'], 5)}"
    zone_label  = f"{zone['tf']} {zone['type']}"

    # ---- BREAKOUT CHECK ----
    if not zone["broken"]:

        # Supply broken upward (bullish breakout)
        if zone["type"] == "SUPPLY" and current_price > zone["top"]:
            zone["broken"]    = True
            zone["break_idx"] = now

            if zone_id not in alerted_breaks:
                alerted_breaks.add(zone_id)
                msg = (
                    f"🚨 <b>BREAKOUT ALERT — {pair}</b>\n\n"
                    f"📈 <b>BULLISH BREAKOUT</b>\n"
                    f"Zone: {zone_label} (Resistance broken)\n"
                    f"Zone Top: <code>{zone['top']:.5f}</code>\n"
                    f"Current Price: <code>{current_price:.5f}</code>\n\n"
                    f"⏳ <b>NOW WATCH FOR RETEST</b>\n"
                    f"Wait for price to pull back to <code>{zone['top']:.5f}</code>\n"
                    f"That will be your BUY setup ✅"
                )
                send_telegram(msg)
                print(f"[{datetime.now()}] BREAKOUT ALERT sent: {pair} {zone_label}")

        # Demand broken downward (bearish breakout)
        elif zone["type"] == "DEMAND" and current_price < zone["bottom"]:
            zone["broken"]    = True
            zone["break_idx"] = now

            if zone_id not in alerted_breaks:
                alerted_breaks.add(zone_id)
                msg = (
                    f"🚨 <b>BREAKOUT ALERT — {pair}</b>\n\n"
                    f"📉 <b>BEARISH BREAKOUT</b>\n"
                    f"Zone: {zone_label} (Support broken)\n"
                    f"Zone Bottom: <code>{zone['bottom']:.5f}</code>\n"
                    f"Current Price: <code>{current_price:.5f}</code>\n\n"
                    f"⏳ <b>NOW WATCH FOR RETEST</b>\n"
                    f"Wait for price to pull back to <code>{zone['bottom']:.5f}</code>\n"
                    f"That will be your SELL setup ✅"
                )
                send_telegram(msg)
                print(f"[{datetime.now()}] BREAKOUT ALERT sent: {pair} {zone_label}")

    # ---- RETEST CHECK ----
    else:
        # Must wait at least 3 minutes after breakout before alerting retest
        if zone["break_idx"] and (now - zone["break_idx"]) < 180:
            continue

        # Cooldown — don't spam retest alerts
        retest_id = zone_id + "_retest"
        if retest_id in last_alert and (now - last_alert[retest_id]) < ALERT_COOLDOWN:
            continue

        retest_triggered = False
        action           = ""
        retest_level     = 0.0

        # Broken Supply retested from above → BUY opportunity
        if zone["type"] == "SUPPLY":
            retest_level = zone["top"]
            if abs(current_price - retest_level) <= RETEST_PIPS:
                retest_triggered = True
                action           = "📈 BUY OPPORTUNITY"

        # Broken Demand retested from below → SELL opportunity
        elif zone["type"] == "DEMAND":
            retest_level = zone["bottom"]
            if abs(current_price - retest_level) <= RETEST_PIPS:
                retest_triggered = True
                action           = "📉 SELL OPPORTUNITY"

        if retest_triggered:
            last_alert[retest_id] = now
            role = "Former Resistance → now Support" if zone["type"] == "SUPPLY" else "Former Support → now Resistance"
            trade_dir = "BUY" if zone["type"] == "SUPPLY" else "SELL"

            msg = (
                f"⚡ <b>RETEST ALERT — {pair}</b>\n\n"
                f"{action}\n"
                f"Zone: {zone_label} ({role})\n"
                f"Retest Level: <code>{retest_level:.5f}</code>\n"
                f"Current Price: <code>{current_price:.5f}</code>\n\n"
                f"✅ <b>ACTION: LOOK TO {trade_dir}</b>\n\n"
                f"<b>Before entering, check:</b>\n"
                f"📊 D1 trend direction\n"
                f"📊 H4 zone alignment\n"
                f"📰 Fundamental bias\n"
                f"⏱️ Confirm on M5/M1 first!\n\n"
                f"🧠 Remember Nathan's rule:\n"
                f"<i>Know the trend → Spot it → Enter on M1/M5</i>"
            )
            send_telegram(msg)
            print(f"[{datetime.now()}] RETEST ALERT sent: {pair} {zone_label}")
```

# —————————————————––

# MAIN LOOP

# —————————————————––

def main():
print(”=” * 50)
print(”  Supply & Demand Alert Bot Starting…”)
print(”=” * 50)

```
# Validate config
if "YOUR_BOT_TOKEN" in TELEGRAM_BOT_TOKEN or "YOUR_CHAT_ID" in TELEGRAM_CHAT_ID:
    print("ERROR: Please set your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    print("Set them as environment variables before running.")
    return

send_startup_message()

# Initial zone scan
print("\nRunning initial zone scan...")
for pair, ticker in PAIRS.items():
    print(f"  Scanning {pair}...")
    zone_store[pair] = scan_zones(pair, ticker)
    print(f"  Found {len(zone_store[pair])} zones for {pair}")

print(f"\nBot running. Scanning every {SCAN_INTERVAL} seconds...\n")

scan_count = 0
while True:
    try:
        scan_count += 1

        # Re-scan zones every 60 scans (~1 hour)
        if scan_count % 60 == 0:
            print(f"[{datetime.now()}] Refreshing zones...")
            for pair, ticker in PAIRS.items():
                zone_store[pair] = scan_zones(pair, ticker)

        # Check interactions on every scan
        for pair, ticker in PAIRS.items():
            if pair in zone_store:
                check_interactions(pair, ticker, zone_store[pair])

        time.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        print("\nBot stopped by user.")
        send_telegram("⛔ Supply & Demand Alert Bot has been stopped.")
        break
    except Exception as e:
        print(f"Error in main loop: {e}")
        time.sleep(60)  # Wait a minute before retrying
```

if **name** == “**main**”:
main()
