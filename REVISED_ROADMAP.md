# Revised Roadmap: Focus on What Matters

**Based on Client Requirements:**
- ❌ NO mobile app
- ❌ NO multi-broker
- ❌ NO MF/FD
- ✅ FOCUS: Tax reports (STCG/LTCG)
- ✅ FOCUS: Calculation accuracy

---

## 🎯 Current Phase (DONE ✅)

### Phase 1: Core Portfolio Dashboard
```
✅ Multi-Kite account support
✅ Account manager & switching
✅ Manual sync with smart cache
✅ Sharpe Ratio calculation
✅ Trade history display
✅ Holdings list
✅ Performance overview

TIME: Complete
TESTING: Ready
```

---

## 🔥 Phase 2: PRIORITY (Next 2 weeks)

### Tax Report Generation (CRITICAL)
```
Needed:
├─ Identify short-term vs long-term trades
│  └─ < 1 year = Short-term (STCG)
│  └─ >= 1 year = Long-term (LTCG)
│
├─ Calculate capital gains/losses
│  ├─ Cost basis: (qty × buy_price)
│  ├─ Sale value: (qty × sell_price)
│  └─ Gain/Loss: Sale value - Cost basis
│
├─ Group by financial year (April-March)
│
└─ Export report as:
   ├─ CSV for CA/accountant
   ├─ PDF for filing
   └─ Excel with formulas

DELIVERABLES:
├─ [Backend] POST /clients/{id}/tax-report endpoint
├─ [Backend] STCG/LTCG calculation logic
├─ [Frontend] Tax report viewer/export button
├─ [Tests] Verify calculations against manual examples
└─ [Docs] Tax calculation methodology

TIMELINE: 7-10 days
```

### Calculation Verification System
```
Build a testing framework to verify:

1. Sharpe Ratio
   ├─ Test case 1: Known portfolio (Google Finance)
   ├─ Test case 2: Your account data
   ├─ Compare: Our calculation vs manual Excel
   └─ Tolerance: ±0.01 (rounding)

2. Capital Gains
   ├─ Test FIFO method (Kite uses FIFO)
   ├─ Test specific identification
   ├─ Manual verification with sample trades
   └─ Tolerance: Exact match (no rounding)

3. Cost Basis Calculations
   ├─ Test FIFO matching
   ├─ Test tax lot tracking
   ├─ Test partial sells
   └─ Tolerance: Exact match

4. STCG/LTCG Categorization
   ├─ Test boundary cases (exactly 1 year)
   ├─ Test financial year boundaries (April 1)
   ├─ Manual date verification
   └─ Tolerance: Exact match

DELIVERABLES:
├─ Test suite with real data examples
├─ Calculation verification report
├─ Match vs professional tools (CA opinion)
└─ Documentation of any deviations
```

---

## Phase 3: Polish (Week 3-4)

### Professional Metrics Verification
```
✅ Sharpe Ratio - Already built, verify accuracy
🔄 Beta calculation vs Nifty 50
   ├─ Daily returns correlation
   ├─ Market regression
   └─ Match vs Bloomberg

🔄 CAGR Calculation
   └─ Verify formula vs professional standards

🔄 Max Drawdown
   └─ Peak-to-trough analysis
```

### Dashboard Polish
```
✅ Error messages (already good)
✅ Sync status display
🔄 Performance chart improvements
🔄 Holdings sort/filter
```

---

## ❌ NOT DOING (Removed from roadmap)

```
❌ Mobile App
   Why not: Client doesn't use mobile
   Impact: Saves 2-3 weeks

❌ Multi-Broker Support
   Why not: Client only uses Kite
   Impact: Saves 1-2 weeks

❌ MF/FD Tracking
   Why not: Not needed by client
   Impact: Saves 1 week

❌ Beautiful Onboarding
   Why not: For internal/team use
   Impact: Saves 3-4 days

❌ Team Collaboration
   Why not: Single user focus
   Impact: Saves 1 week
```

---

## 📋 Phase 2 Detailed: Tax Reports

### Backend Implementation (3-4 days)

```python
# NEW FILE: backend/app/services/taxes.py

def identify_stcg_ltcg(trades: list[dict]) -> dict:
    """
    Categorize trades as short-term or long-term capital gains.
    
    STCG: Buy date to sell date < 1 year (365 days)
    LTCG: Buy date to sell date >= 1 year
    
    Returns:
    {
        "stcg": [
            {
                "symbol": "TCS",
                "buy_date": "2023-01-15",
                "sell_date": "2023-06-20",
                "qty": 100,
                "buy_price": 3500,
                "sell_price": 3800,
                "cost_basis": 350000,
                "sale_value": 380000,
                "gain_loss": 30000
            }
        ],
        "ltcg": [...],
        "total_stcg": 150000,
        "total_ltcg": 250000
    }
    """

def calculate_capital_gains(sell_trades: list) -> dict:
    """
    Match sell trades with buy trades using FIFO method (Kite default).
    Calculate cost basis and realized gains/losses.
    """

def group_by_financial_year(trades: list) -> dict:
    """
    Group STCG/LTCG by Indian financial year (April 1 - March 31).
    
    Returns:
    {
        "2025-26": {  # April 2025 - March 2026
            "stcg": 150000,
            "ltcg": 250000,
            "trades": [...]
        }
    }
    """

def export_tax_report(gains: dict) -> bytes:
    """
    Export as CSV/PDF/Excel for CA/accountant.
    """
```

### Frontend Implementation (2 days)

```jsx
// NEW: TaxReportViewer.jsx

function TaxReportViewer({ clientId }) {
  const [report, setReport] = useState(null)
  const [year, setYear] = useState("current")
  
  // Show:
  // ├─ Total STCG (short-term gains)
  // ├─ Total LTCG (long-term gains)
  // ├─ Total gains/losses
  // ├─ Breakdown by financial year
  // ├─ Trade-by-trade details
  // └─ [Export as CSV] [Export as PDF] buttons
}
```

### API Endpoints (2 days)

```
GET /clients/{id}/tax-report
  ├─ Query: ?year=2025-26 (or "current")
  └─ Returns: Full tax report JSON

POST /clients/{id}/tax-report/export
  ├─ Query: ?format=csv|pdf|excel
  └─ Returns: File download

GET /clients/{id}/tax-report/verify
  └─ Returns: Calculation verification report
```

### Testing (4-5 days)

```
Create verification suite:

test_stcg_ltcg_categorization():
  ├─ Input: Sample 20 trades
  ├─ Expected: Correct STCG/LTCG split
  └─ Compare: Manual date calculations

test_capital_gains_fifo():
  ├─ Input: Buy 100 @ 1000, Buy 50 @ 1200, Sell 75 @ 1500
  ├─ Expected: 
  │  └─ 75 from first lot @ 1000
  │  └─ Gain: (75 × 1500) - (75 × 1000) = 37,500
  └─ Verify: Exact match

test_financial_year_grouping():
  ├─ Input: Trades from Jan-May
  ├─ Expected: All in FY 2025-26 (April start)
  └─ Verify: Correct year boundaries

test_against_professional_tool():
  ├─ Export report from our system
  ├─ Compare with: 
  │  ├─ Zerodha tax report
  │  ├─ CA manual calculation
  │  └─ Professional accounting tool
  └─ Tolerance: Exact match
```

---

## ✅ Calculation Accuracy Verification

### Sharpe Ratio Verification

```
FORMULA:
Sharpe Ratio = (Annual Return - Risk-Free Rate) / Annual Volatility

COMPONENTS:
1. Annual Return
   ├─ Method: (Ending Value - Starting Value) / Starting Value
   ├─ Annualize: Return × (365 / days_traded)
   └─ Verify: Against benchmark data

2. Risk-Free Rate
   ├─ Current: 6% (10-year government securities)
   ├─ Verify: RBI current rate
   └─ Allow adjustment: User-configurable

3. Annual Volatility
   ├─ Method: Daily returns standard deviation × √252
   ├─ Verify: Against portfolio management textbooks
   └─ Test: Sample portfolios

VERIFICATION TESTS:
Test 1: Zero-volatility portfolio
  ├─ Input: Equal monthly gains (5% each)
  ├─ Expected: High Sharpe (no risk = infinite ratio, cap at 10)
  └─ Verify: Mathematical correctness

Test 2: Known volatile portfolio
  ├─ Input: Daily swings like real traders
  ├─ Compare: vs professional calculators
  └─ Tolerance: ±0.01

Test 3: Negative return portfolio
  ├─ Input: Losses greater than risk-free rate
  ├─ Expected: Negative Sharpe Ratio
  └─ Verify: Correctly calculated as negative
```

### Tax Calculation Verification

```
FIFO METHOD (what Kite uses):
Buy 100 @ 1000 = 100,000 cost basis
Buy 50 @ 1200 = 60,000 cost basis
Sell 75 @ 1500 = First 75 from first lot

Calculation:
├─ Cost basis: 75 × 1000 = 75,000
├─ Sale value: 75 × 1500 = 112,500
├─ Gain: 112,500 - 75,000 = 37,500
└─ Tax category: STCG (if < 1 year) or LTCG (if >= 1 year)

VERIFICATION:
1. Check against Kite's own reports
2. Check against CA calculation
3. Check against tax software (e.g., Cleartax)
4. Manual verification on 5-10 real trades
```

---

## 📊 Testing Plan for Accuracy

### Step 1: Set Up Test Data (Day 1)
```
Create realistic scenarios:
├─ Simple: 5 buy, 2 sell (no complexity)
├─ Medium: 20 buy, 10 sell (mixed dates)
├─ Complex: 50 buy, 30 sell (year boundaries, fractional)
└─ Edge cases:
   ├─ Sell exact day before LTCG cutoff
   ├─ Sell exact day after LTCG cutoff
   ├─ Financial year boundary (March 31 - April 1)
   └─ Zero-gain trades
```

### Step 2: Manual Verification (Day 1-2)
```
For each test case:
├─ Calculate manually in Excel
├─ Show step-by-step work
├─ Create reference spreadsheet
└─ Document assumptions
```

### Step 3: System Calculation (Day 2-3)
```
Run through our system:
├─ Add test trades to test account
├─ Generate tax report
├─ Extract calculations
└─ Compare vs manual
```

### Step 4: Verification Against Gold Standard (Day 3-4)
```
Compare with:
├─ Zerodha's tax reports (for Kite trades)
├─ Professional tax software
├─ CA opinion letter
└─ Accept tolerance: 0% (exact match required)
```

### Step 5: Real Client Verification (Day 5)
```
When client provides credentials:
├─ Generate tax report for current year
├─ Have their CA verify the numbers
├─ Adjust calculations if needed
└─ Retest with corrected logic
```

---

## 📈 Success Criteria for Phase 2

```
✅ STCG/LTCG categorization: 100% accurate (verified vs CA)
✅ Capital gains calculation: 100% accurate (verified vs Kite)
✅ Tax report export: Works in CSV, PDF, Excel
✅ Sharpe Ratio: Within ±0.01 of professional calculators
✅ All edge cases: Tested and passing
✅ Documentation: Clear methodology documented
✅ Client approval: CA signs off on accuracy
```

---

## 📅 Timeline

```
Week 1:
├─ Day 1-2: Tax calculation backend
├─ Day 2-3: Frontend tax report viewer
├─ Day 3-4: API endpoints
└─ Day 4-5: Initial testing

Week 2:
├─ Day 1-2: Verification testing (vs manual/CA)
├─ Day 2-3: Calculation accuracy refinement
├─ Day 3-4: Real client testing
└─ Day 4-5: Polish & documentation

TOTAL: 2 weeks to production-ready tax reports
```

---

## 🎯 What Happens After Phase 2

Once tax reports are verified:

```
Phase 2.5 (OPTIONAL): Advanced Metrics
├─ Beta calculation (vs Nifty 50)
├─ CAGR calculation
└─ Max drawdown
   └─ Only if client wants more metrics

Phase 3 (FUTURE): Polish
├─ Better charts
├─ Sector breakdown
├─ Performance attribution
└─ Advanced filters

Beyond: Only if client requests
```

---

## 💡 Why This Approach

```
OLD ROADMAP: ❌
├─ Mobile app (not needed)
├─ Multi-broker (Kite only)
├─ MF/FD (equity trader only)
└─ Beautiful onboarding (internal use)
└─ Result: Wasted 4-5 weeks on things client doesn't need

NEW ROADMAP: ✅
├─ Tax reports (CRITICAL for compliance)
├─ Calculation accuracy (CRITICAL for trust)
├─ Professional metrics (USEFUL for analysis)
└─ Result: 2 weeks to client-ready product
```

---

## 🚀 Current Status

```
PHASE 1 (COMPLETE) ✅
├─ Multi-account Kite support
├─ Account manager UI
├─ Sharpe Ratio calculation
├─ Smart cache
└─ Ready for testing NOW

PHASE 2 (READY TO START)
├─ Tax reports with STCG/LTCG
├─ Calculation verification
├─ Export functionality
└─ Start IMMEDIATELY after Phase 1 testing

Client-Ready Timeline: 3 weeks total
├─ Week 1: Phase 1 testing
├─ Week 2-3: Phase 2 (tax + verification)
└─ Ready to onboard client by Week 4
```

---

**Updated**: 2026-09-05  
**Focus**: Client needs, not market features  
**Priority**: Tax accuracy > everything else  
**Timeline**: 3 weeks to production  
