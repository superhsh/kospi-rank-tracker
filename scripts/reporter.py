"""
reporter.py
분석 결과 딕셔너리를 받아 self-contained index.html을 생성합니다.

탭 구성: 장중 | 일별 | 주별 | 월별
각 탭 하단에 해당 기간 Top5 종목의 순위 변동 히스토리 차트 포함
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

    /* ── 히스토리 차트 박스 ── */
    .hist-box {
      background: #fff; border-radius: 14px; padding: 18px 20px 14px;
      margin-top: 18px;
      box-shadow: 0 1px 5px rgba(0,0,0,.07);
      border-top: 3px solid #e3f2fd;
    }
    .hist-box.intraday { border-top-color: #ffe0b2; }
    .hist-box.daily    { border-top-color: #c8e6c9; }
    .hist-box.weekly   { border-top-color: #bbdefb; }
    .hist-box.monthly  { border-top-color: #e1bee7; }

    .hist-title {
      font-size: 13px; font-weight: 700; color: #555;
      margin-bottom: 14px; display: flex; align-items: center; gap: 6px;
    }
    .hist-title .hist-badge {
      font-size: 11px; font-weight: 700; padding: 2px 9px;
      border-radius: 8px; color: #fff;
    }
    .hist-badge.intraday { background: #e65100; }
    .hist-badge.daily    { background: #2e7d32; }
    .hist-badge.weekly   { background: #1565c0; }
    .hist-badge.monthly  { background: #6a1b9a; }

    .hist-chart-wrap {
      position: relative; width: 100%; height: 280px;
    }
    .hist-chart-wrap canvas { width: 100% !important; height: 100% !important; }

    .hist-legend {
      display: flex; flex-wrap: wrap; gap: 10px;
      margin-top: 12px; padding-top: 10px;
      border-top: 1px solid #f5f5f5;
    }
    .hist-legend-item {
      display: flex; align-items: center; gap: 5px;
      font-size: 12px; font-weight: 600; color: #444;
    }
    .hist-legend-dot {
      width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
    }

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
      .hist-chart-wrap { height: 220px; }
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

  <!-- 장중 배너 -->
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

  <!-- Top5 카드 영역 -->
  <div id="cards"></div>

  <!-- 히스토리 차트 영역 -->
  <div id="hist-section"></div>

</div>

<footer>
  데이터 출처: 네이버 금융 &nbsp;|&nbsp;
  장중 09:20·11:00·13:00·15:00 KST / 일별 16:00 KST 자동 업데이트
</footer>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
const DATA = /*__DATA__*/null/*__DATA__*/;

let currentMarket = 'kospi';
let currentPeriod = 'intraday';
let activeChart   = null;   // 현재 Chart.js 인스턴스

// ── 색각 이상자(적녹색약) 안전 팔레트 ────────────────────────────────────
// IBM Carbon Colorblind-safe 5색 기반
// 파랑·주황·자홍·황금·보라 → 적녹색약(Deuteranopia/Protanopia) 모두 구분 가능
// 색상 + 선 패턴 + 포인트 모양 3중 식별 체계
const CB_PALETTE = [
  { color:'#648FFF', dash:[],         point:'circle',   width:3   }, // 파랑  실선   ●
  { color:'#FE6100', dash:[8,4],      point:'triangle', width:2.8 }, // 주황  장대시  ▲
  { color:'#DC267F', dash:[3,3],      point:'rect',     width:2.8 }, // 자홍  점선   ■
  { color:'#FFB000', dash:[10,3,2,3], point:'rectRot',  width:2.8 }, // 황금  혼합선  ◆
  { color:'#785EF0', dash:[6,4],      point:'star',     width:2.8 }, // 보라  파선   ★
  // secondary (장중 차트용 - 추가 종목)
  { color:'#648FFF', dash:[3,3],      point:'crossRot', width:2   },
  { color:'#FE6100', dash:[],         point:'star',     width:2   },
  { color:'#DC267F', dash:[8,4],      point:'circle',   width:2   },
  { color:'#FFB000', dash:[5,5],      point:'triangle', width:2   },
  { color:'#785EF0', dash:[10,3,2,3], point:'rect',     width:2   },
  { color:'#648FFF', dash:[5,5],      point:'rectRot',  width:1.8 },
  { color:'#FE6100', dash:[3,3],      point:'crossRot', width:1.8 },
  { color:'#DC267F', dash:[6,4],      point:'star',     width:1.8 },
  { color:'#FFB000', dash:[],         point:'circle',   width:1.8 },
  { color:'#785EF0', dash:[8,4],      point:'triangle', width:1.8 },
];
// Top5 전용 별칭 (하위 호환)
const TOP5_STYLES = CB_PALETTE;

const PERIOD_META = {
  intraday: { label:'장중',  title:'장중 순위 상승 Top 5',         cls:'intraday',
              histTitle:'장중 Top5 진입 종목 — 최근 30일 일별 순위 변동' },
  daily:    { label:'일별',  title:'전일 대비 시총 순위 상승 Top 5', cls:'daily',
              histTitle:'최근 1개월 일별 순위 변동 이력' },
  weekly:   { label:'주별',  title:'전주 대비 시총 순위 상승 Top 5', cls:'weekly',
              histTitle:'최근 3개월 주별 순위 변동 이력' },
  monthly:  { label:'월별',  title:'전월 대비 시총 순위 상승 Top 5', cls:'monthly',
              histTitle:'전체 기간 월별 순위 변동 이력' },
};
const MEDAL_CLASS = ['m1','m2','m3','',''];
const INTRA_MEDAL = ['m1 intra','intra','intra','intra','intra'];

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

  // 항상 4개 탭 표시 (장중 데이터가 없어도 탭은 유지)
  currentPeriod = 'intraday';
  buildPeriodTabs();
  render();
}

function buildPeriodTabs() {
  const container = document.getElementById('period-tabs');
  const periods   = ['intraday','daily','weekly','monthly'];
  container.innerHTML = periods.map(p => {
    const cls = `tab-btn${p === 'intraday' ? ' intraday' : ''}`;
    return `<button class="${cls}" onclick="switchPeriod('${p}')">${PERIOD_META[p].label}</button>`;
  }).join('');
}

/* ── 탭 전환 ────────────────────────────────────────────────────────────── */
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
    btn.classList.toggle('active', btn.textContent === PERIOD_META[p].label);
  });
  render();
}

/* ── 메인 렌더링 ────────────────────────────────────────────────────────── */
function render() {
  // 기존 차트 파기
  if (activeChart) { activeChart.destroy(); activeChart = null; }

  const titleEl  = document.getElementById('section-title');
  const labelEl  = document.getElementById('compare-label');
  const banner   = document.getElementById('intraday-banner');
  titleEl.textContent  = PERIOD_META[currentPeriod].title;
  banner.style.display = 'none';
  labelEl.className    = 'compare-label';

  if (currentPeriod === 'intraday') {
    renderIntraday(titleEl, labelEl, banner);
  } else {
    renderPeriod(labelEl);
  }
}

/* ── 장중 탭 ─────────────────────────────────────────────────────────────── */
function renderIntraday(titleEl, labelEl, banner) {
  const cards = document.getElementById('cards');
  const idata = DATA.intraday?.[currentMarket];

  if (!idata || !idata.available || !idata.top5?.length) {
    labelEl.textContent = '';
    cards.innerHTML     = noDataHTML(idata?.comparison || '장중 데이터 없음');
    document.getElementById('hist-section').innerHTML = '';
    return;
  }

  banner.style.display = 'flex';
  document.getElementById('intraday-time-badge').textContent = idata.label_display || '-';
  document.getElementById('intraday-comp-label').textContent = idata.comparison || '';
  labelEl.className    = 'compare-label orange';
  labelEl.textContent  = idata.comparison || '';
  titleEl.textContent  = `${idata.label_display} 장중 순위 상승 Top 5`;

  cards.innerHTML = idata.top5.map((s, i) => `
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

  renderHistoryChart(idata.history, 'intraday');
}

/* ── 일별/주별/월별 탭 ──────────────────────────────────────────────────── */
function renderPeriod(labelEl) {
  const cards = document.getElementById('cards');
  const pd    = DATA[currentMarket]?.[currentPeriod];

  if (!pd || !pd.available || !pd.top5?.length) {
    labelEl.textContent = '';
    cards.innerHTML     = noDataHTML(pd?.prev_date ? '기준: ' + fmtDate(pd.prev_date) : '데이터 부족');
    document.getElementById('hist-section').innerHTML = '';
    return;
  }

  labelEl.className   = 'compare-label';
  labelEl.textContent = '기준: ' + fmtDate(pd.prev_date);

  cards.innerHTML = pd.top5.map((s, i) => `
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

  renderHistoryChart(pd.history, currentPeriod);
}

/* ── 히스토리 차트 렌더링 ───────────────────────────────────────────────── */
function renderHistoryChart(hdata, period) {
  const section = document.getElementById('hist-section');
  section.innerHTML = '';

  if (!hdata || !hdata.timeline?.length) return;

  const meta = PERIOD_META[period];

  section.innerHTML = `
    <div class="hist-box ${period}">
      <div class="hist-title">
        <span class="hist-badge ${period}">${meta.label}</span>
        ${esc(meta.histTitle)}
      </div>
      <div class="hist-chart-wrap">
        <canvas id="histCanvas"></canvas>
      </div>
      <div class="hist-legend" id="hist-legend"></div>
    </div>`;

  const labels   = hdata.timeline.map(t => t.label);
  const tickers  = hdata.tickers;

  const datasets = tickers.map((ticker, idx) => {
    const st = TOP5_STYLES[idx] || TOP5_STYLES[4];
    return {
      label:            hdata.names[ticker] || ticker,
      data:             hdata.timeline.map(t => t.ranks[ticker] ?? null),
      borderColor:      st.color,
      backgroundColor:  st.color + '15',
      borderWidth:      st.width,
      borderDash:       st.dash,
      pointStyle:       st.point,
      pointRadius:      5,
      pointHoverRadius: 8,
      pointBackgroundColor: st.color,
      pointBorderColor:     '#fff',
      pointBorderWidth:     1.5,
      spanGaps:         true,
      tension:          0.25,
    };
  });

  const ctx = document.getElementById('histCanvas').getContext('2d');
  activeChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      interaction:         { mode: 'nearest', intersect: false, axis: 'xy' },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title:  items => items[0]?.label || '',
            label:  item  => item.raw != null
              ? ` ${item.dataset.label}: ${item.raw}위` : null,
          },
          filter: item => item.raw != null,
        },
      },
      scales: {
        x: {
          ticks: {
            maxRotation: 45, minRotation: 20,
            font: { size: 10 }, color: '#999',
            maxTicksLimit: 20,
          },
          grid: { color: '#f5f5f5' },
        },
        y: {
          reverse:      true,
          min:          1,
          suggestedMax: 50,
          ticks: {
            stepSize: 10,
            font: { size: 11 }, color: '#999',
            callback: v => `${v}위`,
          },
          grid:  { color: '#f0f0f0' },
          title: { display: true, text: '순위 (낮을수록 상위)', font: { size: 10 }, color: '#bbb' },
        },
      },
    },
  });

  // 커스텀 범례 (색상 + 선 패턴 시각화)
  document.getElementById('hist-legend').innerHTML = tickers.map((t, i) => {
    const st   = TOP5_STYLES[i] || TOP5_STYLES[4];
    const dash = st.dash.length
      ? `stroke-dasharray="${st.dash.join(' ')}"`
      : '';
    const svg  = `<svg width="28" height="10" style="vertical-align:middle;margin-right:5px">
      <line x1="0" y1="5" x2="28" y2="5" stroke="${st.color}"
            stroke-width="${st.width}" ${dash}/>
    </svg>`;
    return `<div class="hist-legend-item">${svg}${esc(hdata.names[t] || t)}</div>`;
  }).join('');
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
