# Calculation Verification Guide: Ensuring Accuracy

**Goal**: Verify that all calculations (Sharpe Ratio, Capital Gains, STCG/LTCG) are mathematically correct and match professional standards.

---

## 1️⃣ Sharpe Ratio Verification

### Formula
```
Sharpe Ratio = (Annual Portfolio Return - Risk-Free Rate) / Annual Portfolio Volatility

Where:
- Annual Portfolio Return = (Ending Value - Starting Value) / Starting Value
- Risk-Free Rate = 6% (India 10-year government securities)
- Annual Portfolio Volatility = Daily Volatility × √252
- Daily Volatility = Standard Deviation of daily returns
```

### How We Calculate It (Current Implementation)

```python
# From backend/app/services/analytics.py

def calculate_sharpe_ratio(trades, cash_flow_history=None, risk_free_rate=0.06):
    """
    Step 1: Build daily portfolio value from trades
    Step 2: Calculate daily returns
    Step 3: Calculate volatility (stdev of daily returns)
    Step 4: Annualize volatility: daily_vol × sqrt(252 trading days/year)
    Step 5: Calculate annual return
    Step 6: Sharpe = (annual_return - risk_free_rate) / annual_volatility
    Step 7: Round to 2 decimals
    """
```

### Verification Steps

#### Test Case 1: Simple Portfolio (No Volatility)
```
Scenario: Monthly equal gains
- Start: ₹100,000
- Month 1: +5% = ₹105,000
- Month 2: +5% = ₹110,250
- Month 3: +5% = ₹115,763
- Month 4: +5% = ₹121,551

Expected Result:
├─ Total Return: 21.55% (annual if 4 months)
├─ Volatility: Low (consistent gains)
├─ Sharpe Ratio: HIGH (returns without swings)
└─ Sharpe should be > 2.0

Manual Verification:
1. Open Google Sheets
2. Create daily returns column
3. Calculate STDEV(returns)
4. Multiply by SQRT(252)
5. Calculate Sharpe = (Annual% - 0.06) / Volatility
6. Compare: Our value vs manual value
7. Tolerance: ±0.01
```

#### Test Case 2: Volatile Portfolio (Real Trading)
```
Scenario: Real trader with daily swings
- Day 1: +2%
- Day 2: -1%
- Day 3: +3%
- Day 4: -0.5%
- Day 5: +1.5%
... (30+ days of real data)

Expected Result:
├─ High daily volatility
├─ Annual volatility: 20-30% (typical trader)
├─ Sharpe Ratio: 0.5-2.0 (depending on returns)
└─ Should match professional calculators

Manual Verification:
1. Get 30+ days of trader's actual daily returns
2. Calculate standard deviation
3. Annualize: stdev × sqrt(252)
4. Calculate annual return: (ending - starting) / starting
5. Sharpe = (annual_return - 0.06) / annual_volatility
6. Compare with our system
7. Verify in Excel OR Morningstar OR Bloomberg
```

#### Test Case 3: Losing Portfolio
```
Scenario: Portfolio loses 10% over a year
- Return: -10%
- Volatility: 15% (some ups and downs)
- Expected Sharpe: (-0.10 - 0.06) / 0.15 = -1.07

Expected Result:
├─ NEGATIVE Sharpe Ratio (expected, since lost money)
├─ Value should be approximately -1.07
└─ Correctly shows this portfolio underperformed

Verification:
1. Create losing portfolio scenario
2. Calculate manually
3. Compare with our system
4. Verify negative Sharpe is calculated correctly
```

---

## 2️⃣ Capital Gains Verification (STCG/LTCG)

### What We Need to Calculate

```
For EVERY SELL TRADE:

1. Identify matching BUY trades (FIFO - First In, First Out)
   - Kite uses FIFO by default
   - Match oldest buy with the sell

2. Calculate cost basis
   Cost Basis = Matching Buy Quantity × Matching Buy Price

3. Calculate sale value
   Sale Value = Sell Quantity × Sell Price

4. Calculate capital gain/loss
   Gain/Loss = Sale Value - Cost Basis

5. Categorize as STCG or LTCG
   - If (Sell Date - Buy Date) < 365 days = STCG (Short-term)
   - If (Sell Date - Buy Date) >= 365 days = LTCG (Long-term)

6. Tax applicability in India
   - STCG: Added to income, taxed as per income tax slab (10-30%)
   - LTCG: 20% + Cess (special tax benefit)
   - Note: These are rates as of 2026, may change
```

### Verification with Real Example

#### Scenario: Simple 2 Buy, 1 Sell

```
TRADES:
├─ Buy 100 TCS @ ₹3000 on Jan 15, 2024
├─ Buy 50 TCS @ ₹3200 on Feb 20, 2024
└─ Sell 75 TCS @ ₹3500 on Jun 30, 2024

MANUAL CALCULATION:

Step 1: Match using FIFO
├─ Sell 75 of oldest buy
├─ First buy: 100 TCS @ ₹3000 (Jan 15, 2024)
├─ Use 75 from this lot
└─ Remaining: 25 TCS @ ₹3000 still held

Step 2: Calculate cost basis
├─ Cost = 75 × ₹3000
├─ Cost = ₹225,000
└─ ✓ Verified

Step 3: Calculate sale value
├─ Sale = 75 × ₹3500
├─ Sale = ₹262,500
└─ ✓ Verified

Step 4: Calculate gain/loss
├─ Gain = ₹262,500 - ₹225,000
├─ Gain = ₹37,500
└─ ✓ Verified (profit)

Step 5: Calculate holding period
├─ Buy date: Jan 15, 2024
├─ Sell date: Jun 30, 2024
├─ Days held: 167 days
├─ Is 167 >= 365? NO
└─ Category: STCG (Short-term capital gain)

Step 6: Tax liability
├─ STCG: ₹37,500
├─ If in 30% tax bracket: 30% × ₹37,500 = ₹11,250 tax
└─ Net after tax: ₹37,500 - ₹11,250 = ₹26,250

SYSTEM VERIFICATION:
1. Enter above trades in our system
2. Generate tax report
3. Should show:
   ├─ STCG: ₹37,500 ✓
   ├─ Remaining: 25 TCS @ ₹3000 (cost basis for future sale)
   └─ Holding period: Correct date calculation
4. Compare with our output
5. Tolerance: EXACT MATCH (no rounding allowed)
```

#### Scenario: FIFO with Multiple Buys

```
TRADES:
├─ Buy 100 TCS @ ₹2000 on Jan 1, 2023 (LTCG eligible after Jan 1, 2024)
├─ Buy 50 TCS @ ₹2500 on Jun 1, 2023 (LTCG eligible after Jun 1, 2024)
├─ Buy 30 TCS @ ₹3000 on Dec 1, 2023 (LTCG eligible after Dec 1, 2024)
└─ Sell 120 TCS @ ₹3500 on May 15, 2024

FIFO MATCHING:
├─ First 100 TCS from Jan 1 lot
│  ├─ Cost: 100 × ₹2000 = ₹200,000
│  ├─ Sale: 100 × ₹3500 = ₹350,000
│  ├─ Gain: ₹150,000
│  ├─ Holding: Jan 1, 2023 → May 15, 2024 = 500+ days
│  └─ Category: LTCG ✓
│
└─ Remaining 20 TCS from Jun 1 lot
   ├─ Cost: 20 × ₹2500 = ₹50,000
   ├─ Sale: 20 × ₹3500 = ₹70,000
   ├─ Gain: ₹20,000
   ├─ Holding: Jun 1, 2023 → May 15, 2024 = 348 days
   └─ Category: STCG ✓

TOTAL GAINS:
├─ LTCG: ₹150,000 (20% + Cess tax = ~23% effective)
├─ STCG: ₹20,000 (30% tax in this bracket)
└─ Total gain: ₹170,000

TAX SUMMARY:
├─ LTCG tax: ₹150,000 × 20% = ₹30,000 + Cess
├─ STCG tax: ₹20,000 × 30% = ₹6,000
└─ Total tax: ~₹36,000

SYSTEM VERIFICATION:
1. Enter all trades
2. Check FIFO matching (should match above)
3. Check gain/loss split (LTCG ₹150K, STCG ₹20K)
4. Check category assignment (correct LTCG vs STCG)
5. Compare with manual calculation
6. Tolerance: EXACT MATCH
```

---

## 3️⃣ Financial Year Grouping Verification

### Rules for Indian Financial Year

```
Financial Year runs: April 1 to March 31

For 2025-26:
├─ Starts: April 1, 2025
├─ Ends: March 31, 2026
└─ Any trade from April 1, 2025 to March 31, 2026 belongs in FY 2025-26

Edge Cases to Test:
├─ Trade on March 31 (belongs to current FY)
├─ Trade on April 1 (belongs to NEXT FY)
├─ Trade on March 31, 2026 (last day of FY 2025-26)
└─ Trade on April 1, 2026 (first day of FY 2026-27)
```

### Test Cases for Financial Year Grouping

```
TEST 1: Cross-Year Boundary
├─ Trades in March (FY 2024-25)
├─ Trades in April (FY 2025-26)
└─ Verify: Correct FY assignment

TEST 2: Exact Boundary Dates
├─ Sell on March 31, 2026 (last day of FY)
│  └─ Expected FY: 2025-26
├─ Sell on April 1, 2026 (first day of next FY)
│  └─ Expected FY: 2026-27
└─ Verify: Correct FY boundaries

TEST 3: LTCG Calculation with Year Boundary
├─ Buy: Feb 1, 2024 (FY 2023-24)
├─ Sell: Feb 1, 2025 (FY 2024-25, 365 days later = LTCG)
└─ Report should show:
   ├─ Buy trade: FY 2023-24
   ├─ Sell trade: FY 2024-25
   └─ Gain should appear in FY 2024-25 tax report
```

---

## 4️⃣ Complete Verification Checklist

### Before Going Live with Client

```
✅ SHARPE RATIO
├─ Test Case 1: No volatility portfolio
│  └─ Manual Excel: _____ vs Our System: _____ ✓/✗
├─ Test Case 2: Real volatility data
│  └─ Professional calculator: _____ vs Our System: _____ ✓/✗
├─ Test Case 3: Negative returns
│  └─ Manual: _____ vs Our System: _____ ✓/✗
└─ Verified by: _____________ Date: _______

✅ STCG/LTCG CATEGORIZATION
├─ Test Case 1: Simple 2 buy 1 sell
│  └─ Manual: STCG ₹37,500 vs Our System: _____ ✓/✗
├─ Test Case 2: Complex FIFO matching
│  └─ Manual: LTCG ₹150K, STCG ₹20K vs Our System: _____ ✓/✗
├─ Test Case 3: Edge case (boundary dates)
│  └─ Manual: _____ vs Our System: _____ ✓/✗
└─ Verified by: _____________ Date: _______

✅ CAPITAL GAINS CALCULATION
├─ Cost basis matching: EXACT
├─ Sale value calculation: EXACT
├─ Gain/Loss calculation: EXACT
├─ FIFO method: Correctly implemented
└─ Verified: ✓

✅ FINANCIAL YEAR GROUPING
├─ Year boundary dates: Correct
├─ STCG in correct year: Verified
├─ LTCG in correct year: Verified
└─ Verified: ✓

✅ TAX REPORT EXPORT
├─ CSV format: Readable, correct columns
├─ PDF format: Professional appearance
├─ Excel format: Formulas working
└─ Verified: ✓

✅ AGAINST PROFESSIONAL STANDARDS
├─ Zerodha tax report comparison: Match or explain difference
├─ CA opinion letter: Approved
├─ Professional tax software: Match within tolerance
└─ Verified by: _____________ Date: _______

✅ REAL CLIENT DATA
├─ Client's 2025 trades entered
├─ Tax report generated
├─ Presented to their CA
├─ CA approval: YES / NO
└─ Verified by: Client CA _________________ Date: _______
```

---

## 5️⃣ Testing Workflow

### Week 1: Automated Tests

```bash
# 1. Set up test data file
tests/data/sample_trades.json
├─ Simple scenario: 5 test cases
├─ Complex scenario: 10 test cases
└─ Edge cases: 5 test cases

# 2. Write test functions
tests/test_sharpe_ratio.py
├─ test_simple_portfolio()
├─ test_volatile_portfolio()
└─ test_negative_returns()

tests/test_capital_gains.py
├─ test_fifo_matching()
├─ test_stcg_ltcg_categorization()
└─ test_edge_cases()

tests/test_tax_reports.py
├─ test_financial_year_grouping()
├─ test_export_csv()
├─ test_export_pdf()
└─ test_export_excel()

# 3. Run tests
pytest tests/ -v

# 4. Compare with manual calculations
If all tests pass ✓ → Move to manual verification
```

### Week 2: Manual Verification

```
1. Create Excel workbook with manual calculations
   ├─ Sheet 1: Sharpe Ratio test cases
   ├─ Sheet 2: Capital gains test cases
   ├─ Sheet 3: STCG/LTCG categorization
   └─ Sheet 4: Financial year grouping

2. Enter same test data in our system
   ├─ Generate reports
   ├─ Extract numbers
   └─ Compare cell-by-cell

3. Create comparison report
   ├─ Test case name
   ├─ Expected (manual) vs Actual (system)
   ├─ Match ✓ or Mismatch ✗
   └─ Explanation if mismatch

4. Send to CA for review
   ├─ Provide test cases
   ├─ Provide our calculations
   ├─ Ask for approval
   └─ Get written approval (email)
```

### Week 3: Real Client Testing

```
1. Get client's actual trade data (from Kite)
2. Generate tax report in our system
3. Have client's CA review
4. CA feedback:
   ├─ Approved ✓ → Live!
   ├─ Minor adjustments needed → Fix & retest
   └─ Major issues → Debug & retest

5. Once CA approves:
   ├─ Document any adjustments made
   ├─ Update calculation methodology
   └─ Ready for production
```

---

## 6️⃣ Tolerance Guidelines

```
SHARPE RATIO:
├─ Tolerance: ±0.01
├─ Why: Rounding in intermediate calculations
├─ Example: Our 1.45 vs Manual 1.46 = PASS

CAPITAL GAINS:
├─ Tolerance: EXACT MATCH (₹0 allowed difference)
├─ Why: Tax calculations must be precise
├─ Example: Our ₹37,500 vs Manual ₹37,500 = PASS
├─         Our ₹37,501 vs Manual ₹37,500 = FAIL

STCG/LTCG CATEGORIZATION:
├─ Tolerance: EXACT MATCH
├─ Why: Legal classification, cannot be approximate
├─ Example: Our STCG vs Manual STCG = PASS
├─         Our LTCG vs Manual STCG = FAIL

DATE CALCULATIONS:
├─ Tolerance: EXACT MATCH
├─ Why: Day matters (365 vs 366 days crosses threshold)
├─ Example: Our 365 days vs Manual 365 days = PASS
├─         Our 364 days vs Manual 365 days = FAIL
```

---

## 📋 Sign-Off Document

Once all verifications pass, create this document:

```
CALCULATION VERIFICATION SIGN-OFF
Date: ___________
Verified by: ___________

1. Sharpe Ratio Calculations
   ✓ Test cases passed
   ✓ Manual verification complete
   ✓ Professional calculator agreement
   Tolerance: ±0.01
   Status: APPROVED

2. Capital Gains Calculations
   ✓ FIFO matching verified
   ✓ Cost basis correct
   ✓ STCG/LTCG categorization correct
   Tolerance: EXACT MATCH
   Status: APPROVED

3. Tax Reports
   ✓ Financial year grouping correct
   ✓ Export formats verified
   ✓ Ready for CA submission
   Status: APPROVED

4. Real Client Testing
   ✓ Test data from actual client
   ✓ CA verification complete
   ✓ Client approved
   Status: APPROVED

CONCLUSION: All calculations verified and approved for production use.
CA Sign-off: _________________ Date: _______
```

---

**This guide ensures**: Zero ambiguity, client trust, CA approval, and production-ready accuracy.
