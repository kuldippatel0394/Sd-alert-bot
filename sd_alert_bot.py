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

RETEST_PIPS = 0.0010
ALERT_COOLDOWN = 300
ACCOUNT_SIZE = 1000.0
RISK_PERCENT = 1.0
JPY_PAIRS = [“EURJPY”, “USDJPY”]

STATE_FILE = “bot_state.txt”

def send_telegram(message):
url = “https://api.telegram.org/bot” + TELEGRAM_BOT_TOKEN + “/sendMessage”
payload = {“chat_id”: TELEGRAM_CHAT_ID, “text”: message}
try:
r = requests.post(url, data=payload, timeout=10)
if r.status_code != 200:
print(“Telegram error: “ + r.text)
except Exception as e:
print(“Telegram failed: “ + str(e))

def get_candles(ticker, interval, period):
try:
df = yf.download(ticker, interval=interval, period=period, progress=False)
df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
return df[[“Open”, “High”, “Low”, “Close”]].dropna()
except Exception as e:
print(“Data error: “ + str(e))
return pd.DataFrame()

def get_current_session():
hour = datetime.now(timezone.utc).hour
sessions = []
if 0 <= hour < 9:
sessions.append(“ASIA”)
if 7 <= hour < 16:
sessions.append(“LONDON”)
if 12 <= hour < 21:
sessions.append(“NEWYORK”)
return sessions if sessions else [“OFFMARKET”]

def is_valid_session(pair):
sessions = get_current_session()
if “OFFMARKET” in sessions:
return False, “Off market hours”
if pair in JPY_PAIRS:
return True, “JPY pair valid in: “ + “, “.join(sessions)
else:
valid = any(s in sessions for s in [“LONDON”, “NEWYORK”])
if valid:
return True, “Valid session: “ + “, “.join(sessions)
return False, “Wait for London or New York session”

def check_news():
hour = datetime.now(timezone.utc).hour
minute = datetime.now(timezone.utc).minute
weekday = datetime.now(timezone.utc).weekday()
if weekday == 4 and 12 <= hour <= 14:
return False, “Possible NFP Friday - avoid”
if hour in [13, 14, 15] and minute < 30:
return False, “High impact news window - wait”
return True, “Clear of major news”

def get_d1_trend(ticker):
df = get_candles(ticker, “1d”, “3mo”)
if df.empty or len(df) < 20:
return “UNKNOWN”
closes = df[“Close”].values
highs = df[“High”].values
lows = df[“Low”].values
sma20 = np.mean(closes[-20:])
sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else np.mean(closes)
current = closes[-1]
hh = sum(1 for i in range(-5, -1) if highs[i] > highs[i-1])
hl = sum(1 for i in range(-5, -1) if lows[i] > lows[i-1])
lh = sum(1 for i in range(-5, -1) if highs[i] < highs[i-1])
ll = sum(1 for i in range(-5, -1) if lows[i] < lows[i-1])
if current > sma20 > sma50 and hh >= 2 and hl >= 2:
return “BULLISH”
elif current < sma20 < sma50 and lh >= 2 and ll >= 2:
return “BEARISH”
return “RANGING”

def get_h4_trend(ticker):
df = get_candles(ticker, “4h”, “30d”)
if df.empty or len(df) < 20:
return “UNKNOWN”
closes = df[“Close”].values
sma20 = np.mean(closes[-20:])
return “BULLISH” if closes[-1] > sma20 else “BEARISH”

def rate_zone(zone_type, tf, touch_count):
stars = 1
if tf == “D1”:
stars += 2
else:
stars += 1
if touch_count >= 3:
stars += 2
elif touch_count == 2:
stars += 1
stars = min(5, stars)
display = “*” * stars + “-” * (5 - stars)
return stars, display

def count_touches(zone_top, zone_bottom, ticker, tf):
interval = “1d” if tf == “D1” else “4h”
df = get_candles(ticker, interval, “6mo”)
if df.empty:
return 0
level = (zone_top + zone_bottom) / 2
tolerance = RETEST_PIPS * 5
touches = sum(1 for i in range(len(df)) if df[“Low”].iloc[i] <= level + tolerance and df[“High”].iloc[i] >= level - tolerance)
return max(0, touches - 1)

def find_zones(ticker):
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
top = float(c[“High”])
bottom = float(c[“Open”])
touches = count_touches(top, bottom, ticker, label)
zones.append({“type”: “SUPPLY”, “tf”: label, “top”: top, “bottom”: bottom, “touches”: touches})
if c[“Close”] > c[“Open”] and body > rng * 0.5:
ups = sum(1 for j in range(1, 4) if (i-j) >= 0 and df.iloc[i-j][“Close”] > df.iloc[i-j][“Open”])
if ups >= 2:
top = float(c[“Open”])
bottom = float(c[“Low”])
touches = count_touches(top, bottom, ticker, label)
zones.append({“type”: “DEMAND”, “tf”: label, “top”: top, “bottom”: bottom, “touches”: touches})
deduped = []
for z in zones:
if not any(abs(z[“top”] - d[“top”]) < RETEST_PIPS * 2 for d in deduped):
deduped.append(z)
return deduped

def load_state():
state = {“alerted_breaks”: [], “last_alerts”: {}}
try:
if os.path.exists(STATE_FILE):
with open(STATE_FILE, “r”) as f:
import json
state = json.load(f)
except:
pass
return state

def save_state(state):
try:
import json
with open(STATE_FILE, “w”) as f:
json.dump(state, f)
except:
pass

def calc_lot_size(entry, stop_loss, pair):
risk = ACCOUNT_SIZE * (RISK_PERCENT / 100)
pip_diff = abs(entry - stop_loss)
if pip_diff == 0:
return 0.01
pip_value = 1000 if “JPY” in pair else 10000
pips = pip_diff * pip_value
lot = risk / pips if pips > 0 else 0.01
return max(0.01, round(lot, 2))

def scan_pair(pair, ticker, state):
print(“Scanning “ + pair + “…”)
df_live = get_candles(ticker, “5m”, “1d”)
if df_live.empty:
print(“No live data for “ + pair)
return

```
price = float(df_live["Close"].iloc[-1])
now = time.time()
d1_trend = get_d1_trend(ticker)
h4_trend = get_h4_trend(ticker)
session_ok, session_msg = is_valid_session(pair)
news_ok, news_msg = check_news()
zones = find_zones(ticker)
alerted_breaks = state.get("alerted_breaks", [])
last_alerts = state.get("last_alerts", {})

print(pair + " price=" + str(round(price, 5)) + " D1=" + d1_trend + " zones=" + str(len(zones)))

for zone in zones:
    zid = pair + zone["tf"] + zone["type"] + str(round(zone["top"], 4))
    zlabel = zone["tf"] + " " + zone["type"]
    stars, star_display = rate_zone(zone["type"], zone["tf"], zone["touches"])

    broken = zid in alerted_breaks

    if not broken:
        breakout = False
        direction = ""
        level = 0.0
        trade_dir = ""

        if zone["type"] == "SUPPLY" and price > zone["top"]:
            breakout = True
            direction = "BULLISH BREAKOUT"
            level = zone["top"]
            trade_dir = "BUY"
        elif zone["type"] == "DEMAND" and price < zone["bottom"]:
            breakout = True
            direction = "BEARISH BREAKOUT"
            level = zone["bottom"]
            trade_dir = "SELL"

        if breakout:
            alerted_breaks.append(zid)
            state["alerted_breaks"] = alerted_breaks
            msg = (
                "BREAKOUT ALERT - " + pair + "\n\n"
                + direction + "\n"
                "Zone: " + zlabel + "\n"
                "Rating: " + star_display + " (" + str(stars) + "/5)\n"
                "Touches: " + str(zone["touches"]) + " (Nathan prefers 2-3)\n"
                "Level: " + str(round(level, 5)) + "\n"
                "Price: " + str(round(price, 5)) + "\n\n"
                "D1 Trend: " + d1_trend + "\n"
                "H4 Trend: " + h4_trend + "\n"
                "Session: " + session_msg + "\n\n"
                "Watch for RETEST of " + str(round(level, 5)) + "\n"
                "That will be your " + trade_dir + " setup"
            )
            send_telegram(msg)
            print("BREAKOUT sent: " + pair + " " + zlabel)

    else:
        rid = zid + "retest"
        last_time = last_alerts.get(rid, 0)
        if (now - last_time) < ALERT_COOLDOWN:
            continue

        if zone["type"] == "SUPPLY":
            rl = zone["top"]
            trade_dir = "BUY"
            trend_ok = d1_trend == "BULLISH"
        else:
            rl = zone["bottom"]
            trade_dir = "SELL"
            trend_ok = d1_trend == "BEARISH"

        if abs(price - rl) <= RETEST_PIPS:
            sl_dist = RETEST_PIPS * 3
            sl = rl - sl_dist if trade_dir == "BUY" else rl + sl_dist
            tp = rl + (sl_dist * 3) if trade_dir == "BUY" else rl - (sl_dist * 3)
            lot = calc_lot_size(price, sl, pair)
            risk_usd = round(ACCOUNT_SIZE * RISK_PERCENT / 100, 2)

            if trend_ok and session_ok and news_ok and stars >= 3:
                validity = "VALID SETUP - All checks passed"
            elif not trend_ok:
                validity = "WEAK - Against D1 trend, consider skipping"
            elif stars < 3:
                validity = "WEAK - Zone not strong enough yet"
            else:
                validity = "PARTIAL - Check notes below"

            trend_align = "YES" if trend_ok else "NO - D1 trend is " + d1_trend + ", trade is " + trade_dir

            last_alerts[rid] = now
            state["last_alerts"] = last_alerts

            msg = (
                "RETEST ALERT - " + pair + "\n\n"
                + validity + "\n\n"
                + trade_dir + " OPPORTUNITY\n"
                "Zone: " + zlabel + "\n"
                "Rating: " + star_display + " (" + str(stars) + "/5)\n"
                "Touches: " + str(zone["touches"]) + " (Nathan prefers 2-3)\n\n"
                "Level: " + str(round(rl, 5)) + "\n"
                "Price: " + str(round(price, 5)) + "\n\n"
                "TREND (Nathan Method)\n"
                "D1: " + d1_trend + "\n"
                "H4: " + h4_trend + "\n"
                "Aligned: " + trend_align + "\n\n"
                "SESSION\n"
                + session_msg + "\n\n"
                "NEWS\n"
                + news_msg + "\n\n"
                "RISK MANAGEMENT\n"
                "Stop Loss: " + str(round(sl, 5)) + "\n"
                "Take Profit: " + str(round(tp, 5)) + "\n"
                "Lot Size: " + str(lot) + "\n"
                "Risk: $" + str(risk_usd) + "\n\n"
                "CHECKLIST\n"
                "Trend aligned: " + ("YES" if trend_ok else "NO - SKIP") + "\n"
                "Good session: " + ("YES" if session_ok else "NO - WAIT") + "\n"
                "News clear: " + ("YES" if news_ok else "NO - WAIT") + "\n"
                "Zone strong: " + ("YES" if stars >= 3 else "NO - WEAK") + "\n\n"
                "Confirm on M5 or M1 before entering!"
            )
            send_telegram(msg)
            print("RETEST sent: " + pair + " " + zlabel)
```

def main():
print(“SD Alert Bot - Quick Scan Mode”)
print(“Time: “ + str(datetime.now(timezone.utc)))

```
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: Missing environment variables")
    return

state = load_state()
print("State loaded. Known breaks: " + str(len(state.get("alerted_breaks", []))))

for pair, ticker in PAIRS.items():
    try:
        scan_pair(pair, ticker, state)
    except Exception as e:
        print("Error scanning " + pair + ": " + str(e))

save_state(state)
print("Scan complete. State saved.")
```

if **name** == “**main**”:
main()
