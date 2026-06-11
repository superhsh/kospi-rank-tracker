"""
ribbon_screener.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
한국(KOSPI/KOSDAQ) · 미국(S&P 500) · 코인(CoinGecko Top 30) 전체를
스캔해 HMA(55) 기울기가 음수 → 양수로 전환된 종목을 추려냅니다.

저장: data/ribbon_screener.json
      data/charts/{ticker}_{market}.json  (매칭 종목 차트 데이터)
"""

import json
import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(BASE_DIR, "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "ribbon_screener.json")

# 스캔 유니버스 크기 (GitHub Actions 시간 제한 고려)
KR_KOSPI_LIMIT  = 100
KR_KOSDAQ_LIMIT =  50
US_LIMIT        = 150
COIN_LIMIT      =  30

HMA_LENGTH = 55
MIN_BARS   = HMA_LENGTH + 30   # 최소 데이터 봉수


# ── 유니버스 수집 ─────────────────────────────────────────────────────────────
def _get_kr_universe() -> list[dict]:
    """네이버 금융 KOSPI 상위 100 + KOSDAQ 상위 50 수집."""
    import sys
    sys.path.insert(0, BASE_DIR)
    from scripts.fetcher import fetch_top100_with_shares

    result = []
    for market, limit in [("KOSPI", KR_KOSPI_LIMIT), ("KOSDAQ", KR_KOSDAQ_LIMIT)]:
        try:
            df = fetch_top100_with_shares(market)
            if df.empty:
                print(f"  ⚠ {market} 유니버스 수집 실패")
                continue
            for _, row in df.head(limit).iterrows():
                result.append({
                    "ticker": str(row["ticker"]),
                    "name":   str(row["name"]),
                    "market": market.lower(),
                })
            print(f"  KR {market}: {min(len(df), limit)}개")
        except Exception as e:
            print(f"  ⚠ {market} 수집 오류: {e}")
    return result


def _get_us_universe() -> list[dict]:
    """S&P 500 + NASDAQ 100 tickers (중복 제거, 상위 US_LIMIT개)."""
    import sys
    sys.path.insert(0, BASE_DIR)
    from scripts.fetcher_us import get_sp500_tickers, get_nasdaq100_tickers

    seen    = set()
    tickers = []
    for t in get_nasdaq100_tickers() + get_sp500_tickers():
        if t and t not in seen:
            seen.add(t)
            tickers.append(t)
        if len(tickers) >= US_LIMIT:
            break

    result = [{"ticker": t, "name": t, "market": "us"} for t in tickers]
    print(f"  US 유니버스: {len(result)}개")
    return result


def _get_coin_universe() -> list[dict]:
    """CoinGecko 시총 기준 상위 COIN_LIMIT개 코인."""
    import sys
    sys.path.insert(0, BASE_DIR)
    from scripts.fetcher_crypto import fetch_top_coins

    try:
        df = fetch_top_coins(pages=1)
        result = []
        for _, row in df.head(COIN_LIMIT).iterrows():
            result.append({
                "ticker": str(row["ticker"]),
                "name":   str(row["name"]),
                "market": "coin",
            })
        print(f"  Coin 유니버스: {len(result)}개")
        return result
    except Exception as e:
        print(f"  ⚠ Coin 유니버스 수집 오류: {e}")
        return []


# ── HMA + 리본 계산 (chart_builder 재사용) ────────────────────────────────────
def _load_chart_builder():
    import sys
    sys.path.insert(0, BASE_DIR)
    from scripts.chart_builder import (
        fetch_ohlcv_chart, compute_ribbon, _build_candle_list, save_chart_json,
    )
    return fetch_ohlcv_chart, compute_ribbon, _build_candle_list, save_chart_json


# ── 개별 종목 스캔 ────────────────────────────────────────────────────────────
def _scan_single(stock: dict,
                 fetch_fn, ribbon_fn, candle_fn, save_fn) -> dict | None:
    """
    단일 종목의 HMA(55) 기울기 전환을 감지합니다.
    신호 발생 시 차트 데이터를 저장하고 결과 dict를 반환합니다.
    """
    ticker = stock["ticker"]
    market = stock["market"]
    name   = stock["name"]

    df = fetch_fn(ticker, market, days=220)
    if df.empty or len(df) < MIN_BARS:
        return None

    try:
        norm  = ribbon_fn(df)
        valid = norm.dropna()
        if len(valid) < 2:
            return None
        prev_norm = float(valid.iloc[-2])
        curr_norm = float(valid.iloc[-1])

        if prev_norm < 0 and curr_norm >= 0:
            # 차트 데이터 저장
            candles = candle_fn(df, norm)
            save_fn(ticker, market, name, candles)
            return {
                "ticker":    ticker,
                "name":      name,
                "market":    market,
                "prev_norm": round(prev_norm, 4),
                "curr_norm": round(curr_norm, 4),
            }
    except Exception as e:
        print(f"      ⚠ {ticker} 계산 오류: {e}")
    return None


# ── 배치 OHLCV 다운로드 (US 전용, 속도 최적화) ───────────────────────────────
def _batch_ohlcv_us(tickers: list[str], days: int = 220) -> dict[str, pd.DataFrame]:
    """
    yfinance 배치 다운로드로 US 종목 OHLCV를 한 번에 수집합니다.
    Returns: {ticker: DataFrame(Open,High,Low,Close)}
    """
    end   = datetime.now()
    start = (end - timedelta(days=days)).strftime("%Y-%m-%d")
    end_s = (end + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        raw = yf.download(
            tickers,
            start=start, end=end_s,
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
    except Exception as e:
        print(f"  ⚠ 배치 다운로드 실패: {e}")
        return {}

    result = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for t in tickers:
            try:
                sub = raw[t][["Open", "High", "Low", "Close"]].dropna()
                if not sub.empty:
                    result[t] = sub
            except Exception:
                pass
    else:
        # 단일 ticker 경우
        sub = raw[["Open", "High", "Low", "Close"]].dropna()
        if not sub.empty and tickers:
            result[tickers[0]] = sub
    return result


# ── 마켓별 스캔 ───────────────────────────────────────────────────────────────
def _scan_market(universe: list[dict], use_batch: bool = False) -> list[dict]:
    fetch_fn, ribbon_fn, candle_fn, save_fn = _load_chart_builder()
    signals = []

    if use_batch and universe:
        tickers = [s["ticker"] for s in universe]
        batch   = _batch_ohlcv_us(tickers)
        name_map = {s["ticker"]: s["name"] for s in universe}

        print(f"    배치 다운로드: {len(batch)}/{len(tickers)}개 수신")
        for ticker, df in batch.items():
            if len(df) < MIN_BARS:
                continue
            try:
                norm  = ribbon_fn(df)
                valid = norm.dropna()
                if len(valid) < 2:
                    continue
                prev_norm = float(valid.iloc[-2])
                curr_norm = float(valid.iloc[-1])
                if prev_norm < 0 and curr_norm >= 0:
                    name    = name_map.get(ticker, ticker)
                    candles = candle_fn(df, norm)
                    save_fn(ticker, "us", name, candles)
                    signals.append({
                        "ticker":    ticker,
                        "name":      name,
                        "market":    "us",
                        "prev_norm": round(prev_norm, 4),
                        "curr_norm": round(curr_norm, 4),
                    })
                    print(f"      ✓ {ticker}  {round(prev_norm,3)} → {round(curr_norm,3)}")
            except Exception as e:
                print(f"      ⚠ {ticker}: {e}")
        return signals

    # 개별 다운로드 (KR / Coin)
    for i, stock in enumerate(universe):
        ticker = stock["ticker"]
        market = stock["market"]
        print(f"    [{i+1}/{len(universe)}] {market.upper()} {ticker} ({stock['name'][:12]})...")
        sig = _scan_single(stock, fetch_fn, ribbon_fn, candle_fn, save_fn)
        if sig:
            signals.append(sig)
            print(f"      ✓ 신호 발생  {round(sig['prev_norm'],3)} → {round(sig['curr_norm'],3)}")
        time.sleep(0.2)

    return signals


# ── 메인 스캔 ─────────────────────────────────────────────────────────────────
def run_full_scan() -> dict:
    """전체 유니버스 스캔 후 결과를 저장합니다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*56}")
    print(f"  📡 Ribbon 스크리너 시작  {now}")
    print(f"{'='*56}")

    # ── 한국
    print("\n[1/3] 한국 유니버스 수집 중...")
    kr_universe = _get_kr_universe()
    print(f"  한국 스캔 ({len(kr_universe)}개)...")
    kr_signals = _scan_market(kr_universe, use_batch=False)
    print(f"  한국 신호: {len(kr_signals)}개")

    # ── 미국
    print("\n[2/3] 미국 유니버스 수집 중...")
    us_universe = _get_us_universe()
    print(f"  미국 배치 스캔 ({len(us_universe)}개)...")
    us_signals = _scan_market(us_universe, use_batch=True)
    print(f"  미국 신호: {len(us_signals)}개")

    # ── 코인
    print("\n[3/3] 코인 유니버스 수집 중...")
    coin_universe = _get_coin_universe()
    print(f"  코인 스캔 ({len(coin_universe)}개)...")
    coin_signals = _scan_market(coin_universe, use_batch=False)
    print(f"  코인 신호: {len(coin_signals)}개")

    # ── 저장
    result = {
        "updated_at": now,
        "summary": {
            "kr":   len(kr_signals),
            "us":   len(us_signals),
            "coin": len(coin_signals),
        },
        "kr":   kr_signals,
        "us":   us_signals,
        "coin": coin_signals,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = len(kr_signals) + len(us_signals) + len(coin_signals)
    print(f"\n  📡 완료: 총 {total}개 종목 신호 → {OUTPUT_PATH}")
    print(f"{'='*56}\n")
    return result
