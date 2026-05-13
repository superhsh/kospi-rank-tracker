"""
cci_monitor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
관심종목 watchlist의 CCI(Commodity Channel Index) 신호를 감지하고
Telegram으로 알림을 발송합니다.

신호 종류:
  - CCI 0선 상향돌파: 전일 CCI < 0 → 당일 CCI >= 0
  - CCI -100선 상향돌파(과매도 탈출): 전일 CCI < -100 → 당일 CCI >= -100
  - CCI +100선 돌파(과매수 진입): 전일 CCI < 100 → 당일 CCI >= 100

데이터 소스:
  - 한국 (kospi/kosdaq): yfinance (ticker + ".KS" / ".KQ")
  - 미국 (sp500/nasdaq100/midcap): yfinance (ticker 그대로)
  - 코인 (coin): CoinGecko OHLCV API
"""

import json
import os
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST_PATH = os.path.join(BASE_DIR, "data", "watchlist.json")

CCI_PERIOD = 20  # 표준 CCI 기간

# ── 시장별 yfinance 티커 변환 ────────────────────────────────────────────────
MARKET_SUFFIX = {
    "kospi":    ".KS",
    "kosdaq":   ".KQ",
    "sp500":    "",
    "nasdaq100":"",
    "midcap":   "",
    "coin":     None,  # CoinGecko 별도 처리
}

MARKET_LABEL = {
    "kospi":     "KOSPI",
    "kosdaq":    "KOSDAQ",
    "sp500":     "S&P 500",
    "nasdaq100": "NASDAQ 100",
    "midcap":    "Russell 중형주",
    "coin":      "코인",
}

COINGECKO_IDS = {}  # coin ticker → CoinGecko id 캐시


# ── CCI 계산 ─────────────────────────────────────────────────────────────────
def compute_cci(df: pd.DataFrame, period: int = CCI_PERIOD) -> pd.Series:
    """
    일봉 DataFrame(High/Low/Close 컬럼 필요)으로 CCI를 계산합니다.
    """
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    sma = tp.rolling(window=period).mean()
    mean_dev = tp.rolling(window=period).apply(
        lambda x: abs(x - x.mean()).mean(), raw=True
    )
    cci = (tp - sma) / (0.015 * mean_dev)
    return cci


# ── yfinance OHLCV 수집 (한국/미국) ──────────────────────────────────────────
def fetch_ohlcv_yf(ticker: str, market: str, days: int = 60) -> pd.DataFrame:
    """yfinance로 일봉 OHLCV를 수집합니다."""
    suffix = MARKET_SUFFIX.get(market, "")
    yf_ticker = ticker + suffix

    end   = datetime.now()
    start = end - timedelta(days=days)

    try:
        df = yf.download(
            yf_ticker,
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return pd.DataFrame()
        # 멀티레벨 컬럼 평탄화 (단일 종목은 불필요하지만 방어적으로 처리)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df[["High", "Low", "Close"]].dropna()
    except Exception as e:
        print(f"    ⚠ {yf_ticker} OHLCV 수집 실패: {e}")
        return pd.DataFrame()


# ── CoinGecko OHLCV 수집 (코인) ──────────────────────────────────────────────
def _get_coingecko_id(ticker: str) -> str | None:
    """ticker 심볼 → CoinGecko id 변환."""
    if ticker in COINGECKO_IDS:
        return COINGECKO_IDS[ticker]
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": ticker},
            timeout=10,
        )
        resp.raise_for_status()
        coins = resp.json().get("coins", [])
        for c in coins:
            if c.get("symbol", "").upper() == ticker.upper():
                COINGECKO_IDS[ticker] = c["id"]
                return c["id"]
    except Exception as e:
        print(f"    ⚠ CoinGecko ID 검색 실패 ({ticker}): {e}")
    return None


def fetch_ohlcv_coin(ticker: str, days: int = 60) -> pd.DataFrame:
    """CoinGecko OHLC API로 일봉 데이터를 수집합니다."""
    cg_id = _get_coingecko_id(ticker)
    if not cg_id:
        return pd.DataFrame()
    try:
        resp = requests.get(
            f"https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc",
            params={"vs_currency": "usd", "days": days},
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()
        if not raw:
            return pd.DataFrame()
        df = pd.DataFrame(raw, columns=["timestamp", "Open", "High", "Low", "Close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.set_index("timestamp").sort_index()
        return df[["High", "Low", "Close"]].dropna()
    except Exception as e:
        print(f"    ⚠ CoinGecko OHLCV 실패 ({ticker}): {e}")
        return pd.DataFrame()


# ── 신호 감지 ────────────────────────────────────────────────────────────────
def detect_signals(cci: pd.Series) -> list[dict]:
    """
    CCI 시리즈에서 당일 발생한 신호를 감지합니다.

    반환: [{"type": "zero_cross" | "oversold_exit" | "overbought_enter",
             "label": str, "prev_cci": float, "curr_cci": float}, ...]
    """
    if len(cci.dropna()) < 2:
        return []

    valid = cci.dropna()
    prev = float(valid.iloc[-2])
    curr = float(valid.iloc[-1])
    signals = []

    # 0선 상향돌파
    if prev < 0 and curr >= 0:
        signals.append({
            "type":     "zero_cross",
            "label":    "📈 CCI 0선 상향돌파",
            "prev_cci": round(prev, 1),
            "curr_cci": round(curr, 1),
        })

    # -100선 상향돌파 (과매도 탈출)
    if prev < -100 and curr >= -100:
        signals.append({
            "type":     "oversold_exit",
            "label":    "🔄 CCI -100 과매도 탈출",
            "prev_cci": round(prev, 1),
            "curr_cci": round(curr, 1),
        })

    # +100선 돌파 (과매수 진입)
    if prev < 100 and curr >= 100:
        signals.append({
            "type":     "overbought_enter",
            "label":    "🚀 CCI +100 과매수 진입",
            "prev_cci": round(prev, 1),
            "curr_cci": round(curr, 1),
        })

    return signals


# ── Telegram 발송 ─────────────────────────────────────────────────────────────
def send_telegram(token: str, chat_id: str, message: str) -> bool:
    """Telegram Bot API로 메시지를 발송합니다."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"    ⚠ Telegram 발송 실패: {e}")
        return False


def build_alert_message(stock: dict, signals: list[dict], cci_latest: float) -> str:
    """Telegram 알림 메시지를 구성합니다."""
    mkt_label = MARKET_LABEL.get(stock.get("market", ""), stock.get("market", ""))
    lines = [
        f"<b>📊 CCI 신호 발생</b>",
        f"",
        f"<b>{stock['name']}</b>  <code>{stock['ticker']}</code>",
        f"시장: {mkt_label}",
        f"현재 CCI: <b>{round(cci_latest, 1)}</b>",
        f"",
    ]
    for sig in signals:
        lines.append(
            f"{sig['label']}\n"
            f"  전일: {sig['prev_cci']} → 당일: {sig['curr_cci']}"
        )
    lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ── 워치리스트 로드 ───────────────────────────────────────────────────────────
def load_watchlist() -> list[dict]:
    """data/watchlist.json에서 관심종목 목록을 로드합니다."""
    if not os.path.exists(WATCHLIST_PATH):
        return []
    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("stocks", [])
    except Exception as e:
        print(f"  ⚠ watchlist.json 로드 오류: {e}")
        return []


# ── 메인 모니터링 루프 ───────────────────────────────────────────────────────
def run_monitor(telegram_token: str, telegram_chat_id: str,
                dry_run: bool = False) -> list[dict]:
    """
    워치리스트 전체를 순회하며 CCI 신호를 감지하고 Telegram 알림을 발송합니다.

    dry_run=True 이면 Telegram 발송 없이 신호만 반환합니다.
    반환: [{"stock": dict, "signals": list, "cci": float}, ...]
    """
    stocks = load_watchlist()
    if not stocks:
        print("  관심종목이 없습니다.")
        return []

    print(f"  관심종목 {len(stocks)}개 CCI 모니터링 시작...")
    results = []

    for stock in stocks:
        ticker = stock.get("ticker", "")
        market = stock.get("market", "")
        name   = stock.get("name", ticker)
        print(f"    [{market}] {ticker} ({name})...")

        # OHLCV 수집
        if market == "coin":
            df = fetch_ohlcv_coin(ticker)
        else:
            df = fetch_ohlcv_yf(ticker, market)

        if df.empty or len(df) < CCI_PERIOD + 2:
            print(f"      ⚠ 데이터 부족 ({len(df)}일)")
            continue

        # CCI 계산
        cci = compute_cci(df)
        signals = detect_signals(cci)
        cci_latest = float(cci.dropna().iloc[-1])

        print(f"      CCI: {round(cci_latest, 1)}  신호: {len(signals)}개")

        if signals:
            msg = build_alert_message(stock, signals, cci_latest)
            if not dry_run:
                ok = send_telegram(telegram_token, telegram_chat_id, msg)
                status = "✓ 발송" if ok else "✗ 실패"
            else:
                status = "(dry-run)"
            print(f"      {status}")
            for sig in signals:
                print(f"        → {sig['label']}")

        results.append({
            "stock":   stock,
            "signals": signals,
            "cci":     round(cci_latest, 1),
        })

        time.sleep(0.5)  # API rate limit 방지

    return results


# ── 일별 요약 발송 (신호 없을 때도 선택적으로) ───────────────────────────────
def send_daily_summary(token: str, chat_id: str, results: list[dict]):
    """일별 CCI 현황 요약 메시지를 발송합니다."""
    if not results:
        return

    lines = [
        f"<b>📋 CCI 일별 현황</b>  {datetime.now().strftime('%Y-%m-%d')}",
        f"",
    ]
    for r in results:
        stock   = r["stock"]
        cci_val = r["cci"]
        sigs    = r["signals"]
        ticker  = stock["ticker"]
        name    = stock["name"]

        if cci_val >= 100:
            icon = "🔴"
        elif cci_val >= 0:
            icon = "🟢"
        elif cci_val >= -100:
            icon = "🟡"
        else:
            icon = "🔵"

        sig_str = " ".join(s["label"] for s in sigs) if sigs else ""
        lines.append(f"{icon} <b>{name}</b> CCI {cci_val} {sig_str}")

    send_telegram(token, chat_id, "\n".join(lines))
