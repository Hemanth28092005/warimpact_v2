"""Mathematical scoring engine for Bilateral Aggression Score computation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


QUAD_CLASS_SIGNED: dict[int, float] = {
    1: 0.5,   # Verbal Cooperation
    2: 1.0,   # Material Cooperation
    3: -0.5,  # Verbal Conflict
    4: -1.0,  # Material Conflict
}


@dataclass(frozen=True)
class EventScoringInput:
    global_event_id: int
    quad_class: int | None
    goldstein_scale: float | None
    avg_tone: float | None
    num_mentions: int | None
    num_sources: int | None
    num_articles: int | None


def compute_event_severity(
    avg_tone: float | None,
    goldstein_scale: float | None,
    quad_class: int | None,
) -> float:
    """Compute per-event severity (valence) bounded in [-1.0, +1.0].

    +1.0 represents maximum cooperation, -1.0 represents maximum hostility.
    """
    tone_val = float(avg_tone) if avg_tone is not None else 0.0
    tone_norm = max(-1.0, min(1.0, tone_val / 10.0))

    goldstein_val = float(goldstein_scale) if goldstein_scale is not None else 0.0
    goldstein_norm = max(-1.0, min(1.0, goldstein_val / 10.0))

    quad_val = quad_class if quad_class is not None else 0
    quad_signed = QUAD_CLASS_SIGNED.get(quad_val, 0.0)

    severity = (0.4 * tone_norm) + (0.4 * goldstein_norm) + (0.2 * quad_signed)
    return max(-1.0, min(1.0, severity))


def compute_importance_weight(
    num_mentions: int | None,
    num_sources: int | None,
    num_articles: int | None,
) -> float:
    """Compute per-event importance (significance weight) using log-scaled volume metrics."""
    m = max(0, num_mentions or 1)
    s = max(0, num_sources or 1)
    a = max(0, num_articles or 1)

    weight = (0.5 * math.log1p(m)) + (0.3 * math.log1p(s)) + (0.2 * math.log1p(a))
    return max(0.1, weight)


def compute_pair_aggression_score(events: Sequence[EventScoringInput]) -> float:
    """Compute pair aggression score bounded in [0.0, 100.0] from a list of bilateral events.

    Rescaling Formula:
        weighted_severity = SUM(event_severity * importance_weight) / SUM(importance_weight)
        aggression_score = 50.0 * (1.0 - weighted_severity)

    Direction Matching CII Convention:
        - Maximum Cooperation (weighted_severity = +1.0) -> aggression_score = 0.0
        - Neutral (weighted_severity = 0.0) -> aggression_score = 50.0
        - Maximum Hostility (weighted_severity = -1.0) -> aggression_score = 100.0
    """
    if not events:
        return 50.0

    total_weighted_severity = 0.0
    total_weight = 0.0

    for ev in events:
        severity = compute_event_severity(ev.avg_tone, ev.goldstein_scale, ev.quad_class)
        weight = compute_importance_weight(ev.num_mentions, ev.num_sources, ev.num_articles)

        total_weighted_severity += severity * weight
        total_weight += weight

    if total_weight <= 0.0:
        return 50.0

    weighted_severity = total_weighted_severity / total_weight
    # Rescale from [-1.0, +1.0] severity to [0.0, 100.0] aggression score (higher = more hostile)
    raw_score = 50.0 * (1.0 - weighted_severity)
    return max(0.0, min(100.0, round(raw_score, 2)))
