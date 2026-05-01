"""
fetcher_crypto.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CoinGecko 무료 API를 이용해 시총 기준 상위 100개
암호화폐 데이터를 수집합니다.

저장 형식
  data/coin/{YYYYMMDD}.json
  각 파일: [{"rank":1,"ticker":"BTC","name":"Bitcoin",
             "coin_id":"bitcoin","market_cap":1.3e12}, ...]
"""

import json
import os
import time

import pandas as pd
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
COIN_DIR = os.path.join(DATA_DIR, "coin")

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
HEADERS = {
    "Accept":     "application/json",
    "User-Agent": "kospi-rank-tracker/1.0",
}


# ── 경로 유틸 ─────────────────────────────────────────────────────────────────
def _coin_data_path(date: str) -> str:
    os.makedirs(COIN_DIR, exist_ok=True)
    return os.path.join(COIN_DIR, f"{date}.json")


# ── 현재 시총 수집 ────────────────────────────────────────────────────────────
def _get_with_retry(url: str, params: dict, max_retries: int = 5) -> requests.Response:
    """
    429 Too Many Requests 시 지수 백오프로 재시도합니다.
    첫 429 → 30초, 두 번째 → 60초, 세 번째 → 120초 대기.
    """
    for attempt in range(max_retries):
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        if r.status_code == 429:
            wait = 30 * (2 ** attempt)   # 30, 60, 120, 240, 480 초
            print(f"    ⚡ 429 Too Many Requests — {wait}초 대기 후 재시도 "
                  f"({attempt+1}/{max_retries})...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"429 오류: {max_retries}회 재시도 후 실패")


def fetch_crypto_top100() -> pd.DataFrame:
    """
    CoinGecko API에서 시총 기준 상위 100개 암호화폐를 가져옵니다.

    Columns: rank, ticker, name, coin_id, market_cap
    """
    results = []

    for page in [1, 2]:
        url    = f"{COINGECKO_BASE}/coins/markets"
        params = {
            "vs_currency": "usd",
            "order":       "market_cap_desc",
            "per_page":    50,
            "page":        page,
            "sparkline":   "false",
        }
        try:
            r = _get_with_retry(url, params)
            for coin in r.json():
                mcap = coin.get("market_cap") or 0
                if mcap <= 0:
                    continue
                results.append({
                    "coin_id":    coin["id"],
                    "ticker":     coin["symbol"].upper(),
                    "name":       coin["name"],
                    "market_cap": float(mcap),
                })
        except Exception as e:
            print(f"  ⚠ CoinGecko API 오류 (page {page}): {e}")

        if page < 2:
            time.sleep(3.0)   # 페이지 사이 여유 간격

    if not results:
        return pd.DataFrame()

    df = (
        pd.DataFrame(results)
        .sort_values("market_cap", ascending=False)
        .reset_index(drop=True)
    )
    df["rank"] = range(1, len(df) + 1)
    df["rank"] = df["rank"].astype(int)
    return df[["rank", "ticker", "name", "coin_id", "market_cap"]]


def fetch_coin_market_chart(coin_id: str, days: int = 95) -> list:
    """
    CoinGecko에서 특정 코인의 과거 시총 히스토리를 가져옵니다.
    429 발생 시 지수 백오프로 자동 재시도합니다.
    Returns: [(date_str, market_cap), ...]
    """
    from datetime import datetime as _dt
    url    = f"{COINGECKO_BASE}/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days":        days,
        "interval":    "daily",
    }
    try:
        r = _get_with_retry(url, params)
        out = []
        for ts_ms, mcap in r.json().get("market_caps", []):
            date_str = _dt.utcfromtimestamp(ts_ms / 1000).strftime("%Y%m%d")
            out.append((date_str, float(mcap)))
        return out
    except Exception as e:
        print(f"    ⚠ {coin_id}: {e}")
        return []


# ── 저장 / 로드 ───────────────────────────────────────────────────────────────
def save_crypto_data(date: str, df: pd.DataFrame) -> str:
    path    = _coin_data_path(date)
    records = df.to_dict("records")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    return path


def load_crypto_data(date: str) -> pd.DataFrame:
    path = _coin_data_path(date)
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


def get_available_crypto_dates() -> list:
    if not os.path.exists(COIN_DIR):
        return []
    return sorted([
        f[:-5] for f in os.listdir(COIN_DIR)
        if f.endswith(".json") and len(f) == 13
    ])
