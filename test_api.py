"""
test_api.py — KRX API 진단 스크립트
실제로 어떤 응답이 오는지 확인합니다.
실행: python test_api.py
"""
import requests, json, io
import pandas as pd

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")

BASE_HDR = {
    "User-Agent": UA,
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

DATE   = "20260428"   # 오늘 근처 확실한 거래일
MARKET = "STK"        # KOSPI

session = requests.Session()

print("=" * 60)
print(f"  KRX API 진단  |  날짜: {DATE}  |  마켓: KOSPI")
print("=" * 60)

# ── Step 1: 세션 초기화 ──────────────────────────────────────
print("\n[1] 세션 초기화 (메인 페이지 방문)...")
try:
    r = session.get("http://data.krx.co.kr/", headers={"User-Agent": UA}, timeout=10)
    print(f"    → 상태코드: {r.status_code}  쿠키: {dict(session.cookies)}")
except Exception as e:
    print(f"    → 실패: {e}")

# ── Step 2: JSON API 직접 호출 ────────────────────────────────
print("\n[2] JSON API 직접 호출 (getJsonData.cmd)...")
try:
    r = session.post(
        "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd",
        data={
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
            "mktId": MARKET,
            "trdDd": DATE,
            "share": "1",
            "money": "1",
            "csvxls_isNo": "false",
        },
        headers={**BASE_HDR,
                 "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "X-Requested-With": "XMLHttpRequest",
                 "Accept": "application/json, text/javascript, */*; q=0.01"},
        timeout=20,
    )
    print(f"    → 상태코드: {r.status_code}  Content-Type: {r.headers.get('Content-Type')}")
    print(f"    → 응답 길이: {len(r.content)} bytes")
    print(f"    → 응답 첫 300자:\n{r.text[:300]}")

    if r.text.strip():
        try:
            d = r.json()
            rows = d.get("output", [])
            print(f"    → output 행 수: {len(rows)}")
            if rows:
                print(f"    → 첫 행 키: {list(rows[0].keys())}")
                print(f"    → 첫 행: {rows[0]}")
        except Exception as je:
            print(f"    → JSON 파싱 실패: {je}")
except Exception as e:
    print(f"    → 실패: {e}")

# ── Step 3: OTP 방식 ─────────────────────────────────────────
print("\n[3] OTP 방식 (GenerateOTP → download_csv)...")
try:
    otp_resp = session.post(
        "http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd",
        data={
            "bld":   "dbms/MDC/STAT/standard/MDCSTAT01501",
            "mktId": MARKET,
            "trdDd": DATE,
            "share": "1",
            "money": "1",
            "name":  "fileDown",
            "url":   "dbms/MDC/STAT/standard/MDCSTAT01501",
        },
        headers=BASE_HDR,
        timeout=15,
    )
    otp = otp_resp.text.strip()
    print(f"    → OTP: {repr(otp[:80])}")
    print(f"    → OTP 길이: {len(otp)}")

    if otp:
        csv_resp = session.post(
            "http://data.krx.co.kr/comm/fileDn/download_csv.cmd",
            data={"code": otp},
            headers={**BASE_HDR,
                     "Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        raw = csv_resp.content
        print(f"    → CSV 응답 길이: {len(raw)} bytes")
        print(f"    → CSV 첫 200 bytes (repr): {repr(raw[:200])}")

        # EUC-KR 디코딩 시도
        try:
            text = raw.decode("euc-kr")
            lines = text.splitlines()
            print(f"    → 줄 수: {len(lines)}")
            print(f"    → 첫 5줄:")
            for ln in lines[:5]:
                print(f"        {repr(ln)}")
        except Exception as de:
            print(f"    → 디코딩 실패: {de}")
except Exception as e:
    print(f"    → 실패: {e}")

print("\n" + "=" * 60)
print("  진단 완료")
print("=" * 60)
