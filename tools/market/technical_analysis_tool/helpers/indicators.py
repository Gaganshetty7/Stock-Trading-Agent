#!/usr/bin/env python3

# =========================================================
# INDICATORS
# =========================================================
# Pure calculation helpers: RSI, VWAP, MA, pivot levels.
# Used internally by tool.py — do not import directly in agents.
# =========================================================

from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

from tools.market.technical_analysis_tool.helpers.settings import MA_PERIOD


def calculate_rsi(data, period=14):
    delta    = data["Close"].diff()
    gain     = delta.where(delta > 0, 0)
    loss     = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs       = avg_gain / avg_loss
    rsi      = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def process_stock(ticker, data, data_5m):
    try:
        if data.empty:
            raise Exception("No 1m data")
        if data_5m.empty:
            raise Exception("No 5m data")

        data.dropna(inplace=True)
        data_5m.dropna(inplace=True)

        if len(data) < 25:
            raise Exception("Insufficient 1m data")
        if len(data_5m) < 20:
            raise Exception("Insufficient 5m data")

        latest_completed = data.iloc[-2]
        current_price    = float(latest_completed["Close"])

        last_block = data.iloc[-16:-1]
        H = float(last_block["High"].max())
        L = float(last_block["Low"].min())
        C = current_price

        today_open     = float(data["Open"].iloc[0])
        today_high     = float(data["High"].max())
        today_low      = float(data["Low"].min())
        previous_close = float(data["Close"].iloc[-3])

        # ----- Pivot -----
        P  = (H + L + C) / 3
        R1 = (2 * P) - L
        R2 = P + (H - L)
        R3 = H + 2 * (P - L)
        S1 = (2 * P) - H
        S2 = P - (H - L)
        S3 = L - 2 * (H - P)

        # ----- MA20 -----
        data["MA20"] = data["Close"].rolling(MA_PERIOD).mean()
        ma20 = float(data["MA20"].iloc[-2])

        # ----- VWAP -----
        typical_price        = (data["High"] + data["Low"] + data["Close"]) / 3
        cumulative_tp_volume = (typical_price * data["Volume"]).cumsum()
        cumulative_volume    = data["Volume"].cumsum()
        data["VWAP"]         = cumulative_tp_volume / cumulative_volume
        vwap                 = float(data["VWAP"].iloc[-2])

        # ----- RSI -----
        rsi_1m = calculate_rsi(data)
        rsi_5m = calculate_rsi(data_5m)

        # ----- Volume -----
        total_volume    = int(data["Volume"].sum())
        last_volume     = int(data["Volume"].iloc[-2])
        average_volume  = float(data["Volume"].iloc[-21:-1].mean())
        volume_strength = (last_volume / average_volume) if average_volume != 0 else 0

        # ----- Trend -----
        bullish_trend = current_price > P and current_price > ma20 and current_price > vwap
        bearish_trend = current_price < P and current_price < ma20 and current_price < vwap
        trend = "BULLISH" if bullish_trend else ("BEARISH" if bearish_trend else "SIDEWAYS")

        return {
            "stock"     : ticker,
            "timestamp" : datetime.now(IST).isoformat(),
            "status"    : "ok",
            "market_data": {
                "current_price" : round(current_price, 2),
                "today_open"    : round(today_open, 2),
                "today_high"    : round(today_high, 2),
                "today_low"     : round(today_low, 2),
                "previous_close": round(previous_close, 2)
            },
            "technical_indicators": {
                "pivot"  : round(P, 2),
                "MA20"   : round(ma20, 2),
                "VWAP"   : round(vwap, 2),
                "RSI_1m" : round(rsi_1m, 2),
                "RSI_5m" : round(rsi_5m, 2),
                "trend"  : trend
            },
            "support_resistance": {
                "R1": round(R1, 2), "R2": round(R2, 2), "R3": round(R3, 2),
                "S1": round(S1, 2), "S2": round(S2, 2), "S3": round(S3, 2)
            },
            "volume_analysis": {
                "today_total_volume" : total_volume,
                "last_candle_volume" : last_volume,
                "average_volume"     : int(average_volume),
                "volume_strength"    : round(volume_strength, 2)
            }
        }

    except Exception as e:
        return {
            "stock"    : ticker,
            "status"   : "error",
            "message"  : str(e),
            "timestamp": datetime.now(IST).isoformat()
        }
