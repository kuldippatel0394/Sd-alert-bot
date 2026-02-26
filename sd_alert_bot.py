# Supply and Demand Telegram Alert Bot

# Based on Nathan Williams Strategy

# Monitors: EURJPY, EURUSD, GBPUSD, USDJPY

import os
import time
import requests
from datetime import datetime
import yfinance as yf
import pandas as pd
import numpy as np

TELEGRAM_BOT_TOKEN = os.environ.get(“TELEGRAM_BOT_TOKEN”, “”)
TELEGRAM_CHAT_ID   = os.environ.get(“TELEGRAM_CHAT_ID”, “”)

PAIRS = {
“EURJPY”: “EURJPY=X”,
“EURUSD”: “EURUSD=X”,
“GBPUSD”: “GBPUSD=X”,
“USDJPY”: “USDJPY=X”,
}

ZONE_LOOKBACK  = 100
ZONE_STRENGTH  = 3
RETEST_PIPS    = 0.0010
SCAN_INTERVAL  = 60
ALERT_COOLDOWN = 300

zone_store     = {}
last_alert     = {}
alerted_breaks = set()

def send_telegram(message):
url = “https://api.telegram.org/bot” + TELEGRAM_BOT_TOKEN + “/sendMessage”
payload = {“chat_id”: TELEGRAM_CHAT_ID, “text”: message, “parse_mode”: “HTML”}
try:
r = requests.post(url, data=payload, timeout=10)
if r.status_code != 200:
print(“Telegram error: “ + r.text)
except Exception as e:
print(“Failed to send message: “ + str(e))

def send_startup_message():
msg = (
“Supply and Demand Alert Bot Started!\n\n”
“Monitoring: EURJPY, EURUSD, GBPUSD, USDJPY\n”
“Scanning Daily and 4H zones\n\n”
“You will get alerts for:\n”
“1. Zone Breakouts\n”
“2. Retests - your entry signal\n\n”
“Bot is live. Waiting for setups…”
)
send_telegram(msg)

def get_candles(ticker, interval, period):
try:
df = yf.download(ticker, interval=interval, period=period, progress=False)
df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
df = df[[“Open”, “High”, “Low”, “Close”]].dropna()
return df
except Exception as e:
print(“Data fetch error: “ + str(e))
return pd.DataFrame()

def is_supply_zone(df, idx):
if idx < ZONE_STRENGTH or idx >= len(df) - ZONE_STRENGTH:
return False
candle = df.iloc[idx]
body = abs(candle[“Close”] - candle[“Open”])
rng = candle[“High”] - candle[“Low”]
if rng == 0 or candle[“Close”] >= candle[“Open”] or body < rng * 0.5:
return False
down_count = sum(1 for j in range(1, ZONE_STRENGTH + 1) if (idx - j) >= 0 and df.iloc[idx - j][“Close”] < df.iloc[idx - j][“Open”])
bodies = [abs(df.iloc[idx + j][“Close”] - df.iloc[idx + j][“Open”]) for j in range(1, ZONE_STRENGTH + 1) if (idx + j) < len(df)]
avg = np.mean(bodies) if bodies else 0
return down_count >= ZONE_STRENGTH - 1 and (avg == 0 or body > avg * 1.5)

def is_demand_zone(df, idx):
if idx < ZONE_STRENGTH or idx >= len(df) - ZONE_STRENGTH:
return False
candle = df.iloc[idx]
body = abs(candle[“Close”] - candle[“Open”])
rng = candle[“High”] - candle[“Low”]
if rng == 0 or candle[“Close”] <= candle[“Open”] or body < rng * 0.5:
return False
up_count = sum(1 for j in range(1, ZONE_STRENGTH + 1) if (idx - j) >= 0 and df.iloc[idx - j][“Close”] > df.iloc[idx - j][“Open”])
bodies = [abs(df.iloc[idx + j][“Close”] - df.iloc[idx + j][“Open”]) for j in range(1, ZONE_STRENGTH + 1) if (idx + j) < len(df)]
avg = np.mean(bodies) if bodies else 0
return up_count >= ZONE_STRENGTH - 1 and (avg == 0 or body > avg * 1.5)

def scan_zones(pair, ticker):
zones = []
for interval, label, period in [(“1d”, “D1”, “6mo”), (“4h”, “H4”, “60d”)]:
df = get_candles(ticker, interval, period)
if df.empty or len(df) < ZONE_LOOKBACK:
continue
df = df.tail(ZONE_LOOKBACK).reset_index(drop=True)
for i in range(ZONE_STRENGTH, len(df) - ZONE_STRENGTH):
if is_supply_zone(df, i):
zones.append({“type”: “SUPPLY”, “tf”: label, “top”: df.iloc[i][“High”], “bottom”: max(df.iloc[i][“Open”], df.iloc[i][“Close”]) - RETEST_PIPS, “broken”: False, “break_idx”: None})
if is_demand_zone(df, i):
zones.append({“type”: “DEMAND”, “tf”: label, “top”: min(df.iloc[i][“Open”], df.iloc[i][“Close”]) + RETEST_PIPS, “bottom”: df.iloc[i][“Low”], “broken”: False, “break_idx”: None})
deduped = []
for z in zones:
if not any(abs(z[“top”] - d[“top”]) < RETEST_PIPS * 2 for d in deduped):
deduped.append(z)
return deduped

def check_interactions(pair, ticker, zones):
df_live = get_candles(ticker, “5m”, “1d”)
if df_live.empty:
return
price = float(df_live[“Close”].iloc[-1])
now = time.time()

```
for zone in zones:
    zid = pair + "_" + zone["tf"] + "_" + zone["type"] + "_" + str(round(zone["top"], 5))
    zlabel = zone["tf"] + " " + zone["type"]

    if not zone["broken"]:
        broke = False
        if zone["type"] == "SUPPLY" and price > zone["top"]:
            zone["broken"] = True
            zone["break_idx"] = now
            broke = True
            direction = "BULLISH BREAKOUT"
            level = str(round(zone["top"], 5))
            action = "BUY"
        elif zone["type"] == "DEMAND" and price < zone["bottom"]:
            zone["broken"] = True
            zone["break_idx"] = now
            broke = True
            direction = "BEARISH BREAKOUT"
            level = str(round(zone["bottom"], 5))
            action = "SELL"

        if broke and zid not in alerted_breaks:
            alerted_breaks.add(zid)
            msg = ("BREAKOUT ALERT - " + pair + "\n\n" + direction + "\nZone: " + zlabel + "\nLevel: " + level + "\nPrice: " + str(round(price, 5)) + "\n\nNow watch for RETEST of " + level + "\nThat will be your " + action + " setup")
            send_telegram(msg)
            print("BREAKOUT: " + pair + " " + zlabel)

    else:
        if zone["break_idx"] and (now - zone["break_idx"]) < 180:
            continue
        rid = zid + "_retest"
        if rid in last_alert and (now - last_alert[rid]) < ALERT_COOLDOWN:
            continue

        if zone["type"] == "SUPPLY":
            rl = zone["top"]
            tdir = "BUY"
        else:
            rl = zone["bottom"]
            tdir = "SELL"

        if abs(price - rl) <= RETEST_PIPS:
            last_alert[rid] = now
            msg = ("RETEST ALERT - " + pair + "\n\n" + tdir + " OPPORTUNITY\nZone: " + zlabel + "\nRetest Level: " + str(round(rl, 5)) + "\nPrice: " + str(round(price, 5)) + "\n\nACTION: LOOK TO " + tdir + "\n\nCheck before entering:\nD1 trend direction\nH4 zone alignment\nFundamental bias\nConfirm on M5 or M1 first!")
            send_telegram(msg)
            print("RETEST: " + pair + " " + zlabel)
```

def main():
print(“Supply and Demand Alert Bot Starting…”)
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
print(“ERROR: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables”)
return

```
send_startup_message()

print("Running initial zone scan...")
for pair, ticker in PAIRS.items():
    print("Scanning " + pair + "...")
    zone_store[pair] = scan_zones(pair, ticker)
    print("Found " + str(len(zone_store[pair])) + " zones for " + pair)

print("Bot running...")
scan_count = 0
while True:
    try:
        scan_count += 1
        if scan_count % 60 == 0:
            for pair, ticker in PAIRS.items():
                zone_store[pair] = scan_zones(pair, ticker)
        for pair, ticker in PAIRS.items():
            if pair in zone_store:
                check_interactions(pair, ticker, zone_store[pair])
        time.sleep(SCAN_INTERVAL)
    except KeyboardInterrupt:
        send_telegram("Alert Bot stopped.")
        break
    except Exception as e:
        print("Error: " + str(e))
        time.sleep(60)
```

if **name** == “**main**”:
main()
