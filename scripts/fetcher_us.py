"""
fetcher_us.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
yfinance를 이용해 S&P 500 / NASDAQ 100 구성 종목의
현재 시가총액을 수집하고 랭킹 DataFrame을 생성합니다.

저장 형식
  data/sp500/{YYYYMMDD}.json
  data/nasdaq100/{YYYYMMDD}.json
  각 파일: [{"rank":1,"ticker":"AAPL","name":"Apple Inc.","market_cap":3.2e12}, ...]

이름 캐시: data/name_cache_us.json
"""

import json
import os
import time
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

_WIKI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
_NAME_CACHE_PATH = os.path.join(DATA_DIR, "name_cache_us.json")


# ── 경로 유틸 ─────────────────────────────────────────────────────────────────
def _data_dir(market: str) -> str:
    d = os.path.join(DATA_DIR, market)
    os.makedirs(d, exist_ok=True)
    return d


def _data_path(date: str, market: str) -> str:
    return os.path.join(_data_dir(market), f"{date}.json")


# ── 구성 종목 가져오기 ────────────────────────────────────────────────────────
def _wiki_tables(url: str) -> list:
    """
    Wikipedia URL에서 HTML 테이블을 가져옵니다.
    pd.read_html() 직접 호출은 403이 나므로 requests로 먼저 내려받습니다.
    """
    resp = requests.get(url, headers=_WIKI_HEADERS, timeout=20)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text), flavor="lxml")


def get_sp500_tickers() -> list:
    """Wikipedia에서 S&P 500 구성 종목 티커를 가져옵니다."""
    try:
        url    = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = _wiki_tables(url)
        tickers = (
            tables[0]["Symbol"]
            .str.replace(".", "-", regex=False)
            .tolist()
        )
        print(f"    S&P 500 티커 {len(tickers)}개 수집 완료")
        return tickers
    except Exception as e:
        print(f"  ⚠ S&P 500 티커 목록 로드 실패: {e}")
        return []


def get_nasdaq100_tickers() -> list:
    """Wikipedia에서 NASDAQ 100 구성 종목 티커를 가져옵니다."""
    try:
        url    = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = _wiki_tables(url)
        for t in tables:
            for col in ("Ticker", "Symbol", "Ticker symbol"):
                if col in t.columns and len(t) >= 90:
                    tickers = (
                        t[col]
                        .str.replace(".", "-", regex=False)
                        .tolist()
                    )
                    print(f"    NASDAQ 100 티커 {len(tickers)}개 수집 완료")
                    return tickers
        print("  ⚠ NASDAQ 100 티커 테이블을 찾지 못했습니다.")
        return []
    except Exception as e:
        print(f"  ⚠ NASDAQ 100 티커 목록 로드 실패: {e}")
        return []


# ── 시가총액 수집 ──────────────────────────────────────────────────────────────
def fetch_market_caps(tickers: list, name_cache: dict,
                      batch_size: int = 50) -> pd.DataFrame:
    """
    yfinance fast_info.market_cap을 이용해 현재 시총을 수집합니다.
    시총 내림차순으로 정렬한 rank, ticker, name, market_cap DataFrame 반환.
    """
    results = []
    total   = len(tickers)

    for i in range(0, total, batch_size):
        batch = tickers[i : i + batch_size]
        batch_no = i // batch_size + 1
        total_batches = (total - 1) // batch_size + 1
        print(f"    배치 {batch_no}/{total_batches} ({len(batch)}개)...")

        for ticker in batch:
            try:
                t_obj = yf.Ticker(ticker)
                info  = t_obj.fast_info
                mcap  = getattr(info, "market_cap", None)
                if not mcap or mcap <= 0:
                    continue

                # 이름 캐시
                if ticker not in name_cache:
                    try:
                        full_info = t_obj.info
                        name = (full_info.get("shortName")
                                or full_info.get("longName")
                                or ticker)
                    except Exception:
                        name = ticker
                    name_cache[ticker] = name

                results.append({
                    "ticker":     ticker,
                    "name":       name_cache.get(ticker, ticker),
                    "market_cap": float(mcap),
                })
            except Exception:
                pass

        if i + batch_size < total:
            time.sleep(0.8)

    if not results:
        return pd.DataFrame()

    df = (
        pd.DataFrame(results)
        .sort_values("market_cap", ascending=False)
        .reset_index(drop=True)
    )
    df["rank"] = range(1, len(df) + 1)
    df["rank"] = df["rank"].astype(int)
    return df[["rank", "ticker", "name", "market_cap"]]


# ── 저장 / 로드 ───────────────────────────────────────────────────────────────
def save_us_data(date: str, market: str, df: pd.DataFrame) -> str:
    path = _data_path(date, market)
    records = df.to_dict("records")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    return path


def load_us_data(date: str, market: str) -> pd.DataFrame:
    path = _data_path(date, market)
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        if df.empty:
            return df
        df["rank"]       = df["rank"].astype(int)
        df["market_cap"] = df["market_cap"].astype(float)
        return df
    except Exception as e:
        print(f"  ⚠ {path} 로드 오류: {e}")
        return pd.DataFrame()


def get_available_us_dates(market: str) -> list:
    d = _data_dir(market)
    dates = sorted([
        f[:-5] for f in os.listdir(d)
        if f.endswith(".json") and len(f) == 13
    ])
    return dates


# ── 이름 캐시 ─────────────────────────────────────────────────────────────────
def load_name_cache_us() -> dict:
    if os.path.exists(_NAME_CACHE_PATH):
        try:
            with open(_NAME_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_name_cache_us(cache: dict):
    os.makedirs(os.path.dirname(_NAME_CACHE_PATH), exist_ok=True)
    with open(_NAME_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
