"""
custom_signal_monitor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
관심종목(custom_watchlist.json)의 기술적 신호를 감지하고
Telegram으로 알림을 발송합니다.

신호:
  1. CCI 기준선(0선) 상향돌파  : 전일 CCI < 0  → 당일 CCI >= 0
  2. CCI +100선 상향돌파       : 전일 CCI < 100 → 당일 CCI >= 100
  3. 파라볼릭 SAR 매도 신호    : SAR이 가격 위로 전환 (하락추세 전환)
  4. 파라볼릭 SAR 매수 신호    : SAR이 가격 아래로 전환 (상승추세 전환)

데이터 소스: yfinance (US/KOSPI/KOSDAQ)
"""

import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import yfinance as yf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MARKET_SUFFIX = {
    "kospi":  ".KS",
    "kosdaq": ".KQ",
    "us":     "",
}

MARKET_LABEL = {
    "kospi":  "KOSPI",
    "kosdaq": "KOSDAQ",
    "us":     "미국",
}

CCI_PERIOD = 20
SAR_AF_START = 0.02
SAR_AF_STEP  = 0.02
SAR_AF_MAX   = 0.20


# ── OHLCV 수집 ───────────────────────────────────────────────────────────────
def fetch_ohlcv(ticker: str, market: str, days: int = 90) -> pd.DataFrame:
    """yfinance로 일봉 OHLCV를 수집합니다."""
    suffix    = MARKET_SUFFIX.get(market, "")
    yf_ticker = ticker + suffix
    end       = datetime.now()
    start     = end - timedelta(days=days)

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
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df[["High", "Low", "Close"]].dropna()
    except Exception as e:
        print(f"    ⚠ {yf_ticker} OHLCV 수집 실패: {e}")
        return pd.DataFrame()


# ── CCI 계산 ─────────────────────────────────────────────────────────────────
def compute_cci(df: pd.DataFrame, period: int = CCI_PERIOD) -> pd.Series:
    """일봉 DataFrame(High/Low/Close)으로 CCI를 계산합니다."""
    tp      = (df["High"] + df["Low"] + df["Close"]) / 3
    sma     = tp.rolling(window=period).mean()
    mean_dev = tp.rolling(window=period).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    cci = (tp - sma) / (0.015 * mean_dev)
    return cci


# ── 파라볼릭 SAR 계산 ─────────────────────────────────────────────────────────
def compute_parabolic_sar(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """
    파라볼릭 SAR을 계산합니다.

    반환: (sar_series, trend_series)
      trend: +1 = 상승추세(SAR이 가격 아래), -1 = 하락추세(SAR이 가격 위)
    """
    high  = df["High"].values.astype(float)
    low   = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    n     = len(close)

    sar   = np.zeros(n)
    ep    = np.zeros(n)
    af    = np.zeros(n)
    trend = np.zeros(n, dtype=int)

    # ── 초기값 설정 ──────────────────────────────────────────────────────────
    # 첫 두 봉의 방향으로 초기 추세 결정
    if n < 3:
        return pd.Series(sar, index=df.index), pd.Series(trend, index=df.index)

    trend[0] = 1 if close[1] >= close[0] else -1
    if trend[0] == 1:      # 상승추세 초기화
        sar[0] = low[0]
        ep[0]  = high[0]
    else:                  # 하락추세 초기화
        sar[0] = high[0]
        ep[0]  = low[0]
    af[0] = SAR_AF_START

    # ── 루프 ─────────────────────────────────────────────────────────────────
    for i in range(1, n):
        prev_trend = trend[i - 1]

        if prev_trend == 1:  # ── 상승추세 ──────────────────────────────────
            raw_sar = sar[i - 1] + af[i - 1] * (ep[i - 1] - sar[i - 1])
            # SAR은 직전 두 봉의 저가보다 낮아야 함
            prev2_low = low[i - 2] if i >= 2 else low[i - 1]
            raw_sar   = min(raw_sar, low[i - 1], prev2_low)

            if low[i] < raw_sar:            # 추세 반전 → 하락
                trend[i] = -1
                sar[i]   = ep[i - 1]        # 새 SAR = 이전 EP(고점)
                ep[i]    = low[i]
                af[i]    = SAR_AF_START
            else:                           # 상승추세 유지
                trend[i] = 1
                sar[i]   = raw_sar
                if high[i] > ep[i - 1]:    # 새 고점 갱신
                    ep[i] = high[i]
                    af[i] = min(af[i - 1] + SAR_AF_STEP, SAR_AF_MAX)
                else:
                    ep[i] = ep[i - 1]
                    af[i] = af[i - 1]

        else:  # prev_trend == -1  ── 하락추세 ─────────────────────────────
            raw_sar = sar[i - 1] + af[i - 1] * (ep[i - 1] - sar[i - 1])
            # SAR은 직전 두 봉의 고가보다 높아야 함
            prev2_high = high[i - 2] if i >= 2 else high[i - 1]
            raw_sar    = max(raw_sar, high[i - 1], prev2_high)

            if high[i] > raw_sar:           # 추세 반전 → 상승
                trend[i] = 1
                sar[i]   = ep[i - 1]        # 새 SAR = 이전 EP(저점)
                ep[i]    = high[i]
                af[i]    = SAR_AF_START
            else:                           # 하락추세 유지
                trend[i] = -1
                sar[i]   = raw_sar
                if low[i] < ep[i - 1]:     # 새 저점 갱신
                    ep[i] = low[i]
                    af[i] = min(af[i - 1] + SAR_AF_STEP, SAR_AF_MAX)
                else:
                    ep[i] = ep[i - 1]
                    af[i] = af[i - 1]

    return (
        pd.Series(sar,   index=df.index, name="SAR"),
        pd.Series(trend, index=df.index, name="Trend"),
    )


# ── 신호 감지 ────────────────────────────────────────────────────────────────
def detect_cci_signals(cci: pd.Series) -> list[dict]:
    """CCI 신호를 감지합니다."""
    valid = cci.dropna()
    if len(valid) < 2:
        return []

    prev = float(valid.iloc[-2])
    curr = float(valid.iloc[-1])
    signals = []

    if prev < 0 and curr >= 0:
        signals.append({
            "type":  "cci_zero_cross",
            "label": "📈 CCI 기준선(0) 상향돌파",
            "detail": f"전일 {round(prev,1)} → 당일 {round(curr,1)}",
            "emoji": "📈",
        })

    if prev < 100 and curr >= 100:
        signals.append({
            "type":  "cci_100_cross",
            "label": "🚀 CCI +100선 상향돌파 (과매수 진입)",
            "detail": f"전일 {round(prev,1)} → 당일 {round(curr,1)}",
            "emoji": "🚀",
        })

    return signals


def detect_sar_signals(sar: pd.Series, trend: pd.Series,
                       close: pd.Series) -> list[dict]:
    """파라볼릭 SAR 신호를 감지합니다."""
    if len(trend.dropna()) < 2:
        return []

    valid_idx   = trend.dropna().index
    prev_trend  = int(trend.loc[valid_idx[-2]])
    curr_trend  = int(trend.loc[valid_idx[-1]])
    curr_sar    = float(sar.loc[valid_idx[-1]])
    curr_close  = float(close.loc[valid_idx[-1]])
    signals     = []

    if prev_trend == 1 and curr_trend == -1:
        signals.append({
            "type":  "sar_sell",
            "label": "🔴 파라볼릭 SAR 매도 신호 (상승→하락 전환)",
            "detail": f"SAR {round(curr_sar,2)}  >  종가 {round(curr_close,2)}",
            "emoji": "🔴",
        })

    if prev_trend == -1 and curr_trend == 1:
        signals.append({
            "type":  "sar_buy",
            "label": "🟢 파라볼릭 SAR 매수 신호 (하락→상승 전환)",
            "detail": f"SAR {round(curr_sar,2)}  <  종가 {round(curr_close,2)}",
            "emoji": "🟢",
        })

    return signals


# ── Telegram 발송 ─────────────────────────────────────────────────────────────
def send_telegram(token: str, chat_id: str, message: str) -> bool:
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"    ⚠ Telegram 발송 실패: {e}")
        return False


def build_alert_message(stock: dict, cci_signals: list[dict],
                        sar_signals: list[dict],
                        cci_val: float, sar_val: float,
                        curr_trend: int) -> str:
    mkt   = MARKET_LABEL.get(stock.get("market", "us"), "")
    name  = stock.get("name", stock["ticker"])
    ticker = stock["ticker"]

    trend_str = "▲ 상승추세" if curr_trend == 1 else "▼ 하락추세"
    lines = [
        f"<b>⭐ 관심종목 신호 발생</b>",
        f"",
        f"<b>{name}</b>  <code>{ticker}</code>  [{mkt}]",
        f"CCI: <b>{round(cci_val, 1)}</b>  |  SAR 추세: {trend_str}",
        f"",
    ]

    all_signals = cci_signals + sar_signals
    for sig in all_signals:
        lines.append(f"{sig['label']}")
        lines.append(f"  {sig['detail']}")

    lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ── 메인 모니터링 ─────────────────────────────────────────────────────────────
def run_custom_monitor(telegram_token: str, telegram_chat_id: str,
                       dry_run: bool = False,
                       custom_watchlist: list[dict] | None = None) -> list[dict]:
    """
    관심종목 전체를 순회하며 CCI + 파라볼릭 SAR 신호를 감지합니다.
    dry_run=True 면 Telegram 발송 없이 신호만 반환합니다.
    """
    if custom_watchlist is None:
        # 직접 로드
        import sys
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)
        from scripts.fetcher_custom import load_custom_watchlist
        custom_watchlist = load_custom_watchlist()

    if not custom_watchlist:
        print("  관심종목이 없습니다.")
        return []

    print(f"  관심종목 {len(custom_watchlist)}개 신호 모니터링 시작...")
    results = []

    for stock in custom_watchlist:
        ticker = stock.get("ticker", "")
        market = stock.get("market", "us")
        name   = stock.get("name", ticker)
        print(f"    [{market.upper()}] {ticker} ({name})...")

        df = fetch_ohlcv(ticker, market)
        if df.empty or len(df) < CCI_PERIOD + 5:
            print(f"      ⚠ 데이터 부족 ({len(df)}일)")
            continue

        # CCI
        cci     = compute_cci(df)
        cci_val = float(cci.dropna().iloc[-1])
        cci_signals = detect_cci_signals(cci)

        # 파라볼릭 SAR
        sar, trend = compute_parabolic_sar(df)
        curr_trend  = int(trend.iloc[-1])
        sar_val     = float(sar.iloc[-1])
        sar_signals = detect_sar_signals(sar, trend, df["Close"])

        all_signals = cci_signals + sar_signals

        trend_icon = "▲" if curr_trend == 1 else "▼"
        print(f"      CCI: {round(cci_val,1)}  SAR: {trend_icon}  "
              f"신호: {len(all_signals)}개")

        if all_signals:
            msg = build_alert_message(stock, cci_signals, sar_signals,
                                      cci_val, sar_val, curr_trend)
            if not dry_run:
                ok     = send_telegram(telegram_token, telegram_chat_id, msg)
                status = "✓ 발송" if ok else "✗ 실패"
            else:
                print(f"      [dry-run 메시지]\n{msg}")
                status = "(dry-run)"
            print(f"      {status}")
            for sig in all_signals:
                print(f"        → {sig['label']}")

        results.append({
            "stock":       stock,
            "cci":         round(cci_val, 1),
            "cci_signals": cci_signals,
            "sar_trend":   curr_trend,
            "sar":         round(sar_val, 4),
            "sar_signals": sar_signals,
            "all_signals": all_signals,
        })

        time.sleep(0.5)

    return results


# ── 일별 요약 발송 ───────────────────────────────────────────────────────────
def send_daily_summary(token: str, chat_id: str, results: list[dict]):
    """일별 CCI + SAR 현황 요약 메시지를 발송합니다."""
    if not results:
        return

    lines = [
        f"<b>⭐ 관심종목 신호 요약</b>  {datetime.now().strftime('%Y-%m-%d')}",
        f"",
    ]
    for r in results:
        stock = r["stock"]
        cci   = r["cci"]
        trend = r["sar_trend"]

        cci_icon   = "🔴" if cci >= 100 else ("🟢" if cci >= 0 else ("🟡" if cci >= -100 else "🔵"))
        trend_icon = "▲" if trend == 1 else "▼"
        sig_count  = len(r["all_signals"])
        sig_str    = f"  ⚡{sig_count}건" if sig_count else ""

        lines.append(
            f"{cci_icon}{trend_icon} <b>{stock['name']}</b>  "
            f"CCI {cci}  SAR {trend_icon}{sig_str}"
        )

    send_telegram(token, chat_id, "\n".join(lines))
