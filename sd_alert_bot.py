# placeholder
import os
import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone

TELEGRAM_BOT_TOKEN = os.environ.get(“TELEGRAM_BOT_TOKEN”, “”)
TELEGRAM_CHAT_ID = os.environ.get(“TELEGRAM_CHAT_ID”, “”)

PAIRS = {
“EURJPY”: “EURJPY=X”,
“EURUSD”: “EURUSD=X”,
“GBPUSD”: “GBPUSD=X”,
“USDJPY”: “USDJPY=X”,
}

ZONE_STRENGTH = 3
RETEST_PIPS = 0.0010
ALERT_COOLDOWN = 300
RISK_PERCENT = 1.0
ACCOUNT_SIZE = 1000.0

SESSIONS = {
“ASIA”:   {“start”: 0,  “end”: 9},
“LONDON”: {“start”: 7,  “end”: 16},
“NEWYORK”:{“start”: 12, “end”: 21},
}

JPY_PAIRS = [“EURJPY”, “USDJPY”]
NON_JPY_PAIRS = [“EURUSD”, “GBPUSD”]

zone_store = {}
last_alert = {}
alerted_breaks = set()

def send_telegram(message):
url = “https://api.telegram.org/bot” + TELEGRAM_BOT_TOKEN + “/sendMessage”
payload = {“chat_id”: TELEGRAM_CHAT_ID, “text”: message}
try:
requests.post(url, data=payload, timeout=10)
except Exception as e:
print(str(e))

def get_candles(ticker, interval, period):
try:
df = yf.download(ticker, interval=interval, period=period, progress=False)
df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
return df[[“Open”, “High”, “Low”, “Close”]].dropna()
except:
return pd.DataFrame()

def get_current_session():
hour = datetime.now(timezone.utc).hour
active = []
if SESSIONS[“ASIA”][“start”] <= hour < SESSIONS[“ASIA”][“end”]:
active.append(“ASIA”)
if SESSIONS[“LONDON”][“start”] <= hour < SESSIONS[“LONDON”][“end”]:
active.append(“LONDON”)
if SESSIONS[“NEWYORK”][“start”] <= hour < SESSIONS[“NEWYORK”][“end”]:
active.append(“NEWYORK”)
return active if active else [“OFFMARKET”]

def is_valid_session_for_pair(pair):
sessions = get_current_session()
if “OFFMARKET” in sessions:
return False, “Off market hours”
if pair in JPY_PAIRS:
valid = any(s in sessions for s in [“ASIA”, “LONDON”, “NEWYORK”])
reason = “JPY pair - valid in all sessions: “ + “, “.join(sessions)
return valid, reason
else:
valid = any(s in sessions for s in [“LONDON”, “NEWYORK”])
reason = “Valid session: “ + “, “.join(sessions) if valid else “Wait for London or New York session”
return valid, reason

def get_daily_trend(ticker):
df = get_candles(ticker, “1d”, “3mo”)
if df.empty or len(df) < 20:
return “UNKNOWN”, 0
closes = df[“Close”].values
sma20 = np.mean(closes[-20:])
sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else np.mean(closes)
current = closes[-1]
higher_highs = sum(1 for i in range(-5, -1) if df[“High”].iloc[i] > df[“High”].iloc[i-1])
higher_lows = sum(1 for i in range(-5, -1) if df[“Low”].iloc[i] > df[“Low”].iloc[i-1])
lower_highs = sum(1 for i in range(-5, -1) if df[“High”].iloc[i] < df[“High”].iloc[i-1])
lower_lows = sum(1 for i in range(-5, -1) if df[“Low”].iloc[i] < df[“Low”].iloc[i-1])
if current > sma20 > sma50 and higher_highs >= 2 and higher_lows >= 2:
strength = min(5, higher_highs + higher_lows)
return “BULLISH”, strength
elif current < sma20 < sma50 and lower_highs >= 2 and lower_lows >= 2:
strength = min(5, lower_highs + lower_lows)
return “BEARISH”, strength
else:
return “RANGING”, 0

def get_h4_trend(ticker):
df = get_candles(ticker, “4h”, “30d”)
if df.empty or len(df) < 20:
return “UNKNOWN”
closes = df[“Close”].values
sma20 = np.mean(closes[-20:])
current = closes[-1]
if current > sma20:
return “BULLISH”
elif current < sma20:
return “BEARISH”
return “RANGING”

def check_news_window():
hour = datetime.now(timezone.utc).hour
minute = datetime.now(timezone.utc).minute
weekday = datetime.now(timezone.utc).weekday()
high_impact_hours = [13, 14, 15]
if weekday == 4 and hour in [12, 13, 14]:
return False, “Possible NFP Friday - avoid trading”
if hour in high_impact_hours and minute < 30:
return False, “High impact news window - wait 30 mins”
return True, “Clear of major news”

def rate_zone(zone, ticker):
stars = 1
reasons = []
if zone[“tf”] == “D1”:
stars += 2
reasons.append(“Daily zone +2 stars”)
else:
stars += 1
reasons.append(“H4 zone +1 star”)
touch_count = zone.get(“touch_count”, 0)
if touch_count >= 3:
stars += 2
reasons.append(“Tested “ + str(touch_count) + “ times +2 stars - Nathan preferred entry”)
elif touch_count == 2:
stars += 1
reasons.append(“Tested twice +1 star - Nathan getting interested”)
elif touch_count == 1:
reasons.append(“First test - Nathan prefers to wait”)
else:
reasons.append(“Fresh zone - Nathan waits for first test”)
stars = min(5, stars)
star_display = “”
for i in range(stars):
star_display += “*”
for i in range(5 - stars):
star_display += “-”
return stars, star_display, reasons

def count_zone_touches(zone, ticker):
df = get_candles(ticker, “1d” if zone[“tf”] == “D1” else “4h”, “6mo”)
if df.empty:
return 0
level = zone[“top”] if zone[“type”] == “SUPPLY” else zone[“bottom”]
tolerance = RETEST_PIPS * 5
touches = 0
for i in range(len(df)):
high = df[“High”].iloc[i]
low = df[“Low”].iloc[i]
if low <= level + tolerance and high >= level - tolerance:
touches += 1
return max(0, touches - 1)

def calculate_position_size(entry, stop_loss, pair):
risk_amount = ACCOUNT_SIZE * (RISK_PERCENT / 100)
pip_diff = abs(entry - stop_loss)
if pip_diff == 0:
return 0.01
if “JPY” in pair:
pip_value = 1000
else:
pip_value = 10000
pips_at_risk = pip_diff * pip_value
if pips_at_risk == 0:
return 0.01
lot_size = risk_amount / (pips_at_risk * 1)
lot_size = max(0.01, round(lot_size, 2))
return lot_size

def scan_zones(pair, ticker):
zones = []
for interval, label, period in [(“1d”, “D1”, “6mo”), (“4h”, “H4”, “60d”)]:
df = get_candles(ticker, interval, period)
if df.empty or len(df) < 50:
continue
df = df.tail(100).reset_index(drop=True)
for i in range(3, len(df) - 3):
c = df.iloc[i]
body = abs(c[“Close”] - c[“Open”])
rng = c[“High”] - c[“Low”]
if rng == 0:
continue
if c[“Close”] < c[“Open”] and body > rng * 0.5:
downs = sum(1 for j in range(1, 4) if (i-j) >= 0 and df.iloc[i-j][“Close”] < df.iloc[i-j][“Open”])
if downs >= 2:
zone = {“type”: “SUPPLY”, “tf”: label, “top”: c[“High”], “bottom”: c[“Open”], “broken”: False, “break_idx”: None, “touch_count”: 0}
zone[“touch_count”] = count_zone_touches(zone, ticker)
zones.append(zone)
if c[“Close”] > c[“Open”] and body > rng * 0.5:
ups = sum(1 for j in range(1, 4) if (i-j) >= 0 and df.iloc[i-j][“Close”] > df.iloc[i-j][“Open”])
if ups >= 2:
zone = {“type”: “DEMAND”, “tf”: label, “top”: c[“Open”], “bottom”: c[“Low”], “broken”: False, “break_idx”: None, “touch_count”: 0}
zone[“touch_count”] = count_zone_touches(zone, ticker)
zones.append(zone)
deduped = []
for z in zones:
if not any(abs(z[“top”] - d[“top”]) < RETEST_PIPS * 2 for d in deduped):
deduped.append(z)
return deduped

def check_interactions(pair, ticker, zones):
df = get_candles(ticker, “5m”, “1d”)
if df.empty:
return
price = float(df[“Close”].iloc[-1])
now = time.time()
d1_trend, trend_strength = get_daily_trend(ticker)
h4_trend = get_h4_trend(ticker)
session_valid, session_reason = is_valid_session_for_pair(pair)
news_clear, news_reason = check_news_window()

```
for zone in zones:
    zid = pair + zone["tf"] + zone["type"] + str(round(zone["top"], 4))
    zlabel = zone["tf"] + " " + zone["type"]
    stars, star_display, star_reasons = rate_zone(zone, ticker)

    if not zone["broken"]:
        if zone["type"] == "SUPPLY" and price > zone["top"]:
            zone["broken"] = True
            zone["break_idx"] = now
            if zid not in alerted_breaks:
                alerted_breaks.add(zid)
                msg = (
                    "BREAKOUT ALERT - " + pair + "\n\n"
                    "BULLISH BREAKOUT\n"
                    "Zone: " + zlabel + "\n"
                    "Zone Rating: " + star_display + " (" + str(stars) + "/5)\n"
                    "Level: " + str(round(zone["top"], 5)) + "\n"
                    "Price: " + str(round(price, 5)) + "\n\n"
                    "D1 Trend: " + d1_trend + "\n"
                    "H4 Trend: " + h4_trend + "\n"
                    "Session: " + session_reason + "\n\n"
                    "Now watch for RETEST of " + str(round(zone["top"], 5)) + "\n"
                    "That will be your BUY setup"
                )
                send_telegram(msg)
                print("BREAKOUT: " + pair + " " + zlabel)

        elif zone["type"] == "DEMAND" and price < zone["bottom"]:
            zone["broken"] = True
            zone["break_idx"] = now
            if zid not in alerted_breaks:
                alerted_breaks.add(zid)
                msg = (
                    "BREAKOUT ALERT - " + pair + "\n\n"
                    "BEARISH BREAKOUT\n"
                    "Zone: " + zlabel + "\n"
                    "Zone Rating: " + star_display + " (" + str(stars) + "/5)\n"
                    "Level: " + str(round(zone["bottom"], 5)) + "\n"
                    "Price: " + str(round(price, 5)) + "\n\n"
                    "D1 Trend: " + d1_trend + "\n"
                    "H4 Trend: " + h4_trend + "\n"
                    "Session: " + session_reason + "\n\n"
                    "Now watch for RETEST of " + str(round(zone["bottom"], 5)) + "\n"
                    "That will be your SELL setup"
                )
                send_telegram(msg)
                print("BREAKOUT: " + pair + " " + zlabel)

    else:
        if zone["break_idx"] and (now - zone["break_idx"]) < 180:
            continue
        rid = zid + "retest"
        if rid in last_alert and (now - last_alert[rid]) < ALERT_COOLDOWN:
            continue

        rl = zone["top"] if zone["type"] == "SUPPLY" else zone["bottom"]
        tdir = "BUY" if zone["type"] == "SUPPLY" else "SELL"

        if abs(price - rl) <= RETEST_PIPS:
            trend_aligned = False
            trend_note = ""
            if tdir == "BUY" and d1_trend == "BULLISH" and h4_trend == "BULLISH":
                trend_aligned = True
                trend_note = "STRONG - Both D1 and H4 bullish"
            elif tdir == "BUY" and d1_trend == "BULLISH":
                trend_aligned = True
                trend_note = "GOOD - D1 bullish, H4 mixed"
            elif tdir == "SELL" and d1_trend == "BEARISH" and h4_trend == "BEARISH":
                trend_aligned = True
                trend_note = "STRONG - Both D1 and H4 bearish"
            elif tdir == "SELL" and d1_trend == "BEARISH":
                trend_aligned = True
                trend_note = "GOOD - D1 bearish, H4 mixed"
            else:
                trend_note = "WARNING - Trade against D1 trend, skip this"

            sl_distance = RETEST_PIPS * 3
            if tdir == "BUY":
                stop_loss = rl - sl_distance
                take_profit = rl + (sl_distance * 3)
            else:
                stop_loss = rl + sl_distance
                take_profit = rl - (sl_distance * 3)

            lot_size = calculate_position_size(price, stop_loss, pair)
            risk_amount = round(ACCOUNT_SIZE * RISK_PERCENT / 100, 2)

            last_alert[rid] = now

            validity = "VALID SETUP" if (trend_aligned and session_valid and news_clear and stars >= 3) else "WEAK SETUP - Check notes"

            msg = (
                "RETEST ALERT - " + pair + "\n\n"
                + validity + "\n"
                + tdir + " OPPORTUNITY\n"
                "Zone: " + zlabel + "\n"
                "Zone Rating: " + star_display + " (" + str(stars) + "/5)\n"
                "Touch Count: " + str(zone["touch_count"]) + " times (Nathan prefers 2-3)\n\n"
                "Level: " + str(round(rl, 5)) + "\n"
                "Price: " + str(round(price, 5)) + "\n\n"
                "TREND ANALYSIS (Nathan Method)\n"
                "D1 Trend: " + d1_trend + "\n"
                "H4 Trend: " + h4_trend + "\n"
                "Alignment: " + trend_note + "\n\n"
                "SESSION\n"
                + session_reason + "\n\n"
                "NEWS\n"
                + news_reason + "\n\n"
                "RISK MANAGEMENT\n"
                "Stop Loss: " + str(round(stop_loss, 5)) + "\n"
                "Take Profit: " + str(round(take_profit, 5)) + "\n"
                "Lot Size: " + str(lot_size) + "\n"
                "Risk: $" + str(risk_amount) + "\n\n"
                "FINAL CHECKLIST\n"
                "Trend aligned: " + ("YES" if trend_aligned else "NO - SKIP") + "\n"
                "Good session: " + ("YES" if session_valid else "NO - WAIT") + "\n"
                "News clear: " + ("YES" if news_clear else "NO - WAIT") + "\n"
                "Zone strong: " + ("YES" if stars >= 3 else "NO - WEAK") + "\n\n"
                "Confirm on M5 or M1 before entering!"
            )
            send_telegram(msg)
            print("RETEST: " + pair + " " + zlabel + " Stars:" + str(stars))
```

def main():
print(“SD Alert Bot Starting - Enhanced Version”)
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
print(“ERROR: Set environment variables”)
return

```
send_telegram(
    "SD Alert Bot Started - Enhanced Version\n\n"
    "Monitoring: EURJPY EURUSD GBPUSD USDJPY\n\n"
    "Features active:\n"
    "Nathan D1 trend filter\n"
    "Zone strength rating 1-5 stars\n"
    "Session filter (Asia/London/NY)\n"
    "News window filter\n"
    "Risk management calculator\n"
    "Full checklist on every alert\n\n"
    "Bot is live. Waiting for setups..."
)

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
        time.sleep(60)
    except KeyboardInterrupt:
        send_telegram("Alert Bot stopped.")
        break
    except Exception as e:
        print("Error: " + str(e))
        time.sleep(60)
```

if **name** == “**main**”:
main()
