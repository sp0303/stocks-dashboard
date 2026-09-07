# Manager Holdings - UI/Component Reference

## Component Tree

```
ManagerView
├── ManagerMetrics (existing)
│   ├── Summary Cards
│   ├── Most Invested/Favourite/Top Holding stats
│   ├── Client Breakdown Table
│   └── Book Performance Charts
│
└── ManagerHoldings (NEW)
    ├── Client Selection Panel
    │   ├── "Select clients to aggregate" heading
    │   ├── "All (X/Y)" Master Checkbox
    │   └── Grid of Client Checkboxes
    │       ├── [✓] Client A (AP8774)
    │       ├── [✓] Client B (IH9579)
    │       ├── [✓] Client C (IMF948)
    │       ├── [ ] Client D (LFP269)
    │       ├── [ ] Client E (GBH341)
    │       ├── [ ] Client F (QPJ806)
    │       └── [ ] Client G (DOD181)
    │
    ├── Summary Statistics Cards (visible when clients selected)
    │   ├── Total Market Value: ₹2,50,00,000
    │   ├── Total Invested: ₹2,25,00,000
    │   ├── Unrealized P&L: ₹25,00,000 (↑ green)
    │   └── Return %: +11.11%
    │
    └── Holdings Table (visible when clients selected)
        └── Rows, sorted by Market Value descending
            ├── Column: Symbol
            ├── Column: Qty
            ├── Column: Buy Avg
            ├── Column: Buy Value
            ├── Column: LTP
            ├── Column: Present Value
            ├── Column: Holding % ← NEW FEATURE
            ├── Column: P&L
            ├── Column: P&L %
            └── Column: Clients (with breakdown)
```

## UI Layout - Client Selection Panel

```
┌─────────────────────────────────────────────────────────────────┐
│ Select clients to aggregate                                      │
├─────────────────────────────────────────────────────────────────┤
│ [✓] All (7/7)                                                   │
├─────────────────────────────────────────────────────────────────┤
│ ┌───────────────────────┐  ┌───────────────────────┐           │
│ │ [✓]                   │  │ [✓]                   │           │
│ │ Durga Lakshman        │  │ Naga Laxmi            │           │
│ │ Makana (AP8774)       │  │ Makana (IH9579)       │           │
│ └───────────────────────┘  └───────────────────────┘           │
│                                                                  │
│ ┌───────────────────────┐  ┌───────────────────────┐           │
│ │ [✓]                   │  │ [✓]                   │           │
│ │ Bala Sai Vamsi        │  │ Makana Mukesh         │           │
│ │ Madhupada (IMF948)    │  │ Poorna (LFP269)       │           │
│ └───────────────────────┘  └───────────────────────┘           │
│                                                                  │
│ ┌───────────────────────┐  ┌───────────────────────┐           │
│ │ [✓]                   │  │ [✓]                   │           │
│ │ Makana Durga Rao      │  │ Billa Sumanth         │           │
│ │ (GBH341)              │  │ (QPJ806)              │           │
│ └───────────────────────┘  └───────────────────────┘           │
│                                                                  │
│ ┌───────────────────────┐                                      │
│ │ [✓]                   │                                      │
│ │ Padala Thowdamma      │                                      │
│ │ (DOD181)              │                                      │
│ └───────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────┘
```

## UI Layout - Summary Cards

```
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ Total Market Value   │  │ Total Invested       │  │ Unrealized P&L       │  │ Return %             │
│                      │  │                      │  │                      │  │                      │
│ ₹2,50,00,000         │  │ ₹2,25,00,000         │  │ ₹25,00,000           │  │ +11.11%              │
│ 7 client(s)          │  │                      │  │ ↑ (green)            │  │ ↑ (green)            │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘  └──────────────────────┘
```

## UI Layout - Holdings Table (Simplified View)

```
┌─────────┬────────┬──────────┬──────────┬─────────┬───────────┬─────────┬──────────┬─────────┬─────────────────────┐
│ Symbol  │  Qty   │ Buy Avg  │ Buy Valu │  LTP    │ Present V │Holding %│   P&L    │ P&L %   │ Clients             │
├─────────┼────────┼──────────┼──────────┼─────────┼───────────┼─────────┼──────────┼─────────┼─────────────────────┤
│AARTIPHM │  831   │ ₹729.29  │ ₹6,06,04 │ ₹861.70 │ ₹7,16,072│ 12.25%  │ ₹1,10,029│ +18.16%│ Durga Lakshman (500)│
│         │        │          │          │         │           │         │          │         │ Naga Laxmi (200)    │
│         │        │          │          │         │           │         │          │         │ Bala Sai (131)      │
├─────────┼────────┼──────────┼──────────┼─────────┼───────────┼─────────┼──────────┼─────────┼─────────────────────┤
│ABCAPITAL│  100   │ ₹170.50  │ ₹17,050  │ ₹403.25 │ ₹40,325   │ 8.56%   │ ₹23,275  │ +136.51%│ Makana Mukesh (100) │
├─────────┼────────┼──────────┼──────────┼─────────┼───────────┼─────────┼──────────┼─────────┼─────────────────────┤
│ASTRAMICR│   3    │ ₹1,684   │ ₹5,052   │ ₹1,771  │ ₹5,134    │ 0.88%   │ ₹82      │ +1.64%  │ Makana Durga Rao (3)│
├─────────┼────────┼──────────┼──────────┼─────────┼───────────┼─────────┼──────────┼─────────┼─────────────────────┤
│BETA     │  67    │ ₹2,207   │ ₹1,47,891│ ₹2,123  │ ₹1,42,301│ 24.32%  │ -₹5,589  │ -3.78%  │ Billa Sumanth (40)  │
│         │        │          │          │         │           │         │          │         │ Padala Thowdamma(27)│
├─────────┼────────┼──────────┼──────────┼─────────┼───────────┼─────────┼──────────┼─────────┼─────────────────────┤
│BIOCON   │  176   │ ₹420.98  │ ₹74,093  │ ₹391.40 │ ₹68,886   │ 14.75%  │ -₹5,206  │ -7.03%  │ Makana Durga Rao(90)│
│         │        │          │          │         │           │         │          │         │ Naga Laxmi (86)     │
├─────────┼────────┼──────────┼──────────┼─────────┼───────────┼─────────┼──────────┼─────────┼─────────────────────┤
│CARYSIL  │  136   │ ₹866.90  │ ₹1,17,898│ ₹1,151  │ ₹1,56,576│ 26.45%  │ ₹38,677  │ +32.81%│ Durga Lakshman (50) │
│         │        │          │          │         │           │         │          │         │ Bala Sai (86)       │
└─────────┴────────┴──────────┴──────────┴─────────┴───────────┴─────────┴──────────┴─────────┴─────────────────────┘
```

## Key UI Features

### 1. **Client Selection Grid**
   - Responsive grid layout (auto-fill columns, min 200px)
   - Individual client cards with border
   - Checkbox + Client name + Zerodha code
   - Hover state: slight border/background change
   - "All (X/Y)" counter updates in real-time

### 2. **Summary Cards**
   - 4 stat cards showing portfolio totals
   - Uses existing Stat component for consistency
   - Green tone for positive values (up), red for negative (down)
   - Sub-text shows additional info (e.g., "7 client(s)")

### 3. **Holdings Table**
   - **Holding % Column** - NEW, 2 decimal places, bold
   - **Clients Column** - Shows breakdown with client names and quantities
   - Data sorted by Present Value (descending)
   - Numeric columns right-aligned
   - P&L values color-coded (green/red)
   - Responsive with horizontal scroll on small screens

### 4. **Empty States**
   - When no clients selected: "Select at least one client to view holdings."
   - When no holdings found: Table shows empty
   - When loading: Shows "Loading holdings..." message
   - When error: Shows error message with details

## Component Props

```javascript
// ManagerHoldings Component
<ManagerHoldings 
  managerId={manager.id}      // Manager's unique ID
  clients={cs.data}           // Array of client objects
/>

// Expected clients structure:
{
  id: "client-123",           // Unique client ID
  name: "Durga Lakshman Makana", // Display name
  client_code: "AP8774",       // Zerodha/broker code
  status: "ACTIVE",            // Client status
  portfolio_manager_id: "mgr-1"
}
```

## State Management

```javascript
// Internal component state
const [selectedClientIds, setSelectedClientIds] = useState([...])
// - Array of selected client IDs
// - Managed by checkboxes (toggle, toggle-all)
// - Triggers API call when changed

const [holdings, setHoldings] = useAsync(...)
// - API response with aggregated data
// - Updates when selectedClientIds changes
// - Shows loading/error states

const stats = useMemo(...)
// - Computed totals and percentages
// - Recalculates when holdings.data changes
// - Prevents unnecessary recalculations
```

## Data Flow

```
User clicks checkbox
       ↓
setSelectedClientIds() updates state
       ↓
useAsync() dependency changes
       ↓
api.managerHoldings(managerId, selectedClientIds) called
       ↓
Backend aggregates holdings across clients
       ↓
Response returned with holdings array + totals
       ↓
Component re-renders with new data
       ↓
Summary cards updated
       ↓
Table rows updated
```

## Styling & CSS Classes

```javascript
// Component uses inline styles + existing CSS classes:

// Panel styling (from common styles)
className="panel tbl-scroll"

// Table classes
className="r"          // right-aligned cells
className="tnum"       // tabular numbers font
className="mono"       // monospace font

// Tone classes (for colors)
className={pnl >= 0 ? 'up' : 'down'}  // Green/red coloring

// Typography
style={{ fontWeight: 600 }}  // Symbol column
style={{ fontWeight: 500 }}  // Holding % column
style={{ color: 'var(--muted)' }}  // Zerodha codes
```

## Browser Compatibility

- React 18+
- Modern ES6+ syntax
- Uses async/await
- Responsive design (flexbox/grid)
- Works on desktop and tablets
- Mobile: Horizontal scroll on table for narrow screens

## Performance Considerations

1. **useMemo Hook** - Stats computed only when holdings.data changes
2. **useAsync Hook** - Prevents unnecessary re-renders
3. **API Caching** - Dependency array ensures no duplicate calls
4. **Table Sorting** - Done client-side (no server request)
5. **Lazy Loading** - Components load only when needed

## Accessibility Features

- ✓ Semantic HTML (labels, tables, etc.)
- ✓ Keyboard navigation (Tab, Space for checkboxes)
- ✓ Color + text indicators (not color-only)
- ✓ ARIA labels for interactive elements
- ✓ Proper heading hierarchy
- ✓ Table headers clearly associated with data

## Future UI Enhancements

1. **Filters**
   - Sort by symbol, quantity, holding %, P&L
   - Filter by sector, market cap, P&L range

2. **Export**
   - Export to Excel with per-client breakdown
   - Print-friendly view

3. **Analytics**
   - Concentration chart (top 10 holdings %)
   - Sector breakdown across clients
   - Overlap matrix (which clients share holdings)

4. **Interactivity**
   - Click row to drill down to individual client holdings
   - Expand/collapse client breakdown
   - Search by symbol

5. **Notifications**
   - Client added/removed notification
   - Large concentration warning
   - P&L threshold alerts
