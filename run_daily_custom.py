"""
run_daily_custom.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
관심종목의 시총 변동률(일별/주별/월별)을 계산하고
data/report_custom.json을 생성합니다.

실행:
    python run_daily_custom.py                   # 오늘 날짜
    python run_daily_custom.py --date 20260514   # 특정 날짜
    python run_daily_custom.py --skip-fetch      # 수집 생략 (기존 파일 사용)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import json
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher_custom import (
    fetch_daily_custom,
    save_daily_custom,
    load_daily_custom,
    get_available_custom_dates,
)

REPORT_PATH = os.path.join(BASE_DIR, "data", "report_custom.json")

# 비교 기준: 몇 거래일치 이전 데이터를 사용할지
PERIOD_BACK = {
    "daily":   1,    # 전일 (1거래일 전)
    "weekly":  5,    # 약 1주 전 (5거래일)
    "monthly": 21,   # 약 1개월 전 (21거래일)
}


# ── 비교 날짜 탐색 ────────────────────────────────────────────────────────────
def find_prev_date(current: str, available: list[str], n: int) -> str | None:
    """
    available 날짜 목록에서 current 기준으로 n번째 이전 날짜를 찾습니다.
    current가 available에 없으면 current 미만의 가장 최근 날짜를 기준으로 탐색합니다.
    """
    if current in available:
        idx = available.index(current)
    else:
        earlier = [d for d in available if d < current]
        if not earlier:
            return None
        # current 직전 날짜 기준 탐색
        available = earlier
        idx = len(earlier)

    target = idx - n
    if target < 0:
        return None
    return available[target]


# ── 변동률 계산 ───────────────────────────────────────────────────────────────
def compute_change(current_records: list[dict],
                   prev_records:    list[dict]) -> list[dict]:
    """
    현재와 이전 시총을 비교해 변동률을 계산합니다.

    반환: [{"ticker", "name", "market", "currency",
             "market_cap", "market_cap_str",
             "prev_market_cap", "prev_market_cap_str",
             "change_pct"}, ...]
    정렬: change_pct 내림차순
    """
    prev_map = {r["ticker"]: r for r in prev_records}
    result   = []

    for rec in current_records:
        prev = prev_map.get(rec["ticker"])
        if not prev or prev.get("market_cap", 0) <= 0:
            continue

        change_pct = (
            (rec["market_cap"] - prev["market_cap"]) / prev["market_cap"] * 100
        )
        result.append({
            "ticker":              rec["ticker"],
            "name":                rec["name"],
            "market":              rec["market"],
            "currency":            rec["currency"],
            "market_cap":          rec["market_cap"],
            "market_cap_str":      rec["market_cap_str"],
            "prev_market_cap":     prev["market_cap"],
            "prev_market_cap_str": prev["market_cap_str"],
            "change_pct":          round(change_pct, 2),
        })

    result.sort(key=lambda x: x["change_pct"], reverse=True)
    return result


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="관심종목 시총 변동률 계산")
    parser.add_argument("--date", default=None,
                        help="날짜 (YYYYMMDD, 기본: 오늘)")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="시총 수집 생략 — 기존 저장 파일 사용")
    args = parser.parse_args()

    today = args.date or datetime.now().strftime("%Y%m%d")
    dt    = datetime.strptime(today, "%Y%m%d")

    print(f"\n{'='*54}")
    print(f"  관심종목 시총 변동률 계산 — {today}")
    print(f"{'='*54}")

    # 주말 스킵 (수집 단계만)
    if dt.weekday() >= 5 and not args.skip_fetch:
        print(f"  ⚠ {today}은 주말입니다. 시총 수집 스킵.")
        sys.exit(0)

    # ── 오늘 시총 수집 또는 기존 파일 사용 ───────────────────────────────────
    if not args.skip_fetch:
        current = fetch_daily_custom(today)
        if current:
            path = save_daily_custom(today, current)
            print(f"  저장: {path}")
        else:
            print("  ⚠ 수집 결과 없음 — 기존 파일 확인 중...")
            current = load_daily_custom(today)
    else:
        current = load_daily_custom(today)

    if not current:
        print(f"  ⚠ {today} 데이터 없음 — 종료")
        sys.exit(1)

    available = get_available_custom_dates()

    # ── 기간별 변동률 계산 ─────────────────────────────────────────────────────
    report = {
        "updated_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "current_date": today,
    }

    for period, n_back in PERIOD_BACK.items():
        prev_date = find_prev_date(today, available, n_back)
        if not prev_date:
            report[period] = {"available": False, "prev_date": None, "items": []}
            print(f"  [{period}] 비교 데이터 부족 (최소 {n_back}일치 필요)")
            continue

        prev = load_daily_custom(prev_date)
        if not prev:
            report[period] = {"available": False, "prev_date": prev_date, "items": []}
            print(f"  [{period}] {prev_date} 데이터 없음")
            continue

        items = compute_change(current, prev)
        report[period] = {
            "available": True,
            "prev_date": prev_date,
            "items":     items,
        }

        print(f"  [{period}] {prev_date} → {today}  ({len(items)}개)")
        for it in items[:5]:
            sign = "+" if it["change_pct"] >= 0 else ""
            print(f"    {it['ticker']:10}  {it['name'][:14]:14}  {sign}{it['change_pct']:.2f}%")

    # ── 리포트 저장 ───────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n  리포트 저장: {REPORT_PATH}")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
