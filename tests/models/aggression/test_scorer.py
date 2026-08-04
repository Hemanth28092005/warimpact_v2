"""Unit tests for Bilateral Aggression Score mathematical engine."""

from __future__ import annotations

import math
import pytest

from models.aggression.scorer import (
    compute_event_severity,
    compute_importance_weight,
    compute_pair_aggression_score,
    EventScoringInput,
)


def test_event_severity_bounds_and_direction() -> None:
    # 1. Maximum Material Cooperation (quad_class=2, positive tone, positive goldstein)
    coop_severity = compute_event_severity(avg_tone=10.0, goldstein_scale=10.0, quad_class=2)
    assert coop_severity == 1.0  # Maximum cooperation (+1.0)

    # 2. Maximum Material Conflict (quad_class=4, negative tone, negative goldstein)
    conflict_severity = compute_event_severity(avg_tone=-10.0, goldstein_scale=-10.0, quad_class=4)
    assert conflict_severity == -1.0  # Maximum hostility (-1.0)

    # 3. Neutral Event
    neutral_severity = compute_event_severity(avg_tone=0.0, goldstein_scale=0.0, quad_class=None)
    assert neutral_severity == 0.0

    # 4. Clipping out of bounds
    extreme_severity = compute_event_severity(avg_tone=50.0, goldstein_scale=20.0, quad_class=2)
    assert extreme_severity == 1.0


def test_importance_weight_scaling() -> None:
    w_small = compute_importance_weight(num_mentions=1, num_sources=1, num_articles=1)
    w_large = compute_importance_weight(num_mentions=100, num_sources=50, num_articles=100)

    assert w_small > 0.0
    assert w_large > w_small


def test_pair_aggression_score_direction_and_bounds() -> None:
    # Known Hostile Events (military strikes / material conflict)
    hostile_events = [
        EventScoringInput(
            global_event_id=1,
            quad_class=4,
            goldstein_scale=-10.0,
            avg_tone=-8.5,
            num_mentions=20,
            num_sources=5,
            num_articles=20,
        ),
        EventScoringInput(
            global_event_id=2,
            quad_class=3,
            goldstein_scale=-7.0,
            avg_tone=-6.0,
            num_mentions=15,
            num_sources=3,
            num_articles=15,
        ),
    ]

    # Known Allied Events (cooperation / trade treaties)
    allied_events = [
        EventScoringInput(
            global_event_id=3,
            quad_class=2,
            goldstein_scale=8.0,
            avg_tone=6.0,
            num_mentions=25,
            num_sources=5,
            num_articles=25,
        ),
        EventScoringInput(
            global_event_id=4,
            quad_class=1,
            goldstein_scale=5.0,
            avg_tone=4.0,
            num_mentions=10,
            num_sources=2,
            num_articles=10,
        ),
    ]

    hostile_score = compute_pair_aggression_score(hostile_events)
    allied_score = compute_pair_aggression_score(allied_events)

    # Higher score = more hostile
    assert 0.0 <= hostile_score <= 100.0
    assert 0.0 <= allied_score <= 100.0
    assert hostile_score > 70.0
    assert allied_score < 30.0
    assert hostile_score > allied_score
