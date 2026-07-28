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
    confidence: float  # 1.0 if RoBERTa article score, 0.5 if AvgTone fallback
    used_article_text: bool


def score_events_sentiment(
    events: Sequence[Any],
    cached_articles: dict[str, Any],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[EventSentimentResult]:
    """Calculate sentiment score in [-1.0, 1.0] for each sampled event using RoBERTa or AvgTone fallback."""
    pipe = _get_sentiment_pipeline()
    results: list[EventSentimentResult] = []

    # Separate events into article text scoring vs AvgTone fallback
    text_events: list[tuple[int, int, str, str]] = []  # (index, event_id, url, text)

    for idx, event in enumerate(events):
        url = event.source_url
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
