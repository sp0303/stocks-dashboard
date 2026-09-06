"""Portfolio viewer endpoints - read-only dashboard with manual sync."""
from fastapi import APIRouter, HTTPException
from datetime import datetime
import logging

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clients/{client_id}", tags=["portfolio-viewer"])


@router.post("/{client_id}/sync-portfolio")
async def sync_portfolio_data(client_id: str):
    """Manual sync - fetch latest holdings, trades, margins from Kite MCP.

    Called when user clicks "Fetch Latest Data" button.
    Returns updated portfolio data.
    """
    try:
        from app.store import get_store
        from app.services import kite

        store = get_store()

        # Fetch from Kite MCP (user already authorized)
        try:
            holdings = kite.get_holdings_from_mcp()
            margins = kite.get_margins_from_mcp()
            trades = kite.get_trades_from_mcp()
            profile = kite.get_profile_from_mcp()
        except Exception as e:
            log.error(f"MCP fetch error: {e}")
            raise HTTPException(status_code=503, detail=f"Could not fetch data from Kite: {str(e)}")

        # Calculate portfolio metrics
        total_value = sum(
            h.get("last_price", 0) * h.get("quantity", 0)
            for h in (holdings or [])
        )
        total_cost = sum(
            h.get("average_price", 0) * h.get("quantity", 0)
            for h in (holdings or [])
        )
        total_pnl = sum(h.get("pnl", 0) for h in (holdings or []))

        portfolio_data = {
            "client_id": client_id,
            "profile": profile,
            "holdings": holdings or [],
            "margins": margins,
            "trades": trades or [],
            "summary": {
                "total_holdings": len(holdings or []),
                "total_value": total_value,
                "total_cost": total_cost,
                "total_pnl": total_pnl,
                "pnl_percent": (total_pnl / total_cost * 100) if total_cost > 0 else 0,
            },
            "synced_at": datetime.now().isoformat(),
        }

        # Save to database for future quick access
        await store.save_portfolio_snapshot(client_id, portfolio_data)

        return {
            "data": portfolio_data,
            "message": f"✓ Portfolio synced. {len(holdings or [])} holdings, {len(trades or [])} trades."
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/{client_id}/portfolio")
async def get_portfolio(client_id: str):
    """Get latest portfolio data (from cache, no API call).

    Returns: Holdings, trades, margins, summary, last sync time.
    User must click "Fetch Latest Data" to update.
    """
    try:
        from app.store import get_store

        store = get_store()

        # Get cached portfolio data
        portfolio = await store.get_portfolio_snapshot(client_id)

        if not portfolio:
            return {
                "data": None,
                "message": "No data yet. Click 'Fetch Latest Data' to sync."
            }

        return {
            "data": portfolio,
            "message": f"Last synced: {portfolio.get('synced_at')}"
        }

    except Exception as e:
        log.error(f"Portfolio fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
