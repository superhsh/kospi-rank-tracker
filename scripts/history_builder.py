"""
history_builder.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
일별 + 장중 스냅샷을 병합하여 종목별 순위 시계열 JSON을 생성합니다.

저장 경로:
  data/history_kospi.json
  data/history_kosdaq.json

JSON 구조:
  {
    "market":     "KOSPI",
    "updated_at": "2026-04-30 18:30",
    "tickers":    ["005930", ...],          # TOP_N 종목 (최신 일별 기준)
    "names":      {"005930": "삼성전자"},
    "timeline": [
      {"ts":"20260401",       "type":"daily",    "label":"04.01",       "ranks":{"005930":1,...}},
      {"ts":"20260430_0920",  "type":"intraday", "label":"04.30 09:20", "ranks":{...}},
      ...
    ]
  }
"""

import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
INTR_DIR = os.path.join(DATA_DIR, "intraday")

TOP_N = 30   # 추적할 종목 수 (최신 일별 순위 기준 상위 N)


# ── 내부 유틸 ─────────────────────────────────────────────────────────────────
def _load_daily_snaps(market: str) -> tuple[dict, dict]:
    """
    일별 JSON을 모두 읽어 {date: {ticker: rank}} 와 {ticker: name} 반환.
    """
    daily_dir = os.path.join(DATA_DIR, market.lower())
    snaps: dict[str, dict] = {}
    names: dict[str, str]  = {}

    if not os.path.exists(daily_dir):
        return snaps, names

    for fname in sorted(os.listdir(daily_dir)):
        if not fname.endswith(".json"):
            continue
        date = fname[:-5]  # YYYYMMDD
        path = os.path.join(daily_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            snap: dict[str, int] = {}
            for s in data.get("stocks", []):
                snap[s["ticker"]] = int(s["rank"])
                names[s["ticker"]] = s.get("name", s["ticker"])
            snaps[date] = snap
        except Exception:
            pass

    return snaps, names


def _load_intra_snaps(market: str, names: dict) -> dict:
    """
    장중 JSON을 모두 읽어 {"YYYYMMDD_HHMM": {ticker: rank}} 반환.
    names dict 를 in-place 로 업데이트합니다.
    """
    intra_dir = os.path.join(INTR_DIR, market.lower())
    snaps: dict[str, dict] = {}

    if not os.path.exists(intra_dir):
        return snaps

    for fname in sorted(os.listdir(intra_dir)):
        if not fname.endswith(".json"):
            continue
        key  = fname[:-5]  # YYYYMMDD_HHMM
        path = os.path.join(intra_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            snap: dict[str, int] = {}
            for s in data.get("stocks", []):
                snap[s["ticker"]] = int(s["rank"])
                names.setdefault(s["ticker"], s.get("name", s["ticker"]))
            snaps[key] = snap
        except Exception:
            pass

    return snaps


# ── 공개 API ──────────────────────────────────────────────────────────────────
def build_history(market: str) -> dict:
    """
    일별 + 장중 스냅샷을 병합한 히스토리 dict를 반환합니다.
    """
    daily_snaps, names = _load_daily_snaps(market)
    intra_snaps        = _load_intra_snaps(market, names)

    if not daily_snaps:
        return {
            "market": market, "updated_at": "",
            "tickers": [], "names": {}, "timeline": [],
        }

    # ── 추적 종목: 최신 일별 스냅샷 기준 상위 TOP_N ────────────────────────────
    latest_date = max(daily_snaps.keys())
    latest_snap = daily_snaps[latest_date]
    tracked = sorted(
        latest_snap.keys(),
        key=lambda t: latest_snap.get(t, 9999)
    )[:TOP_N]

    # ── 타임라인 조립 ─────────────────────────────────────────────────────────
    timeline = []

    for date in sorted(daily_snaps.keys()):
        snap = daily_snaps[date]
        mo, d = date[4:6], date[6:8]

        # 일별 엔트리
        timeline.append({
            "ts":    date,
            "type":  "daily",
            "label": f"{mo}.{d}",
            "ranks": {t: snap[t] for t in tracked if t in snap},
        })

        # 해당 날짜의 장중 스냅샷 (시간 순)
        for key in sorted(intra_snaps.keys()):
            if not key.startswith(date + "_"):
                continue
            hhmm  = key[9:]   # HHMM
            h, m  = hhmm[:2], hhmm[2:]
            snap2 = intra_snaps[key]
            timeline.append({
                "ts":    key,
                "type":  "intraday",
                "label": f"{mo}.{d} {h}:{m}",
                "ranks": {t: snap2[t] for t in tracked if t in snap2},
            })

    return {
        "market":     market,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tickers":    tracked,
        "names":      {t: names.get(t, t) for t in tracked},
        "timeline":   timeline,
    }


def save_history(market: str) -> str:
    """히스토리 JSON을 생성하고 저장합니다."""
    data = build_history(market)
    path = os.path.join(DATA_DIR, f"history_{market.lower()}.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  [{market}] 히스토리 저장 완료 → {os.path.basename(path)} "
          f"(종목 {len(data['tickers'])}개, "
          f"타임스탬프 {len(data['timeline'])}개)")
    return path
