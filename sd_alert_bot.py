elif zone["type"] == "DEMAND":
            trade_dir = "SELL"
            trend_ok = d1_trend == "BEARISH"
            sl = zone["bottom"] + RETEST_PIPS * 3
            tp = zone["bottom"] - (RETEST_PIPS * 9)
            note = "Broken Demand retested - Old Support now Resistance - Nathan SELLS here"

        lot = calc_lot_size(price, sl, pair)
        risk_usd = round(ACCOUNT_SIZE * RISK_PERCENT / 100, 2)

        if trend_ok and session_ok and news_ok and stars >= 3:
            validity = "VALID SETUP"
        else:
            validity = "WEAK SETUP - check notes"

        trend_align = "YES" if trend_ok else "NO - D1 is " + d1_trend + " but trade is " + trade_dir

        alerted[alert_id] = now
        state["alerted"] = alerted

        send_telegram(
            "RETEST ALERT - " + pair + "\n\n"
            + validity + "\n"
            + trade_dir + " OPPORTUNITY\n\n"
            + note + "\n\n"
            "Zone: " + zlabel + "\n"
            "Rating: " + star_display + " (" + str(stars) + "/5)\n"
            "Touches: " + str(zone["touches"]) + " (Nathan prefers 2-3)\n\n"
            "Zone Top: " + str(round(zone["top"], 5)) + "\n"
            "Zone Bottom: " + str(round(zone["bottom"], 5)) + "\n"
            "Price: " + str(round(price, 5)) + "\n\n"
            "TREND (Nathan method)\n"
            "D1: " + d1_trend + "\n"
            "H4: " + h4_trend + "\n"
            "Aligned: " + trend_align + "\n\n"
            "SESSION: " + session_msg + "\n"
            "NEWS: " + news_msg + "\n\n"
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
            "Confirm on M5 then enter on M1!"
        )
        print("RETEST sent: " + pair + " " + zlabel + " " + trade_dir)

def main():
print(“SD Alert Bot - Nathan Williams Method”)
print(“Time: “ + str(datetime.now(timezone.utc)))
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("ERROR: Missing environment variables")
    return

state = load_state()

for pair, ticker in PAIRS.items():
    try:
        scan_pair(pair, ticker, state)
    except Exception as e:
        print("Error scanning " + pair + ": " + str(e))

save_state(state)
print("Scan complete.")

if name == “**main**”:
main()