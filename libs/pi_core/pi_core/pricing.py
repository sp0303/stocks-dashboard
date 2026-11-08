"""Pricing policy constants shared by the engine and the API (one definition, R5)."""

# A close older than this many calendar days is not carried forward: the position is
# unpriced and leaves both cost and value (R6) instead of being shown at a stale price.
MAX_PRICE_CARRY_DAYS = 10
