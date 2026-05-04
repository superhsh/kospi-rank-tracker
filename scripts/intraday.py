"""
intraday.py
장중 시가총액 순위 스냅샷 저장·로드·비교 모듈

스냅샷 저장 경로: data/intraday/{market}/{YYYYMMDD}_{HHMM}.json
실행 라벨: 0920 / 1100 / 1300 / 1500
"""

import json
import os
from datetime import datetime

import pandas as pd

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTR_DIR  = os.path.join(BASE_DIR, "data", "intraday")

# 하루 실행 순서 (비교 기준 계산에 사용)
LABELS_ORDER = ["0920", "1100", "1300", "1500"]


# ── 경로 유틸 ─────────────────────────────────────────────────────────────────
def _snap_dir(market: str) -> str:
    d = os.path.join(INTR_DIR, market.lower())
    os.makedirs(d, exist_ok=True)
    return d


def _snap_path(market: str, date: str, label: str) -> str:
    return os.path.join(_snap_dir(market), f"{date}_{label}.json")


# ── 저장 / 로드 ────────────────────────────────────────────────────────────────
def save_intraday(market: str, date: str, label: str, df: pd.DataFrame) -> str:
    """장중 스냅샷을 JSON으로 저장합니다."""
    path = _snap_path(market, date, label)
    payload = {
        "date":     date,
        "label":    label,
        "market":   market,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "stocks":   df.to_dict(orient="records"),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def load_intraday(market: str, date: str, label: str) -> pd.DataFrame:
    """저장된 장중 스냅샷을 DataFrame으로 불러옵니다."""
    path = _snap_path(market, date, label)
    if not os.path.exists(path):
        return pd.DataFrame()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return pd.DataFrame(data["stocks"])


def get_saved_labels(market: str, date: str) -> list[str]:
    """해당 날짜에 저장된 라벨 목록을 정렬하여 반환합니다."""
    d = _snap_dir(market)
    prefix = f"{date}_"
    return sorted(
        f.replace(prefix, "").replace(".json", "")
        for f in os.listdir(d)
        if f.startswith(prefix) and f.endswith(".json")
    )


# ── 비교 기준 결정 ────────────────────────────────────────────────────────────
def resolve_comparison(market: str, today: str, current_label: str,
                        daily_dates: list[str]) -> tuple:
    """
    현재 라벨에 따라 비교할 데이터의 (source, date, label, desc)를 반환합니다.

    source: 'daily' | None
    desc  : 화면에 표시할 비교 기준 문자열

    모든 시간대(0920/1100/1300/1500)에서 전날 종가 기준으로 순위 변동을 계산합니다.
    """
    candidates = [d for d in daily_dates if d < today]
    if not candidates:
        return None, None, None, "전날 데이터 없음"
    prev_date = max(candidates)
    desc = f"전날 종가 ({prev_date[:4]}.{prev_date[4:6]}.{prev_date[6:]})"
    return "daily", prev_date, None, desc


# ── Top 5 계산 ────────────────────────────────────────────────────────────────
def _fmt_cap(value: float) -> str:
    if value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}조"
    elif value >= 100_000_000:
        return f"{value / 100_000_000:.0f}억"
    return f"{value:,.0f}원"


def compute_top5(current_df: pd.DataFrame,
                 prev_df: pd.DataFrame) -> list[dict]:
    """두 시점 DataFrame의 순위 상승 Top 5를 계산합니다."""
    if current_df.empty or prev_df.empty:
        return []

    merged = current_df.merge(
        prev_df[["ticker", "rank"]].rename(columns={"rank": "prev_rank"}),
        on="ticker", how="inner",
    )
    merged["rank_change"] = merged["prev_rank"] - merged["rank"]
    improved = merged[merged["rank_change"] > 0].nlargest(5, "rank_change")

    result = []
    for _, row in improved.iterrows():
        result.append({
            "rank":           int(row["rank"]),
            "prev_rank":      int(row["prev_rank"]),
            "rank_change":    int(row["rank_change"]),
            "ticker":         row["ticker"],
            "name":           row["name"],
            "market_cap":     float(row["market_cap"]),
            "market_cap_str": _fmt_cap(float(row["market_cap"])),
        })
    return result
