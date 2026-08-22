"""Unit tests verifying Indian government action actor detection and canonical action types."""

import pytest
from ingestion.dashboard.llm_filter import validate_headline_relevance


def test_official_government_actions_accepted():
    """Verify official Indian government decisions, orders, and policies are accepted."""
    # 1. Ministry decision
    is_rel, conf, reason, brief, val_src, brief_src, actor, act_type = validate_headline_relevance(
        "government_actions",
        headline="Ministry of External Affairs Signs Strategic Trade Agreement with UAE",
        url="https://mea.gov.in/press-releases/strategic-trade-agreement",
    )
    assert is_rel
    assert conf >= 0.70
    assert act_type in {"diplomatic", "administrative", "regulatory"}

    # 2. Cabinet order
    is_rel, conf, reason, brief, val_src, brief_src, actor, act_type = validate_headline_relevance(
        "government_actions",
        headline="Cabinet Approves New Financial Incentive Scheme for Semiconductor Manufacturing",
        url="https://pib.gov.in/pressrelease/semiconductor-incentive",
    )
    assert is_rel
    assert conf >= 0.70


def test_petitions_and_demands_rejected():
    """Verify headlines where government is merely petitioned or demanded to act are rejected."""
    # Case 1: Crash victims families demand report
    is_rel, conf, reason, brief, _, _, _, _ = validate_headline_relevance(
        "government_actions",
        headline="Train Accident Victims' Families Demand Government Release Probe Report",
        url="https://timesofindia.com/city/patna/families-demand-report",
    )
    assert not is_rel, "Demands directed at government must not be classified as government actions!"

    # Case 2: Opposition criticism
    is_rel, conf, reason, brief, _, _, _, _ = validate_headline_relevance(
        "government_actions",
        headline="Opposition Slams Government Over Inflation and Unemployment Figures",
        url="https://thehindu.com/news/national/opposition-slams-govt",
    )
    assert not is_rel, "Political criticism must not be classified as government actions!"

    # Case 3: Public petition
    is_rel, conf, reason, brief, _, _, _, _ = validate_headline_relevance(
        "government_actions",
        headline="Citizens Group Urges Centre to Halt Forest Land Allocation in Western Ghats",
        url="https://indianexpress.com/article/india/citizens-plea-centre",
    )
    assert not is_rel, "Petitions urging the centre must not be classified as government actions!"
