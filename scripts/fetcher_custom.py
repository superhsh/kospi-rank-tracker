"""
fetcher_custom.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용자가 직접 등록한 관심종목의 시가총액을 수집하고
일별 데이터를 저장합니다.

지원 시장:
  - kospi:  한국 KOSPI  (yfinance .KS suffix)
  - kosdaq: 한국 KOSDAQ (yfinance .KQ suffix)
  - us:     미국 주식   (yfinance 그대로)

저장 형식:
  data/custom_watchlist.json  — 관심종목 목록 (브라우저 → GitHub 동기화)
  data/custom/{YYYYMMDD}.json — 일별 시총 스냅샷
"""

import json
import os
import time
from datetime import datetime

import yfinance as yf

BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR       = os.path.join(BASE_DIR, "data")
CUSTOM_DIR     = os.path.join(DATA_DIR, "custom")
WATCHLIST_PATH = os.path.join(DATA_DIR, "custom_watchlist.json")

MARKET_SUFFIX = {
    "kospi":  ".KS",
    "kosdaq": ".KQ",
    "us":     "",
}

CURRENCY = {
    "kospi":  "KRW",
    "kosdaq": "KRW",
    "us":     "USD",
}

MARKET_LABEL = {
    "kospi":  "KOSPI",
    "kosdaq": "KOSDAQ",
    "us":     "미국",
}


# ── 디렉토리 초기화 ──────────────────────────────────────────────────────────
def _ensure_dirs():
    os.makedirs(CUSTOM_DIR, exist_ok=True)


# ── 관심종목 목록 로드 ───────────────────────────────────────────────────────
def load_custom_watchlist() -> list[dict]:
    """data/custom_watchlist.json에서 관심종목 목록을 로드합니다."""
    if not os.path.exists(WATCHLIST_PATH):
        return []
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("stocks", [])
    except Exception as e:
        print(f"  ⚠ custom_watchlist.json 로드 오류: {e}")
        return []


# ── 시총 수집 ────────────────────────────────────────────────────────────────
def fetch_market_cap(ticker: str, market: str) -> float | None:
    """
    yfinance로 시가총액을 수집합니다.
    반환: float (KRW 또는 USD) 또는 None (실패 시)
    """
    suffix    = MARKET_SUFFIX.get(market, "")
    yf_ticker = ticker + suffix
    try:
        info = yf.Ticker(yf_ticker).fast_info
        mc   = getattr(info, "market_cap", None)
        if mc and mc > 0:
            return float(mc)
    except Exception as e:
        print(f"    ⚠ {yf_ticker} 시총 수집 실패: {e}")
    return None


def fmt_market_cap(mc: float, currency: str) -> str:
    """시총을 보기 좋은 문자열로 변환합니다."""
    if currency == "KRW":
        t = mc / 1_000_000_000_000   # 조
        if t >= 1:
            return f"{t:.2f}조"
        b = mc / 100_000_000         # 억
        return f"{b:.0f}억"
    else:  # USD
        t = mc / 1_000_000_000_000   # Trillion
        if t >= 1:
            return f"${t:.2f}T"
        b = mc / 1_000_000_000       # Billion
        return f"${b:.1f}B"


# ── 일별 시총 수집 ───────────────────────────────────────────────────────────
def fetch_daily_custom(date_str: str | None = None) -> list[dict]:
    """
    관심종목 전체의 시총을 수집합니다.

    반환: [{"ticker":..., "name":..., "market":..., "currency":...,
             "market_cap":..., "market_cap_str":...}, ...]
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")

    stocks = load_custom_watchlist()
    if not stocks:
        print("  관심종목이 없습니다. 브라우저에서 종목을 추가하고 GitHub 저장 후 다시 실행하세요.")
        return []

    print(f"  관심종목 {len(stocks)}개 시총 수집 중...")
    records = []

    for s in stocks:
        ticker = s.get("ticker", "")
        market = s.get("market", "us")
        name   = s.get("name", ticker)
        curr   = CURRENCY.get(market, "USD")

        print(f"    [{MARKET_LABEL.get(market, market)}] {ticker} ({name})...")
        mc = fetch_market_cap(ticker, market)

        if mc is None:
            print(f"      ⚠ 시총 수집 실패 — 스킵")
            continue

        mc_str = fmt_market_cap(mc, curr)
        records.append({
            "ticker":         ticker,
            "name":           name,
            "market":         market,
            "currency":       curr,
            "market_cap":     mc,
            "market_cap_str": mc_str,
        })
        print(f"      시총: {mc_str}")
        time.sleep(0.4)   # API rate limit 방지

    print(f"  완료: {len(records)}/{len(stocks)}개 수집")
    return records


# ── 저장 / 로드 ──────────────────────────────────────────────────────────────
def save_daily_custom(date_str: str, records: list[dict]) -> str:
    """일별 시총 스냅샷을 저장합니다."""
    _ensure_dirs()
    path = os.path.join(CUSTOM_DIR, f"{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    return path


def load_daily_custom(date_str: str) -> list[dict]:
    """일별 시총 스냅샷을 로드합니다."""
    path = os.path.join(CUSTOM_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_available_custom_dates() -> list[str]:
    """저장된 일별 데이터의 날짜 목록을 반환합니다 (오름차순)."""
    if not os.path.isdir(CUSTOM_DIR):
        return []
    return sorted(
        f.replace(".json", "")
        for f in os.listdir(CUSTOM_DIR)
        if f.endswith(".json") and len(f) == 13   # YYYYMMDD.json = 13글자
    )
