"""
reporter.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
분석 결과 딕셔너리를 받아 self-contained index.html 을 생성합니다.

그룹 탭 구성: 🇰🇷 한국 | 🇺🇸 미국 | 🪙 코인

• 한국: KR 데이터를 HTML에 임베드 (DATA_KR)
  - 마켓 탭: KOSPI / KOSDAQ
  - 기간 탭: 장중 / 일별 / 주별 / 월별

• 미국: data/report_us.json 을 fetch() 로 동적 로딩 (DATA_US)
  - 마켓 탭: S&P 500 / 나스닥 100
  - 기간 탭: 일별 / 주별 / 월별

• 코인: data/report_crypto.json 을 fetch() 로 동적 로딩 (DATA_CRYPTO)
  - 마켓 탭: 없음 (단일 시장)
  - 기간 탭: 일별 / 주별 / 월별

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
  <title>📈 글로벌 시총 순위 상승 트래커</title>
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

    /* 그룹 탭 */
    .group-tabs { margin-bottom: 16px; }
    .group-tabs .tab-btn.active { background: #1a237e; color: #fff; border-color: #1a237e; }

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

    /* ── 로딩 스피너 ── */
    .loading-wrap {
      text-align: center; padding: 60px 20px;
      background: #fff; border-radius: 14px;
      box-shadow: 0 1px 5px rgba(0,0,0,.07);
    }
    .spinner {
      width: 40px; height: 40px; margin: 0 auto 16px;
      border: 4px solid #e3f2fd;
      border-top-color: #1976d2;
      border-radius: 50%;
      animation: spin .8s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .loading-wrap p { color: #999; font-size: 14px; }

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
    .stock-name-link { color: inherit; text-decoration: none; }
    .stock-name-link:hover { color: #1565c0; text-decoration: underline; }
    .stock-ticker-link { text-decoration: none; display: inline-flex; align-items: center; }
    .stock-ticker-link .stock-ticker::after { content: ' ↗'; font-size: 9px; opacity: .55; }
    .stock-ticker-link:hover .stock-ticker { background: #bbdefb; }

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
  <h1 id="page-title">📈 글로벌 시총 순위 상승 트래커</h1>
  <div class="meta">
    <span>🕐 업데이트: <b id="last-updated">-</b></span>
    <span>📅 기준일: <b id="current-date">-</b></span>
  </div>
</header>

<div class="container">

  <!-- 그룹 탭 -->
  <div class="tab-bar group-tabs">
    <button class="tab-btn active" onclick="switchGroup('korea')">🇰🇷 한국</button>
    <button class="tab-btn"        onclick="switchGroup('us')">🇺🇸 미국</button>
    <button class="tab-btn"        onclick="switchGroup('coin')">🪙 코인</button>
  </div>

  <!-- 마켓 탭 (코인 그룹에선 숨김) -->
  <div class="tab-bar market-tabs" id="market-tabs"></div>

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

<footer id="footer-text">
  데이터: 네이버금융(한국) · Yahoo Finance(미국) · CoinGecko(코인) &nbsp;|&nbsp; 자동 업데이트
</footer>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>
// ── 임베드된 한국 데이터 ──────────────────────────────────────────────────────
const DATA_KR = /*__DATA_KR__*/null/*__DATA_KR__*/;

// ── 동적 로딩 데이터 (US/Crypto) ──────────────────────────────────────────────
let DATA_US     = null;
let DATA_CRYPTO = null;
let loadingUS     = false;
let loadingCrypto = false;

// ── 상태 ──────────────────────────────────────────────────────────────────────
let currentGroup  = 'korea';
let currentMarket = 'kospi';
let currentPeriod = 'intraday';
let activeChart   = null;

// ── 그룹별 마켓/기간 정의 ─────────────────────────────────────────────────────
const GROUP_MARKETS = {
  korea: ['kospi', 'kosdaq'],
  us:    ['sp500', 'nasdaq100'],
  coin:  ['coin'],
};
const GROUP_PERIODS = {
  korea: ['intraday','daily','weekly','monthly'],
  us:    ['daily','weekly','monthly'],
  coin:  ['daily','weekly','monthly'],
};
const MARKET_LABEL = {
  kospi:     'KOSPI',
  kosdaq:    'KOSDAQ',
  sp500:     'S&P 500',
  nasdaq100: '나스닥 100',
  coin:      '코인',
};
const GROUP_TITLE = {
  korea: '📈 KOSPI / KOSDAQ 시총 순위 상승 트래커',
  us:    '📈 S&P 500 / NASDAQ 100 시총 순위 상승 트래커',
  coin:  '📈 암호화폐 시총 순위 상승 트래커',
};

const PERIOD_META = {
  intraday: {
    label:'장중', cls:'intraday',
    title:'장중 순위 상승 Top 5',
    histTitle:'장중 Top5 진입 종목 — 최근 30일 일별 순위 변동',
  },
  daily: {
    label:'일별', cls:'daily',
    title:'전일 대비 시총 순위 상승 Top 5',
    histTitle:'최근 1개월 일별 순위 변동 이력',
  },
  weekly: {
    label:'주별', cls:'weekly',
    title:'전주 대비 시총 순위 상승 Top 5',
    histTitle:'최근 3개월 주별 순위 변동 이력',
  },
  monthly: {
    label:'월별', cls:'monthly',
    title:'전월 대비 시총 순위 상승 Top 5',
    histTitle:'전체 기간 월별 순위 변동 이력',
  },
};
const MEDAL_CLASS = ['m1','m2','m3','',''];
const INTRA_MEDAL = ['m1 intra','intra','intra','intra','intra'];

// ── 색각 이상자(적녹색약) 안전 팔레트 IBM Carbon 기반 ─────────────────────────
const CB_PALETTE = [
  { color:'#648FFF', dash:[],         point:'circle',   width:3   },
  { color:'#FE6100', dash:[8,4],      point:'triangle', width:2.8 },
  { color:'#DC267F', dash:[3,3],      point:'rect',     width:2.8 },
  { color:'#FFB000', dash:[10,3,2,3], point:'rectRot',  width:2.8 },
  { color:'#785EF0', dash:[6,4],      point:'star',     width:2.8 },
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

/* ── 유틸 ────────────────────────────────────────────────────────────────── */
function fmtDate(d) {
  if (!d || d.length < 8) return d || '-';
  return `${d.slice(0,4)}.${d.slice(4,6)}.${d.slice(6,8)}`;
}
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function naverUrl(ticker) {
  // 6자리 숫자 = 한국 종목 코드 → 종목 직접 페이지
  // 그 외 (미국/코인 영문 티커) → 검색 결과 페이지
  return /^\d{6}$/.test(ticker)
    ? `https://finance.naver.com/item/main.naver?code=${ticker}`
    : `https://finance.naver.com/search/search.naver?query=${encodeURIComponent(ticker)}&endUrl=&encoding=UTF-8`;
}

/* ── 현재 그룹의 데이터 반환 ────────────────────────────────────────────── */
function getGroupData() {
  if (currentGroup === 'korea') return DATA_KR;
  if (currentGroup === 'us')    return DATA_US;
  return DATA_CRYPTO;
}

/* ── 초기화 ─────────────────────────────────────────────────────────────── */
function init() {
  if (!DATA_KR) { showError('한국 데이터를 불러올 수 없습니다.'); return; }
  currentGroup  = 'korea';
  currentMarket = 'kospi';
  currentPeriod = 'intraday';
  buildGroupTabs();
  buildMarketTabs();
  buildPeriodTabs();
  updateHeader();
  render();
}

/* ── 그룹 탭 구성 ────────────────────────────────────────────────────────── */
function buildGroupTabs() {
  document.querySelectorAll('.group-tabs .tab-btn').forEach((btn, i) => {
    const groups = ['korea','us','coin'];
    btn.classList.toggle('active', groups[i] === currentGroup);
  });
}

/* ── 마켓 탭 구성 ────────────────────────────────────────────────────────── */
function buildMarketTabs() {
  const container = document.getElementById('market-tabs');
  const markets   = GROUP_MARKETS[currentGroup];

  // 코인은 단일 시장이므로 탭 숨김
  if (markets.length <= 1) {
    container.style.display = 'none';
    return;
  }
  container.style.display = 'flex';
  container.innerHTML = markets.map(m =>
    `<button class="tab-btn${m===currentMarket?' active':''}"
             onclick="switchMarket('${m}')">${esc(MARKET_LABEL[m])}</button>`
  ).join('');
}

/* ── 기간 탭 구성 ────────────────────────────────────────────────────────── */
function buildPeriodTabs() {
  const container = document.getElementById('period-tabs');
  const periods   = GROUP_PERIODS[currentGroup];
  container.innerHTML = periods.map(p => {
    const cls = `tab-btn${p==='intraday'?' intraday':''}${p===currentPeriod?' active':''}`;
    return `<button class="${cls}" onclick="switchPeriod('${p}')">${PERIOD_META[p].label}</button>`;
  }).join('');
}

/* ── 헤더 업데이트 ───────────────────────────────────────────────────────── */
function updateHeader() {
  const data = getGroupData();
  document.getElementById('page-title').textContent    = GROUP_TITLE[currentGroup];
  document.getElementById('last-updated').textContent  = data?.updated_at  || '-';
  document.getElementById('current-date').textContent  = fmtDate(data?.current_date);
}

/* ── 그룹 전환 ───────────────────────────────────────────────────────────── */
function switchGroup(g) {
  currentGroup  = g;
  currentMarket = GROUP_MARKETS[g][0];
  currentPeriod = GROUP_PERIODS[g][0];

  buildGroupTabs();
  buildMarketTabs();
  buildPeriodTabs();

  if (g === 'us' && !DATA_US) {
    loadUSData();
    return;
  }
  if (g === 'coin' && !DATA_CRYPTO) {
    loadCryptoData();
    return;
  }

  updateHeader();
  render();
}

/* ── 마켓 전환 ───────────────────────────────────────────────────────────── */
function switchMarket(m) {
  currentMarket = m;
  buildMarketTabs();
  render();
}

/* ── 기간 전환 ───────────────────────────────────────────────────────────── */
function switchPeriod(p) {
  currentPeriod = p;
  buildPeriodTabs();
  render();
}

/* ── 동적 데이터 로딩: 미국 ─────────────────────────────────────────────── */
function loadUSData() {
  if (loadingUS) return;
  loadingUS = true;
  showLoadingSpinner('🇺🇸 미국 데이터 로딩 중...');

  fetch('data/report_us.json')
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then(data => {
      DATA_US   = data;
      loadingUS = false;
      updateHeader();
      render();
    })
    .catch(err => {
      loadingUS = false;
      showError(`미국 데이터를 불러올 수 없습니다.<br><small>${esc(err.message)}</small>`);
    });
}

/* ── 동적 데이터 로딩: 코인 ─────────────────────────────────────────────── */
function loadCryptoData() {
  if (loadingCrypto) return;
  loadingCrypto = true;
  showLoadingSpinner('🪙 코인 데이터 로딩 중...');

  fetch('data/report_crypto.json')
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    })
    .then(data => {
      DATA_CRYPTO   = data;
      loadingCrypto = false;
      updateHeader();
      render();
    })
    .catch(err => {
      loadingCrypto = false;
      showError(`코인 데이터를 불러올 수 없습니다.<br><small>${esc(err.message)}</small>`);
    });
}

/* ── 메인 렌더링 ─────────────────────────────────────────────────────────── */
function render() {
  if (activeChart) { activeChart.destroy(); activeChart = null; }

  document.getElementById('section-title').textContent = PERIOD_META[currentPeriod].title;
  document.getElementById('intraday-banner').style.display = 'none';
  document.getElementById('compare-label').className = 'compare-label';

  if (currentGroup === 'korea' && currentPeriod === 'intraday') {
    renderIntraday();
  } else {
    renderPeriod();
  }
}

/* ── 장중 탭 렌더링 (한국 전용) ─────────────────────────────────────────── */
function renderIntraday() {
  const cards  = document.getElementById('cards');
  const idata  = DATA_KR?.intraday?.[currentMarket];
  const label  = document.getElementById('compare-label');
  const banner = document.getElementById('intraday-banner');

  if (!idata || !idata.available || !idata.top5?.length) {
    label.textContent = '';
    cards.innerHTML   = noDataHTML(idata?.comparison || '장중 데이터 없음');
    document.getElementById('hist-section').innerHTML = '';
    return;
  }

  banner.style.display = 'flex';
  document.getElementById('intraday-time-badge').textContent = idata.label_display || '-';
  document.getElementById('intraday-comp-label').textContent = idata.comparison || '';
  label.className   = 'compare-label orange';
  label.textContent = idata.comparison || '';
  document.getElementById('section-title').textContent =
    `${idata.label_display} 장중 순위 상승 Top 5`;

  cards.innerHTML = idata.top5.map((s, i) => {
    const invUrl   = `https://kr.investing.com/search/?q=${encodeURIComponent(s.ticker)}`;
    const nvrUrl = naverUrl(s.ticker);
    return `
    <div class="card intraday-card">
      <div class="medal ${INTRA_MEDAL[i]}">${i+1}</div>
      <div class="stock-info">
        <div class="stock-name"><a class="stock-name-link" href="${invUrl}" target="_blank" rel="noopener">${esc(s.name)}</a></div>
        <div class="stock-sub">
          <a class="stock-ticker-link" href="${nvrUrl}" target="_blank" rel="noopener"><span class="stock-ticker">${esc(s.ticker)}</span></a>
          <span class="stock-mktcap">시총 ${esc(s.market_cap_str)}</span>
        </div>
      </div>
      <div class="rank-change">
        <div class="change-arrow">▲</div>
        <div class="change-num">+${s.rank_change}</div>
        <div class="rank-path"><strong>${s.prev_rank}위</strong> → <strong>${s.rank}위</strong></div>
      </div>
    </div>`;
  }).join('');

  renderHistoryChart(idata.history, 'intraday');
}

/* ── 일별/주별/월별 탭 렌더링 (모든 그룹) ──────────────────────────────── */
function renderPeriod() {
  const cards = document.getElementById('cards');
  const label = document.getElementById('compare-label');
  const data  = getGroupData();
  const pd    = data?.[currentMarket]?.[currentPeriod];

  if (!pd || !pd.available || !pd.top5?.length) {
    label.textContent = '';
    cards.innerHTML   = noDataHTML(
      pd?.prev_date ? '기준: ' + fmtDate(pd.prev_date) : '데이터 부족'
    );
    document.getElementById('hist-section').innerHTML = '';
    return;
  }

  label.className   = 'compare-label';
  label.textContent = '기준: ' + fmtDate(pd.prev_date);

  cards.innerHTML = pd.top5.map((s, i) => {
    const invUrl   = `https://kr.investing.com/search/?q=${encodeURIComponent(s.ticker)}`;
    const nvrUrl = naverUrl(s.ticker);
    return `
    <div class="card">
      <div class="medal ${MEDAL_CLASS[i]}">${i+1}</div>
      <div class="stock-info">
        <div class="stock-name"><a class="stock-name-link" href="${invUrl}" target="_blank" rel="noopener">${esc(s.name)}</a></div>
        <div class="stock-sub">
          <a class="stock-ticker-link" href="${nvrUrl}" target="_blank" rel="noopener"><span class="stock-ticker">${esc(s.ticker)}</span></a>
          <span class="stock-mktcap">시총 ${esc(s.market_cap_str)}</span>
        </div>
      </div>
      <div class="rank-change">
        <div class="change-arrow">▲</div>
        <div class="change-num">+${s.rank_change}</div>
        <div class="rank-path"><strong>${s.prev_rank}위</strong> → <strong>${s.rank}위</strong></div>
      </div>
    </div>`;
  }).join('');

  renderHistoryChart(pd.history, currentPeriod);
}

/* ── 히스토리 차트 렌더링 ────────────────────────────────────────────────── */
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
      <div class="hist-chart-wrap"><canvas id="histCanvas"></canvas></div>
      <div class="hist-legend" id="hist-legend"></div>
    </div>`;

  const labels   = hdata.timeline.map(t => t.label);
  const tickers  = hdata.tickers;
  const datasets = tickers.map((ticker, idx) => {
    const st = CB_PALETTE[idx] || CB_PALETTE[4];
    return {
      label:               hdata.names[ticker] || ticker,
      data:                hdata.timeline.map(t => t.ranks[ticker] ?? null),
      borderColor:         st.color,
      backgroundColor:     st.color + '15',
      borderWidth:         st.width,
      borderDash:          st.dash,
      pointStyle:          st.point,
      pointRadius:         5,
      pointHoverRadius:    8,
      pointBackgroundColor: st.color,
      pointBorderColor:    '#fff',
      pointBorderWidth:    1.5,
      spanGaps:            true,
      tension:             0.25,
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
            title: items => items[0]?.label || '',
            label: item  => item.raw != null
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
          title: { display: true, text: '순위 (낮을수록 상위)',
                   font: { size: 10 }, color: '#bbb' },
        },
      },
    },
  });

  // 커스텀 범례
  document.getElementById('hist-legend').innerHTML = tickers.map((t, i) => {
    const st   = CB_PALETTE[i] || CB_PALETTE[4];
    const dash = st.dash.length ? `stroke-dasharray="${st.dash.join(' ')}"` : '';
    const svg  = `<svg width="28" height="10" style="vertical-align:middle;margin-right:5px">
      <line x1="0" y1="5" x2="28" y2="5"
            stroke="${st.color}" stroke-width="${st.width}" ${dash}/>
    </svg>`;
    return `<div class="hist-legend-item">${svg}${esc(hdata.names[t] || t)}</div>`;
  }).join('');
}

/* ── 공통 UI ─────────────────────────────────────────────────────────────── */
function showLoadingSpinner(msg) {
  document.getElementById('cards').innerHTML = `
    <div class="loading-wrap">
      <div class="spinner"></div>
      <p>${esc(msg)}</p>
    </div>`;
  document.getElementById('hist-section').innerHTML = '';
  document.getElementById('compare-label').textContent = '';
  document.getElementById('intraday-banner').style.display = 'none';
}
function noDataHTML(msg) {
  return `<div class="no-data">
    <div class="icon">📊</div>
    <p>표시할 데이터가 없습니다.</p>
    <p style="margin-top:8px;font-size:12px;color:#bbb">${esc(msg)}</p>
  </div>`;
}
function showError(msg) {
  document.getElementById('cards').innerHTML = `<div class="no-data">
    <div class="icon">⚠️</div>
    <p style="color:#e53935">${msg}</p>
  </div>`;
  document.getElementById('hist-section').innerHTML = '';
}

init();
</script>
</body>
</html>
"""


def generate_html(report_data: dict, output_path: str = OUTPUT_HTML) -> str:
    """
    KR report_data 를 받아 DATA_KR 로 임베드한 index.html 을 생성합니다.
    US/Crypto 데이터는 JS에서 fetch()로 동적 로딩합니다.
    """
    data_json = json.dumps(report_data, ensure_ascii=False)
    html = _HTML_TEMPLATE.replace(
        "/*__DATA_KR__*/null/*__DATA_KR__*/", data_json
    )
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 리포트 생성 완료: {output_path}")
    return output_path
