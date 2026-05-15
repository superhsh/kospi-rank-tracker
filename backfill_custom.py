"""
backfill_custom.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
관심종목의 과거 30 거래일치 시총 데이터를 채웁니다.

원리:
  yfinance batch download로 과거 일별 종가를 받고,
  현재 발행주식수(shares outstanding)와 곱해 시총을 근사합니다.

실행: python backfill_custom.py
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

from scripts.fetcher_custom import (
    CURRENCY,
    MARKET_SUFFIX,
    fmt_market_cap,
    get_available_custom_dates,
    load_custom_watchlist,
    save_daily_custom,
)

CALENDAR_DAYS = 60   # 60 캘린더일 = 약 30 거래일


def backfill_market_group(market: str, stock_list: list[dict],
                          start_dt: datetime, end_dt: datetime,
                          skip_dates: set[str]) -> dict[str, list[dict]]:
    """
    단일 시장 그룹의 과거 종가 × 발행주식수로 시총을 근사합니다.
    반환: {date_str: [record, ...]}
    """
    suffix   = MARKET_SUFFIX.get(market, "")
    currency = CURRENCY.get(market, "USD")

    yf_tickers      = [s["ticker"] + suffix for s in stock_list]
    ticker_to_stock = {s["ticker"] + suffix: s for s in stock_list}

    print(f"\n  [{market.upper()}] {len(yf_tickers)}개 종목 과거 종가 다운로드...")

    # ── 과거 종가 다운로드 ─────────────────────────────────────────────────
    try:
        prices_raw = yf.download(
            yf_tickers,
            start=start_dt.strftime("%Y-%m-%d"),
            end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        print(f"  ⚠ 다운로드 오류: {e}")
        return {}

    if prices_raw.empty:
        print(f"  ⚠ 가격 데이터 없음")
        return {}

    # Close 패널 추출
    try:
        close_raw = prices_raw["Close"]
        if isinstance(close_raw, pd.Series):
            close_df = close_raw.to_frame(name=yf_tickers[0])
        else:
            close_df = close_raw
    except Exception as e:
        print(f"  ⚠ Close 패널 추출 실패: {e}")
        return {}

    print(f"  가격 데이터: {len(close_df)}일 × {len(close_df.columns)}종목")

    # ── 발행주식수 수집 ────────────────────────────────────────────────────
    print(f"  발행주식수 수집 중...")
    shares_map: dict[str, float] = {}
    for yft in yf_tickers:
        try:
            fi     = yf.Ticker(yft).fast_info
            shares = getattr(fi, "shares", None)
            if shares and shares > 0:
                shares_map[yft] = float(shares)
        except Exception:
            pass
        time.sleep(0.3)

    print(f"  발행주식수 확보: {len(shares_map)}/{len(yf_tickers)}개")

    col_set = set(close_df.columns.tolist())

    # ── 날짜별 레코드 생성 ─────────────────────────────────────────────────
    result: dict[str, list[dict]] = {}

    for date_idx in close_df.index:
        date_str = date_idx.strftime("%Y%m%d")
        if date_str in skip_dates:
            continue   # 이미 저장된 날짜는 건너뜀

        day_records = []
        for yft, s in ticker_to_stock.items():
            if yft not in shares_map or yft not in col_set:
                continue
            try:
                price = float(close_df.loc[date_idx, yft])
            except Exception:
                continue
            if pd.isna(price) or price <= 0:
                continue

            mc     = price * shares_map[yft]
            mc_str = fmt_market_cap(mc, currency)
            day_records.append({
                "ticker":         s["ticker"],
                "name":           s.get("name", s["ticker"]),
                "market":         market,
                "currency":       currency,
                "market_cap":     mc,
                "market_cap_str": mc_str,
            })

        if day_records:
            result[date_str] = result.get(date_str, []) + day_records

    return result


def main():
    today    = datetime.now()
    start_dt = today - timedelta(days=CALENDAR_DAYS)
    end_dt   = today - timedelta(days=1)   # 오늘은 실시간 워크플로우가 담당

    print(f"\n{'='*54}")
    print(f"  관심종목 백필 — {start_dt.strftime('%Y%m%d')} ~ {end_dt.strftime('%Y%m%d')}")
    print(f"{'='*54}")

    stocks = load_custom_watchlist()
    if not stocks:
        print("  관심종목이 없습니다. 브라우저에서 종목을 추가하세요.")
        return

    print(f"  관심종목: {len(stocks)}개")

    skip_dates = set(get_available_custom_dates())
    print(f"  기존 저장 날짜: {len(skip_dates)}개 → 건너뜀")

    # ── 시장별 그룹핑 ─────────────────────────────────────────────────────
    by_market: dict[str, list[dict]] = {}
    for s in stocks:
        m = s.get("market", "us")
        by_market.setdefault(m, []).append(s)

    # ── 시장별 백필 ───────────────────────────────────────────────────────
    all_by_date: dict[str, list[dict]] = {}

    for market, stock_list in by_market.items():
        result = backfill_market_group(
            market, stock_list, start_dt, end_dt, skip_dates
        )
        for date_str, records in result.items():
            all_by_date.setdefault(date_str, []).extend(records)

    # ── 날짜별 저장 ───────────────────────────────────────────────────────
    saved = 0
    for date_str in sorted(all_by_date.keys()):
        records = all_by_date[date_str]
        if not records:
            continue
        path = save_daily_custom(date_str, records)
        saved += 1
        print(f"  {date_str}: {len(records)}개 종목 → {path}")

    print(f"\n{'='*54}")
    print(f"  백필 완료: {saved}일 저장")
    print(f"  이제 'python run_daily_custom.py --skip-fetch'로 리포트를 재생성하세요.")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
