import logging

from flask import Flask, jsonify, render_template_string, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def belgian_buying_costs(
    price, loan, region, primary_residence=True, is_new_build=False
):
    """Estimate Belgian real estate buying costs."""
    if is_new_build:
        registration = price * 0.21
        reg_rate = 21
        abatement = 0
    else:
        if region == "flanders":
            reg_rate_dec = 0.02 if primary_residence else 0.12
        elif region == "wallonia":
            # Jan 2025 reform: 3% for primary/sole residence, 12.5% for all others.
            # The old €20k abatement and chèque habitat were abolished at the same time.
            reg_rate_dec = 0.03 if primary_residence else 0.125
        else:  # brussels
            reg_rate_dec = 0.125
        reg_rate = reg_rate_dec * 100
        abatement = 0
        taxable = price
        if primary_residence:
            if region == "brussels" and price <= 600_000:
                # Since April 2023 the Brussels abatement is €200,000 (raised from €175k).
                # Only applies when price ≤ €600,000.
                exempt = min(200_000, price)
                abatement = exempt * reg_rate_dec
                taxable = max(0, price - 200_000)
        registration = taxable * reg_rate_dec

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
    notary *= 1.5  # VAT on notary fees + disbursements

    # Mortgage deed: 1% registration fee + 0.3% mortgage duty (both levied on loan amount)
    deed = loan * 0.013
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


def compute_schedule(
    price,
    down,
    rate,
    term_years,
    loan_type,
    region,
    is_new_build,
    primary_residence,
    life_insurance_rate,
    fire_insurance_annual,
):
    """Core mortgage calculation. Returns result dict or None on invalid input."""
    loan = price - down
    if loan <= 0 or price <= 0 or term_years <= 0:
        return None

    ltv_pct = loan / price * 100
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
            balance = max(balance - capital, 0)
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
            balance = max(balance - capital_pm, 0)
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

    # Life insurance with 2% Belgian insurance premium tax
    life_monthly_rate = life_insurance_rate / 12
    total_life_insurance = (
        sum(r["start_balance"] * life_monthly_rate for r in schedule) * 1.02
    )
    monthly_life_insurance = (
        schedule[0]["start_balance"] * life_monthly_rate * 1.02 if schedule else 0
    )
    total_fire_insurance = fire_insurance_annual * term_years

    annual = []
    cum_interest = 0
    for yr in range(1, term_years + 1):
        rows = schedule[(yr - 1) * 12 : yr * 12]
        yr_interest = sum(r["interest"] for r in rows)
        cum_interest += yr_interest
        annual.append(
            {
                "year": yr,
                "payment": sum(r["payment"] for r in rows),
                "capital": sum(r["capital"] for r in rows),
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

    return {
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
        "monthly_schedule": [
            {
                "month": r["month"],
                "payment": r["payment"],
                "capital": r["capital"],
                "interest": r["interest"],
                "balance": r["balance"],
            }
            for r in schedule
        ],
    }


def parse_params(data):
    return dict(
        price=float(data["price"]),
        down=float(data["down"]),
        rate=float(data["rate"]) / 100,
        term_years=int(data["term"]),
        loan_type=data["loan_type"],
        region=data["region"],
        is_new_build=bool(data.get("is_new_build", False)),
        primary_residence=bool(data.get("primary_residence", True)),
        life_insurance_rate=float(data.get("life_insurance_rate", 0.20)) / 100,
        fire_insurance_annual=float(data.get("fire_insurance_annual", 350)),
    )


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
      --blue: #5b9bd5;
      --blue-dim: rgba(91,155,213,0.12);
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
      grid-template-columns: 400px 1fr;
      gap: 32px;
      align-items: start;
    }
    @media (max-width: 960px) {
      .container { grid-template-columns: 1fr; padding: 20px; }
    }

    /* TABS (left panel) */
    .tab-bar {
      display: flex;
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }
    .tab-btn {
      flex: 1;
      padding: 14px 8px;
      font-family: 'DM Mono', monospace;
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      cursor: pointer;
      transition: all 0.2s;
    }
    .tab-btn:hover { color: var(--text); }
    .tab-btn.active {
      color: var(--gold);
      border-bottom-color: var(--gold);
    }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

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
      justify-content: space-between;
      gap: 10px;
    }
    .panel-header-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .panel-header::before, .panel-header-left::before {
      content: '';
      width: 6px; height: 6px;
      background: var(--gold);
      border-radius: 50%;
      flex-shrink: 0;
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
    input[type="number"].input-error {
      border-color: var(--red);
      box-shadow: 0 0 0 3px rgba(224,85,85,0.15);
    }
    select { cursor: pointer; padding-right: 36px; }
    .error-msg {
      font-size: 11px;
      color: var(--red);
      margin-top: 5px;
      display: none;
    }
    .error-msg.visible { display: block; }

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

    /* BUTTONS */
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
    .btn-secondary {
      padding: 8px 14px;
      background: transparent;
      color: var(--muted);
      font-family: 'DM Mono', monospace;
      font-size: 10px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      border: 1px solid var(--border);
      border-radius: 7px;
      cursor: pointer;
      transition: all 0.2s;
    }
    .btn-secondary:hover {
      border-color: var(--gold);
      color: var(--gold);
    }

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

    /* COMPARISON */
    .compare-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .compare-table th {
      padding: 10px 16px;
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      border-bottom: 1px solid var(--border);
    }
    .compare-table th:nth-child(2) { color: var(--gold); }
    .compare-table th:nth-child(3) { color: var(--blue); }
    .compare-table th:nth-child(4) { color: var(--muted); }
    .compare-table td { padding: 10px 16px; border-bottom: 1px solid rgba(37,42,56,0.5); }
    .compare-table td:first-child { color: var(--muted); text-align: left; }
    .compare-table td:not(:first-child) { text-align: right; }
    .delta-pos { color: var(--green); }
    .delta-neg { color: var(--red); }
    .scenario-badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 10px;
      letter-spacing: 0.08em;
      margin-left: 8px;
    }
    .badge-a { background: var(--gold-dim); color: var(--gold); }
    .badge-b { background: var(--blue-dim); color: var(--blue); }

    /* OVERPAYMENT */
    .overpay-result {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-top: 16px;
    }
    .overpay-stat {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      text-align: center;
    }
    .overpay-stat .o-label { font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }
    .overpay-stat .o-val { font-family: 'Playfair Display', serif; font-size: 22px; font-weight: 700; color: var(--green); }
    .overpay-stat .o-sub { font-size: 11px; color: var(--muted); margin-top: 4px; }

    /* AFFORDABILITY */
    .afford-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-top: 16px;
    }
    .afford-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
    }
    .afford-card .a-label { font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }
    .afford-card .a-val { font-size: 18px; font-family: 'Playfair Display', serif; font-weight: 700; }
    .afford-card .a-sub { font-size: 11px; color: var(--muted); margin-top: 4px; }
    .a-val.ok { color: var(--green); }
    .a-val.warn { color: var(--orange); }
    .a-val.bad { color: var(--red); }
    .stress-bar-wrap {
      margin-top: 12px;
      background: var(--border);
      border-radius: 4px;
      height: 6px;
      overflow: hidden;
    }
    .stress-bar {
      height: 100%;
      border-radius: 4px;
      transition: width 0.4s ease;
    }

    /* PRICE RANGE BAR */
    .afford-range-bar {
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 14px 0 4px;
    }
    .range-label-33 { font-size: 11px; color: var(--green); font-weight: 700; min-width: 28px; }
    .range-label-40 { font-size: 11px; color: var(--orange); font-weight: 700; min-width: 28px; }
    .range-track {
      flex: 1;
      background: var(--border);
      border-radius: 6px;
      height: 10px;
      position: relative;
    }
    .range-fill {
      position: absolute;
      left: 0; top: 0; bottom: 0;
      width: 100%;
      background: linear-gradient(90deg, var(--green) 0%, var(--orange) 100%);
      border-radius: 6px;
      opacity: 0.55;
    }
    .range-pin {
      position: absolute;
      top: 50%;
      transform: translate(-50%, -50%);
      font-size: 10px;
      font-weight: 700;
      white-space: nowrap;
      padding: 2px 6px;
      border-radius: 4px;
    }
    .pin-33 { left: 10%; background: var(--green); color: #000; }
    .pin-40 { left: 90%; background: var(--orange); color: #000; }

    /* SCENARIO B INFO BOX */
    .info-box {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.6;
      margin-bottom: 20px;
    }
    .info-box strong { color: var(--text); }

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
    @media (max-width: 960px) {
      .disclaimer { padding: 0 20px; }
    }

    /* MOBILE IMPROVEMENTS */
    @media (max-width: 480px) {
      header { padding: 32px 20px 24px; }
      header::before { font-size: 160px; }
      .container { padding: 16px; gap: 20px; }
      .stats-grid { grid-template-columns: 1fr 1fr; gap: 10px; }
      .stat-card { padding: 14px; }
      .stat-value { font-size: 20px; }
      .panel-body { padding: 16px; }
      .panel-header { padding: 14px 16px; font-size: 10px; }
      .tab-btn { padding: 12px 6px; font-size: 9px; }
      .field { margin-bottom: 16px; }
      .overpay-result { grid-template-columns: 1fr; }
      .afford-grid { grid-template-columns: 1fr; }
      .compare-table td, .compare-table th { padding: 8px 10px; font-size: 11px; }
      .costs-list li { font-size: 12px; gap: 8px; flex-wrap: wrap; }
      .costs-list .cost-val { margin-left: auto; }
      .btn-calc { font-size: 12px; padding: 14px; }
      .disclaimer { padding: 0 16px; margin-bottom: 32px; }
    }

    /* Make tables horizontally scrollable on mobile */
    .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
    .compare-table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
    table { min-width: 360px; }
    .compare-table { min-width: 380px; }

    /* Larger touch targets for range sliders */
    @media (hover: none) and (pointer: coarse) {
      input[type="range"] { height: 6px; }
      input[type="range"]::-webkit-slider-thumb {
        width: 26px; height: 26px;
        box-shadow: 0 0 12px rgba(201,168,76,0.5);
      }
      .tab-btn { padding: 14px 8px; }
    }

    /* Prevent iOS font size adjustment */
    body { -webkit-text-size-adjust: 100%; }

    /* Ensure inputs don't trigger zoom on iOS (needs 16px+) */
    @media (max-width: 768px) {
      input[type="number"], select { font-size: 16px; }
    }

    /* URL SHARE TOAST */
    .toast {
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%) translateY(80px);
      background: var(--card);
      border: 1px solid var(--gold);
      border-radius: 8px;
      padding: 12px 20px;
      font-size: 12px;
      color: var(--gold);
      letter-spacing: 0.08em;
      transition: transform 0.3s ease;
      z-index: 999;
      pointer-events: none;
    }
    .toast.visible { transform: translateX(-50%) translateY(0); }


    /* KO-FI BUTTON */
    .kofi-btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-top: 20px;
      padding: 10px 20px;
      background: #29abe0;
      color: #fff;
      font-family: 'DM Mono', monospace;
      font-size: 12px;
      font-weight: 500;
      letter-spacing: 0.08em;
      text-decoration: none;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      transition: background 0.2s, transform 0.1s;
    }
    .kofi-btn:hover { background: #1a9acf; transform: translateY(-1px); }
    .kofi-btn:active { transform: translateY(0); }
    .kofi-btn svg { flex-shrink: 0; }

    /* FOOTER */
    .site-footer {
      text-align: center;
      padding: 40px 20px;
      border-top: 1px solid var(--border);
      color: var(--muted);
      font-size: 12px;
    }
    .site-footer p { margin-bottom: 12px; }

    /* TOOLTIPS */
    .tip-wrap { position: relative; display: inline-flex; align-items: center; vertical-align: middle; margin-left: 4px; }
    .tip-icon {
      display: inline-flex; align-items: center; justify-content: center;
      width: 15px; height: 15px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 50%;
      font-size: 9px; color: var(--muted); cursor: help; flex-shrink: 0;
      font-style: normal; line-height: 1;
      transition: border-color 0.15s, color 0.15s;
      -webkit-user-select: none; user-select: none;
    }
    .tip-icon:hover, .tip-icon:focus { border-color: var(--gold); color: var(--gold); outline: none; }
    .tip-bubble {
      position: absolute;
      bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%);
      background: var(--card); border: 1px solid var(--gold); border-radius: 8px;
      padding: 10px 13px; font-size: 11px; color: var(--text); line-height: 1.6;
      width: 230px; max-width: 80vw; z-index: 200;
      opacity: 0; pointer-events: none; transition: opacity 0.15s;
      white-space: normal; text-align: left; box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }
    .tip-bubble::after {
      content: ''; position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
      border: 5px solid transparent; border-top-color: var(--gold);
    }
    .tip-wrap:hover .tip-bubble, .tip-bubble.visible { opacity: 1; pointer-events: auto; }

    /* SENSITIVITY MATRIX */
    .sensitivity-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; border: 1px solid var(--border); }
    .sensitivity-table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 340px; }
    .sensitivity-table th {
      padding: 10px 14px; background: var(--surface);
      font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
      color: var(--gold); font-weight: 400; text-align: right;
      border-bottom: 1px solid var(--border);
    }
    .sensitivity-table th:first-child { text-align: left; }
    .sensitivity-table td {
      padding: 9px 14px; text-align: right;
      color: var(--muted); border-bottom: 1px solid rgba(37,42,56,0.5); transition: background 0.1s;
    }
    .sensitivity-table td.rate-label { text-align: left; color: var(--text); }
    .sensitivity-table td.rate-label.current-rate { color: var(--gold); font-weight: 500; }
    .sensitivity-table td.cell-active { background: var(--gold-dim); color: var(--gold); font-weight: 500; }
    .sensitivity-table tr:hover td { background: var(--surface); }
    .sensitivity-table tr:hover td.cell-active { background: rgba(201,168,76,0.2); }
    .sensitivity-note { font-size: 11px; color: var(--muted); padding: 10px 16px; border-top: 1px solid var(--border); }

    /* MOBILE: scroll shadow on overflowing tables */
    @media (max-width: 640px) {
      .table-wrap, .sensitivity-wrap { box-shadow: inset -24px 0 16px -16px rgba(13,15,20,0.7); }
      .panel-header { font-size: 10px; }
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
  <a href="https://ko-fi.com/halfbrowse" target="_blank" rel="noopener noreferrer" class="kofi-btn">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M23.881 8.948c-.773-4.085-4.859-4.593-4.859-4.593H.723c-.604 0-.679.798-.679.798s-.082 7.324-.022 11.822c.164 2.424 2.586 2.672 2.586 2.672s8.267-.023 11.966-.049c2.438-.426 2.683-2.566 2.658-3.734 4.352.24 7.422-2.831 6.649-6.916zm-11.062 3.511c-1.246 1.453-4.011 3.976-4.011 3.976s-.121.119-.31.023c-.076-.057-.108-.09-.108-.09-.443-.441-3.368-3.049-4.034-3.954-.709-.965-1.041-2.7-.091-3.71.951-1.01 3.005-1.086 4.363.407 0 0 1.565-1.782 3.468-.963 1.904.82 1.832 2.692.723 4.311zm6.173.478c-.928.116-1.682.028-1.682.028V7.284h1.77s1.971.551 1.971 2.638c0 1.913-.985 2.015-2.059 2.015z"/></svg>
    Support this project on Ko-fi
  </a>
</header>

<div class="container">
  <!-- LEFT: INPUTS -->
  <div>
    <div class="panel">
      <div class="tab-bar">
        <button class="tab-btn active" onclick="switchTab('main')">Loan</button>
        <button class="tab-btn" onclick="switchTab('compare')">Compare B</button>
        <button class="tab-btn" onclick="switchTab('afford')">Affordability</button>
        <button class="tab-btn" onclick="switchTab('refi')">Refi</button>
      </div>

      <!-- TAB: MAIN LOAN -->
      <div class="tab-content active" id="tab-main">
        <div class="panel-body">
          <div class="field">
            <label>Property Price</label>
            <div class="input-wrap">
              <input type="number" id="price" value="350000" min="10000" step="1000"
                oninput="onNumberInput(this); debouncedCalc()"/>
              <span class="unit">€</span>
            </div>
            <div class="error-msg" id="err-price"></div>
          </div>

          <div class="field">
            <label>Down Payment</label>
            <div class="input-wrap">
              <input type="number" id="down" value="70000" min="0" step="1000"
                oninput="onNumberInput(this); debouncedCalc()"/>
              <span class="unit">€</span>
            </div>
            <div class="error-msg" id="err-down"></div>
          </div>

          <div class="field">
            <label>Annual Interest Rate — <span id="rateDisplay">3.50</span>%</label>
            <div class="slider-wrap">
              <input type="range" id="rate" min="0.5" max="8" step="0.05" value="3.5"
                oninput="document.getElementById('rateDisplay').textContent=parseFloat(this.value).toFixed(2); document.getElementById('rateVal').textContent=parseFloat(this.value).toFixed(2); debouncedCalc();"/>
              <span class="range-val"><span id="rateVal">3.50</span>%</span>
            </div>
          </div>

          <div class="field">
            <label>Loan Term — <span id="termDisplay">20</span> years</label>
            <div class="slider-wrap">
              <input type="range" id="term" min="5" max="30" step="1" value="20"
                oninput="document.getElementById('termDisplay').textContent=this.value; document.getElementById('termVal').textContent=this.value; debouncedCalc();"/>
              <span class="range-val"><span id="termVal">20</span>y</span>
            </div>
          </div>

          <div class="field">
            <label>Repayment Type <span class="tip-wrap"><span class="tip-icon" tabindex="0" onclick="toggleTip(this)">?</span><span class="tip-bubble">Annuity: equal monthly payments throughout — more interest early, more capital later. Straight-line: fixed capital each month, so payments decrease over time and you pay less total interest overall.</span></span></label>
            <div class="radio-group">
              <div class="radio-btn">
                <input type="radio" name="type" id="annuity" value="annuity" checked onchange="debouncedCalc()"/>
                <label for="annuity">Annuity<br/><small style="color:inherit;opacity:.6">Fixed payment</small></label>
              </div>
              <div class="radio-btn">
                <input type="radio" name="type" id="straight" value="straight" onchange="debouncedCalc()"/>
                <label for="straight">Straight-line<br/><small style="color:inherit;opacity:.6">Fixed capital</small></label>
              </div>
            </div>
          </div>

          <div class="field">
            <label>Belgian Region</label>
            <div class="input-wrap">
              <select id="region" onchange="debouncedCalc()">
                <option value="flanders">Flanders — 2% (primary) / 12% (invest.)</option>
                <option value="brussels">Brussels — 12.5% (€200k abatement ≤€600k)</option>
                <option value="wallonia">Wallonia — 3% (primary) / 12.5% (invest.)</option>
              </select>
            </div>
          </div>

          <div class="field">
            <label>Property Type</label>
            <div class="radio-group">
              <div class="radio-btn">
                <input type="radio" name="build" id="existing" value="existing" checked onchange="debouncedCalc()"/>
                <label for="existing">Existing<br/><small style="color:inherit;opacity:.6">Registration duty</small></label>
              </div>
              <div class="radio-btn">
                <input type="radio" name="build" id="newbuild" value="new" onchange="debouncedCalc()"/>
                <label for="newbuild">New build<br/><small style="color:inherit;opacity:.6">21% VAT</small></label>
              </div>
            </div>
          </div>

          <div class="field">
            <label>Residence Use</label>
            <div class="radio-group">
              <div class="radio-btn">
                <input type="radio" name="residence" id="primary" value="primary" checked onchange="debouncedCalc()"/>
                <label for="primary">Primary<br/><small style="color:inherit;opacity:.6">Abatements apply</small></label>
              </div>
              <div class="radio-btn">
                <input type="radio" name="residence" id="secondary" value="secondary" onchange="debouncedCalc()"/>
                <label for="secondary">Secondary / invest.<br/><small style="color:inherit;opacity:.6">No abatements</small></label>
              </div>
            </div>
          </div>

          <div class="field">
            <label>Life Insurance Rate — <span id="lifeDisplay">0.20</span>%/yr <span class="tip-wrap"><span class="tip-icon" tabindex="0" onclick="toggleTip(this)">?</span><span class="tip-bubble">Schuldsaldoverzekering (SSV): covers your outstanding loan balance if you pass away during the mortgage term. Belgian banks nearly always require it. Rate depends on age and health — typically 0.10–0.40%/yr. A 2% Belgian insurance premium tax (IPT) is added on top.</span></span></label>
            <div class="slider-wrap">
              <input type="range" id="lifeRate" min="0.05" max="0.60" step="0.05" value="0.20"
                oninput="document.getElementById('lifeDisplay').textContent=parseFloat(this.value).toFixed(2); document.getElementById('lifeVal').textContent=parseFloat(this.value).toFixed(2); debouncedCalc();"/>
              <span class="range-val"><span id="lifeVal">0.20</span>%</span>
            </div>
          </div>

          <div class="field">
            <label>Fire Insurance (annual)</label>
            <div class="input-wrap">
              <input type="number" id="fireAnnual" value="350" min="100" max="2000" step="50"
                oninput="debouncedCalc()"/>
              <span class="unit">€</span>
            </div>
          </div>

          <button class="btn-calc" onclick="calculate()">Calculate Mortgage →</button>
          <button class="btn-secondary" style="width:100%;margin-top:8px" onclick="shareURL()">Share / Copy URL</button>
        </div>
      </div>

      <!-- TAB: SCENARIO B -->
      <div class="tab-content" id="tab-compare">
        <div class="panel-body">

          <div class="field">
            <label>Property Price B</label>
            <div class="input-wrap">
              <input type="number" id="priceB" value="350000" min="10000" step="1000"
                oninput="onNumberInput(this); debouncedCalc()"/>
              <span class="unit">€</span>
            </div>
            <div class="error-msg" id="err-priceB"></div>
          </div>

          <div class="field">
            <label>Down Payment B</label>
            <div class="input-wrap">
              <input type="number" id="downB" value="70000" min="0" step="1000"
                oninput="onNumberInput(this); debouncedCalc()"/>
              <span class="unit">€</span>
            </div>
            <div class="error-msg" id="err-downB"></div>
          </div>

          <div class="field">
            <label>Annual Interest Rate B — <span id="rateBDisplay">3.50</span>%</label>
            <div class="slider-wrap">
              <input type="range" id="rateB" min="0.5" max="8" step="0.05" value="3.5"
                oninput="document.getElementById('rateBDisplay').textContent=parseFloat(this.value).toFixed(2); document.getElementById('rateBVal').textContent=parseFloat(this.value).toFixed(2); debouncedCalc();"/>
              <span class="range-val"><span id="rateBVal">3.50</span>%</span>
            </div>
          </div>

          <div class="field">
            <label>Loan Term B — <span id="termBDisplay">20</span> years</label>
            <div class="slider-wrap">
              <input type="range" id="termB" min="5" max="30" step="1" value="20"
                oninput="document.getElementById('termBDisplay').textContent=this.value; document.getElementById('termBVal').textContent=this.value; debouncedCalc();"/>
              <span class="range-val"><span id="termBVal">20</span>y</span>
            </div>
          </div>

          <div class="field">
            <label>Repayment Type B</label>
            <div class="radio-group">
              <div class="radio-btn">
                <input type="radio" name="typeB" id="annuityB" value="annuity" checked onchange="debouncedCalc()"/>
                <label for="annuityB">Annuity<br/><small style="color:inherit;opacity:.6">Fixed payment</small></label>
              </div>
              <div class="radio-btn">
                <input type="radio" name="typeB" id="straightB" value="straight" onchange="debouncedCalc()"/>
                <label for="straightB">Straight-line<br/><small style="color:inherit;opacity:.6">Fixed capital</small></label>
              </div>
            </div>
          </div>

          <div class="field">
            <label>Belgian Region B</label>
            <div class="input-wrap">
              <select id="regionB" onchange="debouncedCalc()">
                <option value="flanders">Flanders — 2% (primary) / 12% (invest.)</option>
                <option value="brussels">Brussels — 12.5% (€200k abatement ≤€600k)</option>
                <option value="wallonia">Wallonia — 3% (primary) / 12.5% (invest.)</option>
              </select>
            </div>
          </div>

          <div class="field">
            <label>Property Type B</label>
            <div class="radio-group">
              <div class="radio-btn">
                <input type="radio" name="buildB" id="existingB" value="existing" checked onchange="debouncedCalc()"/>
                <label for="existingB">Existing<br/><small style="color:inherit;opacity:.6">Registration duty</small></label>
              </div>
              <div class="radio-btn">
                <input type="radio" name="buildB" id="newbuildB" value="new" onchange="debouncedCalc()"/>
                <label for="newbuildB">New build<br/><small style="color:inherit;opacity:.6">21% VAT</small></label>
              </div>
            </div>
          </div>

          <div class="field">
            <label>Residence Use B</label>
            <div class="radio-group">
              <div class="radio-btn">
                <input type="radio" name="residenceB" id="primaryB" value="primary" checked onchange="debouncedCalc()"/>
                <label for="primaryB">Primary<br/><small style="color:inherit;opacity:.6">Abatements apply</small></label>
              </div>
              <div class="radio-btn">
                <input type="radio" name="residenceB" id="secondaryB" value="secondary" onchange="debouncedCalc()"/>
                <label for="secondaryB">Secondary / invest.<br/><small style="color:inherit;opacity:.6">No abatements</small></label>
              </div>
            </div>
          </div>

          <div class="field">
            <label>Life Insurance Rate B — <span id="lifeBDisplay">0.20</span>%/yr</label>
            <div class="slider-wrap">
              <input type="range" id="lifeRateB" min="0.05" max="0.60" step="0.05" value="0.20"
                oninput="document.getElementById('lifeBDisplay').textContent=parseFloat(this.value).toFixed(2); document.getElementById('lifeBVal').textContent=parseFloat(this.value).toFixed(2); debouncedCalc();"/>
              <span class="range-val"><span id="lifeBVal">0.20</span>%</span>
            </div>
          </div>

          <div class="field">
            <label>Fire Insurance B (annual)</label>
            <div class="input-wrap">
              <input type="number" id="fireAnnualB" value="350" min="100" max="2000" step="50"
                oninput="debouncedCalc()"/>
              <span class="unit">€</span>
            </div>
          </div>

          <button class="btn-calc" onclick="calculate()">Compare Scenarios →</button>
        </div>
      </div>

      <!-- TAB: AFFORDABILITY -->
      <div class="tab-content" id="tab-afford">
        <div class="panel-body">
          <div class="info-box">
            Belgian banks typically cap housing costs at <strong>33–40%</strong> of net monthly income. Enter your details below to estimate your price range — no loan setup required.
          </div>

          <div class="field">
            <label>Monthly Take Home Pay</label>
            <div class="input-wrap">
              <input type="number" id="netIncome" value="5000" min="500" step="100"
                oninput="renderAffordabilityEstimator();"/>
              <span class="unit">€</span>
            </div>
          </div>

          <div class="field">
            <label>Monthly Payment I'm Happy With</label>
            <div class="input-wrap">
              <input type="number" id="affordMonthly" value="1500" min="100" step="50"
                oninput="renderAffordabilityEstimator();"/>
              <span class="unit">€</span>
            </div>
          </div>

          <div class="field">
            <label>Deposit Available</label>
            <div class="input-wrap">
              <input type="number" id="affordDown" value="50000" min="0" step="1000"
                oninput="renderAffordabilityEstimator()"/>
              <span class="unit">€</span>
            </div>
          </div>

          <div class="field">
            <label>Loan Term — <span id="affordTermDisplay">20</span> years</label>
            <div class="slider-wrap">
              <input type="range" id="affordTerm" min="5" max="30" step="1" value="20"
                oninput="document.getElementById('affordTermDisplay').textContent=this.value; document.getElementById('affordTermVal').textContent=this.value; renderAffordabilityEstimator();"/>
              <span class="range-val"><span id="affordTermVal">20</span>y</span>
            </div>
          </div>

          <div class="field">
            <label>Interest Rate I Think I Could Get</label>
            <div class="input-wrap">
              <input type="number" id="affordRate" value="3.5" min="0.5" max="15" step="0.05"
                oninput="renderAffordabilityEstimator();"/>
              <span class="unit">%</span>
            </div>
          </div>

          <div class="field">
            <label>Existing Monthly Debt Payments <span class="tip-wrap"><span class="tip-icon" tabindex="0" onclick="toggleTip(this)">?</span><span class="tip-bubble">Include car loans, personal loans, credit card minimums, or other fixed monthly obligations. Belgian banks assess your total debt-to-income ratio — existing debt reduces the mortgage budget available to you.</span></span></label>
            <div class="input-wrap">
              <input type="number" id="existingDebt" value="0" min="0" step="50"
                oninput="renderAffordabilityEstimator();"/>
              <span class="unit">€</span>
            </div>
          </div>

        </div>
      </div>

      <!-- TAB: REFINANCING -->
      <div class="tab-content" id="tab-refi">
        <div class="panel-body">
          <div class="info-box">
            Is it worth switching to a lower rate? Enter your current mortgage details and a new rate offer below. Belgian law caps early repayment penalties at <strong>3 months' interest</strong> on the outstanding balance.
          </div>

          <div class="field">
            <label>Current Remaining Balance</label>
            <div class="input-wrap">
              <input type="number" id="refiBalance" value="200000" min="1000" step="1000"
                oninput="calcRefi();"/>
              <span class="unit">€</span>
            </div>
          </div>

          <div class="field">
            <label>Current Interest Rate</label>
            <div class="input-wrap">
              <input type="number" id="refiCurrentRate" value="3.50" min="0.1" max="15" step="0.05"
                oninput="calcRefi();"/>
              <span class="unit">%</span>
            </div>
          </div>

          <div class="field">
            <label>Remaining Term — <span id="refiTermDisplay">20</span> years</label>
            <div class="slider-wrap">
              <input type="range" id="refiTerm" min="1" max="30" step="1" value="20"
                oninput="document.getElementById('refiTermDisplay').textContent=this.value; document.getElementById('refiTermVal').textContent=this.value; calcRefi();"/>
              <span class="range-val"><span id="refiTermVal">20</span>y</span>
            </div>
          </div>

          <div class="field">
            <label>New Rate Offered — <span id="refiNewRateDisplay">2.80</span>%</label>
            <div class="slider-wrap">
              <input type="range" id="refiNewRate" min="0.5" max="8" step="0.05" value="2.80"
                oninput="document.getElementById('refiNewRateDisplay').textContent=parseFloat(this.value).toFixed(2); document.getElementById('refiNewRateVal').textContent=parseFloat(this.value).toFixed(2); calcRefi();"/>
              <span class="range-val"><span id="refiNewRateVal">2.80</span>%</span>
            </div>
          </div>

          <div class="field">
            <label>Early Repayment Penalty (auto-calculated, editable)</label>
            <div class="input-wrap">
              <input type="number" id="refiPenalty" value="0" min="0" step="100"
                oninput="calcRefi();"/>
              <span class="unit">€</span>
            </div>
          </div>

          <div class="field">
            <label>New Loan Costs / Refinancing Fees (auto-calculated, editable)</label>
            <div class="input-wrap">
              <input type="number" id="refiCosts" value="0" min="0" step="100"
                oninput="calcRefi();"/>
              <span class="unit">€</span>
            </div>
          </div>

        </div>
      </div>

    </div>
  </div>

  <!-- RIGHT: RESULTS (per-tab) -->
  <div style="min-width:0">
    <div class="results" id="results-main">
      <div class="panel">
        <div class="empty">
          <div class="empty-icon">🏠</div>
          <p>Enter your loan details — results update automatically as you type.</p>
        </div>
      </div>
    </div>
    <div class="results" id="results-compare" style="display:none">
      <div class="panel">
        <div class="empty">
          <div class="empty-icon">📊</div>
          <p>Enter Scenario B details — results appear here.</p>
        </div>
      </div>
    </div>
    <div class="results" id="results-afford" style="display:none">
      <div id="afford-estimator"></div>
    </div>
    <div class="results" id="results-refi" style="display:none">
      <div id="refi-estimator">
        <div class="panel">
          <div class="empty">
            <div class="empty-icon">🔄</div>
            <p>Enter your current mortgage details to see if refinancing makes sense.</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>


<div class="disclaimer">
  <div class="disclaimer-inner">
    <strong>Disclaimer:</strong> This simulator is provided for illustrative and informational purposes only. All calculations are estimates based on simplified models and may not reflect actual loan offers, fees, or tax treatment. Belgian tax rules, notary tariffs, and bank policies change frequently — figures shown (registration duties, abatements, notary fees, etc.) are approximations only. Life insurance includes 2% premium tax (IPT). This tool does not constitute financial, legal, or tax advice. Always consult a licensed mortgage broker, notary, or financial adviser before making any property purchase or financing decision.
  </div>
</div>

<div class="toast" id="toast">URL copied to clipboard</div>

<script>
// ─── STATE ───────────────────────────────────────────────────────────────────
let chartInstance = null;
let lastDataA = null;
let lastDataB = null;
let lastRendered = null;
let overpaymentSchedule = null; // null = original, array = revised with overpayments
let showingOverpayment = false;

function toAnnual(schedule) {
  const annual = [];
  const years = Math.ceil(schedule.length / 12);
  for (let yr = 1; yr <= years; yr++) {
    const rows = schedule.slice((yr - 1) * 12, yr * 12);
    if (!rows.length) break;
    annual.push({
      year: yr,
      payment: rows.reduce((s, r) => s + r.payment, 0),
      capital: rows.reduce((s, r) => s + r.capital, 0),
      interest: rows.reduce((s, r) => s + r.interest, 0),
      balance: rows[rows.length - 1].balance,
    });
  }
  return annual;
}

function renderAmortTable(annualRows, label) {
  const lbl = document.getElementById('amort-label');
  if (lbl) lbl.textContent = label || 'Amortisation Schedule (Annual)';
  const tbody = document.getElementById('amort-tbody');
  if (!tbody) return;
  tbody.innerHTML = annualRows.map(r => `
    <tr>
      <td>${r.year}</td>
      <td>${fmt(r.payment)}</td>
      <td class="capital">${fmt(r.capital)}</td>
      <td class="interest">${fmt(r.interest)}</td>
      <td class="balance">${fmt(r.balance)}</td>
    </tr>
  `).join('');
}
let debounceTimer = null;
let activeTab = 'main';

// ─── FORMATTING ───────────────────────────────────────────────────────────────
function fmt(n) {
  return '€' + Math.round(n).toLocaleString('nl-BE');
}
function fmtDiff(n) {
  const sign = n >= 0 ? '+' : '';
  return sign + Math.round(n).toLocaleString('nl-BE');
}

// ─── TOOLTIP HELPERS ─────────────────────────────────────────────────────────
function tip(text) {
  return `<span class="tip-wrap"><span class="tip-icon" tabindex="0" onclick="toggleTip(this)">?</span><span class="tip-bubble">${text}</span></span>`;
}

function toggleTip(el) {
  const bubble = el.nextElementSibling;
  document.querySelectorAll('.tip-bubble.visible').forEach(b => { if (b !== bubble) b.classList.remove('visible'); });
  bubble.classList.toggle('visible');
  if (bubble.classList.contains('visible')) {
    setTimeout(() => document.addEventListener('click', function h(e) {
      if (!e.target.closest('.tip-wrap')) { bubble.classList.remove('visible'); document.removeEventListener('click', h); }
    }), 0);
  }
}

// ─── SENSITIVITY MATRIX ───────────────────────────────────────────────────────
function calcPayment(loan, ratePercent, termYears) {
  const mr = Math.pow(1 + ratePercent / 100, 1 / 12) - 1;
  const n = termYears * 12;
  if (mr <= 0) return loan / n;
  return loan * (mr * Math.pow(1 + mr, n)) / (Math.pow(1 + mr, n) - 1);
}

function buildSensitivityMatrix(loan, currentRatePct, currentTerm) {
  const terms = [10, 15, 20, 25, 30];
  const base = Math.round(currentRatePct * 2) / 2;
  const rates = [];
  for (let r = Math.max(0.5, base - 2); r <= base + 2.01; r += 0.5) {
    rates.push(parseFloat(r.toFixed(1)));
  }
  let html = '<div class="sensitivity-wrap"><table class="sensitivity-table"><thead><tr>';
  html += '<th>Rate</th>' + terms.map(t => `<th>${t}y</th>`).join('') + '</tr></thead><tbody>';
  for (const rate of rates) {
    html += '<tr>';
    const isCurrentRate = Math.abs(rate - currentRatePct) < 0.001;
    html += `<td class="rate-label${isCurrentRate ? ' current-rate' : ''}">${rate.toFixed(1)}%</td>`;
    for (const term of terms) {
      const payment = calcPayment(loan, rate, term);
      const isActive = isCurrentRate && term === currentTerm;
      html += `<td class="${isActive ? 'cell-active' : ''}">${fmt(payment)}</td>`;
    }
    html += '</tr>';
  }
  html += '</tbody></table></div>';
  html += `<div class="sensitivity-note">Loan: ${fmt(loan)} &nbsp;·&nbsp; Highlighted cell = current selection &nbsp;·&nbsp; Monthly payment only</div>`;
  return html;
}

// ─── TABS ─────────────────────────────────────────────────────────────────────
function switchTab(name) {
  activeTab = name;
  const tabs = ['main', 'compare', 'afford', 'refi'];
  document.querySelectorAll('.tab-btn').forEach((b, i) => {
    b.classList.toggle('active', tabs[i] === name);
  });
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');

  // Show the correct right-side results panel
  ['results-main', 'results-compare', 'results-afford', 'results-refi'].forEach(id => {
    document.getElementById(id).style.display = 'none';
  });
  document.getElementById('results-' + name).style.display = '';

  // Properties section only for Loan tab
  if (name === 'afford') { renderAffordabilityEstimator(); }
  if (name === 'refi') { calcRefi(); }
}

// ─── VALIDATION ───────────────────────────────────────────────────────────────
function onNumberInput(el) {
  el.classList.remove('input-error');
}

function validate() {
  let ok = true;
  const price = parseFloat(document.getElementById('price').value) || 0;
  const down = parseFloat(document.getElementById('down').value) || 0;

  const errPrice = document.getElementById('err-price');
  const errDown = document.getElementById('err-down');

  if (price < 10000) {
    errPrice.textContent = 'Price must be at least €10,000';
    errPrice.classList.add('visible');
    document.getElementById('price').classList.add('input-error');
    ok = false;
  } else {
    errPrice.classList.remove('visible');
    document.getElementById('price').classList.remove('input-error');
  }

  if (down < 0) {
    errDown.textContent = 'Down payment cannot be negative';
    errDown.classList.add('visible');
    document.getElementById('down').classList.add('input-error');
    ok = false;
  } else if (down >= price) {
    errDown.textContent = 'Down payment must be less than the property price';
    errDown.classList.add('visible');
    document.getElementById('down').classList.add('input-error');
    ok = false;
  } else {
    errDown.classList.remove('visible');
    document.getElementById('down').classList.remove('input-error');
  }

  return ok;
}

function validateB() {
  let ok = true;
  const priceB = parseFloat(document.getElementById('priceB').value) || 0;
  const downB = parseFloat(document.getElementById('downB').value) || 0;
  const errPriceB = document.getElementById('err-priceB');
  const errDownB = document.getElementById('err-downB');

  if (priceB < 10000) {
    errPriceB.textContent = 'Price must be at least €10,000';
    errPriceB.classList.add('visible');
    document.getElementById('priceB').classList.add('input-error');
    ok = false;
  } else {
    errPriceB.classList.remove('visible');
    document.getElementById('priceB').classList.remove('input-error');
  }

  if (downB < 0) {
    errDownB.textContent = 'Down payment cannot be negative';
    errDownB.classList.add('visible');
    document.getElementById('downB').classList.add('input-error');
    ok = false;
  } else if (downB >= priceB) {
    errDownB.textContent = 'Down payment B must be less than the property price';
    errDownB.classList.add('visible');
    document.getElementById('downB').classList.add('input-error');
    ok = false;
  } else {
    errDownB.classList.remove('visible');
    document.getElementById('downB').classList.remove('input-error');
  }

  return ok;
}

// ─── DEBOUNCED CALCULATION ────────────────────────────────────────────────────
function debouncedCalc() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(calculate, 450);
}

// ─── PARAMS HELPERS ───────────────────────────────────────────────────────────
function getParamsA() {
  return {
    price: parseFloat(document.getElementById('price').value),
    down: parseFloat(document.getElementById('down').value),
    rate: parseFloat(document.getElementById('rate').value),
    term: parseInt(document.getElementById('term').value),
    loan_type: document.querySelector('input[name="type"]:checked').value,
    region: document.getElementById('region').value,
    is_new_build: document.querySelector('input[name="build"]:checked').value === 'new',
    primary_residence: document.querySelector('input[name="residence"]:checked').value === 'primary',
    life_insurance_rate: parseFloat(document.getElementById('lifeRate').value),
    fire_insurance_annual: parseFloat(document.getElementById('fireAnnual').value),
  };
}

function getParamsB() {
  return {
    price: parseFloat(document.getElementById('priceB').value),
    down: parseFloat(document.getElementById('downB').value),
    rate: parseFloat(document.getElementById('rateB').value),
    term: parseInt(document.getElementById('termB').value),
    loan_type: document.querySelector('input[name="typeB"]:checked').value,
    region: document.getElementById('regionB').value,
    is_new_build: document.querySelector('input[name="buildB"]:checked').value === 'new',
    primary_residence: document.querySelector('input[name="residenceB"]:checked').value === 'primary',
    life_insurance_rate: parseFloat(document.getElementById('lifeRateB').value),
    fire_insurance_annual: parseFloat(document.getElementById('fireAnnualB').value),
  };
}

// ─── MAIN CALCULATE ───────────────────────────────────────────────────────────
function calculate() {
  if (activeTab === 'compare') {
    if (!validateB()) return;
    const paramsB = getParamsB();
    fetch('/calculate', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(paramsB) })
      .then(r => r.json())
      .then(data => {
        lastDataB = data;
        renderResultsB(lastDataB);
      });
    return;
  }

  if (!validate()) return;
  const paramsA = getParamsA();

  fetch('/calculate', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(paramsA) })
    .then(r => r.json())
    .then(data => {
      lastDataA = data;
      saveToURL(paramsA, null);
      renderResults(lastDataA, null);
    });
}

// ─── RENDER RESULTS ───────────────────────────────────────────────────────────
function renderResults(d, dB, targetId = 'results-main') {
  lastRendered = d;
  overpaymentSchedule = null;
  showingOverpayment = false;
  const el = document.getElementById(targetId);
  const bc = d.buying_costs;

  const ltvLimit = d.primary_residence ? 90 : 80;
  const ltvWarning = d.ltv_pct > ltvLimit
    ? `<div class="ltv-warning animate">
        <span class="ltv-warning-icon">⚠</span>
        <span>LTV of ${d.ltv_pct.toFixed(1)}% exceeds NBB guideline of ${ltvLimit}% for ${d.primary_residence ? 'primary residences' : 'secondary / investment properties'}. Most Belgian banks will require a larger down payment or additional guarantees.</span>
       </div>`
    : '';

  const abatementRow = bc.abatement > 0
    ? `<li><span class="cost-label">Regional abatement saving</span><span class="cost-val saving">− ${fmt(bc.abatement)}</span></li>`
    : '';

  const trueMonthly = d.loan_type === 'annuity'
    ? fmt(d.monthly_payment + d.monthly_life_insurance + d.fire_insurance_annual / 12)
    : '—';

  const comparePanel = dB ? renderCompare(d, dB) : '';

  el.innerHTML = `
    ${ltvWarning}

    <!-- STATS -->
    <div class="stats-grid animate">
      <div class="stat-card primary">
        <div class="stat-label">Monthly Payment${dB ? ' <span class="scenario-badge badge-a">A</span>' : ''}</div>
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

    ${comparePanel}

    <!-- CHART -->
    <div class="panel chart-panel animate" style="animation-delay:0.1s">
      <div class="panel-header">Balance Over Time${dB ? ' — A vs B' : ''}</div>
      <div class="panel-body">
        <canvas id="myChart"></canvas>
      </div>
    </div>

    <!-- OVERPAYMENT -->
    <div class="panel animate" style="animation-delay:0.12s">
      <div class="panel-header">Overpayment Simulator</div>
      <div class="panel-body">
        <div class="field" style="margin-bottom:12px">
          <label>Extra Monthly Payment — <span id="extraDisplay">€0</span></label>
          <div class="slider-wrap">
            <input type="range" id="extraPayment" min="0" max="1000" step="50" value="0"
              oninput="document.getElementById('extraDisplay').textContent='€'+this.value; updateOverpayment();"/>
            <span class="range-val" style="color:var(--green)">€<span id="extraVal">0</span></span>
          </div>
        </div>
        <div id="overpay-results">
          <div style="font-size:12px;color:var(--muted)">Move the slider to simulate extra monthly repayments.</div>
        </div>
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
            <span class="cost-label">${bc.is_new_build ? 'VAT 21% (new build / VEFA)' : 'Registration fees (' + bc.reg_rate + '%)'}${tip(bc.is_new_build ? 'New builds attract 21% Belgian VAT (BTW/TVA) instead of registration duty. Paid to the developer at completion.' : 'Transfer tax (verkooprecht / droits d\\'enregistrement) paid to the Belgian region. Rates differ by region, property type, and primary vs secondary residence.')}</span>
            <span class="cost-val">${fmt(bc.registration)}</span>
          </li>
          ${abatementRow}
          <li><span class="cost-label">Notary fees (est.)${tip('Includes the notary\\'s statutory professional fee (degressive scale set by law) plus 21% VAT and disbursements such as search fees and admin costs. Estimated here at approx. 1.5× the statutory base fee.')}</span><span class="cost-val">${fmt(bc.notary)}</span></li>
          <li><span class="cost-label">Mortgage deed / hypotheekakte (est.)${tip('Registering the mortgage with the Belgian Mortgage Registry costs approx. 1.3% of the loan amount: 1% registration tax + 0.3% mortgage duty (hypotheekrecht), both levied on the loan amount.')}</span><span class="cost-val">${fmt(bc.deed)}</span></li>
          <li><span class="cost-label" style="color:var(--text)">Total upfront</span><span class="cost-val accent">${fmt(bc.total)}</span></li>

          <span class="costs-section">Ongoing Costs Over ${d.term} Years</span>

          <li><span class="cost-label">Total repaid (capital + interest)</span><span class="cost-val">${fmt(d.total_repaid)}</span></li>
          <li>
            <span class="cost-label">Life ins. (SSV, ${d.life_insurance_rate.toFixed(2)}%/yr + 2% IPT)${tip('Schuldsaldoverzekering (SSV): pays off the outstanding balance if you die during the mortgage. The 2% IPT (Insurance Premium Tax) is a Belgian federal tax applied to all insurance premiums. Cost shown is estimated over the full term on a declining balance.')}</span>
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
      <div class="panel-header">
        <div class="panel-header-left" style="display:flex;align-items:center;gap:10px;">
          <span id="amort-label">Amortisation Schedule (Annual)</span>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <button class="btn-secondary" id="toggleOverpay" style="display:none" onclick="toggleOverpayTable()">⚡ With Overpayments</button>
          <button class="btn-secondary" onclick="exportCSV()">↓ CSV</button>
        </div>
      </div>
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
            <tbody id="amort-tbody">
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

    <!-- SENSITIVITY MATRIX -->
    <div class="panel animate" style="animation-delay:0.25s">
      <div class="panel-header">Rate × Term Sensitivity ${tip('Monthly payment for this loan amount at different interest rates and terms. The highlighted cell is your current selection. Useful for quickly seeing how a better rate or shorter term changes your payment.')}</div>
      <div class="panel-body" style="padding:0">
        ${buildSensitivityMatrix(d.loan_amount, parseFloat(document.getElementById('rate').value), d.term)}
      </div>
    </div>
  `;

  drawChart(d, dB);
  updateOverpayment();
}

// ─── SCENARIO COMPARISON ──────────────────────────────────────────────────────
function renderCompare(a, b) {
  const rows = [
    ['Monthly payment', a.monthly_display, b.monthly_display, null, true],
    ['Loan amount', fmt(a.loan_amount), fmt(b.loan_amount), b.loan_amount - a.loan_amount, false],
    ['Total interest', fmt(a.total_interest), fmt(b.total_interest), b.total_interest - a.total_interest, false],
    ['Life insurance', fmt(a.total_life_insurance), fmt(b.total_life_insurance), b.total_life_insurance - a.total_life_insurance, false],
    ['Upfront costs', fmt(a.buying_costs.total), fmt(b.buying_costs.total), b.buying_costs.total - a.buying_costs.total, false],
    ['Grand total', fmt(a.grand_total), fmt(b.grand_total), b.grand_total - a.grand_total, false],
  ];

  return `
    <div class="panel animate" style="animation-delay:0.08s">
      <div class="panel-header">Scenario Comparison</div>
      <div class="panel-body" style="padding:0">
        <div class="compare-table-wrap">
        <table class="compare-table">
          <thead>
            <tr>
              <th style="text-align:left">Metric</th>
              <th>Scenario A <span class="scenario-badge badge-a" style="font-size:9px">A</span></th>
              <th>Scenario B <span class="scenario-badge badge-b" style="font-size:9px">B</span></th>
              <th>Δ vs A</th>
            </tr>
          </thead>
          <tbody>
            ${rows.map(([label, va, vb, delta, noFormat]) => {
              let deltaCell = '—';
              if (delta !== null) {
                const cls = delta < 0 ? 'delta-pos' : 'delta-neg';
                deltaCell = `<span class="${cls}">${fmtDiff(delta)}</span>`;
              }
              return `<tr>
                <td>${label}</td>
                <td style="color:var(--gold)">${va}</td>
                <td style="color:var(--blue)">${vb}</td>
                <td>${deltaCell}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
        </div>
      </div>
    </div>
  `;
}

// ─── RENDER RESULTS B (standalone, no cross-tab data) ─────────────────────────
function renderResultsB(d) {
  renderResults(d, null, 'results-compare');
}

// ─── CHART ────────────────────────────────────────────────────────────────────
function drawChart(d, dB) {
  if (chartInstance) chartInstance.destroy();
  const ctx = document.getElementById('myChart').getContext('2d');

  const labels = d.annual.map(r => 'Y' + r.year);
  const labelSuffix = dB ? ' A' : '';
  const datasets = [
    {
      label: 'Balance' + labelSuffix,
      data: d.annual.map(r => r.balance),
      borderColor: '#c9a84c',
      backgroundColor: 'rgba(201,168,76,0.08)',
      fill: true, tension: 0.3, pointRadius: 3,
      pointBackgroundColor: '#c9a84c',
    },
    {
      label: 'Cumul. Interest' + labelSuffix,
      data: d.annual.map(r => r.cum_interest),
      borderColor: '#e05555',
      backgroundColor: 'rgba(224,85,85,0.05)',
      fill: true, tension: 0.3, pointRadius: 3,
      pointBackgroundColor: '#e05555',
    },
  ];

  if (dB) {
    // Align B labels to A's x-axis length
    datasets.push({
      label: 'Balance B',
      data: dB.annual.map(r => r.balance),
      borderColor: '#5b9bd5',
      backgroundColor: 'rgba(91,155,213,0.06)',
      fill: false, tension: 0.3, pointRadius: 2,
      borderDash: [4, 4],
      pointBackgroundColor: '#5b9bd5',
    });
    datasets.push({
      label: 'Cumul. Interest B',
      data: dB.annual.map(r => r.cum_interest),
      borderColor: '#a07cc8',
      backgroundColor: 'transparent',
      fill: false, tension: 0.3, pointRadius: 2,
      borderDash: [4, 4],
      pointBackgroundColor: '#a07cc8',
    });
    // Extend labels to max term
    const maxYr = Math.max(d.term, dB.term);
    for (let i = labels.length + 1; i <= maxYr; i++) labels.push('Y' + i);
  }

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: '#7a7d8a', font: { family: 'DM Mono', size: 11 } } },
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

// ─── OVERPAYMENT SIMULATOR ────────────────────────────────────────────────────
function updateOverpayment() {
  if (!lastRendered) return;
  const extra = parseFloat(document.getElementById('extraPayment').value) || 0;
  document.getElementById('extraVal').textContent = extra;
  const el = document.getElementById('overpay-results');
  const toggleBtn = document.getElementById('toggleOverpay');
  if (!el) return;

  if (extra === 0) {
    overpaymentSchedule = null;
    showingOverpayment = false;
    if (toggleBtn) toggleBtn.style.display = 'none';
    renderAmortTable(lastRendered.annual, 'Amortisation Schedule (Annual)');
    el.innerHTML = '<div style="font-size:12px;color:var(--muted)">Move the slider to simulate extra monthly repayments.</div>';
    return;
  }

  const d = lastRendered;
  if (d.loan_type !== 'annuity') {
    overpaymentSchedule = null;
    if (toggleBtn) toggleBtn.style.display = 'none';
    el.innerHTML = '<div style="font-size:12px;color:var(--muted)">Overpayment simulation is available for annuity loans only.</div>';
    return;
  }

  const loan = d.loan_amount;
  const mp = d.monthly_payment;
  const n0 = d.term * 12;

  // Simulate with extra payment — now returns full monthly schedule
  const simResult = simulateExtra(loan, mp, extra, d.term);
  const monthsSaved = n0 - simResult.months;
  const interestSaved = d.total_interest - simResult.totalInterest;
  const yearsSaved = Math.floor(monthsSaved / 12);
  const remMonths = monthsSaved % 12;

  const timeStr = yearsSaved > 0
    ? (yearsSaved + 'y ' + (remMonths > 0 ? remMonths + 'm' : ''))
    : (remMonths + ' months');

  // Store revised schedule and update table
  overpaymentSchedule = simResult.monthlySchedule;
  showingOverpayment = true;
  if (toggleBtn) {
    toggleBtn.style.display = '';
    toggleBtn.textContent = '📋 Show Original';
  }
  renderAmortTable(toAnnual(overpaymentSchedule), 'Amortisation Schedule — With Overpayments');

  el.innerHTML = `
    <div class="overpay-result">
      <div class="overpay-stat">
        <div class="o-label">Time Saved</div>
        <div class="o-val">${timeStr.trim()}</div>
        <div class="o-sub">${simResult.months} months remaining</div>
      </div>
      <div class="overpay-stat">
        <div class="o-label">Interest Saved</div>
        <div class="o-val">${fmt(interestSaved)}</div>
        <div class="o-sub">${Math.round(interestSaved/d.total_interest*100)}% less interest</div>
      </div>
    </div>
  `;
}

function toggleOverpayTable() {
  if (!lastRendered || !overpaymentSchedule) return;
  const btn = document.getElementById('toggleOverpay');
  showingOverpayment = !showingOverpayment;
  if (showingOverpayment) {
    renderAmortTable(toAnnual(overpaymentSchedule), 'Amortisation Schedule — With Overpayments');
    if (btn) btn.textContent = '📋 Show Original';
  } else {
    renderAmortTable(lastRendered.annual, 'Amortisation Schedule (Annual)');
    if (btn) btn.textContent = '⚡ With Overpayments';
  }
}

function simulateExtra(loan, requiredPayment, extra, termYears) {
  // Find monthly_rate from requiredPayment and loan using Newton's method approximation
  // Instead, derive from the schedule data approximation:
  // We approximate monthly_rate by back-calculating from payment formula
  let balance = loan;
  let months = 0;
  let totalInterest = 0;
  const monthlySchedule = [];

  // Get monthly rate: payment = loan * r(1+r)^n / ((1+r)^n - 1)
  // Use bisection to find r
  const n = termYears * 12;
  let rLo = 0.0001, rHi = 0.01;
  for (let iter = 0; iter < 50; iter++) {
    const rMid = (rLo + rHi) / 2;
    const pmt = loan * (rMid * Math.pow(1+rMid, n)) / (Math.pow(1+rMid, n) - 1);
    if (pmt < requiredPayment) rLo = rMid; else rHi = rMid;
  }
  const monthlyRate = (rLo + rHi) / 2;

  while (balance > 0.01 && months < n) {
    months++;
    const interest = balance * monthlyRate;
    totalInterest += interest;
    const totalPmt = Math.min(balance + interest, requiredPayment + extra);
    const capital = totalPmt - interest;
    balance = Math.max(balance - capital, 0);
    monthlySchedule.push({ month: months, payment: totalPmt, capital, interest, balance });
  }
  return { months, totalInterest, monthlySchedule };
}

// ─── AFFORDABILITY ESTIMATOR (standalone, no Scenario A required) ─────────────
function renderAffordabilityEstimator() {
  const el = document.getElementById('afford-estimator');
  if (!el) return;

  const income        = parseFloat(document.getElementById('netIncome').value)     || 0;
  const targetMonthly = parseFloat(document.getElementById('affordMonthly').value) || 0;
  const down          = parseFloat(document.getElementById('affordDown').value)     || 0;
  const term          = parseInt(document.getElementById('affordTerm').value)       || 20;
  const rate          = parseFloat(document.getElementById('affordRate').value) / 100;
  const existingDebt  = parseFloat(document.getElementById('existingDebt').value)  || 0;

  if (targetMonthly <= 0 && income <= 0) {
    el.innerHTML = '<div class="info-box" style="color:var(--muted)">Enter your details above to see your price range.</div>';
    return;
  }

  // Monthly rate (compound)
  const mr = Math.pow(1 + rate, 1/12) - 1;
  const n  = term * 12;

  // Annuity formula: max loan = payment × [(1+r)^n − 1] / [r × (1+r)^n]
  function maxLoanForBudget(monthlyBudget) {
    if (mr <= 0) return monthlyBudget * n;
    return monthlyBudget * (Math.pow(1+mr, n) - 1) / (mr * Math.pow(1+mr, n));
  }

  // Primary: use the monthly budget the user is happy with
  const budget = targetMonthly > 0 ? targetMonthly : income * 0.33;
  const loan   = maxLoanForBudget(budget);
  const price  = loan + down;
  const ltvPct = price > 0 ? (loan / price * 100) : 100;
  const incomeRatioPct = income > 0 ? (budget / income * 100) : null;

  // Total DTI = (mortgage payment + existing debt) / income
  const totalDTI = income > 0 ? ((budget + existingDebt) / income * 100) : null;
  const dtiColor = totalDTI === null ? 'var(--text)'
    : totalDTI <= 33 ? 'var(--green)'
    : totalDTI <= 43 ? 'var(--orange)'
    : 'var(--red)';

  // Max affordable mortgage given existing debt and 43% DTI cap
  const maxTotalDebt43 = income > 0 ? income * 0.43 : null;
  const maxMortgageBudget = maxTotalDebt43 ? Math.max(0, maxTotalDebt43 - existingDebt) : null;
  const maxLoanWithDebt = maxMortgageBudget ? maxLoanForBudget(maxMortgageBudget) : null;
  const maxPriceWithDebt = maxLoanWithDebt !== null ? maxLoanWithDebt + down : null;

  // Stress test at rate + 1%
  const stressRate = rate + 0.01;
  const smr = Math.pow(1 + stressRate, 1/12) - 1;
  const sLoan  = smr <= 0 ? budget * n : budget * (Math.pow(1+smr, n) - 1) / (smr * Math.pow(1+smr, n));
  const sPrice = sLoan + down;

  // What the banks' 33%/40% guidelines give, for context
  const budget33 = income > 0 ? income * 0.33 : null;
  const budget40 = income > 0 ? income * 0.40 : null;
  const price33  = budget33 ? maxLoanForBudget(budget33) + down : null;
  const price40  = budget40 ? maxLoanForBudget(budget40) + down : null;

  const ratioColor = incomeRatioPct === null ? 'var(--text)'
    : incomeRatioPct <= 33 ? 'var(--green)'
    : incomeRatioPct <= 40 ? 'var(--orange)'
    : 'var(--red)';

  const dtiCardBorder = totalDTI !== null && totalDTI > 43 ? 'border-color:var(--red)' : '';

  el.innerHTML = `
    <div style="margin-bottom:8px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;">Your Budget Estimate</div>
    <div class="afford-grid" style="margin-top:4px;">
      <div class="afford-card" style="border-color:var(--green)">
        <div class="a-label">Max Property Price</div>
        <div class="a-val ok" style="font-size:18px;">${fmt(price)}</div>
        <div class="a-sub">Loan ${fmt(loan)} · LTV ${ltvPct.toFixed(0)}%</div>
      </div>
      <div class="afford-card">
        <div class="a-label">Deposit</div>
        <div class="a-val" style="font-size:16px;color:var(--text)">${fmt(down)}</div>
        <div class="a-sub">${ltvPct < 100 ? ltvPct.toFixed(0) + '% LTV — ' + (100 - ltvPct).toFixed(0) + '% equity' : 'no deposit entered'}</div>
      </div>
      <div class="afford-card">
        <div class="a-label">Stress Test at ${((rate+0.01)*100).toFixed(2)}%</div>
        <div class="a-val" style="font-size:16px;color:var(--text)">${fmt(sPrice)}</div>
        <div class="a-sub">if rate rises 1%, same monthly budget</div>
      </div>
      <div class="afford-card">
        <div class="a-label">Housing Cost Ratio</div>
        <div class="a-val" style="font-size:16px;color:${ratioColor}">${incomeRatioPct !== null ? incomeRatioPct.toFixed(1) + '%' : '—'}</div>
        <div class="a-sub">mortgage only · banks prefer ≤33–40%</div>
      </div>
    </div>

    <div style="margin-top:14px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;">Debt-to-Income (DTI) Assessment</div>
    <div class="afford-grid" style="margin-top:4px;">
      <div class="afford-card" style="${dtiCardBorder}">
        <div class="a-label">Total DTI</div>
        <div class="a-val" style="font-size:16px;color:${dtiColor}">${totalDTI !== null ? totalDTI.toFixed(1) + '%' : '—'}</div>
        <div class="a-sub">mortgage + existing debt · bank hard limit ≈43%</div>
      </div>
      ${existingDebt > 0 && maxPriceWithDebt !== null ? `
      <div class="afford-card">
        <div class="a-label">Max Price at 43% DTI</div>
        <div class="a-val" style="font-size:15px;color:var(--text)">${fmt(maxPriceWithDebt)}</div>
        <div class="a-sub">after existing debt of ${fmt(existingDebt)}/mo</div>
      </div>` : `
      <div class="afford-card">
        <div class="a-label">Existing Monthly Debt</div>
        <div class="a-val" style="font-size:15px;color:var(--muted)">${fmt(existingDebt)}</div>
        <div class="a-sub">add existing obligations in the input above</div>
      </div>`}
    </div>

    ${price33 || price40 ? `
    <div style="margin-top:14px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;">Bank Guidelines (for reference)</div>
    <div class="afford-grid" style="margin-top:4px;">
      ${price33 ? `<div class="afford-card"><div class="a-label">Conservative (33%)</div><div class="a-val" style="font-size:15px;color:var(--text)">${fmt(price33)}</div><div class="a-sub">${budget33.toFixed(0)}€/mo</div></div>` : ''}
      ${price40 ? `<div class="afford-card"><div class="a-label">Upper bound (40%)</div><div class="a-val" style="font-size:15px;color:var(--text)">${fmt(price40)}</div><div class="a-sub">${budget40.toFixed(0)}€/mo</div></div>` : ''}
    </div>` : ''}
    <div class="info-box" style="margin-top:10px;font-size:11px;color:var(--muted)">
      Price = loan + deposit. Buying costs (registration tax, notary fees) come on top — budget an extra 10–15% for existing properties or 2–4% for new builds.
    </div>
  `;
}

function fmtK(v) {
  if (v >= 1000000) return (v/1000000).toFixed(2) + 'M';
  if (v >= 1000) return Math.round(v/1000) + 'K';
  return Math.round(v) + '';
}

// ─── AFFORDABILITY ────────────────────────────────────────────────────────────
function renderAffordability() {
  if (!lastDataA) return;
  const income = parseFloat(document.getElementById('netIncome').value) || 0;
  const el = document.getElementById('afford-results');
  if (!el || income <= 0) return;

  const d = lastDataA;
  if (d.loan_type !== 'annuity') {
    el.innerHTML = '<div class="info-box">Affordability check is available for annuity loans.</div>';
    return;
  }

  const trueMonthlyCost = d.monthly_payment + d.monthly_life_insurance + d.fire_insurance_annual / 12;
  const ratio = trueMonthlyCost / income * 100;
  const guideline = d.primary_residence ? 33 : 30;

  // Stress test: recalculate payment at rate + 1%
  const baseRate = parseFloat(document.getElementById('rate').value) / 100;
  const stressRate = baseRate + 0.01;
  const mr = Math.pow(1 + stressRate, 1/12) - 1;
  const n = d.term * 12;
  const stressPayment = d.loan_amount * (mr * Math.pow(1+mr, n)) / (Math.pow(1+mr, n) - 1);
  const stressTotal = stressPayment + d.monthly_life_insurance + d.fire_insurance_annual / 12;
  const stressRatio = stressTotal / income * 100;

  // Max affordable loan at this income and rate
  const maxPayment = income * (guideline / 100);
  const maxLoan = mr > 0
    ? maxPayment * (Math.pow(1+mr,n) - 1) / (mr * Math.pow(1+mr,n))
    : maxPayment * n;
  const minIncome = trueMonthlyCost / (guideline / 100);

  const ratioClass = ratio <= guideline ? 'ok' : ratio <= guideline + 7 ? 'warn' : 'bad';
  const stressClass = stressRatio <= guideline ? 'ok' : stressRatio <= guideline + 7 ? 'warn' : 'bad';
  const barColor = ratio <= guideline ? 'var(--green)' : ratio <= guideline + 7 ? 'var(--orange)' : 'var(--red)';
  const barW = Math.min(ratio / (guideline * 2) * 100, 100).toFixed(1);

  el.innerHTML = `
    <div class="afford-grid">
      <div class="afford-card">
        <div class="a-label">Housing Cost Ratio</div>
        <div class="a-val ${ratioClass}">${ratio.toFixed(1)}%</div>
        <div class="a-sub">of net income (guideline: ${guideline}%)</div>
        <div class="stress-bar-wrap"><div class="stress-bar" style="width:${barW}%;background:${barColor}"></div></div>
      </div>
      <div class="afford-card">
        <div class="a-label">Stress Test (+1%)</div>
        <div class="a-val ${stressClass}">${stressRatio.toFixed(1)}%</div>
        <div class="a-sub">at ${((baseRate + 0.01)*100).toFixed(2)}% rate</div>
      </div>
      <div class="afford-card">
        <div class="a-label">Max Affordable Loan</div>
        <div class="a-val" style="font-size:16px;color:var(--text)">${fmt(maxLoan)}</div>
        <div class="a-sub">at ${guideline}% rule, current rate &amp; term</div>
      </div>
      <div class="afford-card">
        <div class="a-label">Min. Income Required</div>
        <div class="a-val" style="font-size:16px;color:var(--text)">${fmt(minIncome)}/mo</div>
        <div class="a-sub">net, for ${guideline}% ratio</div>
      </div>
    </div>
  `;
}

// ─── REFINANCING CALCULATOR ───────────────────────────────────────────────────
function calcRefi() {
  const el = document.getElementById('refi-estimator');
  if (!el) return;

  const balance  = parseFloat(document.getElementById('refiBalance').value)     || 0;
  const curRate  = parseFloat(document.getElementById('refiCurrentRate').value) || 0;
  const term     = parseInt(document.getElementById('refiTerm').value)           || 20;
  const newRate  = parseFloat(document.getElementById('refiNewRate').value)     || 0;

  if (balance <= 0 || curRate <= 0 || newRate <= 0) {
    el.innerHTML = '<div class="panel"><div class="empty"><div class="empty-icon">🔄</div><p>Enter your current mortgage details to see if refinancing makes sense.</p></div></div>';
    return;
  }

  const n = term * 12;
  const rOld = Math.pow(1 + curRate / 100, 1/12) - 1;
  const rNew = Math.pow(1 + newRate  / 100, 1/12) - 1;

  // Monthly payments
  const pmtOld = rOld === 0 ? balance / n : balance * (rOld * Math.pow(1+rOld, n)) / (Math.pow(1+rOld, n) - 1);
  const pmtNew = rNew === 0 ? balance / n : balance * (rNew * Math.pow(1+rNew, n)) / (Math.pow(1+rNew, n) - 1);
  const monthlySaving = pmtOld - pmtNew;

  // Auto-fill penalty and costs if they are still at their default (0) or user hasn't touched them
  const penaltyField = document.getElementById('refiPenalty');
  const costsField   = document.getElementById('refiCosts');
  const autoPenalty  = Math.round(balance * (curRate / 100 / 12) * 3);
  const autoCosts    = Math.round(balance * 0.013);
  if (parseFloat(penaltyField.value) === 0) penaltyField.value = autoPenalty;
  if (parseFloat(costsField.value)   === 0) costsField.value   = autoCosts;

  const penalty   = parseFloat(penaltyField.value) || 0;
  const refiCosts = parseFloat(costsField.value)   || 0;
  const totalCost = penalty + refiCosts;

  // Total interest over remaining term (simple annuity sum)
  let totalIntOld = 0, totalIntNew = 0, balOld = balance, balNew = balance;
  for (let i = 0; i < n; i++) {
    totalIntOld += balOld * rOld;
    balOld -= (pmtOld - balOld * rOld);
    totalIntNew += balNew * rNew;
    balNew -= (pmtNew - balNew * rNew);
  }
  const interestSaved = totalIntOld - totalIntNew;

  // Break-even
  const breakEvenMonths = monthlySaving > 0 ? Math.ceil(totalCost / monthlySaving) : Infinity;
  const breakEvenYears  = Math.floor(breakEvenMonths / 12);
  const breakEvenRem    = breakEvenMonths % 12;
  const breakEvenStr    = breakEvenMonths === Infinity ? 'Never'
    : breakEvenYears > 0 ? (breakEvenYears + 'y ' + (breakEvenRem ? breakEvenRem + 'm' : ''))
    : (breakEvenMonths + ' months');

  const net5yr  = (monthlySaving * 60)  - totalCost;
  const net10yr = (monthlySaving * 120) - totalCost;
  const notWorthwhile = breakEvenMonths > n;

  const rateColor = newRate < curRate ? 'var(--green)' : 'var(--red)';
  const savingColor = monthlySaving > 0 ? 'var(--green)' : 'var(--red)';

  el.innerHTML = `
    <div class="panel animate">
      <div class="panel-header">Refinancing Analysis</div>
      <div class="panel-body">
        ${notWorthwhile ? `<div class="ltv-warning animate" style="margin-bottom:16px">
          ⚠️ Break-even (${breakEvenStr}) exceeds your remaining term (${term}y). Refinancing may not be worthwhile at this rate difference.
        </div>` : ''}

        <div class="stat-grid" style="grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:16px;">
          <div class="stat-card" style="background:var(--card-bg)">
            <div class="stat-label">Current Payment</div>
            <div class="stat-val">${fmt(pmtOld)}<span class="stat-unit">/mo</span></div>
            <div class="stat-sub">at ${curRate.toFixed(2)}%</div>
          </div>
          <div class="stat-card" style="background:var(--card-bg)">
            <div class="stat-label">New Payment</div>
            <div class="stat-val" style="color:${rateColor}">${fmt(pmtNew)}<span class="stat-unit">/mo</span></div>
            <div class="stat-sub">at ${newRate.toFixed(2)}%</div>
          </div>
          <div class="stat-card" style="background:var(--card-bg)">
            <div class="stat-label">Monthly Saving</div>
            <div class="stat-val" style="color:${savingColor}">${fmt(Math.abs(monthlySaving))}</div>
            <div class="stat-sub">${monthlySaving >= 0 ? 'saved per month' : 'extra per month'}</div>
          </div>
          <div class="stat-card" style="background:var(--card-bg)">
            <div class="stat-label">Break-Even</div>
            <div class="stat-val" style="color:${notWorthwhile ? 'var(--red)' : 'var(--gold)'}">${breakEvenStr}</div>
            <div class="stat-sub">to recoup refi costs</div>
          </div>
        </div>

        <div class="costs-list">
          <div class="costs-section-title">Refinancing Costs</div>
          <div class="costs-row"><span>Early repayment penalty (3 mo. interest)</span><span>${fmt(penalty)}</span></div>
          <div class="costs-row"><span>New mortgage deed &amp; fees (~1.3%)</span><span>${fmt(refiCosts)}</span></div>
          <div class="costs-row costs-total"><span>Total upfront cost</span><span>${fmt(totalCost)}</span></div>

          <div class="costs-section-title" style="margin-top:14px">Long-Term Benefit</div>
          <div class="costs-row"><span>Interest saved over full term</span><span style="color:var(--green)">${fmt(interestSaved)}</span></div>
          <div class="costs-row"><span>Net benefit after 5 years</span><span style="color:${net5yr >= 0 ? 'var(--green)' : 'var(--red)'}">${net5yr >= 0 ? '+' : ''}${fmt(net5yr)}</span></div>
          <div class="costs-row"><span>Net benefit after 10 years</span><span style="color:${net10yr >= 0 ? 'var(--green)' : 'var(--red)'}">${net10yr >= 0 ? '+' : ''}${fmt(net10yr)}</span></div>
        </div>
      </div>
    </div>
  `;
}

// ─── CSV EXPORT ───────────────────────────────────────────────────────────────
function exportCSV() {
  if (!lastRendered) return;
  const d = lastRendered;
  const useOverpay = showingOverpayment && overpaymentSchedule;
  const source = useOverpay ? overpaymentSchedule : d.monthly_schedule;
  const rows = [['Month', 'Payment (€)', 'Capital (€)', 'Interest (€)', 'Balance (€)']];
  source.forEach(r => {
    rows.push([r.month, Math.round(r.payment), Math.round(r.capital), Math.round(r.interest), Math.round(r.balance)]);
  });
  const csv = rows.map(r => r.join(',')).join('\\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = useOverpay ? 'mortgage_schedule_overpayment.csv' : 'mortgage_schedule.csv';
  a.click();
  URL.revokeObjectURL(url);
}

// ─── URL HASH STATE ───────────────────────────────────────────────────────────
function saveToURL(paramsA, paramsB) {
  const p = new URLSearchParams();
  p.set('price', paramsA.price);
  p.set('down', paramsA.down);
  p.set('rate', paramsA.rate.toFixed ? (paramsA.rate * 100).toFixed(2) : paramsA.rate);
  p.set('term', paramsA.term);
  p.set('type', paramsA.loan_type);
  p.set('region', paramsA.region);
  p.set('build', paramsA.is_new_build ? 'new' : 'existing');
  p.set('res', paramsA.primary_residence ? 'primary' : 'secondary');
  p.set('life', paramsA.life_insurance_rate);
  p.set('fire', paramsA.fire_insurance_annual);
  if (paramsB) {
    p.set('rateB', (paramsB.rate * 100).toFixed(2));
    p.set('termB', paramsB.term);
    p.set('downB', paramsB.down);
    p.set('typeB', paramsB.loan_type);
  }
  history.replaceState(null, '', '#' + p.toString());
}

function loadFromURL() {
  const hash = window.location.hash.slice(1);
  if (!hash) return;
  const p = new URLSearchParams(hash);
  const set = (id, val) => { if (val !== null) { const el = document.getElementById(id); if (el) el.value = val; } };
  const setRadio = (name, val) => { const el = document.querySelector(`input[name="${name}"][value="${val}"]`); if (el) el.checked = true; };

  set('price', p.get('price'));
  set('down', p.get('down'));
  if (p.get('rate')) {
    set('rate', p.get('rate'));
    document.getElementById('rateDisplay').textContent = parseFloat(p.get('rate')).toFixed(2);
    document.getElementById('rateVal').textContent = parseFloat(p.get('rate')).toFixed(2);
  }
  if (p.get('term')) {
    set('term', p.get('term'));
    document.getElementById('termDisplay').textContent = p.get('term');
    document.getElementById('termVal').textContent = p.get('term');
  }
  if (p.get('type')) setRadio('type', p.get('type'));
  if (p.get('region')) set('region', p.get('region'));
  if (p.get('build')) setRadio('build', p.get('build'));
  if (p.get('res')) setRadio('residence', p.get('res'));
  if (p.get('life')) {
    set('lifeRate', p.get('life'));
    document.getElementById('lifeDisplay').textContent = parseFloat(p.get('life')).toFixed(2);
    document.getElementById('lifeVal').textContent = parseFloat(p.get('life')).toFixed(2);
  }
  if (p.get('fire')) set('fireAnnual', p.get('fire'));

  if (p.get('rateB')) {
    set('rateB', p.get('rateB'));
    document.getElementById('rateBDisplay').textContent = parseFloat(p.get('rateB')).toFixed(2);
    document.getElementById('rateBVal').textContent = parseFloat(p.get('rateB')).toFixed(2);
  }
  if (p.get('termB')) {
    set('termB', p.get('termB'));
    document.getElementById('termBDisplay').textContent = p.get('termB');
    document.getElementById('termBVal').textContent = p.get('termB');
  }
  if (p.get('downB')) set('downB', p.get('downB'));
  if (p.get('typeB')) setRadio('typeB', p.get('typeB'));

  calculate();
}

// ─── SHARE URL ────────────────────────────────────────────────────────────────
function shareURL() {
  const url = window.location.href;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(url).then(() => showToast('URL copied to clipboard'));
  } else {
    showToast('Copy the URL from your address bar');
  }
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('visible');
  setTimeout(() => t.classList.remove('visible'), 2500);
}

// ─── INIT ────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  loadFromURL();
  renderAffordabilityEstimator();
  if (!window.location.hash) calculate();
});
</script>

<footer class="site-footer">
  <p>If this tool saved you time, consider buying me a coffee ☕</p>
  <a href="https://ko-fi.com/halfbrowse" target="_blank" rel="noopener noreferrer" class="kofi-btn">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M23.881 8.948c-.773-4.085-4.859-4.593-4.859-4.593H.723c-.604 0-.679.798-.679.798s-.082 7.324-.022 11.822c.164 2.424 2.586 2.672 2.586 2.672s8.267-.023 11.966-.049c2.438-.426 2.683-2.566 2.658-3.734 4.352.24 7.422-2.831 6.649-6.916zm-11.062 3.511c-1.246 1.453-4.011 3.976-4.011 3.976s-.121.119-.31.023c-.076-.057-.108-.09-.108-.09-.443-.441-3.368-3.049-4.034-3.954-.709-.965-1.041-2.7-.091-3.71.951-1.01 3.005-1.086 4.363.407 0 0 1.565-1.782 3.468-.963 1.904.82 1.832 2.692.723 4.311zm6.173.478c-.928.116-1.682.028-1.682.028V7.284h1.77s1.971.551 1.971 2.638c0 1.913-.985 2.015-2.059 2.015z"/></svg>
    Buy me a coffee on Ko-fi
  </a>
</footer>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/calculate", methods=["POST"])
def calculate_route():
    data = request.get_json()
    try:
        params = parse_params(data)
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    price = params["price"]
    down = params["down"]

    if price < 10000:
        return jsonify({"error": "Price must be at least €10,000"}), 400
    if down < 0 or down >= price:
        return jsonify({"error": "Down payment must be >= 0 and < price"}), 400

    result = compute_schedule(**params)
    if result is None:
        return jsonify({"error": "Invalid parameters"}), 400
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
