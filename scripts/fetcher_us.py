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


def _find_ticker_col(df, candidates=("Symbol", "Ticker", "Ticker symbol", "ticker")) -> str | None:
    """DataFrame에서 티커 컬럼명을 유연하게 탐지합니다."""
    for col in candidates:
        if col in df.columns:
            return col
    # 대소문자 무시 탐색
    col_lower = {c.lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in col_lower:
            return col_lower[candidate.lower()]
    return None


def get_sp500_tickers() -> list:
    """Wikipedia에서 S&P 500 구성 종목 티커를 가져옵니다."""
    try:
        url    = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        tables = _wiki_tables(url)
        col = _find_ticker_col(tables[0])
        if col is None:
            print(f"  ⚠ S&P 500 티커 컬럼을 찾지 못했습니다. 컬럼: {list(tables[0].columns)}")
            return []
        tickers = (
            tables[0][col]
            .str.replace(".", "-", regex=False)
            .tolist()
        )
        print(f"    S&P 500 티커 {len(tickers)}개 수집 완료")
        return tickers
    except Exception as e:
        print(f"  ⚠ S&P 500 티커 목록 로드 실패: {e}")
        return []


def get_nasdaq100_tickers() -> list:
    """Wikipedia → Slickcharts 순으로 NASDAQ 100 구성 종목 티커를 가져옵니다."""
    # ── 1차: Wikipedia ───────────────────────────────────────────────────────
    try:
        url    = "https://en.wikipedia.org/wiki/Nasdaq-100"
        tables = _wiki_tables(url)
        print(f"    Wikipedia 테이블 {len(tables)}개 발견")
        for i, t in enumerate(tables):
            col = _find_ticker_col(t, candidates=(
                "Ticker", "Symbol", "Ticker symbol", "NASDAQ symbol",
                "ticker", "symbol", "Company Symbol",
            ))
            print(f"      테이블[{i}]: {len(t)}행, 컬럼={list(t.columns)[:6]}, ticker컬럼={col}")
            if col and len(t) >= 90:
                tickers = (
                    t[col]
                    .astype(str)
                    .str.strip()
                    .str.replace(".", "-", regex=False)
                    .tolist()
                )
                print(f"    NASDAQ 100 티커 {len(tickers)}개 수집 완료 (Wikipedia, 컬럼={col})")
                return tickers
        print("  ⚠ Wikipedia에서 NASDAQ 100 티커 테이블을 찾지 못했습니다 — Slickcharts 시도")
    except Exception as e:
        print(f"  ⚠ Wikipedia NASDAQ 100 로드 실패: {e} — Slickcharts 시도")

    # ── 2차: Slickcharts ─────────────────────────────────────────────────────
    try:
        url  = "https://www.slickcharts.com/nasdaq100"
        resp = requests.get(url, headers=_WIKI_HEADERS, timeout=20)
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        for t in tables:
            col = _find_ticker_col(t, candidates=("Symbol", "Ticker", "ticker", "symbol"))
            if col and len(t) >= 90:
                tickers = (
                    t[col]
                    .astype(str)
                    .str.strip()
                    .str.replace(".", "-", regex=False)
                    .tolist()
                )
                print(f"    NASDAQ 100 티커 {len(tickers)}개 수집 완료 (Slickcharts)")
                return tickers
        print("  ⚠ Slickcharts에서도 NASDAQ 100 테이블을 찾지 못했습니다.")
    except Exception as e:
        print(f"  ⚠ Slickcharts NASDAQ 100 로드 실패: {e}")

    return []


# ── 시가총액 수집 ──────────────────────────────────────────────────────────────
def _get_market_cap(t_obj) -> float | None:
    """
    yfinance API 버전에 무관하게 시총을 가져옵니다.
    fast_info.market_cap (0.2.x/1.x 공통) → info["marketCap"] 순서로 시도.
    """
    # 방법 1: fast_info.market_cap
    try:
        mcap = getattr(t_obj.fast_info, "market_cap", None)
        if mcap and mcap > 0:
            return float(mcap)
    except Exception:
        pass
    # 방법 2: .info dict (느리지만 더 안정적)
    try:
        full_info = t_obj.info
        mcap = full_info.get("marketCap") or full_info.get("market_cap")
        if mcap and mcap > 0:
            return float(mcap)
    except Exception:
        pass
    return None


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
                mcap  = _get_market_cap(t_obj)
                if not mcap:
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
                    "market_cap": mcap,
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


def refresh_names(name_cache: dict) -> int:
    """
    name_cache에서 이름이 티커 심볼과 동일한 항목(잘못 저장된 항목)을
    yfinance info로 재조회해 업데이트합니다.

    backfill_us.py가 fast_info(이름 속성 없음)로 저장한 항목을 복구하는 용도.
    Returns: 업데이트된 항목 수
    """
    to_fix = [t for t, n in name_cache.items() if n == t]
    if not to_fix:
        return 0

    print(f"  이름 재조회: {len(to_fix)}개 티커 (이름=티커로 잘못 저장된 항목)...")
    fixed = 0
    for i, ticker in enumerate(to_fix):
        try:
            info = yf.Ticker(ticker).info
            name = info.get("shortName") or info.get("longName") or ticker
            if name and name != ticker:
                name_cache[ticker] = name
                fixed += 1
        except Exception:
            pass
        time.sleep(0.15)
        if (i + 1) % 50 == 0:
            print(f"    ... {i+1}/{len(to_fix)}")

    print(f"  이름 업데이트 완료: {fixed}/{len(to_fix)}개")
    return fixed
