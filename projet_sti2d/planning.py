"""Compatibility facade for planning modules.

This file re-exports planning classes and helpers so existing imports
(`from planning import PlanningTab`) keep working after modularization.
"""

from planning_common import (
    JOURS_SEMAINE,
    _darken_hex,
    _expand_comp_refs_for_pb,
    _parse_hhmm,
    _seance_sort_key,
    _slot_duration_hours,
    _truncate_text_px,
    compute_competency_usage,
)
from planning_dialogs import SeanceDialog, SequenceDialog, WeekDetailDialog
from planning_tab import PlanningTab

__all__ = [
    "JOURS_SEMAINE",
    "compute_competency_usage",
    "_expand_comp_refs_for_pb",
    "_parse_hhmm",
    "_slot_duration_hours",
    "_seance_sort_key",
    "_darken_hex",
    "_truncate_text_px",
    "SeanceDialog",
    "WeekDetailDialog",
    "SequenceDialog",
    "PlanningTab",
]
