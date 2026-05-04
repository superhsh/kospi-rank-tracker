"""
history_builder.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
각 주기(장중/일별/주별/월별) Top5 종목의 순위 변동 이력을 계산하여
report_data 딕셔너리에 직접 첨부합니다.

첨부 위치:
  report_data["kospi"]["daily"]["history"]   = { tickers, names, timeline }
  report_data["kospi"]["weekly"]["history"]  = { ... }
  report_data["kospi"]["monthly"]["history"] = { ... }
  report_data["intraday"]["kospi"]["history"]= { ... }  ← run_hourly 에서만
"""

import os
from collections import defaultdict
from datetime import datetime, timedelta

import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTRA_LABELS = ["0920", "1100", "1300", "1500"]


# ── 내부 유틸 ─────────────────────────────────────────────────────────────────
def _ticker_ranks(df: pd.DataFrame, tickers: list) -> dict:
    """DataFrame → {ticker: rank} 매핑 (없으면 제외)."""
    if df is None or df.empty:
        return {}
    out = {}
    for t in tickers:
        rows = df[df["ticker"] == t]
        if not rows.empty:
            out[t] = int(rows.iloc[0]["rank"])
    return out


def _fmt_date(d: str) -> str:
    """YYYYMMDD → MM.DD"""
    return f"{d[4:6]}.{d[6:8]}"


def _fmt_month(d: str) -> str:
    """YYYYMMDD → YY.MM"""
    return f"{d[2:4]}.{d[4:6]}"


# ── 장중 이력: 최근 3일 × 4 시간대 ──────────────────────────────────────────
def build_intraday_history(market: str, today: str, tickers: list) -> list:
    from scripts.fetcher import get_available_dates
    from scripts.intraday import get_saved_labels, load_intraday

    # 일별 데이터 날짜 + today 합산 (오늘 일별 데이터가 없어도 장중 스냅샷은 존재)
    daily_dates = set(get_available_dates(market))
    all_dates   = sorted(daily_dates | {today})
    recent = sorted([d for d in all_dates if d <= today], reverse=True)[:3]
    recent = sorted(recent)

    timeline = []
    for date in recent:
        saved = get_saved_labels(market, date)
        for label in INTRA_LABELS:
            if label not in saved:
                continue
            df    = load_intraday(market, date, label)
            ranks = _ticker_ranks(df, tickers)
            if not ranks:
                continue
            h, m = label[:2], label[2:]
            timeline.append({
                "label": f"{_fmt_date(date)} {h}:{m}",
                "ranks": ranks,
            })
    return timeline


# ── 일별 이력: 최근 30일 ────────────────────────────────────────────────────
def build_daily_history(market: str, today: str, tickers: list) -> list:
    from scripts.fetcher import get_available_dates, load_market_data

    cutoff = (datetime.strptime(today, "%Y%m%d") - timedelta(days=30)).strftime("%Y%m%d")
    dates  = [d for d in get_available_dates(market) if cutoff <= d <= today]

    timeline = []
    for date in dates:
        df    = load_market_data(date, market)
        ranks = _ticker_ranks(df, tickers)
        if ranks:
            timeline.append({"label": _fmt_date(date), "ranks": ranks})
    return timeline


# ── 주별 이력: 최근 13주 ────────────────────────────────────────────────────
def build_weekly_history(market: str, today: str, tickers: list) -> list:
    from scripts.fetcher import get_available_dates, load_market_data

    cutoff = (datetime.strptime(today, "%Y%m%d") - timedelta(days=91)).strftime("%Y%m%d")
    dates  = [d for d in get_available_dates(market) if cutoff <= d <= today]

    week_map: dict = defaultdict(list)
    for d in dates:
        dt  = datetime.strptime(d, "%Y%m%d")
        iso = dt.isocalendar()
        week_map[(iso[0], iso[1])].append(d)

    timeline = []
    for wk in sorted(week_map.keys()):
        last = max(week_map[wk])
        df   = load_market_data(last, market)
        ranks = _ticker_ranks(df, tickers)
        if ranks:
            timeline.append({"label": _fmt_date(last), "ranks": ranks})
    return timeline


# ── 월별 이력: 전체 가용 기간 ───────────────────────────────────────────────
def build_monthly_history(market: str, today: str, tickers: list) -> list:
    from scripts.fetcher import get_available_dates, load_market_data

    dates = [d for d in get_available_dates(market) if d <= today]

    month_map: dict = defaultdict(list)
    for d in dates:
        month_map[d[:6]].append(d)   # YYYYMM

    timeline = []
    for ym in sorted(month_map.keys()):
        last  = max(month_map[ym])
        df    = load_market_data(last, market)
        ranks = _ticker_ranks(df, tickers)
        if ranks:
            timeline.append({"label": _fmt_month(last), "ranks": ranks})
    return timeline


# ── 공개 API ──────────────────────────────────────────────────────────────────
def attach_histories(report_data: dict, markets: list, today: str) -> dict:
    """
    report_data 의 daily / weekly / monthly 각 섹션에
    해당 Top5 종목의 순위 이력을 history 필드로 추가합니다.
    """
    builders = {
        "daily":   build_daily_history,
        "weekly":  build_weekly_history,
        "monthly": build_monthly_history,
    }

    for market in markets:
        mk = market.lower()
        for period, builder in builders.items():
            top5 = report_data.get(mk, {}).get(period, {}).get("top5", [])
            if not top5:
                continue
            tickers  = [s["ticker"] for s in top5]
            names    = {s["ticker"]: s["name"] for s in top5}
            timeline = builder(market, today, tickers)
            report_data[mk][period]["history"] = {
                "tickers":  tickers,
                "names":    names,
                "timeline": timeline,
            }

    return report_data


def get_all_intraday_top5_tickers(market: str, today: str) -> dict:
    """
    오늘 모든 장중 시간대(0920/1100/1300/1500)에서
    Top5에 한 번이라도 진입한 고유 종목 {ticker: name}을 반환합니다.
    """
    from scripts.fetcher import get_available_dates, load_market_data
    from scripts.intraday import get_saved_labels, load_intraday, compute_top5

    saved_today = set(get_saved_labels(market, today))
    if not saved_today:
        return {}

    all_dates = sorted(get_available_dates(market))
    tickers: dict[str, str] = {}   # ticker → name
    prev_df: pd.DataFrame   = pd.DataFrame()

    for label in INTRA_LABELS:
        if label not in saved_today:
            continue

        current_df = load_intraday(market, today, label)
        if current_df.empty:
            prev_df = current_df
            continue

        if label == "0920":
            prev_candidates = [d for d in all_dates if d < today]
            ref_df = (load_market_data(max(prev_candidates), market)
                      if prev_candidates else pd.DataFrame())
        else:
            ref_df = prev_df

        top5 = compute_top5(current_df, ref_df)
        for s in top5:
            tickers[s["ticker"]] = s["name"]

        prev_df = current_df

    return tickers


def attach_intraday_history(report_data: dict, markets: list, today: str) -> dict:
    """
    장중 탭 히스토리:
      - 오늘 모든 시간대(0920/1100/1300/1500) Top5에 진입한 전체 종목 수집
      - 해당 종목들의 최근 3일 × 시간대별 장중 순위 변동을 history 필드로 추가
      (일별 데이터 대신 장중 스냅샷 사용 → 오늘 데이터 누락 방지)
    """
    for market in markets:
        mk    = market.lower()
        idata = report_data.get("intraday", {}).get(mk, {})
        if not idata.get("available"):
            continue

        # 모든 시간대 Top5 종목 수집
        all_tickers = get_all_intraday_top5_tickers(market, today)

        # fallback: 현재 시간대 top5
        if not all_tickers:
            for s in idata.get("top5", []):
                all_tickers[s["ticker"]] = s["name"]

        if not all_tickers:
            continue

        tickers  = list(all_tickers.keys())
        # 일별 히스토리 → 장중 스냅샷 기반 히스토리로 변경
        timeline = build_intraday_history(market, today, tickers)

        report_data["intraday"][mk]["history"] = {
            "tickers":  tickers,
            "names":    all_tickers,
            "timeline": timeline,
        }

    return report_data
