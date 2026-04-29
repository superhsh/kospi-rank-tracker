# KOSPI/KOSDAQ 시총 순위 상승 트래커 — 설정 가이드

## 1단계 — 로컬 환경 준비

```bash
# 의존성 설치
pip install -r requirements.txt

# 과거 3개월치 데이터 일괄 수집 (최초 1회, 약 10~15분 소요)
python backfill.py

# 정상 수집 확인
python run_daily.py
# → index.html 생성 완료 메시지 확인
```

## 2단계 — GitHub 저장소 생성 및 업로드

```bash
# GitHub에서 새 퍼블릭 저장소 생성 후:
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<YOUR_USERNAME>/<REPO_NAME>.git
git push -u origin main
```

> **⚠ data/ 폴더**는 백필 결과 JSON이 들어 있으므로 반드시 함께 push하세요.

## 3단계 — GitHub Pages 활성화

1. 저장소 → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / Folder: **/ (root)**
4. Save → 잠시 후 `https://<username>.github.io/<repo>/` 접속

## 4단계 — GitHub Actions 자동화 확인

- **Actions** 탭에서 `📈 Update Stock Rankings` 워크플로우가 보이면 정상
- **매 평일 18:30 KST** 자동 실행 (cron: `30 9 * * 1-5` UTC)
- 수동 실행: Actions 탭 → 워크플로우 선택 → **Run workflow**

## 파일 구조

```
kospi-rank-tracker/
├── .github/workflows/
│   └── update.yml          ← GitHub Actions 자동화
├── scripts/
│   ├── fetcher.py           ← KRX/Naver 데이터 수집
│   ├── processor.py         ← 순위 변동 계산
│   └── reporter.py          ← HTML 생성
├── data/
│   ├── kospi/YYYYMMDD.json  ← 날짜별 시총 스냅샷
│   ├── kosdaq/YYYYMMDD.json
│   └── ticker_names.json    ← 종목명 캐시
├── backfill.py              ← 최초 1회: 과거 데이터 수집
├── run_daily.py             ← 매일 실행: 수집 + HTML 재생성
├── requirements.txt
└── index.html               ← 자동 생성 리포트 (GitHub Pages로 서빙)
```

## 자주 묻는 질문

**Q. 공휴일에는?**
KRX API가 빈 데이터를 반환하므로 자동으로 스킵됩니다.

**Q. 과거 특정 날짜 데이터만 다시 받고 싶을 때?**
```bash
python run_daily.py --date 20250401
```

**Q. 백필 범위를 바꾸고 싶을 때?**
```bash
python backfill.py --months 6          # 6개월치
python backfill.py --start 20240101    # 특정 날짜부터
```

**Q. 요청이 너무 빠르면?**
```bash
python backfill.py --sleep 2.0   # 요청 간격 2초로 늘리기
```
