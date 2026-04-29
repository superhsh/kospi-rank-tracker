"""
backfill.py  (네이버 금융 + FinanceDataReader 버전)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
최초 1회 실행 전용 — 과거 3개월치 시가총액 데이터를 구축합니다.

수집 방식:
  1) 네이버 금융에서 현재 시가총액 상위 100종목 + 상장주식수 조회
  2) FinanceDataReader로 각 종목의 과거 3개월 주가 조회
  3) 날짜별  시총 = 종가 × 상장주식수  계산 → JSON 저장

사용법:
    python backfill.py
    python backfill.py --months 3
    python backfill.py --start 20260126
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import os
import sys
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher import (
    build_historical_snapshots,
    fetch_top100_with_shares,
    get_available_dates,
    save_market_data,
    save_name_cache,
    load_name_cache,
)

MARKETS = ["KOSPI", "KOSDAQ"]


def parse_args():
    p = argparse.ArgumentParser(description="과거 데이터 백필")
    p.add_argument("--months", type=int, default=3,
                   help="수집할 과거 개월 수 (기본: 3)")
    p.add_argument("--start", type=str, default=None,
                   help="시작일 YYYYMMDD (지정 시 --months 무시)")
    return p.parse_args()


def main():
    args = parse_args()
    end_date   = datetime.today().strftime("%Y%m%d")
    start_date = (args.start if args.start
                  else (datetime.today() - timedelta(days=args.months * 31))
                       .strftime("%Y%m%d"))

    print(f"\n{'='*58}")
    print(f"  백필 시작 | 범위: {start_date} ~ {end_date}")
    print(f"  방식: 네이버 금융 현재 순위 × 과거 주가 (FinanceDataReader)")
    print(f"{'='*58}")

    name_cache = load_name_cache()

    for market in MARKETS:
        print(f"\n▶ [{market}] 현재 시가총액 상위 100 종목 수집 중...")
        top100 = fetch_top100_with_shares(market)

        if top100.empty:
            print(f"  ⚠ [{market}] 네이버 금융 데이터 수집 실패. 스킵합니다.")
            continue

        print(f"  ✓ [{market}] {len(top100)}개 종목 확인")
        for _, row in top100.iterrows():
            name_cache[row["ticker"]] = row["name"]

        # 이미 저장된 날짜는 건너뜀
        already_saved = set(get_available_dates(market))

        # 과거 주가로 날짜별 시총 계산
        snapshots = build_historical_snapshots(
            market, top100, start_date, end_date
        )

        saved = skipped = 0
        for date, df in snapshots.items():
            if date in already_saved:
                skipped += 1
                continue
            save_market_data(date, market, df)
            saved += 1

        print(f"\n  [{market}] 완료 — 저장: {saved}일  스킵(기존): {skipped}일")

    save_name_cache(name_cache)

    print(f"\n{'='*58}")
    print(f"  백필 완료! 이제 python run_daily.py 를 실행하세요.")
    print(f"{'='*58}\n")


if __name__ == "__main__":
    main()
