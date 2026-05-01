"""
run_daily_us.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
S&P 500 / NASDAQ 100 시총 순위 데이터를 수집하고
data/report_us.json 을 생성합니다.

실행:
    python run_daily_us.py
    python run_daily_us.py --date 20250425
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher_us import (
    fetch_market_caps,
    get_available_us_dates,
    get_nasdaq100_tickers,
    get_sp500_tickers,
    load_name_cache_us,
    load_us_data,
    refresh_names,
    save_name_cache_us,
    save_us_data,
)
from scripts.processor_generic import (
    build_history_generic,
    compute_top5_generic,
    find_prev_date,
)

US_MARKETS = {
    "sp500":     "S&P 500",
    "nasdaq100": "NASDAQ 100",
}
PERIODS = ["daily", "weekly", "monthly"]

REPORT_PATH = os.path.join(BASE_DIR, "data", "report_us.json")

PERIOD_CUTOFF_DAYS = {"daily": 30, "weekly": 91, "monthly": 0}


def _get_tickers(market_key: str) -> list:
    if market_key == "sp500":
        return get_sp500_tickers()
    return get_nasdaq100_tickers()


def _period_load_fn(market_key: str):
    def load(date: str):
        return load_us_data(date, market_key)
    return load


def _apply_name_cache(df: pd.DataFrame, name_cache: dict) -> pd.DataFrame:
    """name 컬럼을 name_cache로 보정합니다 (name=ticker 항목 교정)."""
    if df.empty or not name_cache:
        return df
    df = df.copy()
    df["name"] = df["ticker"].apply(lambda t: name_cache.get(t, t))
    return df


def build_us_report(today: str, name_cache: dict) -> dict:
    report = {
        "updated_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "current_date": today,
    }

    for market_key, market_name in US_MARKETS.items():
        print(f"\n  [{market_name}] 처리 중...")
        available_dates = get_available_us_dates(market_key)

        # ── 오늘 데이터 수집 또는 로드 ─────────────────────────────────────
        if today in available_dates:
            print(f"  [{market_name}] 오늘 데이터 이미 있음 — 로드")
            current_df = load_us_data(today, market_key)
            # name=ticker로 잘못 저장된 항목을 캐시로 보정 후 재저장
            current_df = _apply_name_cache(current_df, name_cache)
            save_us_data(today, market_key, current_df)
        else:
            print(f"  [{market_name}] 티커 목록 수집 중...")
            tickers = _get_tickers(market_key)
            if not tickers:
                print(f"  [{market_name}] ⚠ 티커 없음")
                report[market_key] = {}
                continue

            print(f"  [{market_name}] {len(tickers)}개 종목 시총 수집 중...")
            current_df = fetch_market_caps(tickers, name_cache)

            if current_df.empty:
                print(f"  [{market_name}] ⚠ 데이터 없음")
                report[market_key] = {}
                continue

            save_us_data(today, market_key, current_df)
            available_dates = get_available_us_dates(market_key)
            print(f"  [{market_name}] ✓ {len(current_df)}개 종목 저장")

        load_fn = _period_load_fn(market_key)

        # ── 기간별 Top5 + 히스토리 ─────────────────────────────────────────
        market_data = {}
        for period in PERIODS:
            prev_date = find_prev_date(today, period, available_dates)

            if prev_date is None:
                market_data[period] = {
                    "available": False, "prev_date": None, "top5": []
                }
                continue

            prev_df = load_us_data(prev_date, market_key)
            result  = compute_top5_generic(current_df, prev_df, currency="USD")
            result["prev_date"] = prev_date

            # ── 일별 폴백: 장 개장 전 수집으로 변동 없으면
            #    직전 거래일 vs 그 전날로 비교 ───────────────────────────────
            if period == "daily" and not result["available"]:
                hist = [d for d in available_dates if d < today]
                if len(hist) >= 2:
                    fb_cur_date  = hist[-1]
                    fb_candidates = [d for d in available_dates if d < fb_cur_date]
                    fb_prev_date  = find_prev_date(fb_cur_date, "daily", fb_candidates)
                    if fb_prev_date:
                        fb_cur_df  = _apply_name_cache(
                            load_us_data(fb_cur_date, market_key), name_cache)
                        fb_prev_df = load_us_data(fb_prev_date, market_key)
                        fb_result  = compute_top5_generic(
                            fb_cur_df, fb_prev_df, currency="USD")
                        if fb_result["available"]:
                            result    = fb_result
                            prev_date = fb_prev_date
                            result["prev_date"] = fb_prev_date
                            print(f"    [daily] 폴백 → {fb_cur_date} vs {fb_prev_date}")

            if result["available"] and result["top5"]:
                tickers_top5 = [s["ticker"] for s in result["top5"]]
                names_top5   = {s["ticker"]: s["name"] for s in result["top5"]}

                # 기간별 날짜 범위
                days = PERIOD_CUTOFF_DAYS[period]
                if days > 0:
                    cutoff = (
                        datetime.strptime(today, "%Y%m%d") - timedelta(days=days)
                    ).strftime("%Y%m%d")
                    hist_dates = [d for d in available_dates
                                  if cutoff <= d <= today]
                else:
                    hist_dates = [d for d in available_dates if d <= today]

                timeline = build_history_generic(
                    load_fn, hist_dates, tickers_top5, period
                )
                result["history"] = {
                    "tickers":  tickers_top5,
                    "names":    names_top5,
                    "timeline": timeline,
                }

            market_data[period] = result
            status = "✓" if result["available"] else "✗"
            n = len(result.get("top5", []))
            print(f"    [{period}] {status} Top{n}  기준일: {prev_date}")

        report[market_key] = market_data

    return report


def main():
    parser = argparse.ArgumentParser(description="미국 시장 데이터 수집 및 리포트 생성")
    parser.add_argument("--date", type=str, default=None,
                        help="수집 날짜 YYYYMMDD (기본: 오늘)")
    args  = parser.parse_args()
    today = args.date or datetime.now().strftime("%Y%m%d")

    print(f"\n{'='*54}")
    print(f"  미국 시장 업데이트 시작 — {today}")
    print(f"{'='*54}")

    name_cache = load_name_cache_us()

    # 이름이 티커로 잘못 저장된 항목(backfill 오류) 재조회
    fixed = refresh_names(name_cache)
    if fixed:
        save_name_cache_us(name_cache)

    report = build_us_report(today, name_cache)
    save_name_cache_us(name_cache)

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False)

    print(f"\n{'='*54}")
    print(f"  완료! → {REPORT_PATH}")
    for mk in US_MARKETS:
        for p in PERIODS:
            n = len(report.get(mk, {}).get(p, {}).get("top5", []))
            if n:
                print(f"  {US_MARKETS[mk]} {p}: Top{n}")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
