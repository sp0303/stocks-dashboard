# Manager Holdings Feature

## Overview
This feature allows managers to view aggregated holdings across selected clients with detailed metrics including:
- Individual holdings with quantity per client
- Holding percentage (% of total manager's portfolio)
- Market value, invested value, and P&L metrics
- Client-level contribution to each holding

## What Was Added

### Backend Changes
**File:** `backend/app/routers/clients.py`

New endpoint: `GET /api/managers/{manager_id}/holdings`

**Parameters:**
- `manager_id` (required): The manager's ID
- `client_ids` (optional): Comma-separated list of client IDs to include. If not provided, all clients are included.

**Response Structure:**
```json
{
  "data": {
    "holdings": [
      {
        "symbol": "INFY",
        "qty": 150,
        "buy_avg": 1500.25,
        "buy_value": 225037.50,
        "ltp": 1650.00,
        "present_value": 247500.00,
        "holding_pct": 12.35,
        "pnl": 22462.50,
        "pnl_pct": 9.98,
        "clients": [
          {"name": "Client A", "qty": 100},
          {"name": "Client B", "qty": 50}
        ]
      }
    ],
    "totals": {
      "market_value": 2000000.00,
      "invested_value": 1900000.00,
      "unrealized_pnl": 100000.00
    },
    "client_count": 2
  }
}
```

**Key Features:**
- Aggregates holdings across multiple clients
- Groups by symbol, summing quantities
- Calculates holding percentage for each stock relative to total portfolio
- Tracks which clients hold each stock and their quantities
- Sorts by market value (largest holdings first)

### Frontend Changes

#### 1. **API Integration** (`frontend/src/api.js`)
New API method:
```javascript
managerHoldings: (id, clientIds = null) => {
  const url = clientIds ? `/api/managers/${id}/holdings?client_ids=${clientIds.join(',')}` : `/api/managers/${id}/holdings`
  return req(url).then((r) => r.data)
}
```

#### 2. **New Component** (`frontend/src/components/ManagerHoldings.jsx`)
A complete React component featuring:

**Client Selection:**
- Checkboxes to select/deselect individual clients
- "Select All" checkbox for bulk selection
- Shows client name and Zerodha code
- Real-time filtering as selections change

**Summary Statistics (Cards):**
- Total Market Value
- Total Invested
- Unrealized P&L
- Return %

**Holdings Table:**
| Column | Description |
|--------|-------------|
| Symbol | Stock symbol |
| Qty | Total quantity across selected clients |
| Buy Avg | Average buy price |
| Buy Value | Total amount invested |
| LTP | Last Traded Price |
| Present Value | Current market value |
| **Holding %** | NEW: Percentage of total portfolio |
| P&L | Unrealized profit/loss in ₹ |
| P&L % | Return percentage |
| Clients | List of clients holding this stock with their quantities |

#### 3. **Integration** (`frontend/src/components/ManagerView.jsx`)
- Imported the new `ManagerHoldings` component
- Added it to the manager view below the metrics dashboard
- Passes client list for selection

## How to Use

### For Managers:

1. **Navigate to Manager View**
   - Click "Manager" tab in the top navigation
   - Select your manager account from the dropdown

2. **Scroll to "Holdings by selected clients" Section**
   - Located below "Book metrics — all clients"

3. **Select Clients**
   - Check individual client checkboxes to include their holdings
   - Or use "All" to select/deselect everyone at once
   - The counter shows "X/Total" selected clients

4. **View Aggregated Holdings**
   - Summary stats update in real-time
   - Table shows all holdings across selected clients
   - Each row includes:
     - Client breakdown showing which clients hold the stock
     - **Holding % column** showing this stock's portion of the total portfolio

### Example Scenario:
```
Manager selects: Client A, Client B, Client C

Holdings are aggregated:
- INFY: 250 qty (Client A: 100, Client B: 75, Client C: 75)
  - Holding %: 15.2% (this INFY holding is 15.2% of the three clients' total portfolio)
- TCS: 100 qty (Client B: 60, Client C: 40)
  - Holding %: 8.5%
```

## Backend Implementation Details

### Algorithm:
1. **Client Filtering**: If `client_ids` provided, filter manager's clients
2. **Holdings Aggregation**: For each client
   - Fetch their trades
   - Build holdings using existing analytics engine
   - Aggregate by symbol:
     - Sum quantities
     - Sum buy values
     - Sum market values
     - Track individual client contributions
3. **Calculations**:
   - Buy average = total buy value / total quantity
   - Holding % = symbol's market value / total market value × 100
   - P&L % = total pnl / total buy value × 100
4. **Sorting**: By market value (descending)

### Edge Cases Handled:
- No clients selected → shows empty state
- No trades in selected clients → handles gracefully
- Single client → shows holdings with client name and "100%" holding
- Zero market value → prevents division by zero

## Database Queries

The endpoint makes efficient use of existing store methods:
- `store.get_manager()` - Verify manager exists
- `store.list_clients()` - Get manager's clients
- `store.list_trades()` - Get trades per client
- Reuses existing analytics.build_holdings() for consistency

## Testing Checklist

- [ ] Select single client → view only that client's holdings with 100% weights
- [ ] Select multiple clients → see aggregated holdings with correct percentages
- [ ] Select all clients → view full manager portfolio
- [ ] Deselect all → see empty state message
- [ ] Client with no trades → doesn't break aggregation
- [ ] Holdings sum correctly across clients
- [ ] Holding % values sum to ~100% (minus rounding)
- [ ] Client names display correctly in holdings breakdown

## Future Enhancements

1. **Filters:**
   - Filter by sector, market cap
   - Sort by holding %, P&L, etc.

2. **Analysis:**
   - Concentration analysis (top 10 holdings %)
   - Overlap analysis (which clients share holdings)
   - Rebalancing recommendations

3. **Export:**
   - Export to Excel with per-client breakdown
   - Print-friendly view

4. **Performance:**
   - Cache aggregations for frequently viewed client groups
   - Add date range filtering (as of date X)

## Files Modified

1. `backend/app/routers/clients.py` - Added manager holdings endpoint
2. `frontend/src/api.js` - Added API method
3. `frontend/src/components/ManagerView.jsx` - Integrated component
4. `frontend/src/components/ManagerHoldings.jsx` - New component (created)
