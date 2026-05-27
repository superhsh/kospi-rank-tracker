"""
fetcher_midcap.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Russell 1000 하위 500종목(중형주) 시총 순위 수집기.

유니버스 전략 (효율 우선)
  - IWB (iShares Russell 1000 ETF) CSV에서 구성 종목 1000개 수집
  - 전체 1000종목 시총을 한 번 조회 → 내림차순 정렬 → 501~1000위 추출
  - 결과를 data/midcap_universe.json에 캐시 (7일 유효)
  - 매일 업데이트는 캐시된 500종목만 조회 → 약 3~5분 소요

저장 형식
  data/midcap_universe.json   — 유니버스 캐시 (500종목)
  data/midcap/{YYYYMMDD}.json — 일별 순위 데이터
  data/name_cache_midcap.json — 종목명 캐시

각 일별 파일: [{"rank":1,"ticker":"...","name":"...","market_cap":1.2e10}, ...]
"""

import json
import os
import time
from datetime import datetime, timedelta
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MIDCAP_DIR = os.path.join(DATA_DIR, "midcap")
UNIVERSE_PATH = os.path.join(DATA_DIR, "midcap_universe.json")
NAME_CACHE_PATH = os.path.join(DATA_DIR, "name_cache_midcap.json")

UNIVERSE_MAX_AGE_DAYS = 7   # 7일마다 유니버스 갱신
UNIVERSE_FULL_SIZE = 1000   # IWB Russell 1000
MIDCAP_START = 501          # 하위 절반 시작 순위 (inclusive)
MIDCAP_END = 1000           # 하위 절반 종료 순위 (inclusive)

def _get_market_cap(t_obj) -> float | None:
    """
    yfinance API 버전에 무관하게 시총을 가져옵니다.
    fast_info.market_cap → info["marketCap"] 순서로 시도.
    """
    try:
        mcap = getattr(t_obj.fast_info, "market_cap", None)
        if mcap and mcap > 0:
            return float(mcap)
    except Exception:
        pass
    try:
        full_info = t_obj.info
        mcap = full_info.get("marketCap") or full_info.get("market_cap")
        if mcap and mcap > 0:
            return float(mcap)
    except Exception:
        pass
    return None


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ── 디렉토리 유틸 ─────────────────────────────────────────────────────────────
def _ensure_dirs():
    os.makedirs(MIDCAP_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)


# ── 이름 캐시 ─────────────────────────────────────────────────────────────────
def load_name_cache() -> dict:
    if os.path.exists(NAME_CACHE_PATH):
        try:
            with open(NAME_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_name_cache(cache: dict):
    _ensure_dirs()
    with open(NAME_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── IWB ETF 구성 종목 파싱 ────────────────────────────────────────────────────
def _fetch_iwb_tickers() -> list[dict]:
    """
    iShares IWB (Russell 1000 ETF) CSV를 내려받아
    미국 주식 티커 최대 1000개와 종목명을 반환합니다.

    반환: [{"ticker": "AAPL", "name": "Apple Inc."}, ...]
    """
    urls = [
        # iShares 공식 CSV (가장 신뢰도 높음)
        "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/"
        "1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund",
        # 백업 URL
        "https://www.ishares.com/us/products/239707/ISHARES-RUSSELL-1000-ETF/"
        "1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund",
    ]

    for url in urls:
        try:
            print(f"    IWB ETF CSV 다운로드 중...")
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            resp.raise_for_status()
            text = resp.text

            # iShares CSV는 상단에 펀드 정보 행이 있어 실제 데이터는 헤더 탐색 필요
            lines = text.splitlines()
            header_row = None
            for i, line in enumerate(lines):
                if "Ticker" in line and "Name" in line:
                    header_row = i
                    break

            if header_row is None:
                print(f"    ⚠ 헤더 행을 찾지 못했습니다.")
                continue

            csv_text = "\n".join(lines[header_row:])
            df = pd.read_csv(StringIO(csv_text))

            # 컬럼명 정규화
            df.columns = [c.strip() for c in df.columns]
            ticker_col = next((c for c in df.columns if c.lower() in ("ticker", "symbol")), None)
            name_col   = next((c for c in df.columns if c.lower() in ("name", "security name")), None)
            asset_col  = next((c for c in df.columns if "asset" in c.lower()), None)

            if ticker_col is None:
                print(f"    ⚠ Ticker 컬럼을 찾지 못했습니다. 컬럼: {list(df.columns)}")
                continue

            # 미국 주식만 필터 (ETF·채권·현금 제외)
            if asset_col:
                df = df[df[asset_col].astype(str).str.upper().isin(
                    ["EQUITY", "US EQUITY"]
                )]

            # "-" 또는 빈 티커 제거
            df[ticker_col] = df[ticker_col].astype(str).str.strip()
            df = df[df[ticker_col].notna() & (df[ticker_col] != "") & (df[ticker_col] != "-")]

            # yfinance 호환 형식으로 변환 ("." → "-")
            df[ticker_col] = df[ticker_col].str.replace(".", "-", regex=False)

            result = []
            for _, row in df.head(UNIVERSE_FULL_SIZE).iterrows():
                ticker = str(row[ticker_col]).strip()
                name   = str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else ticker
                result.append({"ticker": ticker, "name": name})

            print(f"    ✓ IWB CSV 파싱 완료: {len(result)}개 종목")
            return result

        except Exception as e:
            print(f"    ⚠ IWB CSV 오류 ({url[:60]}...): {e}")
            continue

    return []


def _fetch_iwb_tickers_fallback() -> list[dict]:
    """
    iShares CSV 실패 시 Wikipedia Russell 1000 관련 페이지 또는
    S&P 500 + 추가 종목으로 대체 유니버스를 구성합니다.
    """
    print("    ⚠ IWB CSV 불가 — 대체 유니버스 구성 시도 (S&P 1000 ETF 방식)")

    # PRFZ (iShares Russell 2000) 대신 SPSM/IWR 사용
    # 간단하게 S&P MidCap 400 Wikipedia 목록 사용
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
        resp = requests.get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text), flavor="lxml")
        for t in tables:
            for col in ("Symbol", "Ticker", "Ticker symbol"):
                if col in t.columns and len(t) >= 300:
                    tickers = t[col].astype(str).str.replace(".", "-", regex=False).tolist()
                    print(f"    S&P 400 폴백: {len(tickers)}개 수집")
                    # 이름 컬럼 찾기
                    name_col = next(
                        (c for c in t.columns if "name" in c.lower() or "security" in c.lower()), None
                    )
                    result = []
                    for _, row in t.iterrows():
                        ticker = str(row[col]).strip().replace(".", "-")
                        name   = str(row[name_col]).strip() if name_col else ticker
                        result.append({"ticker": ticker, "name": name})
                    return result
    except Exception as e:
        print(f"    ⚠ S&P 400 폴백도 실패: {e}")

    return []


# ── 유니버스 캐시 관리 ────────────────────────────────────────────────────────
def _load_universe_cache() -> dict | None:
    """캐시된 유니버스를 로드합니다. 없거나 만료되면 None 반환."""
    if not os.path.exists(UNIVERSE_PATH):
        return None
    try:
        with open(UNIVERSE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        fetched_at = data.get("fetched_at", "")
        if not fetched_at:
            return None
        dt = datetime.strptime(fetched_at, "%Y-%m-%d %H:%M")
        if datetime.now() - dt > timedelta(days=UNIVERSE_MAX_AGE_DAYS):
            print(f"  유니버스 캐시 만료 ({fetched_at}) — 갱신 필요")
            return None
        print(f"  유니버스 캐시 유효 ({fetched_at}, {len(data.get('tickers', []))}종목)")
        return data
    except Exception as e:
        print(f"  ⚠ 유니버스 캐시 로드 오류: {e}")
        return None


def _save_universe_cache(tickers_info: list[dict]):
    """미드캡 유니버스(500종목)를 캐시 파일에 저장합니다."""
    _ensure_dirs()
    data = {
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "count": len(tickers_info),
        "tickers": tickers_info,  # [{"ticker": ..., "name": ..., "full_rank": ...}]
    }
    with open(UNIVERSE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 유니버스 캐시 저장: {len(tickers_info)}종목 → {UNIVERSE_PATH}")


def refresh_universe(name_cache: dict) -> list[dict]:
    """
    IWB 1000종목 전체의 시총을 조회하여 501~1000위 종목 500개를
    미드캡 유니버스로 확정하고 캐시에 저장합니다.

    반환: [{"ticker":str, "name":str, "full_rank":int}, ...]  (500개)
    """
    print("\n  ── 유니버스 갱신 시작 (Russell 1000 하위 500종목) ──")

    # 1. IWB CSV에서 1000종목 목록 가져오기
    raw_list = _fetch_iwb_tickers()
    if not raw_list:
        raw_list = _fetch_iwb_tickers_fallback()
    if not raw_list:
        raise RuntimeError("IWB 구성 종목을 가져오지 못했습니다.")

    tickers_1000 = [d["ticker"] for d in raw_list]
    name_from_csv = {d["ticker"]: d["name"] for d in raw_list}

    # 2. 전체 1000종목 시총 수집 (1회성, 약 15~20분)
    print(f"  1000종목 시총 수집 중 (약 15~20분 소요)...")
    results = []
    total = len(tickers_1000)

    for i, ticker in enumerate(tickers_1000):
        try:
            t_obj = yf.Ticker(ticker)
            mcap  = _get_market_cap(t_obj)
            if not mcap:
                continue

            # 이름 우선순위: name_cache > CSV 이름
            if ticker not in name_cache:
                csv_name = name_from_csv.get(ticker, ticker)
                name_cache[ticker] = csv_name

            results.append({
                "ticker":     ticker,
                "name":       name_cache.get(ticker, ticker),
                "market_cap": float(mcap),
            })
        except Exception:
            pass

        if (i + 1) % 100 == 0:
            print(f"    진행: {i+1}/{total} (수집됨: {len(results)}개)")
        if (i + 1) % 50 == 0 and i + 1 < total:
            time.sleep(1.0)

    if not results:
        raise RuntimeError("시총 수집 결과가 없습니다.")

    # 3. 시총 내림차순 정렬 → 501~1000위 추출
    df = (
        pd.DataFrame(results)
        .sort_values("market_cap", ascending=False)
        .reset_index(drop=True)
    )
    df["full_rank"] = range(1, len(df) + 1)
    midcap_df = df[(df["full_rank"] >= MIDCAP_START) & (df["full_rank"] <= MIDCAP_END)]

    universe_list = []
    for _, row in midcap_df.iterrows():
        universe_list.append({
            "ticker":    str(row["ticker"]),
            "name":      str(row["name"]),
            "full_rank": int(row["full_rank"]),
        })

    print(f"  ✓ 유니버스 확정: {len(universe_list)}종목 (전체 {len(df)}개 중 {MIDCAP_START}~{MIDCAP_END}위)")
    _save_universe_cache(universe_list)
    return universe_list


def get_midcap_universe(name_cache: dict, force_refresh: bool = False) -> list[dict]:
    """
    미드캡 유니버스를 반환합니다.
    캐시가 유효하면 캐시를 사용하고, 없거나 만료되면 refresh_universe()를 호출합니다.
    refresh_universe() 실패 시 만료된 캐시라도 반환하여 스크립트 crash를 방지합니다.

    반환: [{"ticker":str, "name":str, "full_rank":int}, ...]
    """
    if not force_refresh:
        cached = _load_universe_cache()
        if cached and cached.get("tickers"):
            return cached["tickers"]

    try:
        return refresh_universe(name_cache)
    except Exception as e:
        print(f"  ⚠ 유니버스 갱신 실패: {e}")
        # 갱신 실패 시 만료된 캐시라도 사용
        stale = _load_stale_universe_cache()
        if stale:
            print(f"  ↩ 만료된 캐시 사용 ({len(stale)}종목) — 다음 실행 시 재시도")
            return stale
        return []


def _load_stale_universe_cache() -> list[dict]:
    """만료 여부 무관하게 캐시된 유니버스를 반환합니다 (비상용)."""
    if not os.path.exists(UNIVERSE_PATH):
        return []
    try:
        with open(UNIVERSE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("tickers", [])
    except Exception:
        return []


# ── 일별 시총 수집 ────────────────────────────────────────────────────────────
def fetch_midcap_data(universe: list[dict], name_cache: dict,
                      batch_size: int = 50) -> pd.DataFrame:
    """
    유니버스 500종목의 현재 시총을 수집하여 순위 DataFrame을 반환합니다.

    반환: rank, ticker, name, market_cap (시총 내림차순 정렬, rank 1=최대)
    """
    tickers = [d["ticker"] for d in universe]
    total   = len(tickers)
    results = []

    print(f"  {total}종목 시총 수집 중...")
    for i in range(0, total, batch_size):
        batch    = tickers[i: i + batch_size]
        batch_no = i // batch_size + 1
        total_batches = (total - 1) // batch_size + 1
        print(f"    배치 {batch_no}/{total_batches} ({len(batch)}개)...")

        for ticker in batch:
            try:
                t_obj = yf.Ticker(ticker)
                mcap  = _get_market_cap(t_obj)
                if not mcap:
                    continue

                # 이름 캐시 갱신
                if ticker not in name_cache:
                    # 유니버스에서 이름 가져오기
                    uni_name = next((d["name"] for d in universe if d["ticker"] == ticker), ticker)
                    name_cache[ticker] = uni_name

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
def _data_path(date: str) -> str:
    _ensure_dirs()
    return os.path.join(MIDCAP_DIR, f"{date}.json")


def save_midcap_data(date: str, df: pd.DataFrame) -> str:
    path    = _data_path(date)
    records = df.to_dict("records")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)
    return path


def load_midcap_data(date: str) -> pd.DataFrame:
    path = _data_path(date)
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


def get_available_midcap_dates() -> list[str]:
    _ensure_dirs()
    return sorted([
        f[:-5] for f in os.listdir(MIDCAP_DIR)
        if f.endswith(".json") and len(f) == 13  # YYYYMMDD.json
    ])
