"""
run_custom_signals.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
관심종목의 CCI + 파라볼릭 SAR 신호를 감지하고 Telegram 알림을 발송합니다.

실행:
    python run_custom_signals.py              # 신호 발생 시 Telegram 발송
    python run_custom_signals.py --dry-run   # 발송 없이 신호만 출력
    python run_custom_signals.py --summary   # 전체 현황 요약도 발송
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.custom_signal_monitor import (
    run_custom_monitor,
    save_signal_results,
    send_daily_summary,
)


def main():
    parser = argparse.ArgumentParser(description="관심종목 CCI + 파라볼릭 SAR 모니터")
    parser.add_argument("--dry-run", action="store_true",
                        help="Telegram 발송 없이 신호만 출력")
    args = parser.parse_args()

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID",   "")

    if not args.dry_run and (not token or not chat_id):
        print("⚠ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수가 없습니다.")
        print("  --dry-run 으로 실행하거나 환경변수를 설정하세요.")
        sys.exit(1)

    print(f"\n{'='*54}")
    print(f"  ⭐ 관심종목 신호 모니터  "
          f"{'(dry-run)' if args.dry_run else ''}")
    print(f"{'='*54}\n")

    results = run_custom_monitor(
        telegram_token=token,
        telegram_chat_id=chat_id,
        dry_run=args.dry_run,
    )

    total_signals = sum(len(r["all_signals"]) for r in results)
    print(f"\n  결과: {len(results)}개 종목 스캔  |  신호 {total_signals}건")

    # 신호 결과를 JSON으로 저장 (UI 배지 표시용, dry-run 포함 항상 실행)
    save_signal_results(results)

    # 신호 요약 Telegram 발송 (신호 있는 종목만, dry-run 제외)
    if not args.dry_run:
        print("  신호 요약 발송 중...")
        send_daily_summary(token, chat_id, results)

    print(f"{'='*54}\n")


if __name__ == "__main__":
    main()
