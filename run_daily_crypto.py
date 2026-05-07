"""
run_daily_crypto.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CoinGecko에서 상위 100개 암호화폐 시총 데이터를 수집하고
data/report_crypto.json 을 생성합니다.

실행:
    python run_daily_crypto.py
    python run_daily_crypto.py --date 20250425
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher_crypto import (
    fetch_crypto_top100,
    get_available_crypto_dates,
    load_crypto_data,
    save_crypto_data,
)
from scripts.processor_generic import (
    build_history_generic,
    compute_streak_top5_generic,
    compute_top5_generic,
    find_prev_date,
)

PERIODS = ["daily", "weekly", "monthly"]
REPORT_PATH = os.path.join(BASE_DIR, "data", "report_crypto.json")

PERIOD_CUTOFF_DAYS = {"daily": 30, "weekly": 91, "monthly": 0}


def build_crypto_report(today: str) -> dict:
    report = {
        "updated_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "current_date": today,
    }

    available_dates = get_available_crypto_dates()

    # ── 오늘 데이터 수집 또는 로드 ──────────────────────────────────────────
    if today in available_dates:
        print("  오늘 코인 데이터 이미 있음 — 로드")
        current_df = load_crypto_data(today)
    else:
        print("  코인 시총 Top 100 수집 중...")
        current_df = fetch_crypto_top100()

        if current_df.empty:
            print("  ⚠ 코인 데이터 없음")
            report["coin"] = {}
            return report

        save_crypto_data(today, current_df)
        available_dates = get_available_crypto_dates()
        print(f"  ✓ {len(current_df)}개 코인 저장")

    # ── 기간별 Top5 + 히스토리 ───────────────────────────────────────────────
    coin_data = {}
    for period in PERIODS:
        prev_date = find_prev_date(today, period, available_dates)

        if prev_date is None:
            coin_data[period] = {
                "available": False, "prev_date": None, "top5": []
            }
            continue

        prev_df = load_crypto_data(prev_date)

        # 이전 데이터가 너무 적으면(429 오류로 부분 저장) 비교 생략
        if len(prev_df) < 20:
            print(f"    [{period}] ⚠ 이전 데이터 부족 ({len(prev_df)}개) — backfill_crypto.py 재실행 필요")
            coin_data[period] = {"available": False, "prev_date": prev_date, "top5": []}
            continue

        result  = compute_top5_generic(current_df, prev_df, currency="USD")
        result["prev_date"] = prev_date

        if result["available"] and result["top5"]:
            tickers_top5 = [s["ticker"] for s in result["top5"]]
            names_top5   = {s["ticker"]: s["name"] for s in result["top5"]}

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
                load_crypto_data, hist_dates, tickers_top5, period
            )
            result["history"] = {
                "tickers":  tickers_top5,
                "names":    names_top5,
                "timeline": timeline,
            }

        coin_data[period] = result
        status = "✓" if result["available"] else "✗"
        n = len(result.get("top5", []))
        print(f"    [{period}] {status} Top{n}  기준일: {prev_date}")

    # ── 연속 순위 상승 종목 ──────────────────────────────────────────────────
    streak = compute_streak_top5_generic(
        load_crypto_data, available_dates, today, currency="USD"
    )
    coin_data["streak"] = streak
    if streak:
        print(f"    [streak] 연속 상승 {len(streak)}개 종목")
        tickers  = [s["ticker"] for s in streak]
        names    = {s["ticker"]: s["name"] for s in streak}
        cutoff   = (datetime.strptime(today, "%Y%m%d") - timedelta(days=30)).strftime("%Y%m%d")
        hdates   = [d for d in available_dates if cutoff <= d <= today]
        timeline = build_history_generic(load_crypto_data, hdates, tickers, "daily")
        coin_data["streak_history"] = {"tickers": tickers, "names": names, "timeline": timeline}
    else:
        coin_data["streak_history"] = {}

    report["coin"] = coin_data
    return report


def main():
    parser = argparse.ArgumentParser(description="코인 데이터 수집 및 리포트 생성")
    parser.add_argument("--date", type=str, default=None,
                        help="수집 날짜 YYYYMMDD (기본: 오늘)")
    args  = parser.parse_args()
    today = args.date or datetime.now().strftime("%Y%m%d")

    print(f"\n{'='*54}")
    print(f"  코인 시장 업데이트 시작 — {today}")
    print(f"{'='*54}\n")

    report = build_crypto_report(today)

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False)

    print(f"\n{'='*54}")
    print(f"  완료! → {REPORT_PATH}")
    for p in PERIODS:
        n = len(report.get("coin", {}).get(p, {}).get("top5", []))
        if n:
            print(f"  코인 {p}: Top{n}")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
