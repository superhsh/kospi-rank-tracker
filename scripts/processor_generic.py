"""
processor_generic.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
미국(S&P 500 / NASDAQ 100) 및 코인 시장의
순위 변동 Top5 계산과 히스토리 빌더 공통 유틸입니다.

주요 함수
  format_market_cap_usd(value)        → "$2.50T" 형식 문자열
  find_prev_date(date, period, dates) → 비교 기준 날짜
  compute_top5_generic(cur, prev)     → top5 딕셔너리
  build_history_generic(load_fn, dates, tickers, period)
"""

from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd

PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


# ── 시총 포맷 (USD) ────────────────────────────────────────────────────────────
def format_market_cap_usd(value: float) -> str:
    """시가총액(USD)을 T/B/M 단위 문자열로 변환합니다."""
    if value >= 1e12:
        return f"${value / 1e12:.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:.1f}B"
    return f"${value / 1e6:.0f}M"


# ── 날짜 유틸 ─────────────────────────────────────────────────────────────────
def find_prev_date(current_date: str, period: str,
                   available_dates: list) -> str | None:
    """
    period(daily/weekly/monthly)만큼 이전 시점에 가장 가까운
    저장 날짜를 반환합니다. 없으면 None.

    monthly: 전월 마지막 날을 기준으로 사용 (차트의 월별 막대와 일치)
    """
    dt = datetime.strptime(current_date, "%Y%m%d")
    if period == "monthly":
        # 이번 달 1일 - 1일 = 전월 마지막 날
        target = (dt.replace(day=1) - timedelta(days=1)).strftime("%Y%m%d")
    else:
        days = PERIOD_DAYS[period]
        target = (dt - timedelta(days=days)).strftime("%Y%m%d")
    candidates = [d for d in available_dates if d <= target]
    return max(candidates) if candidates else None


# ── Top5 계산 ─────────────────────────────────────────────────────────────────
def compute_top5_generic(current_df: pd.DataFrame,
                         prev_df: pd.DataFrame,
                         currency: str = "USD") -> dict:
    """
    current_df / prev_df: rank, ticker, name, market_cap 컬럼 포함 DataFrame
    currency: 'USD' | 'KRW'

    Returns:
        {
          "available": bool,
          "top5": [
            {"rank":int, "prev_rank":int, "rank_change":int,
             "ticker":str, "name":str,
             "market_cap":float, "market_cap_str":str},
            ...
          ]
        }
    """
    base = {"available": False, "top5": []}

    if current_df is None or current_df.empty:
        return base
    if prev_df is None or prev_df.empty:
        return base

    merged = current_df.merge(
        prev_df[["ticker", "rank"]].rename(columns={"rank": "prev_rank"}),
        on="ticker",
        how="inner",
    )
    merged["rank_change"] = merged["prev_rank"] - merged["rank"]

    improved = merged[merged["rank_change"] > 0].nlargest(5, "rank_change")

    top5 = []
    for _, row in improved.iterrows():
        v = float(row["market_cap"])
        if currency == "USD":
            mcap_str = format_market_cap_usd(v)
        else:  # KRW
            if v >= 1_000_000_000_000:
                mcap_str = f"{v / 1_000_000_000_000:.2f}조"
            elif v >= 100_000_000:
                mcap_str = f"{v / 100_000_000:.0f}억"
            else:
                mcap_str = f"{v:,.0f}원"

        top5.append({
            "rank":           int(row["rank"]),
            "prev_rank":      int(row["prev_rank"]),
            "rank_change":    int(row["rank_change"]),
            "ticker":         str(row["ticker"]),
            "name":           str(row["name"]),
            "market_cap":     v,
            "market_cap_str": mcap_str,
        })

    return {"available": bool(top5), "top5": top5}


# ── 히스토리 내부 유틸 ────────────────────────────────────────────────────────
def _ticker_ranks(df: pd.DataFrame, tickers: list) -> dict:
    if df is None or df.empty:
        return {}
    out = {}
    for t in tickers:
        rows = df[df["ticker"] == t]
        if not rows.empty:
            out[t] = int(rows.iloc[0]["rank"])
    return out


def _fmt_date(d: str) -> str:
    return f"{d[4:6]}.{d[6:8]}"


def _fmt_month(d: str) -> str:
    return f"{d[2:4]}.{d[4:6]}"


# ── 기간별 히스토리 빌더 ──────────────────────────────────────────────────────
def _build_daily(load_fn, dates: list, tickers: list) -> list:
    timeline = []
    for date in dates:
        df    = load_fn(date)
        ranks = _ticker_ranks(df, tickers)
        if ranks:
            timeline.append({"label": _fmt_date(date), "ranks": ranks})
    return timeline


def _build_weekly(load_fn, dates: list, tickers: list) -> list:
    week_map: dict = defaultdict(list)
    for d in dates:
        dt  = datetime.strptime(d, "%Y%m%d")
        iso = dt.isocalendar()
        week_map[(iso[0], iso[1])].append(d)

    timeline = []
    for wk in sorted(week_map.keys()):
        last  = max(week_map[wk])
        df    = load_fn(last)
        ranks = _ticker_ranks(df, tickers)
        if ranks:
            timeline.append({"label": _fmt_date(last), "ranks": ranks})
    return timeline


def _build_monthly(load_fn, dates: list, tickers: list) -> list:
    month_map: dict = defaultdict(list)
    for d in dates:
        month_map[d[:6]].append(d)

    timeline = []
    for ym in sorted(month_map.keys()):
        last  = max(month_map[ym])
        df    = load_fn(last)
        ranks = _ticker_ranks(df, tickers)
        if ranks:
            timeline.append({"label": _fmt_month(last), "ranks": ranks})
    return timeline


def compute_streak_top5_generic(load_fn, available_dates: list, today: str,
                                currency: str = "USD",
                                rank_limit: int = None) -> list:
    """
    연속으로 시총 순위가 상승한(rank 숫자 감소) 종목 중
    3일 이상 streak인 것을 현재 순위 기준으로 정렬해 Top5 반환.

    load_fn(date_str) → pd.DataFrame (rank, ticker, name, market_cap)
    rank_limit       : None이면 전체, 숫자면 현재 해당 순위 이내만 대상
    """
    sorted_dates = sorted([d for d in available_dates if d <= today])
    if len(sorted_dates) < 2:
        return []

    recent = sorted_dates[-31:]   # 최근 31일치만 사용

    rank_maps: dict = {}
    for date in recent:
        df = load_fn(date)
        if not df.empty:
            rank_maps[date] = {
                str(r["ticker"]): int(r["rank"])
                for _, r in df.iterrows()
            }

    valid_dates = sorted(rank_maps.keys())
    if len(valid_dates) < 2:
        return []

    today_date = valid_dates[-1]
    today_df   = load_fn(today_date)
    if today_df.empty:
        return []

    if rank_limit:
        today_df = today_df[today_df["rank"] <= rank_limit]

    streaks: dict = {}
    for ticker in today_df["ticker"].astype(str).tolist():
        streak = 0
        for i in range(len(valid_dates) - 1, 0, -1):
            curr = rank_maps.get(valid_dates[i],   {}).get(ticker)
            prev = rank_maps.get(valid_dates[i-1], {}).get(ticker)
            if curr is None or prev is None:
                break
            if curr < prev:   # 순위 숫자 감소 = 순위 상승
                streak += 1
            else:
                break
        streaks[ticker] = streak

    qualified = [(t, s) for t, s in streaks.items() if s >= 3]
    qualified.sort(key=lambda x: rank_maps[today_date].get(x[0], 9999))

    top5 = []
    for ticker, streak in qualified[:5]:
        rows = today_df[today_df["ticker"].astype(str) == ticker]
        if rows.empty:
            continue
        row = rows.iloc[0]
        v   = float(row["market_cap"])
        if currency == "USD":
            mcap_str = format_market_cap_usd(v)
        else:
            if v >= 1_000_000_000_000:
                mcap_str = f"{v / 1_000_000_000_000:.2f}조"
            elif v >= 100_000_000:
                mcap_str = f"{v / 100_000_000:.0f}억"
            else:
                mcap_str = f"{v:,.0f}원"
        top5.append({
            "rank":           int(row["rank"]),
            "ticker":         str(row["ticker"]),
            "name":           str(row["name"]),
            "market_cap":     v,
            "market_cap_str": mcap_str,
            "streak_days":    streak,
        })
    return top5


def build_history_generic(load_fn, dates: list, tickers: list,
                          period: str) -> list:
    """
    load_fn(date_str) → pd.DataFrame (rank, ticker, name, market_cap)
    dates            : 사용할 날짜 목록 (YYYYMMDD 정렬)
    tickers          : 추적할 종목 티커 목록
    period           : 'daily' | 'weekly' | 'monthly'

    Returns: [{"label": str, "ranks": {ticker: rank}}, ...]
    """
    if period == "daily":
        return _build_daily(load_fn, dates, tickers)
    if period == "weekly":
        return _build_weekly(load_fn, dates, tickers)
    if period == "monthly":
        return _build_monthly(load_fn, dates, tickers)
    return []
