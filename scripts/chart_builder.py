"""
chart_builder.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Dynamic Flow - Premium Ribbon Candle (Pine Script → Python 변환)

Pine Script 원본 공식:
  HMA(_src, _length)  => wma(2*wma(_src,_length/2)-wma(_src,_length), round(sqrt(_length)))
  EHMA(_src, _length) => ema(2*ema(_src,_length/2)-ema(_src,_length), round(sqrt(_length)))
  THMA(_src, _length) => wma(wma(_src,_length/3)*3-wma(_src,_length/2)-wma(_src,_length), _length)
  Mode(_mode,_src,_len) => _mode=="Hma" ? HMA : _mode=="Ehma" ? EHMA : THMA(_src,_len/2)

  _hull = Mode(modeSwitch, src, int(length * lengthMult))
  slope = _hull - _hull[1]
  norm  = max(-1, min(1, slope / atr(14)))

  isGreen = norm >= 0  →  #00A99D
  isRed   = norm <  0  →  #E84A5F

저장: data/charts/{ticker}_{market}.json
"""

import json
import math
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHARTS_DIR = os.path.join(BASE_DIR, "data", "charts")

GREEN_COL = "#00A99D"
RED_COL   = "#E84A5F"
GRAY_COL  = "#888888"

MARKET_SUFFIX = {"kospi": ".KS", "kosdaq": ".KQ", "us": ""}

DEFAULT_MODE        = "Hma"
DEFAULT_LENGTH      = 55
DEFAULT_LENGTH_MULT = 1.0
DEFAULT_DAYS        = 180   # 약 130 거래일(6개월)


# ── 이동평균 함수 ─────────────────────────────────────────────────────────────
def _wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average"""
    period  = max(1, int(period))
    weights = np.arange(1, period + 1, dtype=float)
    w_sum   = weights.sum()
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / w_sum, raw=True
    )


def _ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average"""
    return series.ewm(span=max(1, int(period)), adjust=False).mean()


def _hma(series: pd.Series, length: int) -> pd.Series:
    """Hull MA: WMA(2*WMA(src,L/2)-WMA(src,L), sqrt(L))"""
    half  = max(1, length // 2)
    sqrtl = max(1, round(math.sqrt(length)))
    return _wma(2 * _wma(series, half) - _wma(series, length), sqrtl)


def _thma(series: pd.Series, length: int) -> pd.Series:
    """Triple Hull MA: WMA(WMA(src,L/3)*3-WMA(src,L/2)-WMA(src,L), L)"""
    third = max(1, length // 3)
    half  = max(1, length // 2)
    return _wma(
        _wma(series, third) * 3 - _wma(series, half) - _wma(series, length),
        length
    )


def _ehma(series: pd.Series, length: int) -> pd.Series:
    """EMA Hull MA: EMA(2*EMA(src,L/2)-EMA(src,L), sqrt(L))"""
    half  = max(1, length // 2)
    sqrtl = max(1, round(math.sqrt(length)))
    return _ema(2 * _ema(series, half) - _ema(series, length), sqrtl)


def _mode_hull(mode: str, series: pd.Series, length: int) -> pd.Series:
    """Pine Script: Mode(_mode, _src, _len)"""
    if mode == "Hma":
        return _hma(series, length)
    elif mode == "Ehma":
        return _ehma(series, length)
    else:  # Thma
        return _thma(series, max(1, length // 2))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR (Wilder smoothing — TradingView atr() 동일)"""
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


# ── 지표 계산 ─────────────────────────────────────────────────────────────────
def compute_ribbon(
    df:          pd.DataFrame,
    mode:        str   = DEFAULT_MODE,
    length:      int   = DEFAULT_LENGTH,
    length_mult: float = DEFAULT_LENGTH_MULT,
) -> pd.Series:
    """
    norm 시리즈를 계산합니다.
    norm = max(-1, min(1, slope / ATR(14)))
    """
    eff_len = max(2, int(length * length_mult))
    hull    = _mode_hull(mode, df["Close"], eff_len)
    slope   = hull - hull.shift(1)
    atr14   = _atr(df, 14).replace(0, np.nan)
    return (slope / atr14).clip(-1, 1)


# ── OHLCV 수집 (Open 포함) ────────────────────────────────────────────────────
def fetch_ohlcv_chart(ticker: str, market: str, days: int = DEFAULT_DAYS) -> pd.DataFrame:
    """캔들스틱 차트용 OHLCV 데이터 수집 (Open 포함)."""
    suffix    = MARKET_SUFFIX.get(market, "")
    yf_ticker = ticker + suffix
    end       = datetime.now()
    start     = end - timedelta(days=days)
    try:
        df = yf.download(
            yf_ticker,
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        cols = [c for c in ["Open", "High", "Low", "Close"] if c in df.columns]
        return df[cols].dropna()
    except Exception as e:
        print(f"    ⚠ {yf_ticker} OHLCV 수집 실패: {e}")
        return pd.DataFrame()


# ── 차트 JSON 빌드 & 저장 ─────────────────────────────────────────────────────
def _build_candle_list(df: pd.DataFrame, norm: pd.Series) -> list[dict]:
    """lightweight-charts용 캔들 데이터 생성 (per-bar 색상 포함)."""
    open_col = "Open" if "Open" in df.columns else "Close"
    candles  = []
    for idx in df.index:
        n   = norm.get(idx)
        col = GRAY_COL if pd.isna(n) else (GREEN_COL if n >= 0 else RED_COL)
        candles.append({
            "time":        idx.strftime("%Y-%m-%d"),
            "open":        round(float(df.at[idx, open_col]), 4),
            "high":        round(float(df.at[idx, "High"]),   4),
            "low":         round(float(df.at[idx, "Low"]),    4),
            "close":       round(float(df.at[idx, "Close"]),  4),
            "color":       col,
            "wickColor":   col,
            "borderColor": col,
        })
    return candles


def save_chart_json(ticker: str, market: str, name: str,
                    candles: list[dict]) -> str:
    os.makedirs(CHARTS_DIR, exist_ok=True)
    path = os.path.join(CHARTS_DIR, f"{ticker}_{market}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "ticker":     ticker,
            "market":     market,
            "name":       name,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "candles":    candles,
        }, f, ensure_ascii=False)
    return path


# ── 배치 빌드 ─────────────────────────────────────────────────────────────────
def build_all_charts(
    watchlist:   list[dict],
    mode:        str   = DEFAULT_MODE,
    length:      int   = DEFAULT_LENGTH,
    length_mult: float = DEFAULT_LENGTH_MULT,
    days:        int   = DEFAULT_DAYS,
) -> list[str]:
    """관심종목 전체의 Ribbon Candle 차트 데이터를 빌드합니다."""
    min_bars = length + 30
    saved    = []

    print(f"\n  📊 Ribbon Candle 차트 빌드 ({mode}, L={length}, ×{length_mult}) ...")
    for stock in watchlist:
        ticker = stock.get("ticker", "")
        market = stock.get("market", "us")
        name   = stock.get("name", ticker)
        print(f"    [{market.upper()}] {ticker} ({name})...")

        df = fetch_ohlcv_chart(ticker, market, days=days)
        if df.empty or len(df) < min_bars:
            print(f"      ⚠ 데이터 부족 ({len(df)}봉, 필요 {min_bars}) — 스킵")
            continue

        norm    = compute_ribbon(df, mode=mode, length=length, length_mult=length_mult)
        candles = _build_candle_list(df, norm)
        path    = save_chart_json(ticker, market, name, candles)
        print(f"      ✓ {len(candles)}봉 → {os.path.basename(path)}")
        saved.append(path)

    print(f"  📊 완료: {len(saved)}/{len(watchlist)}개 저장")
    return saved
