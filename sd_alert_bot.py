# placeholder
import os
import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

PAIRS = {
    "EURJPY": "EURJPY=X",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
}

ZONE_STRENGTH = 3
RETEST_PIPS = 0.0010
ALERT_COOLDOWN = 300
zone_store = {}
last_alert = {}
alerted_breaks = set()

def send_telegram(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(str(e))

def get_candles(ticker, interval, period):
    try:
        df = yf.download(ticker, interval=interval, period=period, progress=False)
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df[["Open", "High", "Low", "Close"]].dropna()
    except:
        return pd.DataFrame()

def scan_zones(ticker):
    zones = []
    for interval, label, period in [("1d", "D1", "6mo"), ("4h", "H4", "60d")]:
        df = get_candles(ticker, interval, period)
        if df.empty or len(df) < 50:
            continue
        df = df.tail(100).reset_index(drop=True)
        for i in range(3, len(df) - 3):
            c = df.iloc[i]
            body = abs(c["Close"] - c["Open"])
            rng = c["High"] - c["Low"]
            if rng == 0:
                continue
            if c["Close"] < c["Open"] and body > rng * 0.5:
                downs = sum(1 for j in range(1, 4) if (i-j) >= 0 and df.iloc[i-j]["Close"] < df.iloc[i-j]["Open"])
                if downs >= 2:
                    zones.append({"type": "SUPPLY", "tf": label, "top": c["High"], "bottom": c["Open"], "broken": False, "break_idx": None})
            if c["Close"] > c["Open"] and body > rng * 0.5:
                ups = sum(1 for j in range(1, 4) if (i-j) >= 0 and df.iloc[i-j]["Close"] > df.iloc[i-j]["Open"])
                if ups >= 2:
                    zones.append({"type": "DEMAND", "tf": label, "top": c["Open"], "bottom": c["Low"], "broken": False, "break_idx": None})
    deduped = []
    for z in zones:
        if not any(abs(z["top"] - d["top"]) < RETEST_PIPS * 2 for d in deduped):
            deduped.append(z)
    return deduped

def check_interactions(pair, ticker, zones):
    df = get_candles(ticker, "5m", "1d")
    if df.empty:
        return
    price = float(df["Close"].iloc[-1])
    now = time.time()
    for zone in zones:
        zid = pair + zone["tf"] + zone["type"] + str(round(zone["top"], 4))
        zlabel = zone["tf"] + " " + zone["type"]
        if not zone["broken"]:
            if zone["type"] == "SUPPLY" and price > zone["top"]:
                zone["broken"] = True
                zone["break_idx"] = now
                if zid not in alerted_breaks:
                    alerted_breaks.add(zid)
                    send_telegram("BREAKOUT - " + pair + "\nBULLISH BREAKOUT\nZone: " + zlabel + "\nLevel: " + str(round(zone["top"], 5)) + "\nPrice: " + str(round(price, 5)) + "\nWatch for retest to BUY")
            elif zone["type"] == "DEMAND" and price < zone["bottom"]:
                zone["broken"] = True
                zone["break_idx"] = now
                if zid not in alerted_breaks:
                    alerted_breaks.add(zid)
                    send_telegram("BREAKOUT - " + pair + "\nBEARISH BREAKOUT\nZone: " + zlabel + "\nLevel: " + str(round(zone["bottom"], 5)) + "\nPrice: " + str(round(price, 5)) + "\nWatch for retest to SELL")
        else:
            if zone["break_idx"] and (now - zone["break_idx"]) < 180:
                continue
            rid = zid + "retest"
            if rid in last_alert and (now - last_alert[rid]) < ALERT_COOLDOWN:
                continue
            rl = zone["top"] if zone["type"] == "SUPPLY" else zone["bottom"]
            tdir = "BUY" if zone["type"] == "SUPPLY" else "SELL"
            if abs(price - rl) <= RETEST_PIPS:
                last_alert[rid] = now
                send_telegram("RETEST ALERT - " + pair + "\n" + tdir + " OPPORTUNITY\nZone: " + zlabel + "\nLevel: " + str(round(rl, 5)) + "\nPrice: " + str(round(price, 5)) + "\nACTION: LOOK TO " + tdir + "\nCheck D1 trend, H4 zones, fundamentals\nConfirm on M5 or M1 before entering!")

def main():
    print("Bot starting...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Set environment variables")
        return
    send_telegram("SD Alert Bot Started! Monitoring EURJPY EURUSD GBPUSD USDJPY")
    for pair, ticker in PAIRS.items():
        print("Scanning " + pair)
        zone_store[pair] = scan_zones(ticker)
        print("Found " + str(len(zone_store[pair])) + " zones")
    while True:
        try:
            for pair, ticker in PAIRS.items():
                if pair in zone_store:
                    check_interactions(pair, ticker, zone_store[pair])
            time.sleep(60)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print("Error: " + str(e))
            time.sleep(60)

if __name__ == "__main__":
    main()
