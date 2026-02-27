msg("BREAKOUT - " + pair + "\nBEARISH BREAKOUT\nZone: " + label + "\nLevel: " + str(round(z["bottom"], 5)) + "\nPrice: " + str(round(price, 5)) + "\nD1: " + d1 + "\nWait for RETEST then SELL")
        elif at_zone:
            aid = zid + "_touch"
            if now - alerts.get(aid, 0) < COOLDOWN:
                continue
            if z["type"] == "SUPPLY":
                tdir = "SELL"
                sl = z["top"] + PIPS * 3
                tp = z["bottom"] - PIPS * 9
                trend_ok = d1 == "BEARISH"
                note = "Unbroken Supply - Nathan SELLS here"
            else:
                tdir = "BUY"
                sl = z["bottom"] - PIPS * 3
                tp = z["top"] + PIPS * 9
                trend_ok = d1 == "BULLISH"
                note = "Unbroken Demand - Nathan BUYS here"
            alerts[aid] = now
            state["alerts"] = alerts
            valid = "VALID" if trend_ok and sess else "WEAK - check trend and session"
            msg("ZONE ALERT - " + pair + "\n" + valid + "\n" + tdir + " - " + note + "\nZone: " + label + "\nPrice: " + str(round(price, 5)) + "\nSL: " + str(round(sl, 5)) + "\nTP: " + str(round(tp, 5)) + "\nLot: " + str(lot(price, sl, pair)) + "\nD1: " + d1 + "\nSession: " + ("OK" if sess else "WAIT") + "\nConfirm on M5 then M1!")
    else:
        if not at_zone:
            continue
        aid = zid + "_retest"
        if now - alerts.get(aid, 0) < COOLDOWN:
            continue
        if z["type"] == "SUPPLY":
            tdir = "BUY"
            sl = z["top"] - PIPS * 3
            tp = z["top"] + PIPS * 9
            trend_ok = d1 == "BULLISH"
            note = "Broken Supply retested - Old Resistance now Support - Nathan BUYS"
        else:
            tdir = "SELL"
            sl = z["bottom"] + PIPS * 3
            tp = z["bottom"] - PIPS * 9
            trend_ok = d1 == "BEARISH"
            note = "Broken Demand retested - Old Support now Resistance - Nathan SELLS"
        alerts[aid] = now
        state["alerts"] = alerts
        valid = "VALID" if trend_ok and sess else "WEAK - check trend and session"
        msg("RETEST ALERT - " + pair + "\n" + valid + "\n" + tdir + " - " + note + "\nZone: " + label + "\nPrice: " + str(round(price, 5)) + "\nSL: " + str(round(sl, 5)) + "\nTP: " + str(round(tp, 5)) + "\nLot: " + str(lot(price, sl, pair)) + "\nD1: " + d1 + "\nSession: " + ("OK" if sess else "WAIT") + "\nConfirm on M5 then M1!")

def main():
print(“Bot starting - “ + str(datetime.now(timezone.utc)))
if not TOKEN or not CHAT:
print(“ERROR: Missing env vars”)
return
state = load()
for pair, ticker in PAIRS.items():
try:
scan(pair, ticker, state)
except Exception as e:
print(“Error “ + pair + “: “ + str(e))
save(state)
print(“Done”)

if name == “**main**”:
main()