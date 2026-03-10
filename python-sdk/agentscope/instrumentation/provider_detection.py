from __future__ import annotations

from urllib.parse import urlparse


def detect_provider(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except Exception:
        return None

    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    netloc = (parsed.netloc or "").lower()

    if hostname == "api.openai.com" or "openai.com" in hostname:
        return "openai"
    if hostname == "api.anthropic.com" or "anthropic.com" in hostname:
        return "anthropic"
    if hostname == "api.groq.com" or "groq.com" in hostname:
        return "groq"
    if hostname == "api.together.xyz" or "together.xyz" in hostname:
        return "together"
    if hostname == "localhost" and port == 11434:
        return "ollama"
    if "localhost:11434" in netloc:
        return "ollama"
    return None
