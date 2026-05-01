"""
backfill_crypto.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CoinGecko /coins/{id}/market_chart API로
상위 100개 코인의 과거 3개월 시총 데이터를 수집합니다.

주의: 무료 API는 분당 10~30 요청 제한이 있어 시간이 걸릴 수 있습니다.

실행: python backfill_crypto.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher_crypto import (
    fetch_coin_market_chart,
    fetch_crypto_top100,
    get_available_crypto_dates,
    save_crypto_data,
)


def main():
    end_date   = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=95)).strftime("%Y%m%d")

    print(f"\n{'='*54}")
    print(f"  코인 백필 시작 — {start_date} ~ {end_date}")
    print(f"{'='*54}\n")

    # 현재 상위 100 코인 목록 가져오기
    print("  현재 코인 순위 수집 중...")
    current_df = fetch_crypto_top100()
    if current_df.empty:
        print("  ⚠ 현재 코인 데이터를 가져올 수 없습니다.")
        return

    print(f"  {len(current_df)}개 코인 역사 데이터 수집 시작...\n")

    # {date_str: {coin_id: (symbol, name, market_cap)}}
    date_coin_map: dict = defaultdict(dict)

    for idx, row in current_df.iterrows():
        coin_id = row["coin_id"]
        symbol  = row["ticker"]
        name    = row["name"]

        print(f"  [{idx+1:3d}/{len(current_df)}] {name} ({coin_id})...")
        history = fetch_coin_market_chart(coin_id, days=95)

        for date_str, mcap in history:
            if start_date <= date_str <= end_date:
                date_coin_map[date_str][coin_id] = (symbol, name, mcap)

        time.sleep(4.0)   # CoinGecko 무료 API rate limit 준수 (분당 ~15회)

    # ── 날짜별 DataFrame 생성 및 저장 ──────────────────────────────────────
    available = set(get_available_crypto_dates())
    saved     = 0

    for date_str in sorted(date_coin_map.keys()):
        if date_str in available:
            continue

        coins_today = date_coin_map[date_str]
        records = [
            {
                "coin_id":    cid,
                "ticker":     sym,
                "name":       nm,
                "market_cap": mc,
            }
            for cid, (sym, nm, mc) in coins_today.items()
        ]

        if not records:
            continue

        df = (
            pd.DataFrame(records)
            .sort_values("market_cap", ascending=False)
            .reset_index(drop=True)
        )
        df["rank"] = range(1, len(df) + 1)
        df["rank"] = df["rank"].astype(int)
        df = df[["rank", "ticker", "name", "coin_id", "market_cap"]]

        save_crypto_data(date_str, df)
        saved += 1
        print(f"  {date_str}: {len(df)}개 코인 저장")

    print(f"\n{'='*54}")
    print(f"  코인 백필 완료 — {saved}일 저장")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
