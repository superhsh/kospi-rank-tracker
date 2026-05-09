"""
backfill_midcap.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Russell 1000 하위 500종목(중형주) 과거 3개월치 데이터를 수집합니다.

원리:
  yfinance batch download로 과거 일별 종가를 받고,
  현재 시점의 발행주식수(shares outstanding)와 곱해 시총을 근사합니다.
  (역사적 발행주식수 변화를 반영하지 않지만 순위 비교에는 충분합니다)

실행:
    python backfill_midcap.py
    python backfill_midcap.py --months 3
    python backfill_midcap.py --refresh-universe   # 유니버스 재구성 후 백필
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher_midcap import (
    get_available_midcap_dates,
    get_midcap_universe,
    load_name_cache,
    save_midcap_data,
    save_name_cache,
)


def _get_shares_outstanding(tickers: list) -> dict:
    """현재 발행주식수를 yfinance fast_info로 수집합니다."""
    print(f"  발행주식수 수집 중 ({len(tickers)}종목)...")
    shares = {}
    for i, ticker in enumerate(tickers):
        try:
            info = yf.Ticker(ticker).fast_info
            s = getattr(info, "shares", None)
            if s and s > 0:
                shares[ticker] = float(s)
        except Exception:
            pass
        if (i + 1) % 50 == 0:
            print(f"    진행: {i+1}/{len(tickers)}")
            time.sleep(0.5)
    print(f"  ✓ 발행주식수 수집: {len(shares)}/{len(tickers)}개")
    return shares


def backfill_midcap(start_date: str, end_date: str,
                    universe: list, name_cache: dict):
    """과거 일별 종가 × 현재 발행주식수로 시총을 근사해 저장합니다."""

    available = set(get_available_midcap_dates())
    print(f"  기존 저장 날짜: {len(available)}개")

    # 저장이 필요한 날짜 계산 (주말 제외)
    need_dates = []
    dt = datetime.strptime(start_date, "%Y%m%d")
    end_dt = datetime.strptime(end_date, "%Y%m%d")
    while dt <= end_dt:
        if dt.weekday() < 5:  # 평일만
            d = dt.strftime("%Y%m%d")
            if d not in available:
                need_dates.append(d)
        dt += timedelta(days=1)

    if not need_dates:
        print(f"  모든 날짜에 데이터가 이미 있습니다.")
        return

    print(f"  백필 대상: {len(need_dates)}일 ({need_dates[0]} ~ {need_dates[-1]})")

    tickers = [d["ticker"] for d in universe]

    # ── 1. 발행주식수 수집 ────────────────────────────────────────────────────
    shares_map = _get_shares_outstanding(tickers)

    # ── 2. 과거 종가 일괄 다운로드 ───────────────────────────────────────────
    yf_start = (datetime.strptime(start_date, "%Y%m%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    yf_end   = (datetime.strptime(end_date,   "%Y%m%d") + timedelta(days=2)).strftime("%Y-%m-%d")

    print(f"\n  종가 다운로드 중 ({yf_start} ~ {yf_end}, 배치 50개)...")
    price_map = {}  # ticker → {date_str: close_price}

    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i: i + batch_size]
        batch_no = i // batch_size + 1
        total_batches = (len(tickers) - 1) // batch_size + 1
        print(f"  배치 {batch_no}/{total_batches} ({len(batch)}개)...")

        try:
            raw = yf.download(
                batch, start=yf_start, end=yf_end,
                progress=False, auto_adjust=True,
                group_by="ticker", threads=True,
            )
            # 단일 종목은 컬럼이 다름
            if len(batch) == 1:
                ticker = batch[0]
                if "Close" in raw.columns:
                    s = raw["Close"].dropna()
                    price_map[ticker] = {
                        dt.strftime("%Y%m%d"): float(v)
                        for dt, v in s.items()
                    }
            else:
                for ticker in batch:
                    try:
                        s = raw[ticker]["Close"].dropna()
                        price_map[ticker] = {
                            dt.strftime("%Y%m%d"): float(v)
                            for dt, v in s.items()
                        }
                    except (KeyError, TypeError):
                        pass
        except Exception as e:
            print(f"    ⚠ 배치 다운로드 오류: {e}")

        time.sleep(1.0)

    print(f"  ✓ 종가 수집: {len(price_map)}종목")

    # ── 3. 날짜별 시총 계산 및 저장 ─────────────────────────────────────────
    saved = 0
    for date in need_dates:
        records = []
        for ticker in tickers:
            price  = price_map.get(ticker, {}).get(date)
            shares = shares_map.get(ticker)
            if price and shares and price > 0 and shares > 0:
                mcap = price * shares
                name = name_cache.get(ticker, ticker)
                records.append({
                    "ticker":     ticker,
                    "name":       name,
                    "market_cap": float(mcap),
                })

        if not records:
            print(f"    [{date}] 데이터 없음 — 스킵")
            continue

        df = (
            pd.DataFrame(records)
            .sort_values("market_cap", ascending=False)
            .reset_index(drop=True)
        )
        df["rank"] = range(1, len(df) + 1)
        df["rank"] = df["rank"].astype(int)
        df = df[["rank", "ticker", "name", "market_cap"]]

        save_midcap_data(date, df)
        saved += 1
        print(f"    [{date}] ✓ {len(df)}종목 저장")

    print(f"\n  백필 완료: {saved}/{len(need_dates)}일 저장")


def main():
    parser = argparse.ArgumentParser(description="중형주 과거 데이터 백필")
    parser.add_argument("--months", type=int, default=3,
                        help="백필 기간 (개월, 기본: 3)")
    parser.add_argument("--refresh-universe", action="store_true",
                        help="유니버스 캐시 강제 갱신 후 백필")
    args = parser.parse_args()

    today    = datetime.now()
    end_date = today.strftime("%Y%m%d")
    start_dt = today.replace(day=1)
    for _ in range(args.months - 1):
        start_dt = (start_dt - timedelta(days=1)).replace(day=1)
    start_date = start_dt.strftime("%Y%m%d")

    print(f"\n{'='*54}")
    print(f"  중형주 백필 시작: {start_date} ~ {end_date}")
    print(f"{'='*54}")

    name_cache = load_name_cache()

    print("\n  유니버스 로드 중...")
    universe = get_midcap_universe(name_cache, force_refresh=args.refresh_universe)
    if not universe:
        print("  ⚠ 유니버스를 가져오지 못했습니다. 종료.")
        sys.exit(1)
    print(f"  유니버스: {len(universe)}종목")

    backfill_midcap(start_date, end_date, universe, name_cache)
    save_name_cache(name_cache)

    print(f"\n{'='*54}")
    print(f"  백필 완료!")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
