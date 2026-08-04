"""Unit tests for Phase 4 Cascade / Cross-Stream Correlation system."""

from __future__ import annotations

from datetime import date, timedelta
import pytest

from models.cascade.adjacency import CountryAdjacencyGraph, REST_COUNTRIES_PHYSICAL_BORDERS
from models.cascade.spike import DEFAULT_K
from models.cascade.detector import CascadePairResult


def test_country_adjacency_graph_edges() -> None:
    graph = CountryAdjacencyGraph()
    graph.add_edge("USA", "CAN", edge_type="border")
    graph.add_edge("USA", "MEX", edge_type="border")
    graph.add_edge("USA", "GBR", edge_type="event_link")

    usa_neighbors = graph.neighbors("USA")
    assert "CAN" in usa_neighbors
    assert "MEX" in usa_neighbors
    assert "GBR" in usa_neighbors
    assert len(usa_neighbors) == 3

    assert ("CAN", "USA") in graph.border_edges or ("USA", "CAN") in graph.border_edges
    assert ("GBR", "USA") in graph.event_link_edges or ("USA", "GBR") in graph.event_link_edges


def test_rest_countries_physical_borders_citation() -> None:
    assert "USA" in REST_COUNTRIES_PHYSICAL_BORDERS
    assert "CAN" in REST_COUNTRIES_PHYSICAL_BORDERS["USA"]
    assert "MEX" in REST_COUNTRIES_PHYSICAL_BORDERS["USA"]
    assert "UKR" in REST_COUNTRIES_PHYSICAL_BORDERS
    assert "RUS" in REST_COUNTRIES_PHYSICAL_BORDERS["UKR"]


def test_cascade_pair_result_schema() -> None:
    res = CascadePairResult(
        source_country="YEM",
        target_country="SAU",
        contagion_score=0.5,
        co_spike_count=5,
        source_spike_count=10,
        window_days=7,
        analysis_start_date=date(2025, 7, 28),
        analysis_end_date=date(2026, 7, 31),
    )
    assert res.source_country == "YEM"
    assert res.target_country == "SAU"
    assert res.contagion_score == 0.5
    assert res.co_spike_count == 5
    assert res.source_spike_count == 10
    assert res.window_days == 7
