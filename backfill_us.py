"""
backfill_us.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
S&P 500 / NASDAQ 100 과거 3개월치 데이터를 yfinance로 수집합니다.

원리:
  yfinance batch download로 과거 일별 종가를 받고,
  현재 시점의 발행주식수(shares outstanding)와 곱해 시총을 근사합니다.
  (역사적 발행주식수 변화를 정확히 반영하진 않지만 순위 비교에는 충분합니다)

실행: python backfill_us.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher_us import (
    get_available_us_dates,
    get_nasdaq100_tickers,
    get_sp500_tickers,
    load_name_cache_us,
    save_name_cache_us,
    save_us_data,
)

US_MARKETS = {
    "sp500":     ("S&P 500",    get_sp500_tickers),
    "nasdaq100": ("NASDAQ 100", get_nasdaq100_tickers),
}


def backfill_market(market_key: str, market_name: str,
                    get_tickers_fn, start_date: str, end_date: str,
                    name_cache: dict):
    """과거 일별 종가 × 현재 발행주식수로 시총을 근사해 저장합니다."""

    print(f"\n  [{market_name}] 백필 시작: {start_date} ~ {end_date}")

    available = set(get_available_us_dates(market_key))

    tickers = get_tickers_fn()
    if not tickers:
        print(f"  [{market_name}] ⚠ 티커 없음")
        return

    print(f"  [{market_name}] {len(tickers)}개 종목 과거 종가 다운로드 중...")
    start_dt = datetime.strptime(start_date, "%Y%m%d")
    end_dt   = datetime.strptime(end_date,   "%Y%m%d") + timedelta(days=1)

    try:
        prices_raw = yf.download(
            tickers,
            start=start_dt.strftime("%Y-%m-%d"),
            end=end_dt.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
            group_by="ticker",
        )
    except Exception as e:
        print(f"  [{market_name}] ⚠ 다운로드 오류: {e}")
        return

    if prices_raw.empty:
        print(f"  [{market_name}] ⚠ 가격 데이터 없음")
        return

    # ── Close 패널 추출 ────────────────────────────────────────────────────
    try:
        if isinstance(prices_raw.columns, pd.MultiIndex):
            # group_by="ticker" → (ticker, OHLCV)
            close_panel = prices_raw.xs("Close", axis=1, level=1)
        else:
            close_panel = prices_raw[["Close"]]
    except Exception as e:
        print(f"  [{market_name}] ⚠ Close 패널 추출 실패: {e}")
        return

    # ── 발행주식수 수집 ────────────────────────────────────────────────────
    print(f"  [{market_name}] 발행주식수 수집 중 (약 {len(tickers)}개)...")
    shares_map = {}
    for i, ticker in enumerate(tickers):
        try:
            t_obj  = yf.Ticker(ticker)
            fi     = t_obj.fast_info
            shares = getattr(fi, "shares", None)
            if shares and shares > 0:
                shares_map[ticker] = float(shares)

                if ticker not in name_cache:
                    try:
                        name = (getattr(fi, "long_name", None)
                                or getattr(fi, "shortName", None)
                                or ticker)
                    except Exception:
                        name = ticker
                    name_cache[ticker] = name

        except Exception:
            pass

        if (i + 1) % 50 == 0:
            print(f"    ... {i+1}/{len(tickers)}")
            time.sleep(0.3)

    print(f"  [{market_name}] 발행주식수 확보: {len(shares_map)}개")

    # ── 날짜별 저장 ────────────────────────────────────────────────────────
    saved = 0
    for date_idx in close_panel.index:
        date_str = date_idx.strftime("%Y%m%d")
        if date_str in available:
            continue
        if not (start_date <= date_str <= end_date):
            continue

        records = []
        for ticker in tickers:
            if ticker not in shares_map:
                continue
            if ticker not in close_panel.columns:
                continue
            try:
                price = float(close_panel.loc[date_idx, ticker])
            except Exception:
                continue
            if pd.isna(price) or price <= 0:
                continue

            mcap = price * shares_map[ticker]
            records.append({
                "ticker":     ticker,
                "name":       name_cache.get(ticker, ticker),
                "market_cap": mcap,
            })

        if not records:
            continue

        df = (
            pd.DataFrame(records)
            .sort_values("market_cap", ascending=False)
            .reset_index(drop=True)
        )
        df["rank"] = range(1, len(df) + 1)
        df["rank"] = df["rank"].astype(int)
        df = df[["rank", "ticker", "name", "market_cap"]]

        save_us_data(date_str, market_key, df)
        saved += 1
        print(f"    {date_str}: {len(df)}개 종목 저장")

    print(f"  [{market_name}] 완료 — {saved}일 저장")


def main():
    end_date   = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=95)).strftime("%Y%m%d")

    print(f"\n{'='*54}")
    print(f"  미국 시장 백필 — {start_date} ~ {end_date}")
    print(f"{'='*54}")

    name_cache = load_name_cache_us()

    for market_key, (market_name, get_fn) in US_MARKETS.items():
        backfill_market(market_key, market_name, get_fn,
                        start_date, end_date, name_cache)

    save_name_cache_us(name_cache)

    print(f"\n{'='*54}")
    print("  미국 백필 완료!")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
