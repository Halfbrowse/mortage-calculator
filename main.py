from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Belgian Mortgage Simulator</title>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
  <style>
    :root {
      --bg: #0d0f14;
      --surface: #13161e;
      --card: #1a1e28;
      --border: #252a38;
      --gold: #c9a84c;
      --gold-light: #e8c87a;
      --gold-dim: rgba(201,168,76,0.12);
      --text: #e8e4dc;
      --muted: #7a7d8a;
      --red: #e05555;
      --green: #5db87a;
      --orange: #e8933a;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'DM Mono', monospace;
      min-height: 100vh;
      overflow-x: hidden;
    }

    /* HEADER */
    header {
      position: relative;
      padding: 56px 40px 40px;
      border-bottom: 1px solid var(--border);
      background: linear-gradient(135deg, #0d0f14 0%, #131829 100%);
      overflow: hidden;
    }
    header::before {
      content: '€';
      position: absolute;
      right: -20px; top: -40px;
      font-size: 320px;
      font-family: 'Playfair Display', serif;
      color: rgba(201,168,76,0.04);
      line-height: 1;
      pointer-events: none;
    }
    .header-tag {
      font-size: 11px;
      letter-spacing: 0.2em;
      color: var(--gold);
      text-transform: uppercase;
      margin-bottom: 14px;
    }
    h1 {
      font-family: 'Playfair Display', serif;
      font-size: clamp(32px, 5vw, 56px);
      font-weight: 900;
      line-height: 1.05;
      color: var(--text);
    }
    h1 span { color: var(--gold); }
    .header-sub {
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
      max-width: 500px;
    }
    .be-flag {
      display: inline-flex;
      gap: 3px;
      margin-bottom: 16px;
      vertical-align: middle;
    }
    .be-flag div { width: 8px; height: 20px; border-radius: 2px; }

    /* LAYOUT */
    .container {
      max-width: 1280px;
      margin: 0 auto;
      padding: 40px;
      display: grid;
      grid-template-columns: 380px 1fr;
      gap: 32px;
      align-items: start;
    }
    @media (max-width: 900px) {
      .container { grid-template-columns: 1fr; padding: 20px; }
    }

    /* PANEL */
    .panel {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: hidden;
    }
    .panel-header {
      padding: 20px 24px;
      border-bottom: 1px solid var(--border);
      font-size: 11px;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--gold);
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .panel-header::before {
      content: '';
      width: 6px; height: 6px;
      background: var(--gold);
      border-radius: 50%;
    }
    .panel-body { padding: 24px; }

    /* FORM */
    .field { margin-bottom: 20px; }
    label {
      display: block;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 8px;
    }
    .input-wrap { position: relative; }
    .input-wrap .unit {
      position: absolute;
      right: 14px; top: 50%;
      transform: translateY(-50%);
      color: var(--gold);
      font-size: 13px;
      pointer-events: none;
    }
    input[type="number"], select {
      width: 100%;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      font-family: 'DM Mono', monospace;
      font-size: 15px;
      padding: 12px 40px 12px 16px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
      appearance: none;
    }
    input[type="number"]:focus, select:focus {
      border-color: var(--gold);
      box-shadow: 0 0 0 3px var(--gold-dim);
    }
    select { cursor: pointer; padding-right: 36px; }

    .radio-group {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .radio-btn { position: relative; }
    .radio-btn input { display: none; }
    .radio-btn label {
      display: block;
      padding: 12px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      text-align: center;
      cursor: pointer;
      font-size: 12px;
      letter-spacing: 0.05em;
      text-transform: none;
      color: var(--muted);
      transition: all 0.2s;
    }
    .radio-btn input:checked + label {
      background: var(--gold-dim);
      border-color: var(--gold);
      color: var(--gold);
    }

    /* SLIDER */
    .slider-wrap { display: flex; align-items: center; gap: 12px; }
    input[type="range"] {
      -webkit-appearance: none;
      flex: 1;
      height: 4px;
      background: var(--border);
      border-radius: 4px;
      outline: none;
    }
    input[type="range"]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 18px; height: 18px;
      background: var(--gold);
      border-radius: 50%;
      cursor: pointer;
      box-shadow: 0 0 8px rgba(201,168,76,0.4);
    }
    .range-val {
      min-width: 52px;
      text-align: right;
      color: var(--gold);
      font-size: 15px;
    }

    /* CALCULATE BTN */
    .btn-calc {
      width: 100%;
      padding: 16px;
      background: var(--gold);
      color: #0d0f14;
      font-family: 'DM Mono', monospace;
      font-weight: 500;
      font-size: 13px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      border: none;
      border-radius: 10px;
      cursor: pointer;
      transition: all 0.2s;
      margin-top: 8px;
    }
    .btn-calc:hover {
      background: var(--gold-light);
      transform: translateY(-1px);
      box-shadow: 0 8px 24px rgba(201,168,76,0.3);
    }
    .btn-calc:active { transform: translateY(0); }

    /* RESULTS */
    .results { display: flex; flex-direction: column; gap: 24px; }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }
    @media (max-width: 700px) {
      .stats-grid { grid-template-columns: 1fr 1fr; }
    }
    .stat-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      position: relative;
      overflow: hidden;
      transition: border-color 0.2s;
    }
    .stat-card:hover { border-color: var(--gold); }
    .stat-card::after {
      content: '';
      position: absolute;
      bottom: 0; left: 0;
      height: 2px; width: 100%;
    }
    .stat-card.primary::after { background: var(--gold); }
    .stat-card.danger::after { background: var(--red); }
    .stat-card.success::after { background: var(--green); }
    .stat-card.warn::after { background: var(--orange); }

    .stat-label {
      font-size: 10px;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 10px;
    }
    .stat-value {
      font-family: 'Playfair Display', serif;
      font-size: 26px;
      font-weight: 700;
      color: var(--text);
      line-height: 1;
    }
    .stat-value.gold { color: var(--gold); }
    .stat-value.red { color: var(--red); }
    .stat-value.green { color: var(--green); }
    .stat-value.orange { color: var(--orange); }
    .stat-sub { font-size: 11px; color: var(--muted); margin-top: 6px; }

    /* LTV WARNING */
    .ltv-warning {
      background: rgba(232,147,58,0.1);
      border: 1px solid rgba(232,147,58,0.4);
      border-radius: 10px;
      padding: 14px 18px;
      font-size: 12px;
      color: var(--orange);
      display: flex;
      align-items: flex-start;
      gap: 10px;
      line-height: 1.6;
    }
    .ltv-warning-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }

    /* CHART */
    .chart-panel .panel-body { padding: 20px; }
    canvas { max-height: 280px; }

    /* TABLE */
    .table-wrap {
      max-height: 360px;
      overflow-y: auto;
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    .table-wrap::-webkit-scrollbar { width: 6px; }
    .table-wrap::-webkit-scrollbar-track { background: var(--surface); }
    .table-wrap::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    table { width: 100%; border-collapse: collapse; font-size: 12px; }
    thead tr { background: var(--surface); position: sticky; top: 0; z-index: 1; }
    th {
      padding: 12px 16px;
      text-align: right;
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--gold);
      font-weight: 400;
      border-bottom: 1px solid var(--border);
    }
    th:first-child { text-align: left; }
    tbody tr { border-bottom: 1px solid rgba(37,42,56,0.6); transition: background 0.1s; }
    tbody tr:hover { background: var(--surface); }
    td { padding: 11px 16px; text-align: right; color: var(--muted); }
    td:first-child { text-align: left; color: var(--text); }
    td.interest { color: var(--red); }
    td.capital { color: var(--green); }
    td.balance { color: var(--text); }

    /* COSTS BREAKDOWN */
    .costs-list { list-style: none; }
    .costs-list li {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 0;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
    }
    .costs-list li:last-child { border-bottom: none; }
    .costs-list .cost-label { color: var(--muted); }
    .costs-list .cost-val { color: var(--text); }
    .costs-list .cost-val.accent { color: var(--gold); font-weight: 500; }
    .costs-list .cost-val.saving { color: var(--green); }
    .costs-list .cost-val.orange { color: var(--orange); }
    .costs-section {
      display: block;
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--gold);
      padding: 14px 0 6px;
      border-bottom: 1px solid var(--border);
    }

    /* Empty state */
    .empty {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 80px 40px;
      color: var(--muted);
      text-align: center;
      gap: 12px;
    }
    .empty-icon { font-size: 48px; opacity: 0.3; }
    .empty p { font-size: 13px; }

    /* FADE IN */
    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(16px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .animate { animation: fadeUp 0.4s ease forwards; }

    /* DISCLAIMER */
    .disclaimer {
      max-width: 1280px;
      margin: 0 auto 48px;
      padding: 0 40px;
    }
    .disclaimer-inner {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      font-size: 11px;
      color: var(--muted);
      line-height: 1.7;
    }
    .disclaimer-inner strong { color: var(--text); }
    @media (max-width: 900px) {
      .disclaimer { padding: 0 20px; }
    }
  </style>
</head>
<body>

<header>
  <div class="be-flag">
    <div style="background:#1a1a1a"></div>
    <div style="background:#f9c713"></div>
    <div style="background:#ef3340"></div>
  </div>
  <div class="header-tag">Belgium · Hypotheek / Prêt Hypothécaire</div>
  <h1>Mortgage<br/><span>Simulator</span></h1>
  <p class="header-sub">Model your Belgian home loan — monthly payments, interest costs, amortisation schedule &amp; all buying fees.</p>
</header>

<div class="container">
  <!-- LEFT: INPUTS -->
  <div>
    <div class="panel">
      <div class="panel-header">Loan Parameters</div>
      <div class="panel-body">

        <div class="field">
          <label>Property Price</label>
          <div class="input-wrap">
            <input type="number" id="price" value="350000" min="10000" step="1000"/>
            <span class="unit">€</span>
          </div>
        </div>

        <div class="field">
          <label>Down Payment</label>
          <div class="input-wrap">
            <input type="number" id="down" value="70000" min="0" step="1000"/>
            <span class="unit">€</span>
          </div>
        </div>

        <div class="field">
          <label>Annual Interest Rate — <span id="rateDisplay">3.50</span>%</label>
          <div class="slider-wrap">
            <input type="range" id="rate" min="0.5" max="8" step="0.05" value="3.5"
              oninput="document.getElementById('rateDisplay').textContent=parseFloat(this.value).toFixed(2); document.getElementById('rateVal').textContent=parseFloat(this.value).toFixed(2);"/>
            <span class="range-val"><span id="rateVal">3.50</span>%</span>
          </div>
        </div>

        <div class="field">
          <label>Loan Term — <span id="termDisplay">20</span> years</label>
          <div class="slider-wrap">
            <input type="range" id="term" min="5" max="30" step="1" value="20"
              oninput="document.getElementById('termDisplay').textContent=this.value; document.getElementById('termVal').textContent=this.value;"/>
            <span class="range-val"><span id="termVal">20</span>y</span>
          </div>
        </div>

        <div class="field">
          <label>Repayment Type</label>
          <div class="radio-group">
            <div class="radio-btn">
              <input type="radio" name="type" id="annuity" value="annuity" checked/>
              <label for="annuity">Annuity<br/><small style="color:inherit;opacity:.6">Fixed payment</small></label>
            </div>
            <div class="radio-btn">
              <input type="radio" name="type" id="straight" value="straight"/>
              <label for="straight">Straight-line<br/><small style="color:inherit;opacity:.6">Fixed capital</small></label>
            </div>
          </div>
        </div>

        <div class="field">
          <label>Belgian Region</label>
          <div class="input-wrap">
            <select id="region">
              <option value="flanders">Flanders — 2% (primary) / 12% (invest.)</option>
              <option value="brussels">Brussels — 12.5% registration</option>
              <option value="wallonia">Wallonia — 12.5% registration</option>
            </select>
          </div>
        </div>

        <div class="field">
          <label>Property Type</label>
          <div class="radio-group">
            <div class="radio-btn">
              <input type="radio" name="build" id="existing" value="existing" checked/>
              <label for="existing">Existing<br/><small style="color:inherit;opacity:.6">Registration duty</small></label>
            </div>
            <div class="radio-btn">
              <input type="radio" name="build" id="newbuild" value="new"/>
              <label for="newbuild">New build<br/><small style="color:inherit;opacity:.6">21% VAT</small></label>
            </div>
          </div>
        </div>

        <div class="field">
          <label>Residence Use</label>
          <div class="radio-group">
            <div class="radio-btn">
              <input type="radio" name="residence" id="primary" value="primary" checked/>
              <label for="primary">Primary<br/><small style="color:inherit;opacity:.6">Abatements apply</small></label>
            </div>
            <div class="radio-btn">
              <input type="radio" name="residence" id="secondary" value="secondary"/>
              <label for="secondary">Secondary / invest.<br/><small style="color:inherit;opacity:.6">No abatements</small></label>
            </div>
          </div>
        </div>

        <div class="field">
          <label>Life Insurance Rate — <span id="lifeDisplay">0.20</span>%/yr</label>
          <div class="slider-wrap">
            <input type="range" id="lifeRate" min="0.05" max="0.60" step="0.05" value="0.20"
              oninput="document.getElementById('lifeDisplay').textContent=parseFloat(this.value).toFixed(2); document.getElementById('lifeVal').textContent=parseFloat(this.value).toFixed(2);"/>
            <span class="range-val"><span id="lifeVal">0.20</span>%</span>
          </div>
        </div>

        <div class="field">
          <label>Fire Insurance (annual)</label>
          <div class="input-wrap">
            <input type="number" id="fireAnnual" value="350" min="100" max="2000" step="50"/>
            <span class="unit">€</span>
          </div>
        </div>

        <button class="btn-calc" onclick="calculate()">Calculate Mortgage →</button>
      </div>
    </div>
  </div>

  <!-- RIGHT: RESULTS -->
  <div class="results" id="results">
    <div class="panel">
      <div class="empty">
        <div class="empty-icon">🏠</div>
        <p>Enter your loan details and click <strong>Calculate</strong> to see your repayment schedule.</p>
      </div>
    </div>
  </div>
</div>

<div class="disclaimer">
  <div class="disclaimer-inner">
    <strong>Disclaimer:</strong> This simulator is provided for illustrative and informational purposes only. All calculations are estimates based on simplified models and may not reflect actual loan offers, fees, or tax treatment. Belgian tax rules, notary tariffs, and bank policies change frequently — figures shown (registration duties, abatements, notary fees, etc.) are approximations only. This tool does not constitute financial, legal, or tax advice. Always consult a licensed mortgage broker, notary, or financial adviser before making any property purchase or financing decision.
  </div>
</div>

<script>
let chartInstance = null;

function fmt(n) {
  return '€' + Math.round(n).toLocaleString('nl-BE');
}

function calculate() {
  const price = parseFloat(document.getElementById('price').value);
  const down = parseFloat(document.getElementById('down').value);
  const rate = parseFloat(document.getElementById('rate').value);
  const term = parseInt(document.getElementById('term').value);
  const loanType = document.querySelector('input[name="type"]:checked').value;
  const region = document.getElementById('region').value;
  const isNewBuild = document.querySelector('input[name="build"]:checked').value === 'new';
  const primaryResidence = document.querySelector('input[name="residence"]:checked').value === 'primary';
  const lifeInsuranceRate = parseFloat(document.getElementById('lifeRate').value);
  const fireAnnual = parseFloat(document.getElementById('fireAnnual').value);

  fetch('/calculate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      price, down, rate, term,
      loan_type: loanType,
      region,
      is_new_build: isNewBuild,
      primary_residence: primaryResidence,
      life_insurance_rate: lifeInsuranceRate,
      fire_insurance_annual: fireAnnual
    })
  })
  .then(r => r.json())
  .then(data => renderResults(data));
}

function renderResults(d) {
  const el = document.getElementById('results');
  const bc = d.buying_costs;

  const ltvLimit = d.primary_residence ? 90 : 80;
  const ltvWarning = d.ltv_pct > ltvLimit
    ? `<div class="ltv-warning animate" style="animation-delay:0.02s">
        <span class="ltv-warning-icon">⚠</span>
        <span>LTV of ${d.ltv_pct.toFixed(1)}% exceeds the NBB guideline of ${ltvLimit}% for ${d.primary_residence ? 'primary residences' : 'secondary / investment properties'}. Most Belgian banks will require a larger down payment or additional guarantees.</span>
      </div>`
    : '';

  const abatementRow = bc.abatement > 0
    ? `<li><span class="cost-label">Regional abatement saving</span><span class="cost-val saving">− ${fmt(bc.abatement)}</span></li>`
    : '';

  const trueMonthly = d.loan_type === 'annuity'
    ? fmt(d.monthly_payment + d.monthly_life_insurance + d.fire_insurance_annual / 12)
    : '—';

  el.innerHTML = `
    ${ltvWarning}

    <!-- STATS -->
    <div class="stats-grid animate">
      <div class="stat-card primary">
        <div class="stat-label">Monthly Payment</div>
        <div class="stat-value gold">${d.monthly_display}</div>
        <div class="stat-sub">${d.loan_type === 'annuity' ? 'Fixed every month' : '1st month (decreases)'}</div>
      </div>
      <div class="stat-card warn">
        <div class="stat-label">True Monthly Cost</div>
        <div class="stat-value orange">${trueMonthly}</div>
        <div class="stat-sub">Incl. life &amp; fire insurance</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Loan Amount</div>
        <div class="stat-value">${fmt(d.loan_amount)}</div>
        <div class="stat-sub">${d.ltv_pct.toFixed(1)}% LTV</div>
      </div>
      <div class="stat-card danger">
        <div class="stat-label">Total Interest</div>
        <div class="stat-value red">${fmt(d.total_interest)}</div>
        <div class="stat-sub">${Math.round(d.total_interest/d.loan_amount*100)}% of loan</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Upfront Costs</div>
        <div class="stat-value">${fmt(bc.total)}</div>
        <div class="stat-sub">Fees + notary + deed</div>
      </div>
      <div class="stat-card success">
        <div class="stat-label">Grand Total</div>
        <div class="stat-value green">${fmt(d.grand_total)}</div>
        <div class="stat-sub">Everything in</div>
      </div>
    </div>

    <!-- CHART -->
    <div class="panel chart-panel animate" style="animation-delay:0.1s">
      <div class="panel-header">Balance Over Time</div>
      <div class="panel-body">
        <canvas id="myChart"></canvas>
      </div>
    </div>

    <!-- COSTS BREAKDOWN -->
    <div class="panel animate" style="animation-delay:0.15s">
      <div class="panel-header">Belgian Costs Breakdown</div>
      <div class="panel-body">
        <ul class="costs-list">
          <li><span class="cost-label">Property price</span><span class="cost-val">${fmt(d.price)}</span></li>
          <li><span class="cost-label">Down payment</span><span class="cost-val">${fmt(d.down)}</span></li>
          <li><span class="cost-label">Loan amount</span><span class="cost-val">${fmt(d.loan_amount)}</span></li>

          <span class="costs-section">Upfront Costs</span>

          <li>
            <span class="cost-label">${bc.is_new_build ? 'VAT 21% (new build / VEFA)' : 'Registration fees (' + bc.reg_rate + '%)'}</span>
            <span class="cost-val">${fmt(bc.registration)}</span>
          </li>
          ${abatementRow}
          <li><span class="cost-label">Notary fees (est.)</span><span class="cost-val">${fmt(bc.notary)}</span></li>
          <li><span class="cost-label">Mortgage deed / hypotheekakte (est.)</span><span class="cost-val">${fmt(bc.deed)}</span></li>
          <li><span class="cost-label" style="color:var(--text)">Total upfront</span><span class="cost-val accent">${fmt(bc.total)}</span></li>

          <span class="costs-section">Ongoing Costs Over ${d.term} Years</span>

          <li><span class="cost-label">Total repaid (capital + interest)</span><span class="cost-val">${fmt(d.total_repaid)}</span></li>
          <li>
            <span class="cost-label">Life ins. (schuldsaldoverzekering, ${d.life_insurance_rate.toFixed(2)}%/yr on balance)</span>
            <span class="cost-val orange">${fmt(d.total_life_insurance)}</span>
          </li>
          <li>
            <span class="cost-label">Fire ins. (brandverzekering, ${fmt(d.fire_insurance_annual)}/yr)</span>
            <span class="cost-val orange">${fmt(d.total_fire_insurance)}</span>
          </li>

          <span class="costs-section">Total</span>

          <li>
            <span class="cost-label" style="color:var(--text);font-size:14px">Grand total (all cash out)</span>
            <span class="cost-val accent" style="font-size:15px">${fmt(d.grand_total)}</span>
          </li>
        </ul>
      </div>
    </div>

    <!-- TABLE -->
    <div class="panel animate" style="animation-delay:0.2s">
      <div class="panel-header">Amortisation Schedule (Annual)</div>
      <div class="panel-body" style="padding:0">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Year</th>
                <th>Payment</th>
                <th>Capital</th>
                <th>Interest</th>
                <th>Balance</th>
              </tr>
            </thead>
            <tbody>
              ${d.annual.map(r => `
                <tr>
                  <td>${r.year}</td>
                  <td>${fmt(r.payment)}</td>
                  <td class="capital">${fmt(r.capital)}</td>
                  <td class="interest">${fmt(r.interest)}</td>
                  <td class="balance">${fmt(r.balance)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  // Draw chart
  if (chartInstance) chartInstance.destroy();
  const ctx = document.getElementById('myChart').getContext('2d');
  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: d.annual.map(r => 'Y' + r.year),
      datasets: [
        {
          label: 'Outstanding Balance',
          data: d.annual.map(r => r.balance),
          borderColor: '#c9a84c',
          backgroundColor: 'rgba(201,168,76,0.08)',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointBackgroundColor: '#c9a84c',
        },
        {
          label: 'Cumulative Interest Paid',
          data: d.annual.map(r => r.cum_interest),
          borderColor: '#e05555',
          backgroundColor: 'rgba(224,85,85,0.05)',
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointBackgroundColor: '#e05555',
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: { color: '#7a7d8a', font: { family: 'DM Mono', size: 11 } }
        },
        tooltip: {
          backgroundColor: '#1a1e28',
          borderColor: '#252a38',
          borderWidth: 1,
          titleColor: '#c9a84c',
          bodyColor: '#e8e4dc',
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: €${Math.round(ctx.parsed.y).toLocaleString('nl-BE')}`
          }
        }
      },
      scales: {
        x: { ticks: { color: '#7a7d8a', font: { family: 'DM Mono', size: 10 } }, grid: { color: '#1e2230' } },
        y: {
          ticks: {
            color: '#7a7d8a',
            font: { family: 'DM Mono', size: 10 },
            callback: v => '€' + (v/1000).toFixed(0) + 'k'
          },
          grid: { color: '#1e2230' }
        }
      }
    }
  });
}
</script>
</body>
</html>
"""


def belgian_buying_costs(
    price, loan, region, primary_residence=True, is_new_build=False
):
    """Estimate Belgian real estate buying costs."""

    if is_new_build:
        # New build purchased from developer (VEFA): 21% VAT replaces registration duties.
        # Land portion technically has registration duty in some cases, but the dominant
        # developer-sale scenario applies VAT to the full price.
        registration = price * 0.21
        reg_rate = 21
        abatement = 0
    else:
        if region == "flanders":
            # Flanders: 2% for sole primary residence (since Jan 2025), 12% for investment/second home
            reg_rate_dec = 0.02 if primary_residence else 0.12
        else:
            reg_rate_dec = 0.125
        reg_rate = reg_rate_dec * 100

        abatement = 0
        taxable = price

        if primary_residence:
            if region == "brussels":
                # Brussels: first €200,000 exempt for sole primary residence (2023 reform)
                exempt = min(200_000, price)
                abatement = exempt * reg_rate_dec
                taxable = max(0, price - 175_000)
            elif region == "wallonia":
                # Wallonia: €20,000 abatement on taxable base for primary residence
                exempt = min(20_000, price)
                abatement = exempt * reg_rate_dec
                taxable = max(0, price - 20_000)
            # Flanders: 3% flat rate post-2022, no abatement required

        registration = taxable * reg_rate_dec

    # Notary fee: Belgian sliding scale (Royal Decree tariff, pre-VAT base)
    if price <= 7_500:
        notary = price * 0.0456
    elif price <= 17_500:
        notary = 342 + (price - 7_500) * 0.0285
    elif price <= 30_000:
        notary = 627 + (price - 17_500) * 0.0228
    elif price <= 45_495:
        notary = 912 + (price - 30_000) * 0.0171
    elif price <= 64_095:
        notary = 1_177 + (price - 45_495) * 0.0114
    elif price <= 250_095:
        notary = 1_389 + (price - 64_095) * 0.0057
    else:
        notary = 2_449 + (price - 250_095) * 0.0057
    notary = max(notary, 500)
    notary *= 1.5  # +50% for 21% VAT on notary fees + disbursements

    # Hypotheekakte (mortgage deed): charged on loan amount, not property price
    deed = loan * 0.01

    total = registration + notary + deed

    return {
        "registration": round(registration),
        "notary": round(notary),
        "deed": round(deed),
        "total": round(total),
        "reg_rate": reg_rate,
        "abatement": round(abatement),
        "is_new_build": is_new_build,
    }


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json()
    price = float(data["price"])
    down = float(data["down"])
    rate = float(data["rate"]) / 100
    term_years = int(data["term"])
    loan_type = data["loan_type"]
    region = data["region"]
    is_new_build = bool(data.get("is_new_build", False))
    primary_residence = bool(data.get("primary_residence", True))
    life_insurance_rate = (
        float(data.get("life_insurance_rate", 0.20)) / 100
    )  # convert % to decimal
    fire_insurance_annual = float(data.get("fire_insurance_annual", 350))

    loan = price - down
    ltv_pct = (loan / price * 100) if price > 0 else 0
    # Belgian banks use the actuarial monthly rate, not simple annual/12
    monthly_rate = (1 + rate) ** (1 / 12) - 1 if rate > 0 else 0
    n = term_years * 12

    schedule = []

    if loan_type == "annuity":
        if monthly_rate == 0:
            monthly = loan / n
        else:
            monthly = (
                loan
                * (monthly_rate * (1 + monthly_rate) ** n)
                / ((1 + monthly_rate) ** n - 1)
            )
        monthly_display = f"€{monthly:,.0f}".replace(",", ".")
        monthly_payment = monthly

        balance = loan
        for i in range(1, n + 1):
            start_balance = balance
            interest = balance * monthly_rate
            capital = monthly - interest
            balance -= capital
            balance = max(balance, 0)
            schedule.append(
                {
                    "month": i,
                    "payment": monthly,
                    "capital": capital,
                    "interest": interest,
                    "balance": balance,
                    "start_balance": start_balance,
                }
            )
    else:
        # Straight-line: fixed capital repayment
        capital_pm = loan / n
        balance = loan
        monthly_payment = None
        first_month = None
        for i in range(1, n + 1):
            start_balance = balance
            interest = balance * monthly_rate
            payment = capital_pm + interest
            if i == 1:
                first_month = payment
                monthly_payment = payment
            balance -= capital_pm
            balance = max(balance, 0)
            schedule.append(
                {
                    "month": i,
                    "payment": payment,
                    "capital": capital_pm,
                    "interest": interest,
                    "balance": balance,
                    "start_balance": start_balance,
                }
            )
        monthly_display = (
            f"€{first_month:,.0f} → €{schedule[-1]['payment']:,.0f}".replace(",", ".")
        )

    # Life insurance (schuldsaldoverzekering): premium on outstanding start-of-month balance
    life_monthly_rate = life_insurance_rate / 12
    total_life_insurance = sum(r["start_balance"] * life_monthly_rate for r in schedule)
    monthly_life_insurance = (
        schedule[0]["start_balance"] * life_monthly_rate if schedule else 0
    )

    # Fire insurance (brandverzekering)
    total_fire_insurance = fire_insurance_annual * term_years

    # Annual rollup
    annual = []
    cum_interest = 0
    for yr in range(1, term_years + 1):
        rows = schedule[(yr - 1) * 12 : yr * 12]
        yr_payment = sum(r["payment"] for r in rows)
        yr_capital = sum(r["capital"] for r in rows)
        yr_interest = sum(r["interest"] for r in rows)
        cum_interest += yr_interest
        annual.append(
            {
                "year": yr,
                "payment": yr_payment,
                "capital": yr_capital,
                "interest": yr_interest,
                "balance": rows[-1]["balance"],
                "cum_interest": cum_interest,
            }
        )

    total_interest = sum(r["interest"] for r in schedule)
    total_repaid = sum(r["payment"] for r in schedule)
    buying_costs = belgian_buying_costs(
        price, loan, region, primary_residence, is_new_build
    )

    grand_total = (
        down
        + total_repaid
        + buying_costs["total"]
        + total_life_insurance
        + total_fire_insurance
    )

    return jsonify(
        {
            "loan_amount": loan,
            "price": price,
            "down": down,
            "term": term_years,
            "loan_type": loan_type,
            "monthly_display": monthly_display,
            "monthly_payment": monthly_payment,
            "monthly_life_insurance": monthly_life_insurance,
            "total_interest": total_interest,
            "total_repaid": total_repaid,
            "total_life_insurance": total_life_insurance,
            "total_fire_insurance": total_fire_insurance,
            "fire_insurance_annual": fire_insurance_annual,
            "life_insurance_rate": life_insurance_rate * 100,
            "buying_costs": buying_costs,
            "grand_total": grand_total,
            "annual": annual,
            "ltv_pct": ltv_pct,
            "primary_residence": primary_residence,
        }
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
