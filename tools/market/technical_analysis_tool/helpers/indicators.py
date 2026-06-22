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


def process_stock(ticker, data, data_5m, data_15m, data_1d, ltp: float = None):
    try:
        if data.empty:
            raise Exception("No 1m data")
        if data_5m.empty:
            raise Exception("No 5m data")
        if data_15m.empty:
            raise Exception("No 15m data")
        if data_1d.empty:
            raise Exception("No daily data")

        data.dropna(inplace=True)
        data_5m.dropna(inplace=True)
        data_15m.dropna(inplace=True)
        data_1d.dropna(inplace=True)

        if len(data) < 25:
            raise Exception("Insufficient 1m data")
        if len(data_5m) < 20:
            raise Exception("Insufficient 5m data")
        if len(data_15m) < 20:
            raise Exception("Insufficient 15m data")
        if len(data_1d) < 2:
            raise Exception("Insufficient daily data")

        latest_completed = data.iloc[-2]
        last_completed_1m_candle_close = float(latest_completed["Close"])
        last_traded_price = ltp if ltp is not None else last_completed_1m_candle_close

        last_block = data.iloc[-16:-1]
        H = float(last_block["High"].max())
        L = float(last_block["Low"].min())
        C = last_traded_price

        today_open     = float(data["Open"].iloc[0])
        today_high     = float(data["High"].max())
        today_low      = float(data["Low"].min())

        now_date = datetime.now(IST).date()
        if data_1d.index[-1].date() == now_date:
            previous_day_close = float(data_1d["Close"].iloc[-2]) if len(data_1d) > 1 else float(data_1d["Close"].iloc[-1])
        else:
            previous_day_close = float(data_1d["Close"].iloc[-1])

        # ----- Pivot -----
        P  = (H + L + C) / 3
        R1 = (2 * P) - L
        R2 = P + (H - L)
        R3 = H + 2 * (P - L)
        S1 = (2 * P) - H
        S2 = P - (H - L)
        S3 = L - 2 * (H - P)

        # ----- MA20 (1m) -----
        data["MA20"] = data["Close"].rolling(MA_PERIOD).mean()
        ma20 = float(data["MA20"].iloc[-2])

        # ----- MA (5m) -----
        data_5m["MA20"] = data_5m["Close"].rolling(MA_PERIOD).mean()
        ma20_5m = float(data_5m["MA20"].iloc[-2])

        # ----- MA (15m) -----
        data_15m["MA20"] = data_15m["Close"].rolling(MA_PERIOD).mean()
        ma20_15m = float(data_15m["MA20"].iloc[-2])

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
        average_volume_20m  = float(data["Volume"].iloc[-21:-1].mean())
        volume_strength_20m = (last_volume / average_volume_20m) if average_volume_20m != 0 else 0

        # ----- Trend & Relatives -----
        above_vwap = last_traded_price > vwap
        above_ma20_1m = last_traded_price > ma20
        above_intraday_pivot_15m = last_traded_price > P

        bullish_trend = above_vwap and above_ma20_1m and above_intraday_pivot_15m
        bearish_trend = last_traded_price < P and last_traded_price < ma20 and last_traded_price < vwap
        trend = "BULLISH" if bullish_trend else ("BEARISH" if bearish_trend else "SIDEWAYS")

        price_vs_vwap_pct = ((last_traded_price - vwap) / vwap) * 100 if vwap != 0 else 0
        price_vs_ma20_pct = ((last_traded_price - ma20) / ma20) * 100 if ma20 != 0 else 0
        price_vs_intraday_pivot_pct = ((last_traded_price - P) / P) * 100 if P != 0 else 0
        price_vs_previous_day_close_pct = ((last_traded_price - previous_day_close) / previous_day_close) * 100 if previous_day_close != 0 else 0

        return {
            "stock"     : ticker,
            "timestamp" : datetime.now(IST).isoformat(),
            "status"    : "ok",
            "market_data": {
                "last_traded_price"              : round(last_traded_price, 2),
                "last_completed_1m_candle_close" : round(last_completed_1m_candle_close, 2),
                "today_open"                     : round(today_open, 2),
                "today_high"                     : round(today_high, 2),
                "today_low"                      : round(today_low, 2),
                "previous_day_close"             : round(previous_day_close, 2)
            },
            "technical_indicators": {
                "pivot_15m"                       : round(P, 2),
                "pivot_source"                    : "last_15_1m_candles",
                "VWAP"                            : round(vwap, 2),
                "RSI_1m"                          : round(rsi_1m, 2),
                "RSI_5m"                          : round(rsi_5m, 2),
                "trend"                           : trend,
                "trend_reason": {
                    "above_vwap"               : bool(above_vwap),
                    "above_ma20_1m"            : bool(above_ma20_1m),
                    "above_intraday_pivot_15m" : bool(above_intraday_pivot_15m)
                },
                "price_vs_vwap_pct"               : round(price_vs_vwap_pct, 2),
                "price_vs_ma20_pct"               : round(price_vs_ma20_pct, 2),
                "price_vs_intraday_pivot_pct"     : round(price_vs_intraday_pivot_pct, 2),
                "price_vs_previous_day_close_pct" : round(price_vs_previous_day_close_pct, 2)
            },
            "support_resistance": {
                "R1": round(R1, 2), "R2": round(R2, 2), "R3": round(R3, 2),
                "S1": round(S1, 2), "S2": round(S2, 2), "S3": round(S3, 2)
            },
            "volume_analysis": {
                "today_total_volume"  : total_volume,
                "last_candle_volume"  : last_volume,
                "average_volume_20m"  : int(average_volume_20m),
                "volume_strength_20m" : round(volume_strength_20m, 2)
            },
            "ma_timeframes": {
                "MA20_1m" : round(ma20, 2),
                "MA20_5m" : round(ma20_5m, 2),
                "MA20_15m": round(ma20_15m, 2)
            }
        }

    except Exception as e:
        return {
            "stock"    : ticker,
            "status"   : "error",
            "message"  : str(e),
            "timestamp": datetime.now(IST).isoformat()
        }