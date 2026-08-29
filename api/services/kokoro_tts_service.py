"""Kokoro TTS service for S.A.G.E.

Synthesizes high-fidelity speech from text using local Kokoro-82M model.
Runs inference in a background thread via asyncio.to_thread to keep the
FastAPI event loop non-blocking.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("sage_tts")

DEFAULT_VOICE = os.getenv("KOKORO_VOICE", "af_heart").strip() or "af_heart"
DEFAULT_SPEED = float(os.getenv("KOKORO_SPEED", "1.0"))

_pipeline = None
_pipeline_lock = asyncio.Lock()


def get_kokoro_pipeline():
    """Lazy singleton loader for the Kokoro KPipeline."""
    global _pipeline
    if _pipeline is None:
        logger.info("Initializing Kokoro KPipeline singleton (hexgrad/Kokoro-82M)...")
        from kokoro import KPipeline
        _pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
        logger.info("Kokoro KPipeline loaded successfully.")
    return _pipeline


def clean_text_for_tts(raw_text: str) -> str:
    """Strip markdown formatting, headers, tables, bullets and code symbols for natural speech."""
    if not raw_text:
        return ""

    text = raw_text

    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Remove markdown tables (lines starting and ending with |)
    lines = []
    for line in text.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("|") and trimmed.endswith("|"):
            # If it's a separator line like |---|---|, skip
            if re.match(r"^\|[\s\-:]+\|$", trimmed):
                continue
            # Convert row cells into a spoken sentence: e.g. "Metric: Value"
            cells = [c.strip() for c in trimmed.split("|")[1:-1] if c.strip()]
            if len(cells) >= 2:
                lines.append(f"{cells[0]}: {cells[1]}.")
            elif cells:
                lines.append(cells[0] + ".")
        else:
            lines.append(line)
    text = "\n".join(lines)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Remove markdown links: [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Remove markdown headers: ### Header -> Header
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)

    # Remove bold / italic markers: **bold**, *italic*, __bold__
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)

    # Remove bullet markers: - item, * item, > quote
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)

    # Remove emojis and special tactical symbols
    text = re.sub(r"[🔴🟢🟡⚓🤖✦📺◍🛡️🛢️🚢🌐⚡⚠️•—⇄→]", " ", text)

    # Replace multiple hyphens/underscores/slashes with spaces
    text = re.sub(r"[-_]{2,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Limit to reasonable length (~2500 chars) to prevent extreme TTS wait times
    if len(text) > 2500:
        # Truncate at last sentence end before 2500 chars
        truncated = text[:2500]
        last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
        if last_period > 1000:
            text = truncated[: last_period + 1]
        else:
            text = truncated + "."

    return text


def _synthesize_sync(cleaned_text: str, voice: str, speed: float) -> bytes:
    """Synchronous CPU inference function run inside asyncio.to_thread."""
    import numpy as np
    import soundfile as sf

    pipeline = get_kokoro_pipeline()
    audio_chunks = []

    generator = pipeline(cleaned_text, voice=voice, speed=speed, split_pattern=r"\n+")
    for _, _, audio in generator:
        if audio is not None and len(audio) > 0:
            audio_chunks.append(audio)

    if not audio_chunks:
        raise RuntimeError("Kokoro synthesis generated empty audio stream.")

    full_audio = np.concatenate(audio_chunks)
    buffer = io.BytesIO()
    sf.write(buffer, full_audio, 24000, format="WAV")
    return buffer.getvalue()


async def synthesize_speech(
    text: str,
    voice: Optional[str] = None,
    speed: Optional[float] = None,
) -> bytes:
    """Synthesize clean speech audio WAV bytes asynchronously."""
    cleaned = clean_text_for_tts(text)
    if not cleaned:
        raise ValueError("Cannot synthesize speech from empty or whitespace-only text.")

    v = voice or os.getenv("KOKORO_VOICE", DEFAULT_VOICE)
    s = speed if speed is not None else float(os.getenv("KOKORO_SPEED", str(DEFAULT_SPEED)))

    async with _pipeline_lock:
        wav_bytes = await asyncio.to_thread(_synthesize_sync, cleaned, v, s)

    return wav_bytes
