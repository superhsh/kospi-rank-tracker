"""
reporter.py
분석 결과 딕셔너리를 받아 self-contained index.html을 생성합니다.
일별/주별/월별 탭 + 장중(시간별) 탭 포함
"""

import json
import os

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_HTML = os.path.join(BASE_DIR, "index.html")

_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>📈 KOSPI/KOSDAQ 시총 순위 상승 트래커</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif;
      background: #f0f2f5; color: #1a1a2e; min-height: 100vh;
    }

    /* ── 헤더 ── */
    header {
      background: linear-gradient(135deg, #0d47a1 0%, #1976d2 100%);
      color: #fff; padding: 24px 32px 20px;
      box-shadow: 0 2px 10px rgba(0,0,0,.25);
    }
    header h1 { font-size: 21px; font-weight: 800; }
    header .meta { margin-top: 5px; font-size: 12px; opacity: .78;
                   display: flex; flex-wrap: wrap; gap: 16px; }

    /* ── 레이아웃 ── */
    .container { max-width: 860px; margin: 0 auto; padding: 22px 16px 48px; }

    /* ── 탭 공통 ── */
    .tab-bar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
    .tab-btn {
      padding: 7px 18px; border: 2px solid transparent; border-radius: 20px;
      cursor: pointer; font-size: 13px; font-weight: 700;
      background: #fff; color: #555;
      transition: all .18s; box-shadow: 0 1px 3px rgba(0,0,0,.08);
    }
    .tab-btn:hover { border-color: #90caf9; }

    /* 마켓 탭 */
    .market-tabs .tab-btn.active { background: #0d47a1; color: #fff; border-color: #0d47a1; }

    /* 기간 탭 — 장중(주황) */
    .period-tabs .tab-btn.active          { background: #2e7d32; color: #fff; border-color: #2e7d32; }
    .period-tabs .tab-btn.intraday.active { background: #e65100; color: #fff; border-color: #e65100; }
    .period-tabs .tab-btn.intraday        { color: #e65100; border-color: #ffe0cc; }

    /* ── 장중 배너 ── */
    .intraday-banner {
      background: #fff3e0; border-left: 4px solid #e65100;
      border-radius: 0 8px 8px 0; padding: 10px 16px;
      margin-bottom: 14px; font-size: 13px; color: #bf360c;
      display: flex; align-items: center; gap: 8px;
    }
    .intraday-banner .time-badge {
      background: #e65100; color: #fff; padding: 2px 10px;
      border-radius: 10px; font-weight: 800; font-size: 13px;
    }

    /* ── 섹션 헤더 ── */
    .section-header {
      display: flex; align-items: baseline;
      justify-content: space-between; margin: 4px 0 12px;
    }
    .section-header h2 { font-size: 14px; font-weight: 700; color: #333; }
    .compare-label {
      font-size: 12px; color: #999; background: #e8f5e9;
      padding: 3px 10px; border-radius: 10px;
    }
    .compare-label.orange { background: #fff3e0; color: #bf360c; }

    /* ── 카드 ── */
    .card {
      background: #fff; border-radius: 14px; padding: 16px 20px;
      margin-bottom: 10px; display: flex; align-items: center; gap: 14px;
      box-shadow: 0 1px 5px rgba(0,0,0,.07);
      transition: transform .15s, box-shadow .15s;
      border-left: 4px solid #e3f2fd;
    }
    .card:hover { transform: translateY(-2px); box-shadow: 0 5px 14px rgba(0,0,0,.11); }
    .card:nth-child(1) { border-left-color: #ffd600; }
    .card:nth-child(2) { border-left-color: #bdbdbd; }
    .card:nth-child(3) { border-left-color: #ff8f00; }
    .card.intraday-card { border-left-color: #ff8f00; }
    .card.intraday-card:nth-child(1) { border-left-color: #e65100; }

    .medal {
      width: 44px; height: 44px; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 16px; font-weight: 900; flex-shrink: 0;
      background: #e8f5e9; color: #2e7d32;
    }
    .medal.m1 { background: #fff8e1; color: #f9a825; }
    .medal.m2 { background: #f5f5f5; color: #757575; }
    .medal.m3 { background: #fff3e0; color: #e65100; }
    .medal.intra { background: #fff3e0; color: #e65100; }
    .medal.intra.m1 { background: #fbe9e7; color: #bf360c; }

    .stock-info { flex: 1; min-width: 0; }
    .stock-name  { font-size: 15px; font-weight: 800;
                   white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .stock-sub   { display: flex; gap: 8px; margin-top: 4px; flex-wrap: wrap; }
    .stock-ticker { font-size: 11px; background: #e3f2fd; color: #1565c0;
                    padding: 2px 8px; border-radius: 8px; font-weight: 600; }
    .stock-mktcap { font-size: 12px; color: #666; }

    .rank-change { text-align: right; flex-shrink: 0; }
    .change-num  { font-size: 28px; font-weight: 900; color: #e53935; line-height: 1; }
    .change-arrow { color: #e53935; font-size: 15px; }
    .rank-path   { font-size: 12px; color: #777; margin-top: 3px; }
    .rank-path strong { color: #333; }

    /* ── 데이터 없음 ── */
    .no-data {
      text-align: center; padding: 44px 20px;
      background: #fff; border-radius: 14px;
      color: #aaa; box-shadow: 0 1px 5px rgba(0,0,0,.06);
    }
    .no-data .icon { font-size: 38px; margin-bottom: 10px; }

    /* ── 푸터 ── */
    footer {
      text-align: center; padding: 20px 16px;
      font-size: 11px; color: #bbb;
      border-top: 1px solid #e0e0e0; margin-top: 16px;
    }

    @media (max-width: 520px) {
      header { padding: 18px 14px 14px; }
      header h1 { font-size: 17px; }
      .change-num { font-size: 22px; }
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

  <!-- 기간 탭 (장중 포함) -->
  <div class="tab-bar period-tabs" id="period-tabs"></div>

  <!-- 장중 배너 (장중 탭일 때만 표시) -->
  <div class="intraday-banner" id="intraday-banner" style="display:none">
    <span>⚡ 장중</span>
    <span class="time-badge" id="intraday-time-badge">-</span>
    <span id="intraday-comp-label">기준</span>
  </div>

  <!-- 섹션 헤더 -->
  <div class="section-header">
    <h2 id="section-title">-</h2>
    <span class="compare-label" id="compare-label"></span>
  </div>

  <!-- 카드 영역 -->
  <div id="cards"></div>

</div>

<footer>
  데이터 출처: 네이버 금융 &nbsp;|&nbsp;
  장중 09:20·11:00·13:00·15:00 KST / 일별 18:30 KST 자동 업데이트
</footer>

<script>
const DATA = /*__DATA__*/null/*__DATA__*/;

let currentMarket  = 'kospi';
let currentPeriod  = 'intraday';   // 기본: 장중 (없으면 daily로 fallback)

const PERIOD_META = {
  intraday: { label: '장중',  title: '장중 순위 상승 Top 5', intraday: true  },
  daily:    { label: '일별',  title: '전일 대비 시총 순위 상승 Top 5' },
  weekly:   { label: '주별',  title: '전주 대비 시총 순위 상승 Top 5' },
  monthly:  { label: '월별',  title: '전월 대비 시총 순위 상승 Top 5' },
};
const MEDAL_CLASS  = ['m1','m2','m3','',''];
const INTRA_MEDAL  = ['m1 intra','intra','intra','intra','intra'];

function fmtDate(d) {
  if (!d || d.length < 8) return d || '-';
  return `${d.slice(0,4)}.${d.slice(4,6)}.${d.slice(6,8)}`;
}
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── 초기화 ── */
function init() {
  if (!DATA) { showError('데이터를 불러올 수 없습니다.'); return; }
  document.getElementById('last-updated').textContent = DATA.updated_at || '-';
  document.getElementById('current-date').textContent = fmtDate(DATA.current_date);

  // 장중 데이터 없으면 일별을 기본으로
  const hasIntraday = DATA.intraday && (
    DATA.intraday.kospi?.available || DATA.intraday.kosdaq?.available
  );
  currentPeriod = hasIntraday ? 'intraday' : 'daily';

  buildPeriodTabs(hasIntraday);
  render();
}

function buildPeriodTabs(hasIntraday) {
  const container = document.getElementById('period-tabs');
  const periods   = hasIntraday
    ? ['intraday', 'daily', 'weekly', 'monthly']
    : ['daily', 'weekly', 'monthly'];

  container.innerHTML = periods.map(p => {
    const meta      = PERIOD_META[p];
    const isIntra   = p === 'intraday';
    const cls       = `tab-btn${isIntra ? ' intraday' : ''}`;
    return `<button class="${cls}" onclick="switchPeriod('${p}')">${meta.label}</button>`;
  }).join('');
}

/* ── 탭 전환 ── */
function switchMarket(m) {
  currentMarket = m;
  document.querySelectorAll('.market-tabs .tab-btn').forEach((btn, i) => {
    btn.classList.toggle('active', (i===0 && m==='kospi') || (i===1 && m==='kosdaq'));
  });
  render();
}

function switchPeriod(p) {
  currentPeriod = p;
  document.querySelectorAll('.period-tabs .tab-btn').forEach(btn => {
    const match = btn.textContent === PERIOD_META[p].label;
    btn.classList.toggle('active', match);
  });
  render();
}

/* ── 렌더링 ── */
function render() {
  const container = document.getElementById('cards');
  const titleEl   = document.getElementById('section-title');
  const labelEl   = document.getElementById('compare-label');
  const banner    = document.getElementById('intraday-banner');

  titleEl.textContent  = PERIOD_META[currentPeriod].title;
  banner.style.display = 'none';
  labelEl.className    = 'compare-label';

  if (currentPeriod === 'intraday') {
    renderIntraday(container, titleEl, labelEl, banner);
  } else {
    renderPeriod(container, labelEl);
  }
}

function renderIntraday(container, titleEl, labelEl, banner) {
  const idata = DATA.intraday?.[currentMarket];

  if (!idata || !idata.available || !idata.top5?.length) {
    labelEl.textContent = '';
    container.innerHTML = noDataHTML(idata?.comparison || '장중 데이터 없음');
    return;
  }

  // 배너 업데이트
  banner.style.display = 'flex';
  document.getElementById('intraday-time-badge').textContent = idata.label_display || '-';
  document.getElementById('intraday-comp-label').textContent = idata.comparison || '';
  labelEl.className   = 'compare-label orange';
  labelEl.textContent = idata.comparison || '';
  titleEl.textContent = `${idata.label_display} 장중 순위 상승 Top 5`;

  container.innerHTML = idata.top5.map((s, i) => `
    <div class="card intraday-card">
      <div class="medal ${INTRA_MEDAL[i]}">${i+1}</div>
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
        <div class="rank-path"><strong>${s.prev_rank}위</strong> → <strong>${s.rank}위</strong></div>
      </div>
    </div>`).join('');
}

function renderPeriod(container, labelEl) {
  const pd = DATA[currentMarket]?.[currentPeriod];

  if (!pd || !pd.available || !pd.top5?.length) {
    labelEl.textContent = '';
    container.innerHTML = noDataHTML(pd?.prev_date ? '기준: ' + fmtDate(pd.prev_date) : '데이터 부족');
    return;
  }

  labelEl.className   = 'compare-label';
  labelEl.textContent = '기준: ' + fmtDate(pd.prev_date);

  container.innerHTML = pd.top5.map((s, i) => `
    <div class="card">
      <div class="medal ${MEDAL_CLASS[i]}">${i+1}</div>
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
        <div class="rank-path"><strong>${s.prev_rank}위</strong> → <strong>${s.rank}위</strong></div>
      </div>
    </div>`).join('');
}

function noDataHTML(msg) {
  return `<div class="no-data">
    <div class="icon">📊</div>
    <p>표시할 데이터가 없습니다.</p>
    <p style="margin-top:8px;font-size:12px;color:#bbb">${esc(msg)}</p>
  </div>`;
}

function showError(msg) {
  document.getElementById('cards').innerHTML = noDataHTML(msg);
}

init();
</script>
</body>
</html>
"""


def generate_html(report_data: dict, output_path: str = OUTPUT_HTML) -> str:
    data_json = json.dumps(report_data, ensure_ascii=False)
    html = _HTML_TEMPLATE.replace("/*__DATA__*/null/*__DATA__*/", data_json)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 리포트 생성 완료: {output_path}")
    return output_path
