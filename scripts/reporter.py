"""
reporter.py
분석 결과 딕셔너리를 받아 self-contained index.html을 생성합니다.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_HTML = os.path.join(BASE_DIR, "index.html")

# ── HTML 템플릿 ────────────────────────────────────────────────────────────────
_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>📈 KOSPI/KOSDAQ 시총 순위 상승 트래커</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR",
                   "Apple SD Gothic Neo", sans-serif;
      background: #f0f2f5;
      color: #1a1a2e;
      min-height: 100vh;
    }

    /* ── 헤더 ── */
    header {
      background: linear-gradient(135deg, #0d47a1 0%, #1976d2 100%);
      color: #fff;
      padding: 28px 32px 22px;
      box-shadow: 0 2px 10px rgba(0,0,0,.25);
    }
    header h1 { font-size: 22px; font-weight: 800; letter-spacing: -0.3px; }
    header .meta {
      margin-top: 6px;
      font-size: 12.5px;
      opacity: .78;
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
    }
    header .meta span { display: flex; align-items: center; gap: 4px; }

    /* ── 레이아웃 ── */
    .container { max-width: 860px; margin: 0 auto; padding: 24px 16px 48px; }

    /* ── 탭 버튼 ── */
    .tab-bar { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }

    .tab-btn {
      padding: 7px 20px;
      border: 2px solid transparent;
      border-radius: 20px;
      cursor: pointer;
      font-size: 13.5px;
      font-weight: 700;
      background: #fff;
      color: #555;
      transition: all .18s;
      box-shadow: 0 1px 3px rgba(0,0,0,.08);
    }
    .tab-btn:hover { border-color: #90caf9; }

    /* 마켓 탭 활성 */
    .market-tabs .tab-btn.active { background: #0d47a1; color: #fff; border-color: #0d47a1; }

    /* 기간 탭 활성 */
    .period-tabs .tab-btn.active { background: #2e7d32; color: #fff; border-color: #2e7d32; }

    /* ── 섹션 헤더 ── */
    .section-header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      margin: 6px 0 14px;
    }
    .section-header h2 { font-size: 15px; font-weight: 700; color: #333; }
    .section-header .compare-label {
      font-size: 12px;
      color: #999;
      background: #e8f5e9;
      padding: 3px 10px;
      border-radius: 10px;
    }

    /* ── 순위 카드 ── */
    .card {
      background: #fff;
      border-radius: 14px;
      padding: 18px 20px;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 16px;
      box-shadow: 0 1px 5px rgba(0,0,0,.07);
      transition: transform .15s, box-shadow .15s;
      border-left: 4px solid #e3f2fd;
    }
    .card:hover { transform: translateY(-2px); box-shadow: 0 5px 14px rgba(0,0,0,.11); }
    .card:nth-child(1) { border-left-color: #ffd600; }
    .card:nth-child(2) { border-left-color: #bdbdbd; }
    .card:nth-child(3) { border-left-color: #ff8f00; }

    /* 순위 메달 */
    .medal {
      width: 46px; height: 46px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 17px; font-weight: 900;
      flex-shrink: 0;
      background: #e8f5e9; color: #2e7d32;
    }
    .medal.m1 { background: #fff8e1; color: #f9a825; }
    .medal.m2 { background: #f5f5f5; color: #757575; }
    .medal.m3 { background: #fff3e0; color: #e65100; }

    /* 종목 정보 */
    .stock-info { flex: 1; min-width: 0; }
    .stock-name  { font-size: 16px; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .stock-sub   { display: flex; gap: 10px; margin-top: 4px; flex-wrap: wrap; }
    .stock-ticker { font-size: 11.5px; background: #e3f2fd; color: #1565c0; padding: 2px 8px; border-radius: 8px; font-weight: 600; }
    .stock-mktcap { font-size: 12px; color: #666; }

    /* 순위 변동 */
    .rank-change { text-align: right; flex-shrink: 0; }
    .change-num  { font-size: 30px; font-weight: 900; color: #e53935; line-height: 1; }
    .change-arrow { color: #e53935; font-size: 16px; }
    .rank-path   { font-size: 12px; color: #777; margin-top: 3px; }
    .rank-path strong { color: #333; }

    /* 데이터 없음 */
    .no-data {
      text-align: center;
      padding: 44px 20px;
      background: #fff;
      border-radius: 14px;
      color: #aaa;
      box-shadow: 0 1px 5px rgba(0,0,0,.06);
    }
    .no-data .icon { font-size: 40px; margin-bottom: 10px; }
    .no-data p { font-size: 14px; }

    /* ── 푸터 ── */
    footer {
      text-align: center;
      padding: 24px 16px;
      font-size: 11.5px;
      color: #bbb;
      border-top: 1px solid #e0e0e0;
      margin-top: 16px;
    }

    @media (max-width: 520px) {
      header { padding: 20px 16px 16px; }
      header h1 { font-size: 18px; }
      .change-num { font-size: 24px; }
    }
  </style>
</head>
<body>

<header>
  <h1>📈 KOSPI / KOSDAQ 시총 순위 상승 트래커</h1>
  <div class="meta">
    <span>🕐 마지막 업데이트: <b id="last-updated">-</b></span>
    <span>📅 기준일: <b id="current-date">-</b></span>
  </div>
</header>

<div class="container">

  <!-- 마켓 탭 -->
  <div class="tab-bar market-tabs">
    <button class="tab-btn active" onclick="switchMarket('kospi')">KOSPI</button>
    <button class="tab-btn"        onclick="switchMarket('kosdaq')">KOSDAQ</button>
  </div>

  <!-- 기간 탭 -->
  <div class="tab-bar period-tabs">
    <button class="tab-btn active" onclick="switchPeriod('daily')">일별</button>
    <button class="tab-btn"        onclick="switchPeriod('weekly')">주별</button>
    <button class="tab-btn"        onclick="switchPeriod('monthly')">월별</button>
  </div>

  <!-- 섹션 헤더 -->
  <div class="section-header">
    <h2 id="section-title">전일 대비 시총 순위 상승 Top 5</h2>
    <span class="compare-label" id="compare-label"></span>
  </div>

  <!-- 카드 영역 -->
  <div id="cards"></div>

</div>

<footer>
  데이터 출처: 한국거래소(KRX) · 네이버 금융 &nbsp;|&nbsp;
  매 영업일 18:00 KST 자동 업데이트 (GitHub Actions)
</footer>

<script>
// ── 데이터 주입 (Python에서 치환) ─────────────────────────────────────────
const DATA = /*__DATA__*/null/*__DATA__*/;

// ── 상태 ─────────────────────────────────────────────────────────────────
let currentMarket = 'kospi';
let currentPeriod = 'daily';

const PERIOD_TITLES = {
  daily:   '전일 대비 시총 순위 상승 Top 5',
  weekly:  '전주 대비 시총 순위 상승 Top 5',
  monthly: '전월 대비 시총 순위 상승 Top 5',
};

const MEDAL_CLASS = ['m1','m2','m3','',''];

// ── 초기화 ────────────────────────────────────────────────────────────────
function init() {
  if (!DATA) {
    document.getElementById('cards').innerHTML =
      '<div class="no-data"><div class="icon">⚠️</div><p>데이터를 불러올 수 없습니다.</p></div>';
    return;
  }
  document.getElementById('last-updated').textContent = DATA.updated_at || '-';
  document.getElementById('current-date').textContent = fmtDate(DATA.current_date);
  render();
}

// ── 탭 전환 ───────────────────────────────────────────────────────────────
function switchMarket(m) {
  currentMarket = m;
  document.querySelectorAll('.market-tabs .tab-btn').forEach((btn, i) => {
    btn.classList.toggle('active', (i === 0 && m === 'kospi') || (i === 1 && m === 'kosdaq'));
  });
  render();
}

function switchPeriod(p) {
  currentPeriod = p;
  document.querySelectorAll('.period-tabs .tab-btn').forEach((btn, i) => {
    const match = ['daily','weekly','monthly'][i] === p;
    btn.classList.toggle('active', match);
  });
  render();
}

// ── 렌더링 ────────────────────────────────────────────────────────────────
function render() {
  const container = document.getElementById('cards');
  const titleEl   = document.getElementById('section-title');
  const labelEl   = document.getElementById('compare-label');

  titleEl.textContent = PERIOD_TITLES[currentPeriod];

  const periodData = DATA[currentMarket]?.[currentPeriod];

  if (!periodData || !periodData.available || periodData.top5.length === 0) {
    labelEl.textContent = '';
    container.innerHTML = `
      <div class="no-data">
        <div class="icon">📊</div>
        <p>비교 데이터가 부족합니다.</p>
        <p style="margin-top:8px;font-size:12px">
          ${periodData?.prev_date
            ? '기준 날짜: ' + fmtDate(periodData.prev_date)
            : '더 많은 데이터가 수집되면 표시됩니다.'}
        </p>
      </div>`;
    return;
  }

  labelEl.textContent = '기준: ' + fmtDate(periodData.prev_date);

  container.innerHTML = periodData.top5.map((s, i) => `
    <div class="card">
      <div class="medal ${MEDAL_CLASS[i]}">${i + 1}</div>
      <div class="stock-info">
        <div class="stock-name">${esc(s.name)}</div>
        <div class="stock-sub">
          <span class="stock-ticker">${esc(s.ticker)}</span>
          <span class="stock-mktcap">시총 ${esc(s.market_cap_str)}</span>
        </div>
      </div>
      <div class="rank-change">
        <div class="change-arrow">▲</div>
        <div class="change-num">+${s.rank_change}</div>
        <div class="rank-path">
          <strong>${s.prev_rank}위</strong> → <strong>${s.rank}위</strong>
        </div>
      </div>
    </div>
  `).join('');
}

// ── 유틸 ─────────────────────────────────────────────────────────────────
function fmtDate(d) {
  if (!d || d.length < 8) return d || '-';
  return `${d.slice(0,4)}.${d.slice(4,6)}.${d.slice(6,8)}`;
}

function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

init();
</script>
</body>
</html>
"""


def generate_html(report_data: dict, output_path: str = OUTPUT_HTML) -> str:
    """
    report_data를 HTML에 임베드하여 index.html을 생성합니다.

    Args:
        report_data : processor.build_report_data()의 반환값
        output_path : 저장 경로 (기본값: 프로젝트 루트/index.html)
    Returns:
        저장된 파일 경로
    """
    data_json = json.dumps(report_data, ensure_ascii=False)
    html = _HTML_TEMPLATE.replace(
        "/*__DATA__*/null/*__DATA__*/",
        data_json
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML 리포트 생성 완료: {output_path}")
    return output_path
