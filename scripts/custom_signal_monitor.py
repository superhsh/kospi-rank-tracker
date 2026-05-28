"""
custom_signal_monitor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
관심종목(custom_watchlist.json)의 기술적 신호를 감지하고
Telegram으로 알림을 발송합니다.

신호:
  1. CCI 기준선(0선) 상향돌파       : 전일 CCI < 0   → 당일 CCI >= 0
  2. CCI +100선 상향돌파            : 전일 CCI < 100 → 당일 CCI >= 100
  3. 파라볼릭 SAR 매도 신호         : SAR이 가격 위로 전환 (하락추세 전환)
  4. 파라볼릭 SAR 매수 신호         : SAR이 가격 아래로 전환 (상승추세 전환)
  5. Slow Stoch %K 침체선 상향돌파  : 전일 %K < 20 → 당일 %K >= 20
  6. Slow Stoch %K/%D 골든크로스    : 전일 %K < %D → 당일 %K >= %D

Slow Stochastics 파라미터: K=6, D=3, Smooth=3  /  과열=80, 침체=20

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

CCI_PERIOD   = 20
SAR_AF_START = 0.02
SAR_AF_STEP  = 0.02
SAR_AF_MAX   = 0.20

# Slow Stochastics 파라미터
STOCH_K_PERIOD   = 6     # Fast %K 계산 기간
STOCH_D_PERIOD   = 3     # Fast %K → Slow %K 스무딩
STOCH_SMOOTH     = 3     # Slow %K → Slow %D 스무딩
STOCH_OVERSOLD   = 20.0  # 침체 기준선
STOCH_OVERBOUGHT = 80.0  # 과열 기준선


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
    tp       = (df["High"] + df["Low"] + df["Close"]) / 3
    sma      = tp.rolling(window=period).mean()
    mean_dev = tp.rolling(window=period).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    return (tp - sma) / (0.015 * mean_dev)


# ── 파라볼릭 SAR 계산 ────────────────────────────────────────────────────────
def compute_parabolic_sar(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """
    파라볼릭 SAR을 계산합니다.
    반환: (sar_series, trend_series)
      trend: +1 = 상승추세(SAR 아래), -1 = 하락추세(SAR 위)
    """
    high  = df["High"].values.astype(float)
    low   = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    n     = len(close)

    sar   = np.zeros(n)
    ep    = np.zeros(n)
    af    = np.zeros(n)
    trend = np.zeros(n, dtype=int)

    if n < 3:
        return pd.Series(sar, index=df.index), pd.Series(trend, index=df.index)

    trend[0] = 1 if close[1] >= close[0] else -1
    if trend[0] == 1:
        sar[0], ep[0] = low[0], high[0]
    else:
        sar[0], ep[0] = high[0], low[0]
    af[0] = SAR_AF_START

    for i in range(1, n):
        pt = trend[i - 1]
        if pt == 1:
            raw = sar[i - 1] + af[i - 1] * (ep[i - 1] - sar[i - 1])
            raw = min(raw, low[i - 1], low[i - 2] if i >= 2 else low[i - 1])
            if low[i] < raw:
                trend[i], sar[i], ep[i], af[i] = -1, ep[i - 1], low[i], SAR_AF_START
            else:
                trend[i], sar[i] = 1, raw
                if high[i] > ep[i - 1]:
                    ep[i] = high[i]
                    af[i] = min(af[i - 1] + SAR_AF_STEP, SAR_AF_MAX)
                else:
                    ep[i], af[i] = ep[i - 1], af[i - 1]
        else:
            raw = sar[i - 1] + af[i - 1] * (ep[i - 1] - sar[i - 1])
            raw = max(raw, high[i - 1], high[i - 2] if i >= 2 else high[i - 1])
            if high[i] > raw:
                trend[i], sar[i], ep[i], af[i] = 1, ep[i - 1], high[i], SAR_AF_START
            else:
                trend[i], sar[i] = -1, raw
                if low[i] < ep[i - 1]:
                    ep[i] = low[i]
                    af[i] = min(af[i - 1] + SAR_AF_STEP, SAR_AF_MAX)
                else:
                    ep[i], af[i] = ep[i - 1], af[i - 1]

    return (
        pd.Series(sar,   index=df.index, name="SAR"),
        pd.Series(trend, index=df.index, name="Trend"),
    )


# ── Slow Stochastics 계산 ────────────────────────────────────────────────────
def compute_slow_stochastics(
    df:       pd.DataFrame,
    k_period: int = STOCH_K_PERIOD,
    d_period: int = STOCH_D_PERIOD,
    smooth:   int = STOCH_SMOOTH,
) -> tuple[pd.Series, pd.Series]:
    """
    Slow Stochastics (6, 3, 3) 계산.

    Fast %K  = (Close - LowestLow_k) / (HighestHigh_k - LowestLow_k) × 100
    Slow %K  = SMA(Fast %K, d_period)     ← 스무딩된 %K
    Slow %D  = SMA(Slow %K, smooth)       ← 시그널선

    반환: (slow_k, slow_d)
    """
    low_min  = df["Low"].rolling(window=k_period).min()
    high_max = df["High"].rolling(window=k_period).max()
    denom    = high_max - low_min
    fast_k   = (df["Close"] - low_min) / denom.replace(0, np.nan) * 100
    fast_k   = fast_k.fillna(50.0)  # High == Low 구간 중립값

    slow_k = fast_k.rolling(window=d_period).mean()
    slow_d = slow_k.rolling(window=smooth).mean()

    return slow_k, slow_d


# ── 신호 감지 ────────────────────────────────────────────────────────────────
def detect_cci_signals(cci: pd.Series) -> list[dict]:
    """CCI 신호를 감지합니다."""
    valid = cci.dropna()
    if len(valid) < 2:
        return []

    prev, curr = float(valid.iloc[-2]), float(valid.iloc[-1])
    signals = []

    if prev < 0 and curr >= 0:
        signals.append({
            "type":   "cci_zero_cross",
            "label":  "📈 CCI 기준선(0) 상향돌파",
            "detail": f"전일 {round(prev,1)} → 당일 {round(curr,1)}",
        })
    if prev < 100 and curr >= 100:
        signals.append({
            "type":   "cci_100_cross",
            "label":  "🚀 CCI +100선 상향돌파 (과매수 진입)",
            "detail": f"전일 {round(prev,1)} → 당일 {round(curr,1)}",
        })
    return signals


def detect_sar_signals(sar: pd.Series, trend: pd.Series,
                       close: pd.Series) -> list[dict]:
    """파라볼릭 SAR 신호를 감지합니다."""
    valid_idx  = trend.dropna().index
    if len(valid_idx) < 2:
        return []

    prev_trend = int(trend.loc[valid_idx[-2]])
    curr_trend = int(trend.loc[valid_idx[-1]])
    curr_sar   = float(sar.loc[valid_idx[-1]])
    curr_close = float(close.loc[valid_idx[-1]])
    signals    = []

    if prev_trend == 1 and curr_trend == -1:
        signals.append({
            "type":   "sar_sell",
            "label":  "🔴 파라볼릭 SAR 매도 신호 (상승→하락 전환)",
            "detail": f"SAR {round(curr_sar,2)}  >  종가 {round(curr_close,2)}",
        })
    if prev_trend == -1 and curr_trend == 1:
        signals.append({
            "type":   "sar_buy",
            "label":  "🟢 파라볼릭 SAR 매수 신호 (하락→상승 전환)",
            "detail": f"SAR {round(curr_sar,2)}  <  종가 {round(curr_close,2)}",
        })
    return signals


def detect_stoch_signals(
    slow_k: pd.Series,
    slow_d: pd.Series,
    oversold:    float = STOCH_OVERSOLD,
    overbought:  float = STOCH_OVERBOUGHT,
) -> list[dict]:
    """
    Slow Stochastics 신호를 감지합니다.
      - %K 침체선(20) 상향 돌파: 전일 %K < 20 → 당일 %K >= 20
      - %K/%D 골든크로스       : 전일 %K < %D → 당일 %K >= %D
    """
    common = slow_k.dropna().index.intersection(slow_d.dropna().index)
    if len(common) < 2:
        return []

    vk = slow_k.loc[common]
    vd = slow_d.loc[common]
    prev_k, curr_k = float(vk.iloc[-2]), float(vk.iloc[-1])
    prev_d, curr_d = float(vd.iloc[-2]), float(vd.iloc[-1])

    signals = []

    if prev_k < oversold and curr_k >= oversold:
        signals.append({
            "type":   "stoch_oversold_exit",
            "label":  f"🔵 Slow Stoch %K 침체선({int(oversold)}) 상향돌파",
            "detail": f"%K {round(prev_k,1)} → {round(curr_k,1)}  |  %D {round(curr_d,1)}",
        })
    if prev_k < prev_d and curr_k >= curr_d:
        signals.append({
            "type":   "stoch_golden_cross",
            "label":  "🟡 Slow Stoch %K/%D 골든크로스",
            "detail": f"%K {round(curr_k,1)}  ↑  %D {round(curr_d,1)}",
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


def build_alert_message(
    stock:         dict,
    cci_signals:   list[dict],
    sar_signals:   list[dict],
    stoch_signals: list[dict],
    cci_val:       float,
    sar_val:       float,
    curr_trend:    int,
    slow_k_val:    float,
    slow_d_val:    float,
) -> str:
    mkt    = MARKET_LABEL.get(stock.get("market", "us"), "")
    name   = stock.get("name", stock["ticker"])
    ticker = stock["ticker"]

    trend_str  = "▲ 상승추세" if curr_trend == 1 else "▼ 하락추세"
    stoch_zone = (
        " 🔴과열" if slow_k_val >= STOCH_OVERBOUGHT else
        " 🔵침체" if slow_k_val <= STOCH_OVERSOLD   else ""
    )

    lines = [
        "<b>⭐ 관심종목 신호 발생</b>",
        "",
        f"<b>{name}</b>  <code>{ticker}</code>  [{mkt}]",
        f"CCI(20): <b>{round(cci_val,1)}</b>  |  SAR: {trend_str}",
        f"Stoch({STOCH_K_PERIOD},{STOCH_D_PERIOD},{STOCH_SMOOTH})  "
        f"%K: <b>{round(slow_k_val,1)}</b>  %D: {round(slow_d_val,1)}{stoch_zone}",
        "",
    ]
    for sig in cci_signals + sar_signals + stoch_signals:
        lines.append(sig["label"])
        lines.append(f"  {sig['detail']}")

    lines.append(f"\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


# ── 메인 모니터링 ─────────────────────────────────────────────────────────────
def run_custom_monitor(
    telegram_token:   str,
    telegram_chat_id: str,
    dry_run:          bool = False,
    custom_watchlist: list[dict] | None = None,
) -> list[dict]:
    """
    관심종목 전체를 순회하며 CCI + 파라볼릭 SAR + Slow Stochastics 신호를 감지합니다.
    dry_run=True 면 Telegram 발송 없이 신호만 반환합니다.
    """
    if custom_watchlist is None:
        import sys
        if BASE_DIR not in sys.path:
            sys.path.insert(0, BASE_DIR)
        from scripts.fetcher_custom import load_custom_watchlist
        custom_watchlist = load_custom_watchlist()

    if not custom_watchlist:
        print("  관심종목이 없습니다.")
        return []

    min_bars = max(CCI_PERIOD + 5,
                   STOCH_K_PERIOD + STOCH_D_PERIOD + STOCH_SMOOTH + 5)

    print(f"  관심종목 {len(custom_watchlist)}개 신호 모니터링 시작...")
    results = []

    for stock in custom_watchlist:
        ticker = stock.get("ticker", "")
        market = stock.get("market", "us")
        name   = stock.get("name", ticker)
        print(f"    [{market.upper()}] {ticker} ({name})...")

        df = fetch_ohlcv(ticker, market)
        if df.empty or len(df) < min_bars:
            print(f"      ⚠ 데이터 부족 ({len(df)}일, 필요: {min_bars}일)")
            continue

        # CCI
        cci         = compute_cci(df)
        cci_val     = float(cci.dropna().iloc[-1])
        cci_signals = detect_cci_signals(cci)

        # 파라볼릭 SAR
        sar, trend  = compute_parabolic_sar(df)
        curr_trend  = int(trend.iloc[-1])
        sar_val     = float(sar.iloc[-1])
        sar_signals = detect_sar_signals(sar, trend, df["Close"])

        # Slow Stochastics
        slow_k, slow_d = compute_slow_stochastics(df)
        slow_k_val     = float(slow_k.dropna().iloc[-1])
        slow_d_val     = float(slow_d.dropna().iloc[-1])
        stoch_signals  = detect_stoch_signals(slow_k, slow_d)

        all_signals = cci_signals + sar_signals + stoch_signals

        trend_icon = "▲" if curr_trend == 1 else "▼"
        print(f"      CCI:{round(cci_val,1)}  SAR:{trend_icon}  "
              f"%K:{round(slow_k_val,1)}/%D:{round(slow_d_val,1)}  "
              f"신호:{len(all_signals)}건")

        if all_signals:
            if dry_run:
                msg = build_alert_message(
                    stock, cci_signals, sar_signals, stoch_signals,
                    cci_val, sar_val, curr_trend, slow_k_val, slow_d_val,
                )
                print(f"      [dry-run 미리보기]\n{msg}")
            for sig in all_signals:
                print(f"        → {sig['label']}")

        results.append({
            "stock":         stock,
            "cci":           round(cci_val, 1),
            "cci_signals":   cci_signals,
            "sar_trend":     curr_trend,
            "sar":           round(sar_val, 4),
            "sar_signals":   sar_signals,
            "slow_k":        round(slow_k_val, 1),
            "slow_d":        round(slow_d_val, 1),
            "stoch_signals": stoch_signals,
            "all_signals":   all_signals,
        })

        time.sleep(0.5)

    return results


# ── 신호 결과 JSON 저장 ──────────────────────────────────────────────────────
def save_signal_results(results: list[dict]) -> str:
    """
    신호 감지 결과를 data/signal_latest.json 에 저장합니다.
    UI에서 관심종목 일별 카드에 신호 배지를 표시하는 데 사용합니다.

    저장 형식:
      {
        "updated_at": "2026-05-27 08:00",
        "signals": {
          "AAPL_us": {
            "ticker": "AAPL", "market": "us", "name": "Apple",
            "signals": [{"type":..., "label":..., "detail":...}, ...]
          },
          ...  ← 신호 있는 종목만 저장
        }
      }
    """
    out_path = os.path.join(BASE_DIR, "data", "signal_latest.json")
    signals_by_key = {}
    for r in results:
        if not r["all_signals"]:
            continue
        stock = r["stock"]
        key   = f"{stock['ticker']}_{stock.get('market','us')}"
        signals_by_key[key] = {
            "ticker":  stock["ticker"],
            "market":  stock.get("market", "us"),
            "name":    stock.get("name", stock["ticker"]),
            "signals": r["all_signals"],
        }

    data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "signals":    signals_by_key,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    import json
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 신호 결과 저장: {out_path} ({len(signals_by_key)}개 종목)")
    return out_path


# ── 신호 요약 발송 (신호 있는 종목만) ────────────────────────────────────────
def send_daily_summary(token: str, chat_id: str, results: list[dict]):
    """
    신호가 발생한 종목만 포함한 요약 메시지를 Telegram으로 발송합니다.
    신호 없는 종목은 표시하지 않으며, 신호가 전혀 없으면 '신호 없음' 메시지를 발송합니다.
    """
    signal_results = [r for r in results if r["all_signals"]]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not signal_results:
        msg = (
            f"<b>⭐ 관심종목 신호 요약</b>  {now_str}\n\n"
            f"🔕 오늘 감지된 신호가 없습니다.\n"
            f"<i>(관심종목 {len(results)}개 스캔 완료)</i>"
        )
        send_telegram(token, chat_id, msg)
        return

    lines = [
        f"<b>⭐ 관심종목 신호 요약</b>  {now_str}",
        f"<i>신호 발생 {len(signal_results)}개 종목 / 전체 {len(results)}개 스캔</i>",
        "",
    ]

    for r in signal_results:
        stock  = r["stock"]
        mkt    = MARKET_LABEL.get(stock.get("market", "us"), "")
        lines.append(f"<b>{stock['name']}</b>  <code>{stock['ticker']}</code>  [{mkt}]")
        for sig in r["all_signals"]:
            lines.append(f"  {sig['label']}")
            lines.append(f"  <i>{sig['detail']}</i>")
        lines.append("")

    lines.append(f"🕐 {now_str}")
    msg = "\n".join(lines)
    if len(msg) > 4000:
        msg = msg[:4000] + "\n…(생략)"

    send_telegram(token, chat_id, msg)
