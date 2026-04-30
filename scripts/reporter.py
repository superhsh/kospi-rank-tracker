"""
reporter.py
분석 결과 딕셔너리를 받아 self-contained index.html을 생성합니다.
탭 구성: 장중 | 일별 | 주별 | 월별 | 히스토리(Chart.js 라인 차트)
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

    /* 기간 탭 */
    .period-tabs .tab-btn.active          { background: #2e7d32; color: #fff; border-color: #2e7d32; }
    .period-tabs .tab-btn.intraday.active { background: #e65100; color: #fff; border-color: #e65100; }
    .period-tabs .tab-btn.intraday        { color: #e65100; border-color: #ffe0cc; }
    .period-tabs .tab-btn.history.active  { background: #6a1b9a; color: #fff; border-color: #6a1b9a; }
    .period-tabs .tab-btn.history         { color: #6a1b9a; border-color: #e1bee7; }

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

    /* ── 히스토리 차트 영역 ── */
    .history-section { background: #fff; border-radius: 14px; padding: 20px;
                       box-shadow: 0 1px 5px rgba(0,0,0,.07); }

    .history-controls {
      display: flex; flex-wrap: wrap; gap: 12px;
      align-items: center; margin-bottom: 16px;
    }
    .history-controls label { font-size: 12px; color: #555; font-weight: 600; }

    .filter-group { display: flex; gap: 6px; flex-wrap: wrap; }
    .filter-btn {
      padding: 4px 12px; border: 1.5px solid #ddd; border-radius: 12px;
      background: #fff; font-size: 12px; font-weight: 600; color: #666;
      cursor: pointer; transition: all .15s;
    }
    .filter-btn.active { background: #6a1b9a; color: #fff; border-color: #6a1b9a; }
    .filter-btn:hover:not(.active) { border-color: #ba68c8; color: #6a1b9a; }

    .top-n-select {
      padding: 4px 10px; border: 1.5px solid #ddd; border-radius: 12px;
      font-size: 12px; font-weight: 600; color: #555; cursor: pointer;
      background: #fff;
    }

    .chart-wrapper {
      position: relative; width: 100%; height: 420px;
    }
    .chart-wrapper canvas { width: 100% !important; height: 100% !important; }

    .history-legend {
      display: flex; flex-wrap: wrap; gap: 8px;
      margin-top: 16px; padding-top: 14px;
      border-top: 1px solid #f0f0f0;
    }
    .legend-item {
      display: flex; align-items: center; gap: 5px;
      padding: 3px 10px; border-radius: 10px; cursor: pointer;
      font-size: 12px; font-weight: 600; border: 1.5px solid transparent;
      background: #fafafa; color: #555; transition: all .15s;
    }
    .legend-item:hover { background: #f3e5f5; border-color: #ce93d8; }
    .legend-item.hidden-stock { opacity: .38; text-decoration: line-through; }
    .legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

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
      .chart-wrapper { height: 300px; }
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
  <div class="tab-bar period-tabs" id="period-tabs"></div>

  <!-- 장중 배너 (장중 탭일 때만 표시) -->
  <div class="intraday-banner" id="intraday-banner" style="display:none">
    <span>⚡ 장중</span>
    <span class="time-badge" id="intraday-time-badge">-</span>
    <span id="intraday-comp-label">기준</span>
  </div>

  <!-- 섹션 헤더 (히스토리 탭에서는 숨김) -->
  <div class="section-header" id="section-header">
    <h2 id="section-title">-</h2>
    <span class="compare-label" id="compare-label"></span>
  </div>

  <!-- 카드 / 차트 영역 -->
  <div id="cards"></div>

</div>

<footer>
  데이터 출처: 네이버 금융 &nbsp;|&nbsp;
  장중 09:20·11:00·13:00·15:00 KST / 일별 16:00 KST 자동 업데이트
</footer>

<!-- Chart.js (히스토리 탭 사용) -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
const DATA = /*__DATA__*/null/*__DATA__*/;

let currentMarket = 'kospi';
let currentPeriod = 'intraday';

const PERIOD_META = {
  intraday: { label: '장중',   title: '장중 순위 상승 Top 5',         intraday: true },
  daily:    { label: '일별',   title: '전일 대비 시총 순위 상승 Top 5' },
  weekly:   { label: '주별',   title: '전주 대비 시총 순위 상승 Top 5' },
  monthly:  { label: '월별',   title: '전월 대비 시총 순위 상승 Top 5' },
  history:  { label: '히스토리', title: '시총 순위 변동 히스토리',       history: true },
};
const MEDAL_CLASS = ['m1','m2','m3','',''];
const INTRA_MEDAL = ['m1 intra','intra','intra','intra','intra'];

// ── 히스토리 상태 ──
let historyCache  = {};         // market → history JSON
let historyChart  = null;       // Chart.js 인스턴스
let historyFilter = 'all';      // 'all' | 'daily' | 'intraday'
let historyTopN   = 15;         // 기본 표시 종목 수
let hiddenTickers = new Set();  // 사용자가 숨긴 종목

// 30색 팔레트
const PALETTE = [
  '#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00',
  '#a65628','#f781bf','#4e79a7','#59a14f','#f28e2b',
  '#76b7b2','#edc948','#b07aa1','#ff9da7','#9c755f',
  '#bab0ac','#1b9e77','#d95f02','#7570b3','#e7298a',
  '#66a61e','#e6ab02','#a6761d','#666666','#8dd3c7',
  '#bebada','#fb8072','#80b1d3','#fdb462','#b3de69',
];

function fmtDate(d) {
  if (!d || d.length < 8) return d || '-';
  return `${d.slice(0,4)}.${d.slice(4,6)}.${d.slice(6,8)}`;
}
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                  .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── 초기화 ─────────────────────────────────────────────────────────────── */
function init() {
  if (!DATA) { showError('데이터를 불러올 수 없습니다.'); return; }
  document.getElementById('last-updated').textContent = DATA.updated_at || '-';
  document.getElementById('current-date').textContent = fmtDate(DATA.current_date);

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
    ? ['intraday','daily','weekly','monthly','history']
    : ['daily','weekly','monthly','history'];

  container.innerHTML = periods.map(p => {
    const cls = `tab-btn${p==='intraday' ? ' intraday' : p==='history' ? ' history' : ''}`;
    return `<button class="${cls}" onclick="switchPeriod('${p}')">${PERIOD_META[p].label}</button>`;
  }).join('');
}

/* ── 탭 전환 ────────────────────────────────────────────────────────────── */
function switchMarket(m) {
  currentMarket = m;
  document.querySelectorAll('.market-tabs .tab-btn').forEach((btn, i) => {
    btn.classList.toggle('active', (i===0 && m==='kospi') || (i===1 && m==='kosdaq'));
  });
  if (currentPeriod === 'history') {
    hiddenTickers.clear();
    renderHistory();
  } else {
    render();
  }
}

function switchPeriod(p) {
  currentPeriod = p;
  document.querySelectorAll('.period-tabs .tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.textContent === PERIOD_META[p].label);
  });
  if (p === 'history') {
    hiddenTickers.clear();
    renderHistory();
  } else {
    render();
  }
}

/* ── 일반 탭 렌더링 ──────────────────────────────────────────────────────── */
function render() {
  const container = document.getElementById('cards');
  const titleEl   = document.getElementById('section-title');
  const labelEl   = document.getElementById('compare-label');
  const banner    = document.getElementById('intraday-banner');
  const header    = document.getElementById('section-header');

  header.style.display = 'flex';
  titleEl.textContent  = PERIOD_META[currentPeriod].title;
  banner.style.display = 'none';
  labelEl.className    = 'compare-label';

  // 히스토리 차트 인스턴스 파기
  if (historyChart) { historyChart.destroy(); historyChart = null; }

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

/* ── 히스토리 탭 렌더링 ──────────────────────────────────────────────────── */
async function renderHistory() {
  const container = document.getElementById('cards');
  const header    = document.getElementById('section-header');
  const banner    = document.getElementById('intraday-banner');

  header.style.display = 'none';
  banner.style.display = 'none';

  // 기존 차트 파기
  if (historyChart) { historyChart.destroy(); historyChart = null; }

  container.innerHTML = `<div class="no-data"><div class="icon">📊</div><p>히스토리 로딩 중...</p></div>`;

  // JSON fetch (캐싱)
  if (!historyCache[currentMarket]) {
    try {
      const resp = await fetch(`data/history_${currentMarket}.json`);
      if (!resp.ok) throw new Error('not found');
      historyCache[currentMarket] = await resp.json();
    } catch(e) {
      container.innerHTML = noDataHTML('히스토리 데이터를 아직 불러올 수 없습니다.\n(run_daily.py 또는 run_hourly.py를 실행 후 업데이트됩니다.)');
      return;
    }
  }

  const hdata = historyCache[currentMarket];
  if (!hdata.timeline?.length) {
    container.innerHTML = noDataHTML('히스토리 데이터가 없습니다.');
    return;
  }

  drawHistoryChart(hdata);
}

function drawHistoryChart(hdata) {
  const container = document.getElementById('cards');

  // ── 컨트롤 UI ──
  container.innerHTML = `
    <div class="history-section">
      <div class="history-controls">
        <div>
          <label>표시 범위 &nbsp;</label>
          <div class="filter-group" id="filter-group">
            <button class="filter-btn${historyFilter==='all'?' active':''}"      onclick="setHistoryFilter('all')">전체</button>
            <button class="filter-btn${historyFilter==='daily'?' active':''}"    onclick="setHistoryFilter('daily')">일별만</button>
            <button class="filter-btn${historyFilter==='intraday'?' active':''}" onclick="setHistoryFilter('intraday')">장중만</button>
          </div>
        </div>
        <div>
          <label>종목 수 &nbsp;</label>
          <select class="top-n-select" id="top-n-select" onchange="setTopN(this.value)">
            <option value="5"  ${historyTopN===5 ?'selected':''}>상위 5개</option>
            <option value="10" ${historyTopN===10?'selected':''}>상위 10개</option>
            <option value="15" ${historyTopN===15?'selected':''}>상위 15개</option>
            <option value="20" ${historyTopN===20?'selected':''}>상위 20개</option>
            <option value="30" ${historyTopN===30?'selected':''}>상위 30개</option>
          </select>
        </div>
      </div>
      <div class="chart-wrapper">
        <canvas id="historyChart"></canvas>
      </div>
      <div class="history-legend" id="history-legend"></div>
    </div>`;

  buildChart(hdata);
}

function buildChart(hdata) {
  // ── 타임라인 필터 ──
  let timeline = hdata.timeline;
  if (historyFilter === 'daily')    timeline = timeline.filter(t => t.type === 'daily');
  if (historyFilter === 'intraday') timeline = timeline.filter(t => t.type === 'intraday');

  const labels    = timeline.map(t => t.label);
  const tickers   = hdata.tickers.slice(0, historyTopN);

  // ── 데이터셋 생성 ──
  const datasets = tickers.map((ticker, idx) => {
    const color   = PALETTE[idx % PALETTE.length];
    const isHidden = hiddenTickers.has(ticker);
    return {
      label:           hdata.names[ticker] || ticker,
      ticker:          ticker,
      data:            timeline.map(t => t.ranks[ticker] ?? null),
      borderColor:     color,
      backgroundColor: color + '22',
      borderWidth:     2,
      pointRadius:     timeline.map(t => t.type === 'intraday' ? 3 : 4),
      pointStyle:      timeline.map(t => t.type === 'intraday' ? 'triangle' : 'circle'),
      spanGaps:        true,
      tension:         0.25,
      hidden:          isHidden,
    };
  });

  const ctx = document.getElementById('historyChart').getContext('2d');
  if (historyChart) historyChart.destroy();

  historyChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction:         { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },   // 커스텀 범례 사용
        tooltip: {
          callbacks: {
            title: (items) => items[0]?.label || '',
            label: (item) => {
              const val = item.raw;
              return val != null ? ` ${item.dataset.label}: ${val}위` : null;
            },
          },
          filter: (item) => item.raw != null,
        },
      },
      scales: {
        x: {
          ticks: {
            maxRotation: 45, minRotation: 30,
            font: { size: 10 },
            callback: function(val, idx) {
              // 장중 라벨은 장중 필터일 때만 전부 표시, 아니면 일별만 표시
              const entry = timeline[idx];
              if (!entry) return null;
              if (historyFilter !== 'intraday' && entry.type === 'intraday') return null;
              return entry.label;
            },
          },
          grid: { color: '#f0f0f0' },
        },
        y: {
          reverse:    true,    // 1위가 위로
          min:        1,
          suggestedMax: Math.min(historyTopN + 5, 100),
          ticks: {
            stepSize: 5,
            font: { size: 11 },
            callback: (v) => `${v}위`,
          },
          grid: { color: '#f0f0f0' },
          title: { display: true, text: '순위', font: { size: 11 }, color: '#999' },
        },
      },
    },
  });

  // ── 커스텀 범례 ──
  const legendEl = document.getElementById('history-legend');
  if (legendEl) {
    legendEl.innerHTML = tickers.map((ticker, idx) => {
      const color = PALETTE[idx % PALETTE.length];
      const name  = esc(hdata.names[ticker] || ticker);
      const cls   = hiddenTickers.has(ticker) ? 'legend-item hidden-stock' : 'legend-item';
      return `<div class="${cls}" onclick="toggleTicker('${ticker}')" data-ticker="${ticker}">
        <span class="legend-dot" style="background:${color}"></span>${name}
      </div>`;
    }).join('');
  }
}

/* ── 히스토리 컨트롤 콜백 ─────────────────────────────────────────────────── */
function setHistoryFilter(f) {
  historyFilter = f;
  document.querySelectorAll('#filter-group .filter-btn').forEach(btn => {
    btn.classList.toggle('active',
      (f==='all' && btn.textContent==='전체') ||
      (f==='daily' && btn.textContent==='일별만') ||
      (f==='intraday' && btn.textContent==='장중만')
    );
  });
  const hdata = historyCache[currentMarket];
  if (hdata) buildChart(hdata);
}

function setTopN(n) {
  historyTopN = parseInt(n, 10);
  hiddenTickers.clear();
  const hdata = historyCache[currentMarket];
  if (hdata) buildChart(hdata);
}

function toggleTicker(ticker) {
  if (hiddenTickers.has(ticker)) {
    hiddenTickers.delete(ticker);
  } else {
    hiddenTickers.add(ticker);
  }
  // 차트 데이터셋 토글
  const ds = historyChart?.data.datasets.find(d => d.ticker === ticker);
  if (ds && historyChart) {
    const meta = historyChart.getDatasetMeta(historyChart.data.datasets.indexOf(ds));
    meta.hidden = hiddenTickers.has(ticker);
    historyChart.update();
  }
  // 범례 토글
  document.querySelectorAll(`[data-ticker="${ticker}"]`).forEach(el => {
    el.classList.toggle('hidden-stock', hiddenTickers.has(ticker));
  });
}

/* ── 공통 ────────────────────────────────────────────────────────────────── */
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
