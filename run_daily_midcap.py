"""
run_daily_midcap.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Russell 1000 하위 500종목(중형주) 시총 순위 데이터를 수집하고
data/report_midcap.json 을 생성합니다.

첫 실행 시 유니버스(500종목) 구성에 약 20분 소요됩니다.
이후 일별 업데이트는 약 3~5분 소요됩니다.

실행:
    python run_daily_midcap.py
    python run_daily_midcap.py --date 20250425
    python run_daily_midcap.py --refresh-universe   # 유니버스 강제 갱신
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

from scripts.fetcher_midcap import (
    fetch_midcap_data,
    get_available_midcap_dates,
    get_midcap_universe,
    load_midcap_data,
    load_name_cache,
    save_midcap_data,
    save_name_cache,
)
from scripts.processor_generic import (
    build_history_generic,
    compute_streak_top5_generic,
    compute_top5_generic,
    find_prev_date,
)

REPORT_PATH = os.path.join(BASE_DIR, "data", "report_midcap.json")
PERIODS = ["daily", "weekly", "monthly"]
PERIOD_CUTOFF_DAYS = {"daily": 30, "weekly": 91, "monthly": 0}


def _load_fn(date: str) -> pd.DataFrame:
    return load_midcap_data(date)


def build_midcap_report(today: str, name_cache: dict,
                        force_refresh: bool = False) -> dict:
    report = {
        "updated_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "current_date": today,
    }

    # ── 유니버스 로드 (캐시 또는 갱신) ───────────────────────────────────────
    print("\n  유니버스 로드 중...")
    universe = get_midcap_universe(name_cache, force_refresh=force_refresh)
    if not universe:
        print("  ⚠ 유니버스를 가져오지 못했습니다.")
        report["midcap"] = {}
        return report
    print(f"  유니버스: {len(universe)}종목")

    # ── 오늘 데이터 수집 또는 로드 ────────────────────────────────────────────
    available_dates = get_available_midcap_dates()

    if today in available_dates:
        print(f"\n  [중형주] 오늘 데이터 이미 있음 — 로드")
        current_df = load_midcap_data(today)
    else:
        print(f"\n  [중형주] 시총 데이터 수집 중...")
        current_df = fetch_midcap_data(universe, name_cache)

        if current_df.empty:
            print(f"  ⚠ 데이터 수집 실패")
            report["midcap"] = {}
            return report

        save_midcap_data(today, current_df)
        available_dates = get_available_midcap_dates()
        print(f"  ✓ {len(current_df)}종목 저장")

    # ── 기간별 Top5 + 히스토리 ────────────────────────────────────────────────
    market_data = {}
    for period in PERIODS:
        prev_date = find_prev_date(today, period, available_dates)

        if prev_date is None:
            market_data[period] = {
                "available": False, "prev_date": None, "top5": []
            }
            continue

        prev_df = load_midcap_data(prev_date)
        result  = compute_top5_generic(current_df, prev_df, currency="USD")
        result["prev_date"] = prev_date

        # ── 일별 폴백: 오늘 변동 없으면 직전 거래일 vs 그 전날 비교 ─────────
        if period == "daily" and not result["available"]:
            hist = [d for d in available_dates if d < today]
            if len(hist) >= 2:
                fb_cur_date      = hist[-1]
                fb_candidates    = [d for d in available_dates if d < fb_cur_date]
                fb_prev_date     = find_prev_date(fb_cur_date, "daily", fb_candidates)
                if fb_prev_date:
                    fb_cur_df    = load_midcap_data(fb_cur_date)
                    fb_prev_df   = load_midcap_data(fb_prev_date)
                    fb_result    = compute_top5_generic(
                        fb_cur_df, fb_prev_df, currency="USD")
                    if fb_result["available"]:
                        result    = fb_result
                        prev_date = fb_prev_date
                        result["prev_date"] = fb_prev_date
                        print(f"    [daily] 폴백 → {fb_cur_date} vs {fb_prev_date}")

        if result["available"] and result["top5"]:
            tickers_top5 = [s["ticker"] for s in result["top5"]]
            names_top5   = {s["ticker"]: s["name"] for s in result["top5"]}

            days = PERIOD_CUTOFF_DAYS[period]
            if days > 0:
                cutoff = (
                    datetime.strptime(today, "%Y%m%d") - timedelta(days=days)
                ).strftime("%Y%m%d")
                hist_dates = [d for d in available_dates if cutoff <= d <= today]
            else:
                hist_dates = [d for d in available_dates if d <= today]

            timeline = build_history_generic(_load_fn, hist_dates, tickers_top5, period)
            result["history"] = {
                "tickers":  tickers_top5,
                "names":    names_top5,
                "timeline": timeline,
            }

        market_data[period] = result
        status = "✓" if result["available"] else "✗"
        n = len(result.get("top5", []))
        print(f"    [{period}] {status} Top{n}  기준일: {prev_date}")

    # ── 연속 순위 상승 종목 ───────────────────────────────────────────────────
    streak, streak_mode = compute_streak_top5_generic(
        _load_fn, available_dates, today, currency="USD"
    )
    market_data["streak"]      = streak
    market_data["streak_mode"] = streak_mode
    if streak:
        mode_label = "연속 상승" if streak_mode == "streak" else "5일 중 3회↑"
        print(f"    [streak] {mode_label} {len(streak)}개 종목")
        tickers  = [s["ticker"] for s in streak]
        names    = {s["ticker"]: s["name"] for s in streak}
        cutoff   = (
            datetime.strptime(today, "%Y%m%d") - timedelta(days=30)
        ).strftime("%Y%m%d")
        hdates   = [d for d in available_dates if cutoff <= d <= today]
        timeline = build_history_generic(_load_fn, hdates, tickers, "daily")
        market_data["streak_history"] = {
            "tickers":  tickers,
            "names":    names,
            "timeline": timeline,
        }
    else:
        market_data["streak_history"] = {}

    report["midcap"] = market_data
    return report


def main():
    parser = argparse.ArgumentParser(description="중형주 시장 데이터 수집 및 리포트 생성")
    parser.add_argument("--date", type=str, default=None,
                        help="수집 날짜 YYYYMMDD (기본: 오늘)")
    parser.add_argument("--refresh-universe", action="store_true",
                        help="유니버스 캐시 강제 갱신 (약 20분 소요)")
    args  = parser.parse_args()
    today = args.date or datetime.now().strftime("%Y%m%d")

    print(f"\n{'='*54}")
    print(f"  중형주 업데이트 시작 — {today}")
    print(f"{'='*54}")

    # 주말 스킵 (NYSE 휴장)
    dt = datetime.strptime(today, "%Y%m%d")
    if dt.weekday() >= 5:
        print(f"  ⚠ {today}은 주말입니다. 중형주 업데이트 스킵.")
        sys.exit(0)

    name_cache = load_name_cache()

    report = build_midcap_report(today, name_cache,
                                 force_refresh=args.refresh_universe)
    save_name_cache(name_cache)

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False)

    print(f"\n{'='*54}")
    print(f"  완료! → {REPORT_PATH}")
    for p in ["daily", "weekly", "monthly"]:
        n = len(report.get("midcap", {}).get(p, {}).get("top5", []))
        if n:
            print(f"  중형주 {p}: Top{n}")
    streak = report.get("midcap", {}).get("streak", [])
    if streak:
        print(f"  중형주 streak: {len(streak)}개 종목")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
