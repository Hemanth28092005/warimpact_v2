from models.sentiment.article_fetcher import CachedArticle, SampledEvent
from models.sentiment.scorer import (
    _roberta_outputs_to_score,
    _tone_to_sentiment,
    score_events_sentiment,
)


def test_tone_to_sentiment_mapping() -> None:
    assert _tone_to_sentiment(0.0) == 0.0
    assert _tone_to_sentiment(-10.0) == -1.0
    assert _tone_to_sentiment(10.0) == 1.0
    assert _tone_to_sentiment(-5.0) == -0.5
    assert _tone_to_sentiment(None) == 0.0


def test_roberta_outputs_to_score_transformation() -> None:
    # High positive, low negative
    pos_outputs = [
        {"label": "negative", "score": 0.05},
        {"label": "neutral", "score": 0.15},
        {"label": "positive", "score": 0.80},
    ]
    assert _roberta_outputs_to_score(pos_outputs) == 0.75

    # High negative, low positive
    neg_outputs = [
        {"label": "negative", "score": 0.90},
        {"label": "neutral", "score": 0.05},
        {"label": "positive", "score": 0.05},
    ]
    assert _roberta_outputs_to_score(neg_outputs) == -0.85


def test_score_events_sentiment_falls_back_to_avgtone_on_dead_url() -> None:
    event = SampledEvent(
        global_event_id=101,
        event_date="2026-07-27",
        country_code="USA",
        quad_class=4,
        goldstein_scale=-7.0,
        avg_tone=-6.0,
        num_mentions=10,
        source_url="https://example.com/dead",
    )
    cached_articles = {
        "https://example.com/dead": CachedArticle(
            source_url="https://example.com/dead",
            fetch_status="dead",
            article_text=None,
            text_length=0,
        )
    }

    results = score_events_sentiment([event], cached_articles)

    assert len(results) == 1
    res = results[0]
    assert res.global_event_id == 101
    assert res.used_article_text is False
    assert res.confidence == 0.5
    assert res.sentiment_score == -0.6
