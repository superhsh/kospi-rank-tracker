"""
run_cci_monitor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
관심종목의 CCI 신호를 감지하고 Telegram으로 알림을 발송합니다.

실행:
    python run_cci_monitor.py                   # 정상 실행 (Telegram 발송)
    python run_cci_monitor.py --dry-run         # 신호 감지만 (발송 없음)
    python run_cci_monitor.py --summary         # 신호 + 일별 현황 요약 발송
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.cci_monitor import run_monitor, send_daily_summary


def main():
    parser = argparse.ArgumentParser(description="CCI 신호 모니터링 + Telegram 알림")
    parser.add_argument("--dry-run", action="store_true",
                        help="Telegram 발송 없이 신호만 출력")
    parser.add_argument("--summary", action="store_true",
                        help="신호 외에 일별 전체 현황 요약도 발송")
    args = parser.parse_args()

    # ── Telegram 자격증명 ──────────────────────────────────────────────────────
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not args.dry_run and (not token or not chat_id):
        print("  ⚠ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수가 없습니다.")
        print("    --dry-run 옵션으로 테스트하거나 환경변수를 설정하세요.")
        sys.exit(1)

    today = datetime.now().strftime("%Y%m%d")
    dt    = datetime.strptime(today, "%Y%m%d")

    print(f"\n{'='*54}")
    print(f"  CCI 모니터링 시작 — {today}")
    if args.dry_run:
        print(f"  [DRY-RUN 모드] Telegram 발송 없음")
    print(f"{'='*54}")

    # 주말에는 한국/미국 시장 데이터가 없으므로 스킵
    # (코인은 24/7이지만 일관성을 위해 동일 처리)
    if dt.weekday() >= 5:
        print(f"  ⚠ {today}은 주말입니다. CCI 모니터링 스킵.")
        sys.exit(0)

    results = run_monitor(
        telegram_token=token,
        telegram_chat_id=chat_id,
        dry_run=args.dry_run,
    )

    if args.summary and results and not args.dry_run:
        print("\n  일별 현황 요약 발송 중...")
        send_daily_summary(token, chat_id, results)

    # ── 결과 요약 출력 ────────────────────────────────────────────────────────
    signal_count = sum(len(r["signals"]) for r in results)
    print(f"\n{'='*54}")
    print(f"  완료 — 종목 {len(results)}개 / 신호 {signal_count}개 감지")
    for r in results:
        if r["signals"]:
            for sig in r["signals"]:
                print(f"  ★ {r['stock']['ticker']} ({r['stock']['name']}): {sig['label']}")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
