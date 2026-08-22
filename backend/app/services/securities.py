"""Security master — symbol -> sector / market-cap / asset class.

A curated fallback map (SEBI-style sectors), the same approach as the reference project.
Yahoo's free tier doesn't reliably expose sector, so we classify locally and default
unknown symbols to "Unclassified" rather than failing. Extend freely.
"""
from __future__ import annotations

# sector, cap
_LARGE_MID = {
    # --- reference-project large/mid caps (subset that appears in the tradebooks) ---
    "HDFCLIFE": ("Financial Services", "Large Cap"),
    "NUVAMA": ("Financial Services", "Mid Cap"),
    "UJJIVANSFB": ("Financial Services", "Mid Cap"),
    "INTELLECT": ("Information Technology", "Mid Cap"),
    "RATEGAIN": ("Information Technology", "Mid Cap"),
    "HAL": ("Capital Goods", "Large Cap"),
    "APOLLOHOSP": ("Healthcare / Pharma", "Large Cap"),
    "INDHOTEL": ("Consumer Services", "Large Cap"),
    "AUBANK": ("Financial Services", "Mid Cap"),
    # --- classified for these tradebooks ---
    "AARTIPHARM": ("Healthcare / Pharma", "Mid Cap"),
    "AARTIDRUGS": ("Healthcare / Pharma", "Small Cap"),
    "VENUSREM": ("Healthcare / Pharma", "Small Cap"),
    "VENUSPIPES": ("Capital Goods", "Small Cap"),
    "CARYSIL": ("Consumer Durables", "Small Cap"),
    "CARTRADE": ("Consumer Services", "Small Cap"),
    "GPIL": ("Metals & Mining", "Small Cap"),
    "3BBLACKBIO": ("Healthcare / Pharma", "Small Cap"),
    "ABCAPITAL": ("Financial Services", "Large Cap"),
    "ARVSMART": ("Realty", "Small Cap"),
    "BBOX": ("Information Technology", "Mid Cap"),
    "CCL": ("FMCG", "Small Cap"),
    "CONCORDBIO": ("Healthcare / Pharma", "Mid Cap"),
    "CYIENTDLM": ("Capital Goods", "Small Cap"),
    "DYNAMATECH": ("Capital Goods", "Small Cap"),
    "EFCIL": ("Realty", "Small Cap"),
    "FEDFINA": ("Financial Services", "Small Cap"),
    "GANDHAR": ("Energy / Oil & Gas", "Small Cap"),
    "GRWRHITECH": ("Chemicals", "Small Cap"),
    "HBLENGINE": ("Capital Goods", "Small Cap"),
    "HCG": ("Healthcare / Pharma", "Small Cap"),
    "HPL": ("Capital Goods", "Small Cap"),
    "IEX": ("Financial Services", "Mid Cap"),
    "INNOVACAP": ("Healthcare / Pharma", "Small Cap"),
    "JKIL": ("Infrastructure", "Small Cap"),
    "JMFINANCIL": ("Financial Services", "Mid Cap"),
    "JSLL": ("Metals & Mining", "Small Cap"),
    "JUBLPHARMA": ("Healthcare / Pharma", "Mid Cap"),
    "KSHINTL": ("Capital Goods", "Small Cap"),
    "MAITHANALL": ("Metals & Mining", "Small Cap"),
    "MANYAVAR": ("Consumer Services", "Mid Cap"),
    "METROBRAND": ("Consumer Services", "Mid Cap"),
    "NDTV": ("Media", "Small Cap"),
    "NDTV-RE": ("Media", "Small Cap"),  # rights entitlement, same sector as parent
    "POKARNA": ("Consumer Durables", "Small Cap"),
    "RKFORGE": ("Capital Goods", "Mid Cap"),
    "SAKAR": ("Healthcare / Pharma", "Small Cap"),
    "SAMHI": ("Consumer Services", "Small Cap"),
    "SENORES": ("Healthcare / Pharma", "Small Cap"),
    "SJS": ("Automobile", "Small Cap"),
    "STLTECH": ("Telecommunication", "Small Cap"),
    "TDPOWERSYS": ("Capital Goods", "Mid Cap"),
    "THANGAMAYL": ("Consumer Services", "Small Cap"),
    "TIMETECHNO": ("Capital Goods", "Small Cap"),
    "TMCV": ("Automobile", "Large Cap"),
    "TMPV": ("Automobile", "Large Cap"),
    "VIMTALABS": ("Healthcare / Pharma", "Small Cap"),
    "VIYASH": ("Healthcare / Pharma", "Small Cap"),
    "SBCL": ("Capital Goods", "Small Cap"),  # Shivalik Bimetal Controls — bimetal/trimetal strips
    "SHRIGANG": ("FMCG", "Small Cap"),  # Shri Gang Industries & Allied Products — edible oil + IMFL
    "JSL": ("Metals & Mining", "Mid Cap"),
    "PAYTM": ("Financial Services", "Mid Cap"),
    "JAYNECOIND": ("Metals & Mining", "Small Cap"),
}

# Non-equity asset classes
_ASSET_CLASS_OVERRIDE = {
    "NIFTYBEES": "ETF",
    "NDTV-RE": "OTHER",   # rights entitlement
}
_ETF_SECTOR = {"NIFTYBEES": ("Index / ETF", "ETF")}


# Broader NIFTY-100 / common large-&-mid-cap reference map (SEBI-style sectors).
# Lets watchlist symbols (INFY, RELIANCE, …) classify even if they aren't in a tradebook.
_REFERENCE = {
    "RELIANCE": ("Energy / Oil & Gas", "Large Cap"),
    "TCS": ("Information Technology", "Large Cap"),
    "HDFCBANK": ("Financial Services", "Large Cap"),
    "ICICIBANK": ("Financial Services", "Large Cap"),
    "INFY": ("Information Technology", "Large Cap"),
    "BHARTIARTL": ("Telecommunication", "Large Cap"),
    "ITC": ("FMCG", "Large Cap"),
    "SBIN": ("Financial Services", "Large Cap"),
    "LT": ("Capital Goods", "Large Cap"),
    "AXISBANK": ("Financial Services", "Large Cap"),
    "KOTAKBANK": ("Financial Services", "Large Cap"),
    "TATAMOTORS": ("Automobile", "Large Cap"),
    "TATASTEEL": ("Metals & Mining", "Large Cap"),
    "WIPRO": ("Information Technology", "Large Cap"),
    "HCLTECH": ("Information Technology", "Large Cap"),
    "SUNPHARMA": ("Healthcare / Pharma", "Large Cap"),
    "BAJFINANCE": ("Financial Services", "Large Cap"),
    "BAJAJFINSV": ("Financial Services", "Large Cap"),
    "ULTRACEMCO": ("Cement & Building Materials", "Large Cap"),
    "HINDUNILVR": ("FMCG", "Large Cap"),
    "NESTLEIND": ("FMCG", "Large Cap"),
    "TITAN": ("Consumer Durables", "Large Cap"),
    "ASIANPAINT": ("Consumer Durables", "Large Cap"),
    "MARUTI": ("Automobile", "Large Cap"),
    "POWERGRID": ("Power / Utilities", "Large Cap"),
    "NTPC": ("Power / Utilities", "Large Cap"),
    "ONGC": ("Energy / Oil & Gas", "Large Cap"),
    "COALINDIA": ("Energy / Oil & Gas", "Large Cap"),
    "BPCL": ("Energy / Oil & Gas", "Large Cap"),
    "IOC": ("Energy / Oil & Gas", "Large Cap"),
    "ADANIENT": ("Capital Goods", "Large Cap"),
    "ADANIPORTS": ("Infrastructure", "Large Cap"),
    "ADANIGREEN": ("Power / Utilities", "Large Cap"),
    "VEDL": ("Metals & Mining", "Large Cap"),
    "HINDALCO": ("Metals & Mining", "Large Cap"),
    "JSWSTEEL": ("Metals & Mining", "Large Cap"),
    "GRASIM": ("Cement & Building Materials", "Large Cap"),
    "DRREDDY": ("Healthcare / Pharma", "Large Cap"),
    "CIPLA": ("Healthcare / Pharma", "Large Cap"),
    "DIVISLAB": ("Healthcare / Pharma", "Large Cap"),
    "EICHERMOT": ("Automobile", "Large Cap"),
    "HEROMOTOCO": ("Automobile", "Large Cap"),
    "TECHM": ("Information Technology", "Large Cap"),
    "LTIM": ("Information Technology", "Large Cap"),
    "MPHASIS": ("Information Technology", "Mid Cap"),
    "PERSISTENT": ("Information Technology", "Mid Cap"),
    "COFORGE": ("Information Technology", "Mid Cap"),
    "SBILIFE": ("Financial Services", "Large Cap"),
    "ICICIPRULI": ("Financial Services", "Large Cap"),
    "SHRIRAMFIN": ("Financial Services", "Large Cap"),
    "CHOLAFIN": ("Financial Services", "Mid Cap"),
    "MUTHOOTFIN": ("Financial Services", "Large Cap"),
    "INDHOTEL": ("Consumer Services", "Large Cap"),
    "HAVELLS": ("Consumer Durables", "Large Cap"),
    "VOLTAS": ("Consumer Durables", "Large Cap"),
    "TATACONSUM": ("FMCG", "Large Cap"),
    "GODREJCP": ("FMCG", "Large Cap"),
    "DABUR": ("FMCG", "Large Cap"),
    "MARICO": ("FMCG", "Large Cap"),
    "PIDILITIND": ("Chemicals", "Large Cap"),
    "SIEMENS": ("Capital Goods", "Large Cap"),
    "ABB": ("Capital Goods", "Large Cap"),
    "DLF": ("Realty", "Large Cap"),
    "GAIL": ("Energy / Oil & Gas", "Large Cap"),
    "PNB": ("Financial Services", "Large Cap"),
    "BANKBARODA": ("Financial Services", "Large Cap"),
    "INDUSINDBK": ("Financial Services", "Large Cap"),
    "TATAPOWER": ("Power / Utilities", "Large Cap"),
    "ZOMATO": ("Consumer Services", "Large Cap"),
    "DMART": ("Consumer Services", "Large Cap"),
    "PAYTM": ("Financial Services", "Mid Cap"),
    "IRCTC": ("Consumer Services", "Mid Cap"),
    "TVSMOTOR": ("Automobile", "Large Cap"),
    "BAJAJHLDNG": ("Financial Services", "Large Cap"),
}


def classify(symbol: str) -> dict:
    symbol = symbol.upper()
    asset_class = _ASSET_CLASS_OVERRIDE.get(symbol, "EQUITY")
    if symbol in _ETF_SECTOR:
        sector, cap = _ETF_SECTOR[symbol]
    elif symbol in _LARGE_MID:
        sector, cap = _LARGE_MID[symbol]
    else:
        sector, cap = _REFERENCE.get(symbol, ("Unclassified", "—"))
    return {"symbol": symbol, "sector": sector, "cap": cap, "asset_class": asset_class}
