# Belgian Mortgage Simulator

A Belgian mortgage calculator and simulator built with Python (Flask) and uv.

## Requirements

- [uv](https://docs.astral.sh/uv/) (Python package manager)

## Setup

```bash
uv sync
```

## Usage

```bash
uv run main.py
```

## Development

Install dev dependencies and pre-commit hooks:

```bash
uv sync
uv run pre-commit install
```

Run linting and formatting:

```bash
uv run ruff check .
uv run ruff format .
```

---

## Algorithm & Tax Law Reference

This section documents the Belgian tax rules and real-world benchmarks used to validate the calculator's algorithms.

### Registration Duties (Transfer Tax) — 2025

Registration duties are regionally determined and changed significantly in January 2025:

| Region | Primary/Sole Residence | Other/Investment |
|--------|----------------------|-----------------|
| **Flanders** | **2%** (since Jan 1, 2025) | 12% |
| **Wallonia** | **3%** (since Jan 1, 2025) | 12.5% |
| **Brussels** | 12.5% with **€200k abatement** (price ≤ €600k) | 12.5% |
| **New builds** | **21% VAT** (replaces registration duties) | 21% VAT |

**Key 2025 reform details:**
- **Flanders**: The 2% rate applies if buyer does not own any other residential property. Others pay 12%.
- **Wallonia**: Reduced from 12.5% → 3% for primary/sole residence (Jan 1, 2025). The old €20,000 abatement and *chèque habitat* were **abolished** simultaneously. Non-primary stays at 12.5%.
- **Brussels**: The abatement was raised from €175,000 to **€200,000** in April 2023. The abatement only applies when the purchase price is ≤ €600,000. This creates a maximum tax saving of €25,000 (€200k × 12.5%).

### Mortgage Deed Costs

When taking a mortgage, the notary registers a mortgage deed which incurs two charges:

| Cost | Rate |
|------|------|
| Mortgage registration fee | 1.0% of loan amount |
| Mortgage duty (tax) | 0.3% of loan amount |
| **Total deed cost** | **1.3% of loan amount** |

### Notary Professional Fees (Purchase Deed)

The notary's professional fee follows a regulated degressive scale set by Royal Decree (identical for all Belgian notaries):

| Purchase price bracket | Rate |
|-----------------------|------|
| ≤ €7,500 | 4.56% |
| €7,501 – €17,500 | 2.85% |
| €17,501 – €30,000 | 2.28% |
| €30,001 – €45,495 | 1.71% |
| €45,496 – €64,095 | 1.14% |
| €64,096 – €250,095 | 0.57% |
| > €250,095 | 0.57% |

The calculated fee is multiplied by **1.5×** to approximate VAT (21%) + mandatory administrative searches/disbursements (€800–€1,200 for cadastral records, land registry, certificates, etc.).

### NBB Prudential Limits (Macroprudential Framework)

The National Bank of Belgium sets the following limits on new mortgage origination:

| Borrower type | Max LTV | Tolerance band |
|--------------|---------|----------------|
| First-time buyers (owner-occupied) | 90% | Up to 35% of volume may exceed 90%; up to 5% may exceed 100% |
| Other owner-occupied | 90% | Up to 20% of volume may be 90–100% |
| Buy-to-let | 80% | Up to 10% may be 80–90% |

**Affordability guidelines** used by Belgian banks:
- Monthly housing costs (mortgage + insurance) ≤ **33%** of net household income (conservative guideline, Wikifin standard)
- Upper soft limit: **40%** of net income
- Stress test: NBB requires banks to assess affordability at a stressed rate

### Monthly Payment Calculation Method

The calculator uses the **actuarial method** for converting the annual rate to a monthly rate:

```
monthly_rate = (1 + annual_rate)^(1/12) - 1
```

This is the correct Belgian/European standard. Verified against KBC's published representative example:
- Loan: €170,000 | Term: 20 years | Rate: 5.19% fixed
- **KBC published**: €1,128.51/month
- **This calculator**: €1,128.55/month (difference: €0.04 — rounding only)

### Verified Test Scenarios

All scenarios below are validated against Belgian tax authority rules and official examples:

| Scenario | Price | Loan | Region | Primary | Registration | Deed |
|----------|-------|------|--------|---------|-------------|------|
| Flanders primary | €300,000 | €240,000 | Flanders | Yes | €6,000 | €3,120 |
| Flanders investment | €300,000 | €240,000 | Flanders | No | €36,000 | €3,120 |
| Wallonia primary (2025) | €300,000 | €240,000 | Wallonia | Yes | €9,000 | €3,120 |
| Wallonia primary (2025) | €150,000 | €120,000 | Wallonia | Yes | €4,500 | €1,560 |
| Wallonia investment | €300,000 | €240,000 | Wallonia | No | €37,500 | €3,120 |
| Brussels primary (full abatement) | €150,000 | €120,000 | Brussels | Yes | €0 | €1,560 |
| Brussels primary (partial abatement) | €300,000 | €240,000 | Brussels | Yes | €12,500 | €3,120 |
| Brussels primary (at cap) | €600,000 | €480,000 | Brussels | Yes | €50,000 | €6,240 |
| Brussels primary (over cap, no abatement) | €700,000 | €560,000 | Brussels | Yes | €87,500 | €7,280 |

### Current Rate Environment (March 2026)

- Average Belgian mortgage rate (NBB): ~3.2–3.5% (20-year fixed)
- Rate peaked at 5.52% in October 2023, down from 1.49% low in April 2022
- 85%+ of Belgian mortgages use fixed rates
- Average LTV: ~71% (2024 data)

### Insurance Defaults

- **Life/outstanding balance insurance**: 0.20%/year of outstanding balance × 1.02 (2% Belgian insurance premium tax). Typical market range: 0.10%–0.50% depending on age and health.
- **Fire insurance**: €350/year default. Typical range for houses: €150–€480/year.
