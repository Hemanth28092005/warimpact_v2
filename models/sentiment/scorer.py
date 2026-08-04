"""RoBERTa sentiment scorer with batching and GDELT AvgTone fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from ingestion.common.logger import get_logger

logger = get_logger(__name__)

MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"
DEFAULT_BATCH_SIZE = 64

_MODEL_PIPELINE: Any = None
_MODEL_LOAD_FAILED = False


def _get_sentiment_pipeline() -> Any:
    global _MODEL_PIPELINE, _MODEL_LOAD_FAILED
    if _MODEL_PIPELINE is not None or _MODEL_LOAD_FAILED:
        return _MODEL_PIPELINE

    try:
        from transformers import pipeline

        logger.info("loading_sentiment_model", extra={"model_name": MODEL_NAME})
        _MODEL_PIPELINE = pipeline(
            "text-classification",
            model=MODEL_NAME,
            top_k=None,
            truncation=True,
            max_length=512,
        )
        logger.info("sentiment_model_loaded_successfully")
    except Exception as exc:
        _MODEL_LOAD_FAILED = True
        logger.warning("sentiment_model_load_failed_using_fallback", extra={"error": str(exc)})
        _MODEL_PIPELINE = None

    return _MODEL_PIPELINE


@dataclass(frozen=True)
class EventSentimentResult:
    global_event_id: int
    source_url: str
    sentiment_score: float  # Bounded in [-1.0, 1.0]
    confidence: float  # 1.0 if RoBERTa article score, 0.65 if composite, 0.5 if AvgTone fallback
    used_article_text: bool
    country_code: str = ""


QUAD_CLASS_SIGNED: dict[int, float] = {
    1: 0.5,   # Verbal Cooperation
    2: 1.0,   # Material Cooperation
    3: -0.5,  # Verbal Conflict
    4: -1.0,  # Material Conflict
}


def compute_composite_historical_sentiment(
    avg_tone: float | None,
    goldstein_scale: float | None,
    quad_class: int | None,
) -> float:
    """Compute composite historical sentiment score bounded in [-1.0, 1.0] for backfill dates.

    Formula:
        composite_score = 0.4 * tone_norm + 0.4 * goldstein_norm + 0.2 * quad_class_signed
    """
    tone_val = float(avg_tone) if avg_tone is not None else 0.0
    tone_norm = max(-1.0, min(1.0, tone_val / 10.0))

    goldstein_val = float(goldstein_scale) if goldstein_scale is not None else 0.0
    goldstein_norm = max(-1.0, min(1.0, goldstein_val / 10.0))

    quad_val = quad_class if quad_class is not None else 0
    quad_signed = QUAD_CLASS_SIGNED.get(quad_val, 0.0)

    score = (0.4 * tone_norm) + (0.4 * goldstein_norm) + (0.2 * quad_signed)
    return max(-1.0, min(1.0, round(score, 4)))


def score_events_sentiment(
    events: Sequence[Any],
    cached_articles: dict[str, Any] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    is_historical_backfill: bool = False,
) -> list[EventSentimentResult]:
    """Calculate sentiment score in [-1.0, 1.0] for each sampled event.

    - If is_historical_backfill=True: uses composite historical formula with confidence=0.65.
    - If is_historical_backfill=False: uses real RoBERTa article scoring (confidence=1.0) or AvgTone fallback (confidence=0.5).
    """
    if cached_articles is None:
        cached_articles = {}

    results: list[EventSentimentResult] = []

    # Historical backfill branch: fast composite scoring (no article fetching required)
    if is_historical_backfill:
        for event in events:
            avg_tone = getattr(event, "avg_tone", None)
            goldstein_scale = getattr(event, "goldstein_scale", None)
            quad_class = getattr(event, "quad_class", None)
            country = getattr(event, "country_code", "")
            score = compute_composite_historical_sentiment(avg_tone, goldstein_scale, quad_class)
            results.append(
                EventSentimentResult(
                    global_event_id=event.global_event_id,
                    source_url=event.source_url,
                    sentiment_score=score,
                    confidence=0.65,  # Distinct tier for composite historical fallback
                    used_article_text=False,
                    country_code=country,
                )
            )
        return results

    # Separate events into article text scoring vs AvgTone fallback
    text_events: list[tuple[int, int, str, str]] = []  # (index, event_id, url, text)

    for idx, event in enumerate(events):
        url = event.source_url
        country = getattr(event, "country_code", "")
        article = cached_articles.get(url)
        if article and article.fetch_status == "success" and article.article_text:
            text_events.append((idx, event.global_event_id, url, article.article_text))
        else:
            # Fallback to AvgTone
            score = _tone_to_sentiment(getattr(event, "avg_tone", None))
            results.append(
                EventSentimentResult(
                    global_event_id=event.global_event_id,
                    source_url=url,
                    sentiment_score=score,
                    confidence=0.5,
                    used_article_text=False,
                    country_code=country,
                )
            )

    if not text_events:
        return results

    # Run RoBERTa batch inference if model is loaded
    if pipe is not None:
        texts = [item[3] for item in text_events]
        for start in range(0, len(texts), batch_size):
            batch_texts = texts[start : start + batch_size]
            batch_indices = text_events[start : start + batch_size]
            try:
                raw_outputs = pipe(batch_texts)
                for (b_idx, event_id, url, _), outputs in zip(batch_indices, raw_outputs, strict=True):
                    score = _roberta_outputs_to_score(outputs)
                    results.append(
                        EventSentimentResult(
                            global_event_id=event_id,
                            source_url=url,
                            sentiment_score=score,
                            confidence=1.0,
                            used_article_text=True,
                        )
                    )
            except Exception as exc:
                logger.warning("roberta_batch_inference_failed_falling_back", extra={"error": str(exc)})
                for b_idx, event_id, url, _ in batch_indices:
                    event_obj = events[b_idx]
                    score = _tone_to_sentiment(getattr(event_obj, "avg_tone", None))
                    results.append(
                        EventSentimentResult(
                            global_event_id=event_id,
                            source_url=url,
                            sentiment_score=score,
                            confidence=0.5,
                            used_article_text=False,
                        )
                    )
    else:
        # Pipeline model not available, fallback all to AvgTone
        for idx, event_id, url, _ in text_events:
            event_obj = events[idx]
            score = _tone_to_sentiment(getattr(event_obj, "avg_tone", None))
            results.append(
                EventSentimentResult(
                    global_event_id=event_id,
                    source_url=url,
                    sentiment_score=score,
                    confidence=0.5,
                    used_article_text=False,
                )
            )

    return results


def _roberta_outputs_to_score(scores_list: list[dict[str, Any]]) -> float:
    """Convert RoBERTa output label scores (negative/neutral/positive) into [-1.0, 1.0]."""
    pos_score = 0.0
    neg_score = 0.0
    for item in scores_list:
        label = item["label"].lower()
        score = item["score"]
        if "pos" in label or label == "label_2":
            pos_score = score
        elif "neg" in label or label == "label_0":
            neg_score = score
    diff = pos_score - neg_score
    return max(-1.0, min(1.0, round(diff, 4)))


def _tone_to_sentiment(avg_tone: float | None) -> float:
    """Convert GDELT AvgTone (typically -10 to +10) into [-1.0, 1.0]."""
    if avg_tone is None:
        return 0.0
    val = float(avg_tone) / 10.0
    return max(-1.0, min(1.0, round(val, 4)))
