import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_all_sectors_return_valid_data():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for sector in ["hotels", "banks", "it", "auto"]:
            res = await ac.get(f"/api/sectors/{sector}")
            assert res.status_code == 200, f"Failed for sector {sector}: {res.text}"
            data = res.json()["data"]
            assert data["sector"] == sector
            assert "industry" in data
            assert len(data["covered"]) == 8, f"Sector {sector} covered count is {len(data['covered'])}"
            assert len(data["roster"]) >= 8, f"Sector {sector} roster count is {len(data['roster'])}"

@pytest.mark.asyncio
async def test_hotels_backwards_compatibility():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/sectors/hotels")
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data["covered"]) == 8
        assert any(c["ticker"] == "INDHOTEL" for c in data["covered"])

@pytest.mark.asyncio
async def test_price_matrix_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for sector in ["hotels", "banks", "it", "auto"]:
            res = await ac.get(f"/api/sectors/{sector}/price-matrix")
            assert res.status_code == 200, f"Failed price-matrix for {sector}: {res.text}"
            data = res.json()["data"]
            assert len(data) >= 16

@pytest.mark.asyncio
async def test_unknown_sector_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/sectors/nonexistent")
        assert res.status_code == 404
