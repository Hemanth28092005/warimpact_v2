"""Country Adjacency Graph Builder for Phase 4 Cascade Correlation.

Nodes: 38 target in-scope countries.
Edges:
1. Physical Shared Borders:
   Sourced from REST Countries API v3.1 (https://restcountries.com/v3.1/all).
   Physical land borders between any of the 38 in-scope countries.

2. Bilateral Event Linkage:
   Sourced from `country_aggression_scores.event_count` (trailing 365-day window).
   Selects the top-N (default 5) highest bilateral event volume pairs per country.

Limitations & Analytical Disclaimers:
- Adjacency defines potential interaction channels, but correlation across edges does not imply causation.
- External macro shocks affecting neighboring regions simultaneously can produce co-spikes without real contagion.
"""

from __future__ import annotations

from typing import Any
from psycopg import AsyncConnection
from models.cii.inference import FSI_ANNUAL_BENCHMARKS

# In-scope countries list (38 countries)
IN_SCOPE_COUNTRIES = sorted(list(FSI_ANNUAL_BENCHMARKS.keys()))

# REST Countries API v3.1 Physical Land Borders (filtered to the 38 in-scope ISO-alpha3 codes)
# Source: REST Countries API v3.1 (https://restcountries.com)
REST_COUNTRIES_PHYSICAL_BORDERS: dict[str, list[str]] = {
    "AFG": ["CHN", "IND", "IRN", "PAK"],
    "ARG": ["BRA"],
    "ASM": [],  # Territory
    "AUS": [],  # Island nation
    "BRA": ["ARG", "COL", "VEN"],
    "CAN": ["USA"],
    "CHN": ["AFG", "IND", "PRK", "RUS"],
    "COL": ["BRA", "VEN"],
    "DEU": ["FRA", "POL"],
    "EGY": ["ISR", "SDN"],
    "ESP": ["FRA"],
    "FRA": ["DEU", "ESP", "ITA"],
    "GBR": [],  # Island nation
    "GRC": ["TUR"],
    "IND": ["AFG", "CHN", "PAK"],
    "IRN": ["AFG", "IRQ", "PAK", "TUR"],
    "IRQ": ["IRN", "SAU", "SYR", "TUR"],
    "ISR": ["EGY", "PSE", "SYR"],
    "ITA": ["FRA"],
    "JPN": [],  # Island nation
    "KOR": ["PRK"],
    "MEX": ["USA"],
    "NGA": [],
    "PAK": ["AFG", "CHN", "IND", "IRN"],
    "POL": ["DEU", "RUS", "UKR"],
    "PRK": ["CHN", "KOR", "RUS"],
    "PSE": ["ISR"],
    "RUS": ["CHN", "POL", "PRK", "UKR"],
    "SAU": ["IRQ", "YEM"],
    "SDN": ["EGY", "SSD"],
    "SOM": [],
    "SSD": ["SDN"],
    "SYR": ["IRQ", "ISR", "TUR"],
    "TUR": ["GRC", "IRN", "IRQ", "SYR"],
    "UKR": ["POL", "RUS"],
    "USA": ["CAN", "MEX"],
    "VEN": ["BRA", "COL"],
    "YEM": ["SAU"],
}


class CountryAdjacencyGraph:
    """Represents undirected country graph with border and event-linkage edges."""

    def __init__(self) -> None:
        self.nodes: set[str] = set(IN_SCOPE_COUNTRIES)
        self.adj: dict[str, set[str]] = {c: set() for c in IN_SCOPE_COUNTRIES}
        self.border_edges: set[tuple[str, str]] = set()
        self.event_link_edges: set[tuple[str, str]] = set()

    def add_edge(self, u: str, v: str, edge_type: str = "border") -> None:
        if u in self.nodes and v in self.nodes and u != v:
            self.adj[u].add(v)
            self.adj[v].add(u)
            edge = tuple(sorted([u, v]))
            if edge_type == "border":
                self.border_edges.add(edge)
            else:
                self.event_link_edges.add(edge)

    def neighbors(self, u: str) -> set[str]:
        return self.adj.get(u, set())


async def build_country_adjacency_graph(
    conn: AsyncConnection,
    top_n_event_links: int = 5,
) -> CountryAdjacencyGraph:
    """Build country adjacency graph incorporating REST Countries borders and GDELT aggression linkages.

    Args:
        conn: Async PostgreSQL connection.
        top_n_event_links: Number of top bilateral aggression event pairs per country.

    Returns:
        Populated CountryAdjacencyGraph instance.
    """
    graph = CountryAdjacencyGraph()

    # 1. Add physical border edges (REST Countries API v3.1)
    for c_code, borders in REST_COUNTRIES_PHYSICAL_BORDERS.items():
        for b_code in borders:
            graph.add_edge(c_code, b_code, edge_type="border")

    # 2. Add bilateral event volume linkage edges from country_aggression_scores
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT country_a, country_b, event_count
            FROM country_aggression_scores
            WHERE country_a = ANY(%s) AND country_b = ANY(%s)
            ORDER BY event_count DESC
            """,
            (IN_SCOPE_COUNTRIES, IN_SCOPE_COUNTRIES),
        )
        rows = await cur.fetchall()

    country_pair_counts: dict[str, list[tuple[str, int]]] = {c: [] for c in IN_SCOPE_COUNTRIES}
    for r in rows:
        c1, c2, count = r[0], r[1], int(r[2])
        if c1 in country_pair_counts and c2 in IN_SCOPE_COUNTRIES:
            country_pair_counts[c1].append((c2, count))
        if c2 in country_pair_counts and c1 in IN_SCOPE_COUNTRIES:
            country_pair_counts[c2].append((c1, count))

    for c_code, pairs in country_pair_counts.items():
        # Sort by event_count DESC and take top N
        sorted_pairs = sorted(pairs, key=lambda x: x[1], reverse=True)[:top_n_event_links]
        for neighbor, _ in sorted_pairs:
            graph.add_edge(c_code, neighbor, edge_type="event_link")

    return graph
