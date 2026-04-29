"""
fetcher.py
네이버 금융 스크래핑 + FinanceDataReader 로 시가총액 데이터를 수집합니다.

■ 오늘 데이터 (run_daily.py)
    fetch_market_cap_naver(market) → 네이버 시가총액 순위표 직접 파싱

■ 과거 데이터 (backfill.py)
    fetch_top100_with_shares(market) → 현재 상위 100 종목 + 상장주식수
    fetch_price_history(ticker, start, end) → FinanceDataReader 주가
    calculate_historical_caps(ticker_df, start, end) → 날짜별 시총 추정
"""

import io
import json
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
from bs4 import BeautifulSoup

import xml.etree.ElementTree as ET

# ── 경로 ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
NAME_CACHE_FILE = os.path.join(DATA_DIR, "ticker_names.json")

# ── 공통 헤더 ─────────────────────────────────────────────────────────────────
_HDR = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# sosok: 0 = KOSPI, 1 = KOSDAQ
_SOSOK = {"KOSPI": "0", "KOSDAQ": "1"}


# ── 캐시 유틸 (호환성 유지) ───────────────────────────────────────────────────
def load_name_cache() -> dict:
    if os.path.exists(NAME_CACHE_FILE):
        with open(NAME_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_name_cache(cache: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NAME_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── 네이버 금융: 현재 시가총액 순위 ──────────────────────────────────────────
def fetch_top100_with_shares(market: str,
                              sleep: float = 0.5) -> pd.DataFrame:
    """
    네이버 금융 시가총액 순위표에서 상위 100종목과 상장주식수를 가져옵니다.

    Returns:
        DataFrame [rank, ticker, name, market_cap(원), shares(주)]
    """
    sosok = _SOSOK[market]
    rows = []

    for page in [1, 2]:   # 페이지당 50종목 × 2 = 100종목
        url = (f"https://finance.naver.com/sise/sise_market_sum.naver"
               f"?sosok={sosok}&page={page}")
        try:
            resp = requests.get(url, headers=_HDR, timeout=10)
            resp.encoding = "euc-kr"
            soup = BeautifulSoup(resp.text, "lxml")

            table = soup.select_one("table.type_2")
            if not table:
                continue

            for tr in table.select("tr"):
                tds = tr.select("td")
                if len(tds) < 9:
                    continue

                a_tag = tds[1].select_one("a")
                if not a_tag:
                    continue

                href = a_tag.get("href", "")
                ticker = href.split("code=")[-1].strip() if "code=" in href else ""
                name   = a_tag.get_text(strip=True)

                # 시가총액 (억원) → 원
                cap_txt    = tds[6].get_text(strip=True).replace(",", "")
                # 상장주식수 (천주) → 주
                shares_txt = tds[7].get_text(strip=True).replace(",", "")

                if not ticker or not cap_txt.isdigit():
                    continue

                market_cap = float(cap_txt) * 1e8          # 억원 → 원
                shares     = float(shares_txt) * 1000 if shares_txt.isdigit() else 0

                rows.append({
                    "ticker":     ticker,
                    "name":       name,
                    "market_cap": market_cap,
                    "shares":     shares,
                })

            time.sleep(sleep)

        except Exception as e:
            print(f"  네이버 {market} 페이지 {page} 오류: {e}")

    if not rows:
        return pd.DataFrame()

    df = (pd.DataFrame(rows)
            .sort_values("market_cap", ascending=False)
            .head(100)
            .reset_index(drop=True))
    df.insert(0, "rank", range(1, len(df) + 1))
    return df


# run_daily.py 에서 호출하는 공통 함수 (이름 유지)
def fetch_market_cap_krx(date: str, market: str,
                          name_cache: dict = None,
                          retry: int = 3) -> pd.DataFrame:
    """
    오늘 날짜용: 네이버 금융 현재 시가총액 순위를 가져옵니다.
    (KRX → 네이버로 데이터 소스 교체)
    date 파라미터는 호환성을 위해 유지하지만 내부적으로 무시합니다.
    """
    df = fetch_top100_with_shares(market)
    if df.empty:
        return df

    # 종목명 캐시 업데이트
    if name_cache is not None:
        for _, row in df.iterrows():
            name_cache[row["ticker"]] = row["name"]

    # shares 컬럼 제거 (저장 포맷 호환)
    return df[["rank", "ticker", "name", "market_cap"]].copy()


# ── 네이버 금융 fchart: 개별 주가 히스토리 ───────────────────────────────────
def fetch_price_history(ticker: str,
                         start_date: str,
                         end_date: str,
                         retry: int = 3) -> pd.Series:
    """
    네이버 금융 fchart API로 종목의 날짜별 종가를 가져옵니다.
    (FinanceDataReader 불필요 — requests + xml 만 사용)

    Returns:
        Series (index='YYYYMMDD', value=종가)
    """
    # 3개월 + 여유분 = 약 90 거래일
    url = (f"https://fchart.stock.naver.com/sise.nhn"
           f"?symbol={ticker}&timeframe=day&count=90&requestType=0")

    for attempt in range(1, retry + 1):
        try:
            resp = requests.get(url, headers=_HDR, timeout=10)
            resp.raise_for_status()

            # euc-kr로 디코딩 후 XML 선언 제거
            # (ElementTree는 multi-byte 인코딩 선언을 직접 지원 안 함)
            text = resp.content.decode("euc-kr", errors="replace")
            if text.lstrip().startswith("<?xml"):
                text = text[text.index("?>") + 2:].strip()

            root = ET.fromstring(text)
            records: dict[str, float] = {}

            for item in root.findall(".//item"):
                raw = item.get("data", "")
                parts = raw.split("|")
                if len(parts) < 5:
                    continue
                date  = parts[0].strip()   # YYYYMMDD
                close_str = parts[4].strip()
                if not date or not close_str:
                    continue
                close = float(close_str)
                if start_date <= date <= end_date and close > 0:
                    records[date] = close

            return pd.Series(records)

        except Exception as e:
            if attempt < retry:
                time.sleep(1.5 * attempt)
            else:
                print(f"    [{ticker}] 가격 조회 실패: {e}")

    return pd.Series(dtype=float)


# ── 과거 시총 추정 (backfill 핵심 로직) ──────────────────────────────────────
def build_historical_snapshots(market: str,
                                top100_df: pd.DataFrame,
                                start_date: str,
                                end_date: str,
                                sleep_between: float = 0.3) -> dict[str, pd.DataFrame]:
    """
    현재 상위 100종목의 과거 주가 × 상장주식수로 날짜별 시총을 추정합니다.

    Args:
        market      : 'KOSPI' 또는 'KOSDAQ'
        top100_df   : fetch_top100_with_shares()의 반환값
        start_date  : 'YYYYMMDD'
        end_date    : 'YYYYMMDD'

    Returns:
        {date_str: DataFrame [rank, ticker, name, market_cap]} 날짜→DataFrame 매핑
    """
    tickers    = top100_df["ticker"].tolist()
    names      = dict(zip(top100_df["ticker"], top100_df["name"]))
    shares_map = dict(zip(top100_df["ticker"], top100_df["shares"]))

    print(f"\n  [{market}] 과거 주가 수집 중 (총 {len(tickers)}종목)...")

    # 각 종목의 날짜별 종가 수집
    price_dict: dict[str, pd.Series] = {}
    for i, ticker in enumerate(tickers, 1):
        close = fetch_price_history(ticker, start_date, end_date)
        if not close.empty:
            price_dict[ticker] = close
        print(f"    [{i:>3}/{len(tickers)}] {ticker} {names[ticker]} "
              f"— {len(close)}일 데이터", end="\r")
        time.sleep(sleep_between)

    print(f"\n  [{market}] 날짜별 시총 계산 중...")

    # 날짜별 DataFrame 생성
    all_dates = get_business_days(start_date, end_date)
    snapshots: dict[str, pd.DataFrame] = {}

    for date in all_dates:
        rows = []
        for ticker in tickers:
            prices = price_dict.get(ticker)
            if prices is None or date not in prices.index:
                continue
            price  = prices[date]
            shares = shares_map.get(ticker, 0)
            if shares <= 0 or price <= 0:
                continue
            rows.append({
                "ticker":     ticker,
                "name":       names[ticker],
                "market_cap": price * shares,
            })

        if not rows:
            continue   # 거래 없는 날 (휴장일 등)

        df = (pd.DataFrame(rows)
                .sort_values("market_cap", ascending=False)
                .head(100)
                .reset_index(drop=True))
        df.insert(0, "rank", range(1, len(df) + 1))
        snapshots[date] = df[["rank", "ticker", "name", "market_cap"]]

    return snapshots


# ── JSON 저장 / 로드 ──────────────────────────────────────────────────────────
def save_market_data(date: str, market: str, df: pd.DataFrame) -> str:
    save_dir = os.path.join(DATA_DIR, market.lower())
    os.makedirs(save_dir, exist_ok=True)
    filepath = os.path.join(save_dir, f"{date}.json")
    payload = {
        "date":     date,
        "market":   market,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "stocks":   df.to_dict(orient="records"),
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filepath


def load_market_data(date: str, market: str) -> pd.DataFrame:
    filepath = os.path.join(DATA_DIR, market.lower(), f"{date}.json")
    if not os.path.exists(filepath):
        return pd.DataFrame()
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return pd.DataFrame(data["stocks"])


def get_available_dates(market: str) -> list[str]:
    data_dir = os.path.join(DATA_DIR, market.lower())
    if not os.path.exists(data_dir):
        return []
    return sorted(
        f.replace(".json", "")
        for f in os.listdir(data_dir)
        if f.endswith(".json")
    )


# ── 영업일 유틸 ───────────────────────────────────────────────────────────────
def get_business_days(start_date: str, end_date: str) -> list[str]:
    start = datetime.strptime(start_date, "%Y%m%d")
    end   = datetime.strptime(end_date,   "%Y%m%d")
    days, cur = [], start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return days
