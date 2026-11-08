"""Initial schema baseline (Pure PostgreSQL 16, 8 schemas, 40 tables)

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-22 22:00:00

"""
from pathlib import Path
from alembic import op
import sqlalchemy as sa

revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Read and apply 0001_initial_schema.sql if tables do not exist
    sql_path = Path(__file__).parent.parent / "0001_initial_schema.sql"
    if sql_path.exists():
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()
        op.execute(sql)


def downgrade() -> None:
    # Drop schemas cascade
    for s in ['ops', 'orb', 'research', 'portfolio', 'market', 'ledger', 'auth', 'core']:
        op.execute(f"DROP SCHEMA IF EXISTS {s} CASCADE;")
