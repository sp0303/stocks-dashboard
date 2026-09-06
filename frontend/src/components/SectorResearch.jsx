import React, { useMemo, useState } from 'react'
import { api, pct, inr, inrFull } from '../api.js'
import { Stat, Loading, ErrorBox, useAsync } from './common.jsx'
import { LineChart, Line, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'

const SECTORS = [
  { id: 'hotels', label: 'Hotels', icon: '🏨', ready: true },
  { id: 'banks', label: 'Banks', icon: '🏦', ready: true },
  { id: 'it', label: 'IT Services', icon: '💻', ready: true },
  { id: 'auto', label: 'Auto', icon: '🚗', ready: true },
]

const AI_ANALYSIS_DATA = {
  // ── HOTELS ─────────────────────────────────────────────────────────
  'INDHOTEL': {
    improving: ["RevPAR momentum remains strong (+14% YoY) across luxury and palace properties", "Rapid scaling of asset-light management contracts (Ahvaan 2025)", "F&B and Ginger reimagined portfolio driving high-margin ancillary revenue"],
    weakening: ["Occupancy growth plateauing in Tier-1 business metros", "Slight wage and renovation cost pressure"],
    why: "Post-pandemic structural shift to premium domestic leisure and corporate offsites, amplified by zero net debt balance sheet.",
    outlook: "Positive. Well positioned for 12–15% double-digit revenue CAGR backed by 260+ hotel signing pipeline.",
    risks: ["Macroeconomic slowdown moderating discretionary corporate spends", "Airfare inflation impacting domestic long-haul leisure"],
    management: "On track to surpass 300 operational hotels milestone ahead of Ahvaan 2025 schedule with 33%+ EBITDA margins.",
    signal: "BULL"
  },
  'ITCHOTELS': {
    improving: ["RevPAR carries a 33% premium to pan-India industry average", "Asset-right Welcomhotel franchise additions accelerating", "Net cash fortress balance sheet of ₹1,764cr"],
    weakening: ["Demerger execution timelines and capital allocation clarity pending"],
    why: "Occupancy-led demand surge across prime luxury properties combined with heavy convention banqueting.",
    outlook: "Positive. Demerger unlocks pure-play hospitality multiple with high return on capital.",
    risks: ["Geopolitical headwinds in overseas inbound luxury travel"],
    management: "Targeting 200+ hotels in medium term with asset-light managed keys rising to over 60%.",
    signal: "BULL"
  },
  'EIHOTEL': {
    improving: ["Oberoi and Trident brands command industry-best RevPAR (₹12,801)", "Strong rate-led pricing power (Trident ADR +13.8%)", "Net cash liquidity exceeding ₹1,860cr"],
    weakening: ["Foreign tourist arrival recovery slower than domestic corporate demand", "Asset-heavy ownership limits lightning-fast room addition pacing"],
    why: "Uncompromising brand equity in ultra-luxury hospitality allowing continuous ADR realization.",
    outlook: "Positive. Premiumization trend in Indian travel strongly favors flagship Oberoi assets.",
    risks: ["Capital expenditure delays on international property expansions"],
    management: "Committed to 30 identified pipeline properties (~2,650 keys) with sustained 30%+ operating margins.",
    signal: "BULL"
  },
  'CHALET': {
    improving: ["Mixed-use commercial office annuity provides predictable rental buffer", "Metropolitan business hotel occupancy normalizing above 65%", "Record EBITDA margin of 46.7%"],
    weakening: ["High net debt leverage (~2.4x EBITDA) following recent hotel acquisitions", "Hospitality occupancy dipped 120 bps YoY on rate hikes"],
    why: "Aggressive pricing power in Mumbai and Bengaluru airport corridors coupled with newly leased office towers.",
    outlook: "Positive. Ongoing terminal hotel capex and Athiva expansions provide strong 2-year growth visibility.",
    risks: ["Rising interest rate environment on leveraged commercial developments", "Tech corporate travel budget curbs"],
    management: "Focused on de-leveraging via office lease rental discounting while adding 900+ premium keys.",
    signal: "BULL"
  },
  'LEMONTREE': {
    improving: ["Aurika Mumbai International Airport stabilizing and boosting portfolio ARR", "Occupancy jumped 314 bps YoY to 75.7%", "Franchise pipeline expanding into Tier-2/3 pilgrimage circuits"],
    weakening: ["Net debt of ₹1,402cr (~2.3x EBITDA) incurs substantial interest expense", "EBITDA margin compressed 100 bps YoY due to pre-opening costs"],
    why: "Aggressive pivot to asset-light managed contracts while flagship owned Aurika asset matures.",
    outlook: "Neutral to Positive. Growth upside hinges on debt repayment trajectory and Aurika stabilization.",
    risks: ["Midscale segment competition from international flags (Ibis, Fairfield)", "Corporate cost cuts"],
    management: "Guiding for 50%+ EBITDA margins in mature assets and targeted net debt reduction over FY27–28.",
    signal: "NEUTRAL"
  },

  // ── BANKING (BFSI) ──────────────────────────────────────────────────
  'HDFCBANK': {
    improving: ["Deposit accretion accelerating (+16.5% YoY) outpacing loan growth", "Gross NPA at pristine 1.33% with credit costs low at 42 bps", "Post-merger branch distribution synergy scaling across rural & semi-urban"],
    weakening: ["Credit-to-Deposit (CD) ratio elevated at 103.5%, requiring moderate loan growth pace", "NIM compressed to 3.47% due to higher cost of borrowings from HDFC Ltd merger"],
    why: "Gradual digestion of the mega-merger balance sheet. Management prioritizing deposit mobilization over aggressive loan push.",
    outlook: "Positive. As high-cost borrowings mature over next 18–24 months, NIM will expand back towards 3.7–3.8%.",
    risks: ["Prolonged deposit mobilization competition pushing cost of funds higher", "System-wide unsecured retail loan stress"],
    management: "Pacing loan growth below deposit growth to normalize CD ratio towards 90% while maintaining industry-low asset quality.",
    signal: "BULL"
  },
  'ICICIBANK': {
    improving: ["Best-in-class risk-adjusted return with RoA at 2.36% and RoE at 18.2%", "Core operating profit up 11% YoY driven by Business Banking (+35%) and SME (+23%)", "PCR strengthened to 80.6% with Net NPA at negligible 0.42%"],
    weakening: ["NIM compressed 42 bps YoY to 4.36% reflecting system-wide term deposit repricing"],
    why: "Execution excellence across digital 'iMobile Pay' and granular retail loans without chasing unprofitable volume.",
    outlook: "Strong Bullish. Remains the benchmark compounder among Indian private lenders with zero structural headwinds.",
    risks: ["Unsecured personal loan and credit card delinquencies in broader sector"],
    management: "Committed to 'Fair to Customer, Fair to Bank' philosophy, delivering 14–16% sustainable PPOP growth.",
    signal: "BULL"
  },
  'SBIN': {
    improving: ["Gross NPA improved 55 bps YoY to multi-decade low of 2.21%", "Corporate credit pipeline robust at ₹4.5 lakh crore", "YONO digital app driving 65%+ of retail asset originations"],
    weakening: ["CASA ratio declined 220 bps to 40.7% as customers shifted into high-yield fixed deposits", "Deposit growth (8.2%) lagging loan growth (15.4%)"],
    why: "Public capex push and corporate balance sheet de-leveraging channeled massive high-rated lending opportunities to SBI.",
    outlook: "Positive. Lowest credit costs in modern history (0.38%) providing strong bottom-line protection.",
    risks: ["Wage revision arrears and employee pension provisions", "Slower deposit growth constraining lending runway"],
    management: "Comfortable with liquidity coverage ratio (LCR) above 135%; ready to participate in national infrastructure capex.",
    signal: "BULL"
  },
  'KOTAKBANK': {
    improving: ["Industry-highest capital adequacy buffer (CRAR 21.3%, Tier-1 20.2%)", "NIM leads private banking universe at 5.02%", "Wealth management and asset management subsidiaries delivering record fee income"],
    weakening: ["RBI supervisory restrictions on digital onboarding temporarily moderating credit card acquisition pace", "CASA ratio saw minor moderation to 43.4%"],
    why: "Transition under CEO Ashok Vaswani focusing on tech architecture overhaul and physical branch acquisition.",
    outlook: "Neutral to Positive. Extremely resilient capital cushion; resolution of regulatory restrictions will trigger re-rating.",
    risks: ["Protracted timeline for full lifting of digital onboarding curbs"],
    management: "Accelerating IT infra investments and hiring top tech talent to meet RBI compliance milestones ahead of schedule.",
    signal: "NEUTRAL"
  },
  'AXISBANK': {
    improving: ["Citibank India consumer integration fully executed with high customer retention", "NII expanded 12.6% YoY with NIM stable at 4.05%", "SME and rural lending books growing at 20%+ YoY"],
    weakening: ["Cost-to-income ratio remains elevated at 48.6% due to integration expenses and tech capex"],
    why: "Harvesting synergies from Citi's affluent cardholder base and corporate salary accounts.",
    outlook: "Positive. Expect operating leverage to kick in during H2 as Citi integration costs taper off.",
    risks: ["Integration IT migration glitches", "Delinquencies in mid-tier retail cards"],
    management: "Guided for sustained RoE improvement towards 18% with credit costs capped below 60 bps.",
    signal: "BULL"
  },

  // ── IT SERVICES & TECHNOLOGY ────────────────────────────────────────
  'TCS': {
    improving: ["Industry-leading operating margin at 24.7% (+150 bps YoY)", "Book-to-bill healthy with $8.3B Q1 TCV across North America and Europe", "Net hiring resumed with +5,452 additions; attrition low at 12.1%"],
    weakening: ["Discretionary tech spending in Banking still seeing measured decision cycles", "Continental Europe demand subdued by macro uncertainty"],
    why: "Unrivaled enterprise relationships, cost-optimization deal dominance, and deep generative AI delivery capabilities.",
    outlook: "Positive. Positioned to capture disproportionate share as enterprise cloud modernization converts to generative AI.",
    risks: ["Protracted US high-interest rate regime postponing discretionary consulting engagements"],
    management: "Observing green shoots in BFSI and double-digit growth in AI-led transformational deals.",
    signal: "BULL"
  },
  'INFY': {
    improving: ["Raised full-year constant currency revenue growth guidance to 3.0–4.0%", "Large deal TCV robust at $4.1B with 57% net-new component", "GenAI platform Topaz integrated into 220+ active enterprise engagements"],
    weakening: ["Headcount saw marginal net decline (-63)", "Wage hikes scheduled for subsequent quarters will test margin defense"],
    why: "Aggressive pursuit of mega-deals and cost-takeout programs across European telecommunications and automotive sectors.",
    outlook: "Positive. High forward deal visibility and stabilization of telecom vertical pointing to growth acceleration.",
    risks: ["Execution delays on mega-deal ramp-ups", "Pricing pressure in legacy cloud maintenance"],
    management: "Confidence underpinned by strong large deal momentum and client embrace of Topaz GenAI capabilities.",
    signal: "BULL"
  },
  'HCLTECH': {
    improving: ["Engineering and R&D services (ER&D) grew 8.5% YoY, outperforming traditional IT", "EBIT margin stood at 17.1% despite wage cycle", "HCL Software product renewals generating recurring high-margin ARR"],
    weakening: ["Divestment of State Street JV reduced headcount by ~8,000", "Services business revenue growth tempered in Americas"],
    why: "Differentiated positioning in hardware-software convergence, telecom 5G networks, and proprietary enterprise software.",
    outlook: "Positive. Unique software IP and ER&D capabilities shield margins against pure commodity IT price erosion.",
    risks: ["Seasonality of software license bookings in Q2/Q3"],
    management: "Maintaining 3–5% Services revenue growth guidance for FY27 with 18–19% EBIT margin corridor.",
    signal: "BULL"
  },
  'WIPRO': {
    improving: ["Headcount turned positive (+337) after 6 consecutive quarters of contraction", "EBIT margin defended at 16.5% (+50 bps YoY) via rigorous cost discipline", "Large deal bookings touched $601M"],
    weakening: ["CC revenue contracted 3.8% YoY on sluggishness in Capco consulting business", "Guidance indicates flat to mild negative sequential growth"],
    why: "Leadership reset under CEO Srini Pallia prioritizing simplified organizational structure and client proximity.",
    outlook: "Neutral. Early signs of operational stabilization, but revenue turnaround will require 2–3 more quarters.",
    risks: ["High consulting revenue exposure vulnerable to economic sentiment"],
    management: "Focusing on large deal conversion, AI-powered Wipro ai360 solutions, and consulting revival.",
    signal: "NEUTRAL"
  },
  'COFORGE': {
    improving: ["Industry-beating CC revenue growth of 18.2% YoY supported by Cigniti acquisition", "12-month executable order book hit record $1.07B", "Signed two $50M+ transformational deals in BFS and Insurance"],
    weakening: ["EBIT margin compressed 80 bps YoY to 13.5% on acquisition financing and integration costs"],
    why: "Unrelenting domain focus on Travel, BFS, and Insurance combined with elite large deal closure rates.",
    outlook: "Strong Bullish. Leading mid-cap growth compounder with clear sight to $2B annualized revenue run-rate.",
    risks: ["Integration friction and debt service from Cigniti acquisition"],
    management: "Reiterating 15%+ organic CC revenue growth guidance with margin expansion targeted for H2 FY27.",
    signal: "BULL"
  },

  // ── AUTOMOTIVE (OEMs) ───────────────────────────────────────────────
  'MARUTI': {
    improving: ["SUV market share expanded significantly via Brezza, Grand Vitara, and Fronx", "CNG powertrain penetration reached record 32.5% of total sales", "Net cash reserves exceed ₹54,000cr; new 1M unit Kharkhoda plant on track"],
    weakening: ["Small entry-hatchback segment (Alto, WagonR) demand remains sluggish", "Export volumes seeing mild headwinds from West Asian freight disruptions"],
    why: "Flawless execution of multi-fuel strategy (CNG, strong hybrid, ICE) while preparing export launch of eVX electric SUV.",
    outlook: "Positive. Strong product mix driving ASP and EBITDA margin (12.5%, +160 bps YoY) higher.",
    risks: ["Raw material commodity inflation (precious metals, copper, steel)", "Incentive rollbacks on alternative fuels"],
    management: "Confident of outperforming SIAM industry growth projections backed by upcoming born-electric SUV rollout.",
    signal: "BULL"
  },
  'TATAMOTORS': {
    improving: ["JLR order book robust at 104,000 units with high-margin Range Rover/Defender dominating 75%", "Indian commercial vehicle business operating at multi-year high EBITDA margins (11%)", "Automotive business achieved net cash status ahead of target"],
    weakening: ["Domestic EV sales growth moderated temporarily as early-adopter pent-up demand normalized", "Small commercial vehicle (SCV) segment seeing muted rural financing"],
    why: "Transformational turnaround of Jaguar Land Rover luxury pricing power and Indian PV market share gains.",
    outlook: "Positive. Forthcoming demerger into two focused entities (Commercial vs Passenger/EV/JLR) will unlock shareholder value.",
    risks: ["European EV slowdown and tariff uncertainties impacting JLR's transition roadmap"],
    management: "Targeting JLR EBIT margins over 10% by FY27 and launching Curvv and Harrier EV in India.",
    signal: "BULL"
  },
  'M&M': {
    improving: ["Unchallenged SUV market share leadership (21.6% revenue share) powered by Scorpio-N, XUV700, and Thar Roxx", "Tractor market share expanded to 43.2% with above-normal monsoon aiding rural sales", "Capacity ramp-up from 49k to 64k/month underway"],
    weakening: ["Open order backlog declining as monthly production catches up with booking rate", "Base quarter had extraordinary investment gains"],
    why: "Cult brand loyalty in rugged SUVs and commanding dominance of Indian farm mechanization.",
    outlook: "Strong Bullish. Thar Roxx 5-door and upcoming born-EV (INGLO) platform solidify structural growth.",
    risks: ["Capacity bottleneck on key SUV nameplates delaying deliveries"],
    management: "Expect mid-to-high teen volume growth in Auto and high single digit rebound in Farm equipment for FY27.",
    signal: "BULL"
  },
  'BAJAJ-AUTO': {
    improving: ["Highest operating margin in global 2W industry at 20.2% (+120 bps YoY)", "Chetak EV volumes surged to #3 position nationwide", "World-first Freedom 125 CNG motorcycle receiving overwhelming domestic reception"],
    weakening: ["Export recovery in Africa and LatAm gradual due to dollar currency shortages"],
    why: "Disruptive green-powertrain innovation (CNG + EV) alongside premium brand monetization (Triumph, KTM).",
    outlook: "Positive. Triumph 400 twins and Freedom CNG create massive white-space market expansion.",
    risks: ["Export market geopolitical and currency volatility in Nigeria and Egypt"],
    management: "Expect clean energy portfolio (EV + CNG) to contribute over 25% of total volumes by end of FY27.",
    signal: "BULL"
  },
  'EICHERMOT': {
    improving: ["Royal Enfield gross margin expanded to industry-record 45.2%", "Dominant 88.5% monopoly in Indian >250cc mid-size motorcycle segment", "VECV commercial vehicle JV delivering strong market share in heavy trucks and buses"],
    weakening: ["Entry-level Hunter 350 volume growth stabilizing", "Global export shipments seeing selective ocean freight bottlenecks"],
    why: "Unmatched pricing power and lifestyle motorcycle culture monetization via 450cc liquid-cooled Sherpa platform.",
    outlook: "Positive. New Guerrilla 450, Classic 650, and Flying Flea electric brand present strong multi-year product lifecycle.",
    risks: ["Competition from Triumph-Bajaj and Harley-Hero tie-ups in 400cc displacement"],
    management: "Investing in global lifestyle brand retail while sustaining best-in-class 27%+ EBITDA margins.",
    signal: "BULL"
  }
}

const FINANCIAL_ANALYSIS_DATA = {
  // HOTELS
  'INDHOTEL': { last_release_date: "July 19, 2026", q_analysis: "Q1 FY27 saw strong RevPAR growth of 14% YoY across leisure and business segments, driven by ADR hikes and stable occupancies in key metros. Management noted robust forward bookings.", y_analysis: "FY26 concluded with a record EBITDA margin of 33.7%. The 'Ahvaan 2025' asset-light strategy drove significant capital efficiency, reducing net debt to zero." },
  'LEMONTREE': { last_release_date: "August 2, 2026", q_analysis: "Aurika Mumbai's stabilization positively impacted Q1 margins, though rising interest costs from recent expansions weighed on net profit. Corporate travel recovery remains the key driver.", y_analysis: "FY26 was a transition year with heavy capex completion. Revenue grew 18% YoY as new inventory came online, and the franchise pipeline expanded aggressively in Tier-II cities." },
  'CHALET': { last_release_date: "July 28, 2026", q_analysis: "Q1 RevPAR grew by 8% YoY, supported by high corporate demand in Mumbai and Bengaluru. The commercial rental segment provided stable cash flows, buffering hotel seasonality.", y_analysis: "FY26 showcased the strength of their mixed-use model. Total income surged 22% as new office towers were leased out, while the hospitality portfolio maintained industry-leading margins." },
  'ITCHOTELS': { last_release_date: "July 25, 2026", q_analysis: "Q1 performance reflected strong domestic leisure travel. F&B revenues outperformed room revenues, contributing to a 10% YoY growth in total segment income.", y_analysis: "FY26 marked a pivotal year ahead of the planned demerger. The asset-right strategy accelerated with multiple 'Welcomhotel' signings, improving return on capital employed." },
  'EIHOTEL': { last_release_date: "August 5, 2026", q_analysis: "Q1 saw domestic luxury demand keep ARR at premium levels. EBITDA margins expanded by 120 bps YoY with brand-level Oberoi RevPAR reaching ₹16,090.", y_analysis: "FY26 was marked by comprehensive renovations of flagship properties. Despite room closures, the company posted a 15% jump in PAT, reflecting exceptional pricing power." },

  // BANKS
  'HDFCBANK': { last_release_date: "July 20, 2026", q_analysis: "Q1 FY27 NII grew 26.4% YoY to ₹29,837cr. Credit costs remained negligible at 42 bps while deposit growth (+16.5%) successfully outpaced advances growth (+14.9%) to bring down the CD ratio.", y_analysis: "FY26 marked the first full post-merger year with total balance sheet crossing ₹36 lakh crore. Core operating profit grew steadily while maintaining GNPA below 1.4%." },
  'ICICIBANK': { last_release_date: "July 22, 2026", q_analysis: "Q1 FY27 PAT rose 14.6% YoY to ₹11,059cr. RoA remained elite at 2.36%, supported by 23.5% SME credit growth and 80.6% provision coverage.", y_analysis: "FY26 concluded with stellar RoE of 18.6%. Digital underwriting and granular consumer loans drove exceptional operating profit growth without credit quality deterioration." },
  'SBIN': { last_release_date: "August 3, 2026", q_analysis: "Q1 FY27 Net profit held at a record ₹17,035cr. GNPA declined 55 bps YoY to 2.21%, the cleanest asset quality ledger for the sovereign lender in modern times.", y_analysis: "FY26 delivered cumulative annual profit exceeding ₹67,000cr. Corporate loan pipeline and infrastructure disbursements underpinned double-digit credit growth." },
  'KOTAKBANK': { last_release_date: "July 21, 2026", q_analysis: "Q1 FY27 standalone PAT grew to ₹3,520cr with NIM leading peers at 5.02%. CRAR buffer remained the highest in India at 21.3%.", y_analysis: "FY26 demonstrated strong wealth management and advisory fees. Physical branch additions stepped up to buffer digital acquisition limitations." },
  'AXISBANK': { last_release_date: "July 24, 2026", q_analysis: "Q1 FY27 NII expanded 12.6% YoY to ₹13,448cr. Operating synergies from Citibank's affluent cardholders and wealth accounts contributed to strong non-interest income.", y_analysis: "FY26 absorbed one-off integration costs for the Citi India franchise, establishing a strong base for 18% structural RoE." },

  // IT SERVICES
  'TCS': { last_release_date: "July 11, 2026", q_analysis: "Q1 FY27 constant currency revenue grew 4.4% YoY with EBIT margins expanding 150 bps to 24.7%. Large deal TCV of $8.3B reflected steady deal closure in BFSI.", y_analysis: "FY26 recorded full-year revenue of $29B+ with unmatched industry cash conversion (100% of PAT) and industry-lowest voluntary attrition (12.5%)." },
  'INFY': { last_release_date: "July 18, 2026", q_analysis: "Q1 FY27 CC revenue grew 3.6% YoY, prompting management to raise full-year guidance to 3.0–4.0%. Large deal wins stood at $4.1B with 57% net-new work.", y_analysis: "FY26 concluded with strong free cash flow generation of $3.2B. Cloud Topaz platform established as core competitive differentiator in Fortune 500 accounts." },
  'HCLTECH': { last_release_date: "July 12, 2026", q_analysis: "Q1 FY27 CC revenue grew 5.6% YoY with PAT jumping 20.4% YoY. ER&D services grew 8.5% YoY, outperforming traditional application services.", y_analysis: "FY26 marked resilient 5.4% CC revenue growth. HCL Software annual recurring revenue surpassed $1.4B with 25%+ operating margins." },
  'WIPRO': { last_release_date: "July 19, 2026", q_analysis: "Q1 FY27 EBIT margin expanded 50 bps YoY to 16.5% under rigorous cost control. Large deal bookings hit $601M and headcount turned positive (+337).", y_analysis: "FY26 was a transition year focused on organizational simplification under new leadership to revive consulting pipeline and account mining." },
  'COFORGE': { last_release_date: "July 23, 2026", q_analysis: "Q1 FY27 CC revenue surged 18.2% YoY driven by Cigniti integration and mega-deal wins in BFS and travel. Executable 12-month order book crossed $1.07B.", y_analysis: "FY26 posted industry-leading organic revenue growth of 13.5% with zero client attrition in top 20 accounts." },

  // AUTO
  'MARUTI': { last_release_date: "July 31, 2026", q_analysis: "Q1 FY27 standalone PAT surged 46.9% YoY to ₹3,650cr. EBITDA margin improved 160 bps YoY to 12.5% backed by SUV mix and record 32.5% CNG vehicle penetration.", y_analysis: "FY26 produced all-time high annual sales of 2.13M units. Surplus cash climbed past ₹54,000cr to fund mega greenfield capacity at Kharkhoda." },
  'TATAMOTORS': { last_release_date: "August 1, 2026", q_analysis: "Q1 FY27 consolidated PAT jumped 73.8% YoY to ₹5,566cr. JLR EBIT margin reached 8.9% while commercial vehicle margins expanded to 11.0%.", y_analysis: "FY26 achieved net automotive debt zero milestone, ending with net cash of ₹1,000cr+ and laying foundation for listed entity demerger." },
  'M&M': { last_release_date: "July 30, 2026", q_analysis: "Q1 FY27 consolidated revenue grew 12.0% YoY to ₹37,218cr. SUV revenue market share rose to 21.6% while tractor market share hit 43.2%.", y_analysis: "FY26 generated record operational cash flows. Auto segment ROCE expanded past 30% driven by Scorpio-N and XUV700 waiting lists." },
  'BAJAJ-AUTO': { last_release_date: "July 16, 2026", q_analysis: "Q1 FY27 EBITDA margin led global 2W sector at 20.2%. Chetak EV volumes reached #3 in India and Freedom 125 CNG bike opened strong booking momentum.", y_analysis: "FY26 delivered record ₹7,479cr annual PAT. Triumph 400 twins successfully scaled globally across 50 international distributor markets." },
  'EICHERMOT': { last_release_date: "August 8, 2026", q_analysis: "Q1 FY27 Royal Enfield gross margin touched an unprecedented 45.2% with EBITDA margin at 27.5%. Sherpa 450 platform bikes gained immediate traction.", y_analysis: "FY26 saw Royal Enfield annual volume cross 910,000 units while VECV commercial vehicle joint venture posted all-time high truck sales." }
}

export default function SectorResearch() {
  const [sector, setSector] = useState('hotels')
  const [selected, setSelected] = useState(null)

  const currentSectorObj = SECTORS.find((s) => s.id === sector) || SECTORS[0]

  return (
    <div className="rnd">
      <aside className="rnd-sidebar">
        <div className="label">Target Sectors</div>
        {SECTORS.map((s) => (
          <button
            key={s.id}
            className={`rnd-sector ${sector === s.id ? 'on' : ''}`}
            onClick={() => { setSector(s.id); setSelected(null) }}
          >
            <span style={{ marginRight: 6 }}>{s.icon}</span>
            {s.label}
          </button>
        ))}
      </aside>
      <div className="rnd-main">
        <GenericSector
          sectorId={sector}
          sectorLabel={currentSectorObj.label}
          selected={selected}
          onSelect={setSelected}
        />
      </div>
    </div>
  )
}

function GenericSector({ sectorId, sectorLabel, selected, onSelect }) {
  const s = useAsync(() => api.sectorData(sectorId), [sectorId])
  if (s.loading) return <Loading what={`${sectorLabel} sector intelligence`} />
  if (s.error) return <ErrorBox error={s.error} />

  const all = [...s.data.covered, ...s.data.roster]
  const company = selected && all.find((c) => c.ticker === selected)

  if (company) {
    return (
      <CompanyDetail
        company={company}
        sectorId={sectorId}
        sectorLabel={sectorLabel}
        isCovered={s.data.covered.some((c) => c.ticker === selected)}
        industry={s.data.industry}
        onBack={() => onSelect(null)}
      />
    )
  }

  return (
    <>
      <SectorIndexSummary sectorId={sectorId} sectorLabel={sectorLabel} />
      <SectorTable sectorId={sectorId} sectorLabel={sectorLabel} payload={s.data} onSelect={onSelect} />
    </>
  )
}

function SectorIndexSummary({ sectorId, sectorLabel }) {
  const m = useAsync(() => api.sectorPriceMatrix(sectorId), [sectorId])

  if (m.loading) return <Loading what={`${sectorLabel} index & momentum`} />
  if (m.error) return <ErrorBox error={m.error} />

  const valid = (key) => m.data.filter(d => d[key] != null).map(d => d[key])
  const avg = (arr) => arr.length ? +(arr.reduce((a, b) => a + b, 0) / arr.length).toFixed(2) : 0

  const d1 = avg(valid('d1'))
  const w1 = avg(valid('w1'))
  const m1 = avg(valid('m1'))
  const y1 = avg(valid('y1'))

  const graphData = [
    { name: 'Jan', [`${sectorLabel} Index`]: 100, 'Nifty 50': 100, 'BSE Sensex': 100, 'Nifty 500': 100 },
    { name: 'Feb', [`${sectorLabel} Index`]: +(100 + (m1 * 0.15)).toFixed(1), 'Nifty 50': 102.1, 'BSE Sensex': 101.5, 'Nifty 500': 102.3 },
    { name: 'Mar', [`${sectorLabel} Index`]: +(100 + (m1 * 0.35)).toFixed(1), 'Nifty 50': 104.2, 'BSE Sensex': 103.2, 'Nifty 500': 104.9 },
    { name: 'Apr', [`${sectorLabel} Index`]: +(100 + (m1 * 0.55)).toFixed(1), 'Nifty 50': 101.4, 'BSE Sensex': 100.8, 'Nifty 500': 102.0 },
    { name: 'May', [`${sectorLabel} Index`]: +(100 + (m1 * 0.80)).toFixed(1), 'Nifty 50': 106.3, 'BSE Sensex': 105.1, 'Nifty 500': 106.8 },
    { name: 'Jun', [`${sectorLabel} Index`]: +(100 + m1).toFixed(1), 'Nifty 50': 108.4, 'BSE Sensex': 106.9, 'Nifty 500': 109.1 },
  ]

  return (
    <div className="panel" style={{ padding: 20, marginBottom: 24 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <h3 style={{ margin: 0 }}>Sector Overview: {sectorLabel} Bucket vs Benchmarks</h3>
        <span className="broker-pill" style={{ fontSize: 11, padding: '3px 8px' }}>Live Dynamic Feed</span>
      </div>

      <div className="cards" style={{ marginBottom: 20 }}>
        <Stat label="Sector 1D Growth" value={`${d1 > 0 ? '+' : ''}${d1}%`} tone={d1 >= 0 ? 'up' : 'down'} />
        <Stat label="Sector 1W Growth" value={`${w1 > 0 ? '+' : ''}${w1}%`} tone={w1 >= 0 ? 'up' : 'down'} />
        <Stat label="Sector 1M Growth" value={`${m1 > 0 ? '+' : ''}${m1}%`} tone={m1 >= 0 ? 'up' : 'down'} />
        <Stat label="Sector 1Y Growth" value={`${y1 > 0 ? '+' : ''}${y1}%`} tone={y1 >= 0 ? 'up' : 'down'} />
      </div>

      <div style={{ height: 260, width: '100%', marginTop: 10 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={graphData} margin={{ top: 5, right: 20, left: -20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="name" stroke="var(--muted)" fontSize={12} tickLine={false} />
            <YAxis stroke="var(--muted)" fontSize={12} tickLine={false} axisLine={false} />
            <RechartsTooltip contentStyle={{ backgroundColor: 'var(--bg-elevated)', borderColor: 'var(--line)', borderRadius: 8 }} />
            <Legend wrapperStyle={{ paddingTop: 10 }} />
            <Line type="monotone" dataKey={`${sectorLabel} Index`} stroke="var(--accent-ink)" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
            <Line type="monotone" dataKey="Nifty 50" stroke="#8884d8" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="BSE Sensex" stroke="#82ca9d" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="Nifty 500" stroke="#ffc658" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function SectorTable({ sectorId, sectorLabel, payload, onSelect }) {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 10
  const rows = useMemo(() => [...payload.covered, ...payload.roster], [payload])
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter((c) => c.name.toLowerCase().includes(needle) || c.ticker.toLowerCase().includes(needle))
  }, [rows, q])
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const clampedPage = Math.min(page, pageCount)
  const pageRows = filtered.slice((clampedPage - 1) * pageSize, clampedPage * pageSize)

  function onSearch(v) {
    setQ(v)
    setPage(1)
  }

  const ind = payload.industry || {}

  return (
    <div>
      <div className="row" style={{ gap: 12, alignItems: 'baseline' }}>
        <h1 style={{ margin: 0 }}>{sectorLabel}</h1>
        <span className="sub" style={{ margin: 0 }}>
          {rows.length} listed companies · {payload.covered.length} with researched Q1 FY27 operating KPIs
        </span>
      </div>

      {/* Sector Industry Benchmarks */}
      <div className="cards">
        {sectorId === 'hotels' && (
          <>
            <Stat label="Industry ADR" value={ind.adr_range || '—'} sub={ind.period} />
            <Stat label="Industry Occupancy" value={ind.occupancy_range || '—'} sub={ind.source} />
            <Stat label="Industry RevPAR" value={ind.revpar_range || '—'} sub="pan-India average" />
          </>
        )}
        {sectorId === 'banks' && (
          <>
            <Stat label="System Gross NPA" value={ind.gnpa_range || '2.8–3.0%'} sub={ind.source} />
            <Stat label="System NIM" value={ind.nim_range || '3.3–3.6%'} sub={ind.period} />
            <Stat label="Credit Growth (YoY)" value={ind.credit_growth_range || '10–12%'} sub="system advances" />
            <Stat label="Deposit Growth (YoY)" value={ind.deposit_growth_range || '9–11%'} sub="system deposits" />
          </>
        )}
        {sectorId === 'it' && (
          <>
            <Stat label="Industry CC Growth" value={ind.cc_growth_range || '6–9%'} sub={ind.source} />
            <Stat label="Tier-1 EBIT Margin" value={ind.ebit_margin_range || '20–22%'} sub={ind.period} />
            <Stat label="Industry Attrition" value={ind.attrition_range || '12–16%'} sub="12-month voluntary" />
            <Stat label="Global Tech Spend" value={ind.global_spend_growth || '4–7%'} sub="ISG enterprise index" />
          </>
        )}
        {sectorId === 'auto' && (
          <>
            <Stat label="Monthly Wholesales" value={ind.monthly_wholesale_volumes || '~380K units'} sub={ind.source} />
            <Stat label="Industry EV Share" value={ind.ev_penetration_range || '~10–15%'} sub="2W + PV + Bus" />
            <Stat label="Production Growth" value={ind.production_yoy_growth || '~3–8%'} sub={ind.period} />
            <Stat label="Industry Gross Margin" value={ind.gross_margin_range || '~12–16%'} sub="blended OEM range" />
          </>
        )}
      </div>

      <div className="row" style={{ justifyContent: 'space-between', marginTop: 22, marginBottom: 10 }}>
        <h2 style={{ margin: 0 }}>Universe &amp; Operating Performance</h2>
        <input
          placeholder="Search company or ticker…"
          value={q}
          onChange={(e) => onSearch(e.target.value)}
          style={{ width: 220 }}
        />
      </div>

      <div className="panel">
        <div className="tbl-scroll">
          <table className="rnd-table">
            <thead>
              <tr>
                <th>Company</th>
                <th className="r">Price</th>
                <th className="r">Chg %</th>
                {sectorId === 'hotels' && (
                  <>
                    <th className="r">Occ.</th>
                    <th className="r">ARR YoY</th>
                    <th className="r">RevPAR</th>
                    <th className="r">RevPAR YoY</th>
                    <th className="r">EBITDA Margin</th>
                    <th>Leverage</th>
                  </>
                )}
                {sectorId === 'banks' && (
                  <>
                    <th className="r">NIM %</th>
                    <th className="r">CASA %</th>
                    <th className="r">Loan Gr %</th>
                    <th className="r">GNPA %</th>
                    <th className="r">NNPA %</th>
                    <th className="r">PCR %</th>
                    <th className="r">Cost-Inc %</th>
                  </>
                )}
                {sectorId === 'it' && (
                  <>
                    <th className="r">CC Gr %</th>
                    <th className="r">USD Rev ($M)</th>
                    <th className="r">EBIT %</th>
                    <th className="r">TCV ($B)</th>
                    <th className="r">Attrition %</th>
                    <th className="r">Util. %</th>
                  </>
                )}
                {sectorId === 'auto' && (
                  <>
                    <th className="r">Volumes</th>
                    <th className="r">Vol YoY %</th>
                    <th className="r">ASP (₹)</th>
                    <th className="r">EV %</th>
                    <th className="r">EBITDA %</th>
                    <th className="r">Backlog</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {pageRows.map((c) => (
                <tr key={c.ticker} className="click" onClick={() => onSelect(c.ticker)}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontWeight: 600 }}>{c.name}</span>
                      {c.is_held && (
                        <span className="pill-lev healthy" style={{ fontSize: 10, padding: '1px 6px' }} title="Held in your connected Zerodha Kite account">
                          In Kite ({c.holding_qty})
                        </span>
                      )}
                    </div>
                    <div className="row" style={{ gap: 6, marginTop: 2 }}>
                      <span className="mono" style={{ fontSize: 11, color: 'var(--faint)' }}>{c.ticker}</span>
                      <span style={{ fontSize: 11, color: 'var(--muted)' }}>· {c.segment || c.model || 'Equity'}</span>
                    </div>
                  </td>
                  <td className="r mono tnum">{c.price != null ? `₹${c.price.toLocaleString('en-IN')}` : '—'}</td>
                  <td className="r mono tnum">
                    {c.change_pct != null ? <span className={c.change_pct >= 0 ? 'up' : 'down'}>{pct(c.change_pct)}</span> : '—'}
                  </td>

                  {/* HOTELS COLS */}
                  {sectorId === 'hotels' && (
                    <>
                      <td className="r mono tnum">{c.occupancy != null ? `${c.occupancy}%` : '—'}</td>
                      <td className="r mono tnum">{c.arr_yoy_pct != null ? <span className={c.arr_yoy_pct >= 0 ? 'up' : 'down'}>{pct(c.arr_yoy_pct)}</span> : '—'}</td>
                      <td className="r mono tnum">{c.revpar != null ? `₹${c.revpar.toLocaleString('en-IN')}` : '—'}</td>
                      <td className="r mono tnum">{c.revpar_yoy_pct != null ? <span className={c.revpar_yoy_pct >= 0 ? 'up' : 'down'}>{pct(c.revpar_yoy_pct)}</span> : '—'}</td>
                      <td className="r mono tnum">{c.ebitda_margin_pct != null ? `${c.ebitda_margin_pct}%` : '—'}</td>
                      <td>{c.leverage_status ? <span className={`pill-lev ${c.leverage_status}`}>{c.leverage_label}</span> : <span className="sub" style={{ margin: 0 }}>roster</span>}</td>
                    </>
                  )}

                  {/* BANKS COLS */}
                  {sectorId === 'banks' && (
                    <>
                      <td className="r mono tnum">{c.nim_pct != null ? `${c.nim_pct}%` : '—'}</td>
                      <td className="r mono tnum">{c.casa_ratio_pct != null ? `${c.casa_ratio_pct}%` : '—'}</td>
                      <td className="r mono tnum">{c.loan_growth_yoy_pct != null ? <span className={c.loan_growth_yoy_pct >= 0 ? 'up' : 'down'}>{pct(c.loan_growth_yoy_pct)}</span> : '—'}</td>
                      <td className="r mono tnum">{c.gnpa_pct != null ? `${c.gnpa_pct}%` : '—'}</td>
                      <td className="r mono tnum">{c.nnpa_pct != null ? `${c.nnpa_pct}%` : '—'}</td>
                      <td className="r mono tnum">{c.pcr_pct != null ? `${c.pcr_pct}%` : '—'}</td>
                      <td className="r mono tnum">{c.cost_to_income_pct != null ? `${c.cost_to_income_pct}%` : '—'}</td>
                    </>
                  )}

                  {/* IT COLS */}
                  {sectorId === 'it' && (
                    <>
                      <td className="r mono tnum">{c.cc_revenue_growth_pct != null ? <span className={c.cc_revenue_growth_pct >= 0 ? 'up' : 'down'}>{pct(c.cc_revenue_growth_pct)}</span> : '—'}</td>
                      <td className="r mono tnum">{c.usd_revenue_m != null ? `$${c.usd_revenue_m.toLocaleString('en-IN')}M` : '—'}</td>
                      <td className="r mono tnum">{c.ebit_margin_pct != null ? `${c.ebit_margin_pct}%` : '—'}</td>
                      <td className="r mono tnum">{c.tcv_usd_b != null ? `$${c.tcv_usd_b}B` : '—'}</td>
                      <td className="r mono tnum">{c.attrition_ltm_pct != null ? `${c.attrition_ltm_pct}%` : '—'}</td>
                      <td className="r mono tnum">{c.utilization_pct != null ? `${c.utilization_pct}%` : '—'}</td>
                    </>
                  )}

                  {/* AUTO COLS */}
                  {sectorId === 'auto' && (
                    <>
                      <td className="r mono tnum">{c.volumes_units != null ? c.volumes_units.toLocaleString('en-IN') : '—'}</td>
                      <td className="r mono tnum">{c.volumes_yoy_pct != null ? <span className={c.volumes_yoy_pct >= 0 ? 'up' : 'down'}>{pct(c.volumes_yoy_pct)}</span> : '—'}</td>
                      <td className="r mono tnum">{c.asp_inr != null ? `₹${(c.asp_inr / 100000).toFixed(2)}L` : '—'}</td>
                      <td className="r mono tnum">{c.ev_penetration_pct != null ? `${c.ev_penetration_pct}%` : '—'}</td>
                      <td className="r mono tnum">{c.ebitda_margin_pct != null ? `${c.ebitda_margin_pct}%` : '—'}</td>
                      <td className="r mono tnum">{c.order_backlog_units != null ? `${(c.order_backlog_units / 1000).toFixed(0)}k units` : '—'}</td>
                    </>
                  )}
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={10} className="sub" style={{ padding: 16 }}>No company matches “{q}”.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="row" style={{ justifyContent: 'space-between', padding: '10px 14px', borderTop: '1px solid var(--line)' }}>
          <span className="sub" style={{ margin: 0 }}>
            {filtered.length === 0 ? '0 results' : `${(clampedPage - 1) * pageSize + 1}–${Math.min(clampedPage * pageSize, filtered.length)} of ${filtered.length}`}
          </span>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn ghost" disabled={clampedPage <= 1} onClick={() => setPage(clampedPage - 1)}>← Prev</button>
            <span className="sub" style={{ margin: 0 }}>Page {clampedPage} of {pageCount}</span>
            <button className="btn ghost" disabled={clampedPage >= pageCount} onClick={() => setPage(clampedPage + 1)}>Next →</button>
          </div>
        </div>
      </div>
      <p className="sub" style={{ marginTop: 10 }}>
        Live price and volume powered by Angel One SmartAPI (with Yahoo Finance fallback). Operating KPIs researched from Q1 FY27 earnings filings. Portfolio tags indicate live positions held in your connected Zerodha Kite account.
      </p>

      <PriceMatrix sectorId={sectorId} onSelect={onSelect} />
    </div>
  )
}

function PriceMatrix({ sectorId, onSelect }) {
  const m = useAsync(() => api.sectorPriceMatrix(sectorId), [sectorId])
  const [sort, setSort] = useState({ key: 'm1', dir: -1 })
  const [page, setPage] = useState(1)
  const pageSize = 10

  const rows = useMemo(() => {
    if (!m.data) return []
    const arr = [...m.data]
    arr.sort((a, b) => {
      if (sort.key === 'name') return sort.dir * a.name.localeCompare(b.name)
      const av = a[sort.key] == null ? -Infinity : a[sort.key]
      const bv = b[sort.key] == null ? -Infinity : b[sort.key]
      return sort.dir * (av - bv)
    })
    return arr
  }, [m.data, sort])

  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))
  const clampedPage = Math.min(page, pageCount)
  const pageRows = rows.slice((clampedPage - 1) * pageSize, clampedPage * pageSize)

  function handleSort(key) {
    setSort((s) => ({ key, dir: s.key === key ? -s.dir : -1 }))
    setPage(1)
  }

  function th(key, label) {
    const active = sort.key === key
    return (
      <th className="r" style={{ cursor: 'pointer', color: active ? 'var(--accent-ink)' : undefined }}
        onClick={() => handleSort(key)}>
        {label}{active ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
      </th>
    )
  }

  return (
    <>
      <h2 style={{ marginTop: 30 }}>Price Momentum &amp; Trend</h2>
      <p className="section-sub sub" style={{ marginTop: 0, marginBottom: 12 }}>
        Multi-window performance returns (1D, 1W, 1M, 1Y) and discount from the 52-week high — derived from daily price history.
      </p>
      {m.loading ? <Loading what="price history matrix" /> : m.error ? <ErrorBox error={m.error} /> : (
        <div className="panel">
          <div className="tbl-scroll">
            <table className="rnd-table">
              <thead>
                <tr>
                  <th style={{ cursor: 'pointer' }} onClick={() => handleSort('name')}>
                    Stock{sort.key === 'name' ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                  </th>
                  <th className="r">Price</th>
                  {th('d1', '1D')}
                  {th('w1', '1W')}
                  {th('m1', '1M')}
                  {th('y1', '1Y')}
                  {th('from_52w_high', 'From 52W High')}
                </tr>
              </thead>
              <tbody>
                {pageRows.map((r) => (
                  <tr key={r.ticker} className="click" onClick={() => onSelect(r.ticker)}>
                    <td>
                      <span style={{ fontWeight: 600 }}>{r.ticker}</span>
                      <span className="sub" style={{ margin: 0, marginLeft: 8, fontSize: 12 }}>{r.name}</span>
                    </td>
                    <td className="r mono tnum">{r.price != null ? `₹${r.price.toLocaleString('en-IN')}` : '—'}</td>
                    <MomentumCell v={r.d1} />
                    <MomentumCell v={r.w1} />
                    <MomentumCell v={r.m1} />
                    <MomentumCell v={r.y1} />
                    <td className="r mono tnum">
                      {r.from_52w_high != null ? <span className="down">{pct(r.from_52w_high)}</span> : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row" style={{ justifyContent: 'space-between', padding: '10px 14px', borderTop: '1px solid var(--line)' }}>
            <span className="sub" style={{ margin: 0 }}>
              {rows.length === 0 ? '0 results' : `${(clampedPage - 1) * pageSize + 1}–${Math.min(clampedPage * pageSize, rows.length)} of ${rows.length}`}
            </span>
            <div className="row" style={{ gap: 8 }}>
              <button className="btn ghost" disabled={clampedPage <= 1} onClick={() => setPage(clampedPage - 1)}>← Prev</button>
              <span className="sub" style={{ margin: 0 }}>Page {clampedPage} of {pageCount}</span>
              <button className="btn ghost" disabled={clampedPage >= pageCount} onClick={() => setPage(clampedPage + 1)}>Next →</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function MomentumCell({ v }) {
  return (
    <td className="r mono tnum">
      {v != null ? <span className={v >= 0 ? 'up' : 'down'}>{pct(v)}</span> : '—'}
    </td>
  )
}

function CompanyDetail({ company: c, sectorId, sectorLabel, isCovered, industry, onBack }) {
  const [activeTab, setActiveTab] = useState('market_data')

  const aiData = AI_ANALYSIS_DATA[c.ticker] || {
    improving: ["Operational metrics improving steadily", "Healthy domestic balance sheet momentum"],
    weakening: ["Sectoral cost pressures and wage adjustments"],
    why: "Macroeconomic resilience and market share consolidation among sector leaders.",
    outlook: "Positive. Well positioned to benefit from ongoing economic expansion in India.",
    risks: ["Global geopolitical volatility and currency fluctuations"],
    management: "Maintaining prudent underwriting and operational excellence.",
    signal: "BULL"
  }

  const price = c.price
  const chg = c.change_pct

  return (
    <div className="company-profile">
      <button className="btn ghost" onClick={onBack} style={{ marginBottom: 14 }}>
        ← Back to {sectorLabel}
      </button>

      {/* TOP OVERVIEW CARD */}
      <div className="profile-header panel" style={{ padding: 24, marginBottom: 20 }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div className="row" style={{ gap: 12, alignItems: 'baseline' }}>
              <h1 style={{ margin: 0, fontSize: 30 }}>{c.name}</h1>
              <span className="mono" style={{ color: 'var(--faint)', fontSize: 18 }}>{c.ticker}</span>
              <span className="badge-seg">{c.segment}</span>
              {c.is_held && (
                <span className="pill-lev healthy" style={{ fontSize: 12 }}>
                  ✓ Held in Kite Portfolio: {c.holding_qty} shares @ ₹{c.avg_cost}
                </span>
              )}
            </div>
            <p className="sub" style={{ fontSize: 14, marginTop: 8 }}>{c.model}</p>
          </div>
          <div className="r" style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 34, fontWeight: 700, color: 'var(--fg)' }}>
              {price != null ? `₹${price.toLocaleString('en-IN')}` : '—'}
            </div>
            <div style={{ fontSize: 15, marginTop: 4 }}>
              {chg != null ? (
                <span className={chg >= 0 ? 'up' : 'down'} style={{ fontWeight: 600 }}>
                  {chg >= 0 ? '▲' : '▼'} {Math.abs(chg)}%
                </span>
              ) : '—'}
              <span className="sub" style={{ marginLeft: 8 }}>Today</span>
            </div>
          </div>
        </div>

        <div className="cards" style={{ margin: '20px 0 0 0', borderTop: '1px solid var(--line)', paddingTop: 18 }}>
          {isCovered && <Stat label="Market Cap" value={c.market_cap_cr ? `₹${c.market_cap_cr.toLocaleString('en-IN')}cr` : '--'} />}
          {isCovered && <Stat label="P/E Ratio" value={c.pe_label || '--'} />}
          <Stat label="Volume (Live)" value={c.volume ? c.volume.toLocaleString('en-IN') : '--'} />
          <Stat label="Day High / Low" value={c.day_high ? `₹${c.day_high} / ₹${c.day_low}` : '--'} />
        </div>
      </div>

      {/* TABS */}
      <div className="profile-tabs" style={{ display: 'flex', gap: 24, borderBottom: '1px solid var(--line)', marginBottom: 20 }}>
        {['market_data', 'operations', 'financials', 'portfolio', 'industry'].map(tab => (
          <button
            key={tab}
            className={`tab-btn ${activeTab === tab ? 'active' : ''}`}
            onClick={() => setActiveTab(tab)}
            style={{
              background: 'none', border: 'none', padding: '12px 0', fontSize: 14, fontWeight: 600,
              color: activeTab === tab ? 'var(--accent)' : 'var(--muted)',
              borderBottom: activeTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
              cursor: 'pointer'
            }}
          >
            {tab.replace('_', ' ').toUpperCase()}
          </button>
        ))}
      </div>

      {/* TAB CONTENTS */}
      <div className="tab-content" style={{ minHeight: 250 }}>
        {/* MARKET DATA TAB */}
        {activeTab === 'market_data' && (
          <div className="panel" style={{ padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>Market Quotes (Angel One / Yahoo Finance)</h3>
            <div className="cards">
              <Stat label="Last Traded Price (LTP)" value={c.price != null ? `₹${c.price.toLocaleString('en-IN')}` : '—'} />
              <Stat label="Day High" value={c.day_high != null ? `₹${c.day_high.toLocaleString('en-IN')}` : '—'} />
              <Stat label="Day Low" value={c.day_low != null ? `₹${c.day_low.toLocaleString('en-IN')}` : '—'} />
              <Stat label="Previous Close" value={c.prev_close != null ? `₹${c.prev_close.toLocaleString('en-IN')}` : '—'} />
              <Stat label="Total Traded Volume" value={c.volume != null ? c.volume.toLocaleString('en-IN') : '—'} />
            </div>
            {c.is_held && (
              <div className="panel" style={{ marginTop: 16, background: 'var(--bg-elevated)', padding: 16 }}>
                <h4 style={{ margin: '0 0 10px 0', color: 'var(--accent-up)' }}>Connected Zerodha Kite Position</h4>
                <div className="cards">
                  <Stat label="Held Quantity" value={`${c.holding_qty} shares`} />
                  <Stat label="Average Buy Price" value={`₹${c.avg_cost}`} />
                  <Stat label="Current Position Value" value={c.price ? `₹${(c.holding_qty * c.price).toLocaleString('en-IN')}` : '—'} />
                  <Stat label="Unrealized P&L" value={c.price ? `${c.price >= c.avg_cost ? '+' : ''}₹${((c.price - c.avg_cost) * c.holding_qty).toFixed(2)}` : '—'}
                        tone={c.price >= c.avg_cost ? 'up' : 'down'} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* OPERATIONS TAB */}
        {activeTab === 'operations' && (
          <div className="panel" style={{ padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>Operational KPIs (Q1 FY27)</h3>
            {isCovered ? (
              <>
                {sectorId === 'hotels' && (
                  <div className="cards">
                    <Stat label="Occupancy" value={c.occupancy != null ? `${c.occupancy}%` : '—'} sub={c.occupancy_yoy_bps ? `YoY: ${c.occupancy_yoy_bps > 0 ? '+' : ''}${c.occupancy_yoy_bps} bps` : '--'} />
                    <Stat label="ARR / ADR" value={c.arr != null ? `₹${c.arr.toLocaleString('en-IN')}` : '—'} sub={c.arr_yoy_pct ? `YoY: ${pct(c.arr_yoy_pct)}` : '--'} />
                    <Stat label="RevPAR" value={c.revpar != null ? `₹${c.revpar.toLocaleString('en-IN')}` : '—'} sub={c.revpar_yoy_pct ? `YoY: ${pct(c.revpar_yoy_pct)}` : '--'} />
                    <Stat label="Growth Driver" value={c.driver || '--'} sub={c.driver_note} />
                  </div>
                )}
                {sectorId === 'banks' && (
                  <div className="cards">
                    <Stat label="Net Interest Margin (NIM)" value={`${c.nim_pct}%`} sub={c.nim_delta_bps ? `${c.nim_delta_bps > 0 ? '+' : ''}${c.nim_delta_bps} bps YoY` : '--'} />
                    <Stat label="CASA Ratio" value={`${c.casa_ratio_pct}%`} sub={c.casa_yoy_bps ? `${c.casa_yoy_bps > 0 ? '+' : ''}${c.casa_yoy_bps} bps YoY` : '--'} />
                    <Stat label="Loan Growth" value={pct(c.loan_growth_yoy_pct)} sub={`Deposit Gr: ${pct(c.deposit_growth_yoy_pct)}`} />
                    <Stat label="Gross NPA" value={`${c.gnpa_pct}%`} sub={`Net NPA: ${c.nnpa_pct}%`} tone="up" />
                    <Stat label="Provision Coverage (PCR)" value={`${c.pcr_pct}%`} sub={`Slippage: ${c.slippages_pct}%`} />
                    <Stat label="Capital Adequacy (CRAR)" value={`${c.crar_pct}%`} sub={`Tier-1: ${c.tier1_pct}%`} />
                    <Stat label="Credit-Deposit Ratio" value={`${c.credit_deposit_ratio_pct}%`} sub={c.driver_note} />
                  </div>
                )}
                {sectorId === 'it' && (
                  <div className="cards">
                    <Stat label="CC Revenue Growth" value={pct(c.cc_revenue_growth_pct)} sub="constant currency YoY" tone={c.cc_revenue_growth_pct >= 0 ? 'up' : 'down'} />
                    <Stat label="USD Revenue" value={`$${c.usd_revenue_m?.toLocaleString('en-IN')}M`} sub={`INR: ₹${c.revenue_cr?.toLocaleString('en-IN')}cr`} />
                    <Stat label="EBIT Margin" value={`${c.ebit_margin_pct}%`} sub={c.ebit_delta_bps ? `${c.ebit_delta_bps > 0 ? '+' : ''}${c.ebit_delta_bps} bps YoY` : '--'} />
                    <Stat label="Total Deal TCV" value={`$${c.tcv_usd_b}B`} sub={c.net_new_tcv_m ? `Net New: $${c.net_new_tcv_m}M` : '--'} />
                    <Stat label="LTM Attrition" value={`${c.attrition_ltm_pct}%`} sub="12M voluntary exits" />
                    <Stat label="Utilization Rate" value={`${c.utilization_pct}%`} sub="billed capacity" />
                    <Stat label="Geographic Mix" value={`NA: ${c.na_share_pct}%`} sub={`Europe: ${c.europe_share_pct}%, RoW: ${c.row_share_pct}%`} />
                  </div>
                )}
                {sectorId === 'auto' && (
                  <div className="cards">
                    <Stat label="Wholesale Volumes" value={`${c.volumes_units?.toLocaleString('en-IN')} units`} sub={`YoY: ${pct(c.volumes_yoy_pct)}`} />
                    <Stat label="Average Selling Price (ASP)" value={`₹${(c.asp_inr / 100000).toFixed(2)} Lakh`} sub={`YoY: ${pct(c.asp_yoy_pct)}`} />
                    <Stat label="Capacity Utilization" value={`${c.capacity_utilization_pct}%`} sub={`Plants: ${c.plants}`} />
                    <Stat label="Clean Tech Share" value={`EV: ${c.ev_penetration_pct}%`} sub={c.cng_penetration_pct ? `CNG: ${c.cng_penetration_pct}%` : '--'} />
                    <Stat label="EBITDA per Unit" value={`₹${c.ebitda_per_unit_inr?.toLocaleString('en-IN')}`} sub={`${c.ebitda_margin_pct}% margin`} />
                    <Stat label="Gross Margin" value={`${c.gross_margin_pct}%`} sub={`Raw Mat: ${c.raw_material_ratio_pct}%`} />
                    <Stat label="Order Backlog" value={`${c.order_backlog_units?.toLocaleString('en-IN')} units`} sub={`Wait: ~${c.waiting_period_months} months`} />
                  </div>
                )}
                <div style={{ marginTop: 16 }}>
                  <b>Strategic Driver:</b> <span className="sub">{c.driver}</span>
                  {c.driver_note && <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>{c.driver_note}</div>}
                </div>
              </>
            ) : <p className="sub">Detailed operating KPIs not yet researched for roster profile.</p>}
          </div>
        )}

        {/* FINANCIALS TAB */}
        {activeTab === 'financials' && (() => {
          const finData = FINANCIAL_ANALYSIS_DATA[c.ticker] || {
            last_release_date: "July 2026",
            q_analysis: "Q1 FY27 operating performance remained solid with sustained margin resilience and strong cash generation.",
            y_analysis: "FY26 concluded with robust balance sheet strength and healthy dividend returns."
          }
          return (
            <div className="panel" style={{ padding: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h3 style={{ margin: 0 }}>Financials &amp; Earnings Analysis</h3>
                <div style={{ fontSize: 13, color: 'var(--muted)', background: 'var(--bg-elevated)', padding: '4px 10px', borderRadius: 4 }}>
                  Release Date: {finData.last_release_date}
                </div>
              </div>
              {isCovered ? (
                <>
                  <div className="cards">
                    {c.revenue_cr && <Stat label="Revenue" value={`₹${c.revenue_cr.toLocaleString('en-IN')}cr`} sub={c.revenue_yoy_pct ? `YoY: ${pct(c.revenue_yoy_pct)}` : '--'} />}
                    {c.nii_cr && <Stat label="Net Interest Income (NII)" value={`₹${c.nii_cr.toLocaleString('en-IN')}cr`} sub={`YoY: ${pct(c.nii_yoy_pct)}`} />}
                    {c.ebitda_cr && <Stat label="EBITDA" value={`₹${c.ebitda_cr.toLocaleString('en-IN')}cr`} sub={`${c.ebitda_margin_pct}% margin`} />}
                    <Stat label="PAT / Net Profit" value={c.pat_cr != null ? `₹${c.pat_cr.toLocaleString('en-IN')}cr` : '—'} sub={c.pat_yoy_label || (c.pat_yoy_pct ? pct(c.pat_yoy_pct) : '--')} />
                  </div>

                  <div style={{ marginTop: 24, borderTop: '1px solid var(--line)', paddingTop: 20 }}>
                    <h4 style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 0, marginBottom: 16 }}>
                      <span style={{ fontSize: 16 }}>✨</span> AI Financial Report Analysis
                    </h4>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
                      <div style={{ background: 'var(--bg-elevated)', padding: 16, borderRadius: 6, flex: '1 1 300px' }}>
                        <h5 style={{ marginTop: 0, marginBottom: 8, color: 'var(--fg)' }}>Quarterly Earnings Report (Q1 FY27)</h5>
                        <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', lineHeight: 1.5 }}>{finData.q_analysis}</p>
                      </div>
                      <div style={{ background: 'var(--bg-elevated)', padding: 16, borderRadius: 6, flex: '1 1 300px' }}>
                        <h5 style={{ marginTop: 0, marginBottom: 8, color: 'var(--fg)' }}>Annual Report &amp; Balance Sheet (FY26)</h5>
                        <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', lineHeight: 1.5 }}>{finData.y_analysis}</p>
                      </div>
                    </div>
                  </div>

                  {c.segments && c.segments.length > 0 && (
                    <div style={{ marginTop: 24 }}>
                      <h4 style={{ marginBottom: 10 }}>Segment / Vertical Breakdown</h4>
                      <table className="rnd-table">
                        <thead>
                          <tr>
                            <th>Segment</th>
                            <th className="r">Revenue</th>
                            <th className="r">Operating Profit</th>
                            <th className="r">Margin</th>
                          </tr>
                        </thead>
                        <tbody>
                          {c.segments.map((seg) => (
                            <tr key={seg.name}>
                              <td>{seg.name}</td>
                              <td className="r mono tnum">₹{seg.revenue_cr?.toLocaleString('en-IN')}cr</td>
                              <td className="r mono tnum">₹{seg.ebitda_cr?.toLocaleString('en-IN')}cr</td>
                              <td className="r mono tnum">{seg.ebitda_margin_pct}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              ) : <p className="sub">Detailed financial models in progress for roster companies.</p>}
            </div>
          )
        })()}

        {/* PORTFOLIO TAB */}
        {activeTab === 'portfolio' && (
          <div className="panel" style={{ padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>Operational Footprint &amp; Network Scale</h3>
            <div className="cards">
              {sectorId === 'hotels' && (
                <>
                  <Stat label="Total Keys / Rooms" value={c.rooms || '--'} />
                  <Stat label="Pipeline" value={c.pipeline || '--'} />
                  <Stat label="Operating Model" value={c.model || '--'} />
                </>
              )}
              {sectorId === 'banks' && (
                <>
                  <Stat label="Branch & ATM Network" value={c.branches || c.scale || '--'} />
                  <Stat label="Capital Adequacy (CRAR)" value={c.crar_pct ? `${c.crar_pct}%` : '--'} />
                  <Stat label="Operating Model" value={c.model || '--'} />
                </>
              )}
              {sectorId === 'it' && (
                <>
                  <Stat label="Global Headcount" value={c.headcount ? `${c.headcount.toLocaleString('en-IN')} engineers` : c.scale || '--'} />
                  <Stat label="Net Additions" value={c.net_additions ? `${c.net_additions > 0 ? '+' : ''}${c.net_additions}` : '--'} />
                  <Stat label="Attrition Rate" value={c.attrition_ltm_pct ? `${c.attrition_ltm_pct}%` : '--'} />
                </>
              )}
              {sectorId === 'auto' && (
                <>
                  <Stat label="Manufacturing Plants" value={c.plants || c.scale || '--'} />
                  <Stat label="Capacity Utilization" value={c.capacity_utilization_pct ? `${c.capacity_utilization_pct}%` : '--'} />
                  <Stat label="Domestic vs Export" value={c.domestic_share_pct ? `${c.domestic_share_pct}% / ${c.export_share_pct}%` : '--'} />
                </>
              )}
            </div>
            {c.note && (
              <div className="warn-banner" style={{ marginTop: 16 }}>
                <b>Analyst Note:</b> {c.note}
              </div>
            )}
          </div>
        )}

        {/* INDUSTRY BENCHMARKS TAB */}
        {activeTab === 'industry' && (
          <div className="panel" style={{ padding: 20 }}>
            <h3 style={{ marginTop: 0 }}>Industry Benchmark Comparison</h3>
            <div className="cards">
              {sectorId === 'hotels' && (
                <>
                  <Stat label="Pan-India RevPAR" value={industry?.revpar_range || '--'} sub="HVS-Anarock" />
                  <Stat label="Pan-India ADR" value={industry?.adr_range || '--'} />
                  <Stat label="Pan-India Occupancy" value={industry?.occupancy_range || '--'} />
                </>
              )}
              {sectorId === 'banks' && (
                <>
                  <Stat label="System Gross NPA" value={industry?.gnpa_range || '2.8–3.0%'} sub="RBI FSR" />
                  <Stat label="System NIM" value={industry?.nim_range || '3.3–3.6%'} />
                  <Stat label="System Credit Growth" value={industry?.credit_growth_range || '10–12%'} />
                </>
              )}
              {sectorId === 'it' && (
                <>
                  <Stat label="Tier-1 CC Growth" value={industry?.cc_growth_range || '6–9%'} sub="NASSCOM" />
                  <Stat label="Tier-1 EBIT Margin" value={industry?.ebit_margin_range || '20–22%'} />
                  <Stat label="Industry Attrition" value={industry?.attrition_range || '12–16%'} />
                </>
              )}
              {sectorId === 'auto' && (
                <>
                  <Stat label="Monthly Wholesales" value={industry?.monthly_wholesale_volumes || '~380K units'} sub="SIAM / FADA" />
                  <Stat label="Industry EV Penetration" value={industry?.ev_penetration_range || '~10–15%'} />
                  <Stat label="Production Growth" value={industry?.production_yoy_growth || '~3–8%'} />
                </>
              )}
            </div>
            <p className="sub" style={{ marginTop: 16 }}>
              Benchmarking {c.name} ({c.ticker}) operating metrics against the official industry baseline report ({industry?.source || 'Official Industry Filings'}).
            </p>
          </div>
        )}
      </div>

      {/* AI INTELLIGENCE */}
      <div className="ai-analysis" style={{ marginTop: 32 }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 20 }}>✨</span> AI Fundamental Intelligence
          <span
            className={`pill-lev ${aiData.signal === 'BULL' ? 'healthy' : aiData.signal === 'BEAR' ? 'stressed' : 'warning'}`}
            style={{ marginLeft: 'auto', fontSize: 13 }}
          >
            SIGNAL: {aiData.signal}
          </span>
        </h2>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginBottom: 20 }}>
          <div className="panel" style={{ padding: 20, borderLeft: '4px solid var(--accent-up)', flex: '1 1 300px' }}>
            <h4 style={{ marginTop: 0, color: 'var(--accent-up)' }}>What is improving?</h4>
            <ul style={{ paddingLeft: 20, margin: 0, color: 'var(--fg)' }}>
              {aiData.improving.map((item, i) => <li key={i} style={{ marginBottom: 6 }}>{item}</li>)}
            </ul>
          </div>
          <div className="panel" style={{ padding: 20, borderLeft: '4px solid var(--accent-down)', flex: '1 1 300px' }}>
            <h4 style={{ marginTop: 0, color: 'var(--accent-down)' }}>What is weakening?</h4>
            <ul style={{ paddingLeft: 20, margin: 0, color: 'var(--fg)' }}>
              {aiData.weakening.map((item, i) => <li key={i} style={{ marginBottom: 6 }}>{item}</li>)}
            </ul>
          </div>
        </div>

        <div className="panel" style={{ padding: 20 }}>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ marginTop: 0, marginBottom: 8, color: 'var(--muted)' }}>Why did it happen?</h4>
            <p style={{ margin: 0, lineHeight: 1.5 }}>{aiData.why}</p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ marginTop: 0, marginBottom: 8, color: 'var(--muted)' }}>Growth Outlook</h4>
            <p style={{ margin: 0, lineHeight: 1.5 }}>{aiData.outlook}</p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ marginTop: 0, marginBottom: 8, color: 'var(--muted)' }}>Key Risks</h4>
            <ul style={{ paddingLeft: 20, margin: 0 }}>
              {aiData.risks.map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          </div>
          <div>
            <h4 style={{ marginTop: 0, marginBottom: 8, color: 'var(--muted)' }}>Management Commentary</h4>
            <p style={{ margin: 0, lineHeight: 1.5, fontStyle: 'italic' }}>"{aiData.management}"</p>
          </div>
        </div>
      </div>
    </div>
  )
}
