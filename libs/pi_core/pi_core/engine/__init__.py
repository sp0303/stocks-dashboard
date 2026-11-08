"""Engine components: FIFO, matching, corporate action adjustments, and segments."""

from pi_core.engine.corporate_actions import apply_corporate_actions
from pi_core.engine.fifo import FIFOEngine, EngineResult
from pi_core.engine.matching import match_trades_fifo
from pi_core.engine.segments import separate_segments

__all__ = [
    "apply_corporate_actions",
    "FIFOEngine",
    "EngineResult",
    "match_trades_fifo",
    "separate_segments",
]
