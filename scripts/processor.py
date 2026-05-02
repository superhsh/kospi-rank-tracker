"""
processor.py
저장된 시총 데이터를 읽어 일/주/월 기준 순위 변동 Top 5를 계산합니다.
"""

import os
import sys
from datetime import datetime, timedelta

import pandas as pd

# 상위 디렉토리에서 임포트할 수 있도록 경로 추가
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.fetcher import load_market_data, get_available_dates

MARKETS = ["KOSPI", "KOSDAQ"]
PERIODS = ["daily", "weekly", "monthly"]

PERIOD_CONFIG = {
    "daily":   {"label": "전일 대비",  "days": 1},
    "weekly":  {"label": "전주 대비",  "days": 7},
    "monthly": {"label": "전월 대비",  "days": 30},
}


# ── 날짜 유틸 ─────────────────────────────────────────────────────────────────
def find_prev_date(current_date: str, period: str,
                   available_dates: list[str]) -> str | None:
    """
    현재 날짜에서 period만큼 이전 시점과 가장 가까운 저장 날짜를 반환합니다.
    monthly: 전월 마지막 날 기준 (차트 월별 막대와 일치)
    """
    current_dt = datetime.strptime(current_date, "%Y%m%d")
    if period == "monthly":
        target_str = (current_dt.replace(day=1) - timedelta(days=1)).strftime("%Y%m%d")
    else:
        days_back = PERIOD_CONFIG[period]["days"]
        target_str = (current_dt - timedelta(days=days_back)).strftime("%Y%m%d")

    candidates = [d for d in available_dates if d <= target_str]
    return max(candidates) if candidates else None


# ── 시총 단위 변환 ────────────────────────────────────────────────────────────
def format_market_cap(value: float) -> str:
    """시가총액(원)을 조/억 단위 문자열로 변환합니다."""
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}조"
    elif value >= 100_000_000:
        return f"{value / 100_000_000:.0f}억"
    return f"{value:,.0f}원"


# ── 핵심 계산 로직 ────────────────────────────────────────────────────────────
def compute_top5(current_date: str, market: str, period: str) -> dict:
    """
    특정 날짜·마켓·기간에 대해 순위 상승 Top 5를 계산합니다.

    Returns:
        {
          "available": bool,
          "prev_date": str | None,
          "top5": [
            {
              "rank": int,          # 현재 순위
              "prev_rank": int,     # 이전 순위
              "rank_change": int,   # 순위 상승폭 (양수 = 상승)
              "ticker": str,
              "name": str,
              "market_cap": float,
              "market_cap_str": str,
            },
            ...
          ]
        }
    """
    available_dates = get_available_dates(market)

    result_base = {"available": False, "prev_date": None, "top5": []}

    # 오늘 데이터가 없으면(휴장일·수집 전 등) 가장 최근 날짜로 fallback
    if current_date not in available_dates:
        candidates = [d for d in available_dates if d <= current_date]
        if not candidates:
            return result_base
        current_date = max(candidates)

    current_df = load_market_data(current_date, market)
    if current_df.empty:
        return result_base

    prev_date = find_prev_date(current_date, period, available_dates)
    if prev_date is None:
        return {**result_base, "prev_date": None}

    prev_df = load_market_data(prev_date, market)
    if prev_df.empty:
        return {**result_base, "prev_date": prev_date}

    # 두 시점 공통 종목 병합
    merged = current_df.merge(
        prev_df[["ticker", "rank"]].rename(columns={"rank": "prev_rank"}),
        on="ticker",
        how="inner",
    )
    merged["rank_change"] = merged["prev_rank"] - merged["rank"]  # 양수 = 순위 상승

    # 순위가 상승한 종목만 추려서 상위 5개
    improved = merged[merged["rank_change"] > 0].nlargest(5, "rank_change")

    top5 = []
    for _, row in improved.iterrows():
        top5.append(
            {
                "rank":           int(row["rank"]),
                "prev_rank":      int(row["prev_rank"]),
                "rank_change":    int(row["rank_change"]),
                "ticker":         row["ticker"],
                "name":           row["name"],
                "market_cap":     float(row["market_cap"]),
                "market_cap_str": format_market_cap(float(row["market_cap"])),
            }
        )

    return {
        "available": True,
        "prev_date": prev_date,
        "top5":      top5,
    }


def build_report_data(current_date: str) -> dict:
    """
    KOSPI·KOSDAQ × 일/주/월 전체 분석 결과를 딕셔너리로 반환합니다.

    Returns:
        {
          "updated_at": "YYYY-MM-DD HH:MM",
          "current_date": "YYYYMMDD",
          "kospi":  { "daily": {...}, "weekly": {...}, "monthly": {...} },
          "kosdaq": { "daily": {...}, "weekly": {...}, "monthly": {...} },
        }
    """
    report = {
        "updated_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "current_date": current_date,
    }

    for market in MARKETS:
        market_key = market.lower()
        report[market_key] = {}
        for period in PERIODS:
            report[market_key][period] = compute_top5(current_date, market, period)

    return report
