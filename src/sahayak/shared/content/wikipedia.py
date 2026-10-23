"""Wikipedia grounding client supporting search, summary retrieval, and Redis caching."""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

import httpx

from sahayak.core.cache import Cache
from sahayak.core.security import create_safe_http_client
from sahayak.shared.content.sanitizer import (
    sanitize_grounding_content,
    wrap_grounding_text,
)
from sahayak.shared.llm.ports import ProviderUnavailableError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "Sahayak/1.0 (https://github.com/prateekg7/sahayak; contact@example.com)"
DEFAULT_CACHE_TTL_DAYS = 7


@dataclass(frozen=True)
class WikipediaPage:
    """Retrieved Wikipedia page metadata and extracted summary."""

    title: str
    extract: str
    url: str
    description: str | None = None
    is_disambiguation: bool = False
    language: str = "en"


@dataclass(frozen=True)
class GroundingResult:
    """Sanitized and formatted grounding material ready for prompt injection."""

    title: str
    raw_extract: str
    sanitized_text: str
    wrapped_prompt_text: str
    url: str
    is_disambiguation: bool = False
    language: str = "en"


class WikipediaClient:
    """Async Wikimedia REST client for topic grounding and fact retrieval."""

    def __init__(
        self,
        *,
        cache: Cache | None = None,
        http_client: httpx.AsyncClient | None = None,
        user_agent: str | None = None,
        ttl_days: int = DEFAULT_CACHE_TTL_DAYS,
    ) -> None:
        self._cache = cache
        self._http_client = http_client
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.ttl_days = ttl_days

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

    async def _send_get(
        self,
        url: str,
        host: str,
        timeout: float,
    ) -> httpx.Response:
        """Execute GET request with outbound host validation and timeout."""
        headers = self._headers()
        try:
            if self._http_client is not None:
                return await self._http_client.get(url, headers=headers, timeout=timeout)

            async with create_safe_http_client(allowed_hosts=[host], timeout=timeout) as client:
                return await client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                detail=f"Wikipedia request timed out after {timeout}s"
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderUnavailableError(detail=f"Wikipedia network error: {exc}") from exc

    async def search(
        self,
        query: str,
        *,
        language: str = "en",
        limit: int = 5,
        timeout: float = 5.0,
    ) -> list[str]:
        """Search Wikipedia titles via the opensearch API.

        Args:
            query: Search phrase or topic.
            language: Wikipedia language code (e.g. 'en', 'hi').
            limit: Maximum number of suggested titles to return.
            timeout: Request timeout in seconds.

        Returns:
            List of matching article titles.
        """
        host = f"{language}.wikipedia.org"
        encoded_query = urllib.parse.quote_plus(query.strip())
        url = (
            f"https://{host}/w/api.php?action=opensearch&search={encoded_query}"
            f"&limit={limit}&namespace=0&format=json"
        )

        response = await self._send_get(url, host=host, timeout=timeout)
        if response.status_code == 429:
            raise ProviderUnavailableError(detail="Wikipedia search rate limit exceeded")
        if response.is_server_error:
            raise ProviderUnavailableError(detail="Wikipedia search service error")
        if response.is_error:
            logger.warning(
                "Wikipedia search returned HTTP %s for query %s", response.status_code, query
            )
            return []

        try:
            data = response.json()
            if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
                return [str(title) for title in data[1]]
        except Exception as exc:
            logger.warning("Failed to parse Wikipedia search response: %s", exc)

        return []

    async def get_summary(
        self,
        title: str,
        *,
        language: str = "en",
        timeout: float = 5.0,
    ) -> WikipediaPage | None:
        """Fetch article summary via Wikimedia REST API, with Redis caching.

        Args:
            title: Exact or close article title.
            language: Wikipedia language code.
            timeout: Request timeout in seconds.

        Returns:
            WikipediaPage object if found, or None if the article does not exist.
        """
        normalized_title = title.strip()
        cache_key = f"wiki:summary:{language}:{normalized_title.lower()}"

        if self._cache is not None:
            try:
                cached_data = await self._cache.get_json(cache_key)
                if isinstance(cached_data, dict):
                    return WikipediaPage(
                        title=str(cached_data.get("title", "")),
                        extract=str(cached_data.get("extract", "")),
                        url=str(cached_data.get("url", "")),
                        description=cached_data.get("description"),
                        is_disambiguation=bool(cached_data.get("is_disambiguation", False)),
                        language=str(cached_data.get("language", language)),
                    )
            except Exception as exc:
                logger.warning("Redis cache read failed for %s: %s", cache_key, exc)

        host = f"{language}.wikipedia.org"
        quoted_title = urllib.parse.quote(normalized_title.replace(" ", "_"), safe="")
        url = f"https://{host}/api/rest_v1/page/summary/{quoted_title}"

        response = await self._send_get(url, host=host, timeout=timeout)

        if response.status_code == 404:
            return None
        if response.status_code == 429:
            raise ProviderUnavailableError(detail="Wikipedia rate limit exceeded")
        if response.is_server_error:
            raise ProviderUnavailableError(detail="Wikipedia service error")
        if response.is_error:
            logger.warning(
                "Wikipedia summary returned status %s for %s", response.status_code, title
            )
            return None

        try:
            data: dict[str, Any] = response.json()
        except Exception as exc:
            raise ProviderUnavailableError(detail=f"Invalid Wikipedia JSON: {exc}") from exc

        page_type = data.get("type", "standard")
        is_disambiguation = page_type == "disambiguation"
        extract = data.get("extract", "")
        description = data.get("description")
        desktop_url = (
            data.get("content_urls", {}).get("desktop", {}).get("page")
            or f"https://{host}/wiki/{quoted_title}"
        )
        resolved_title = data.get("title", normalized_title)

        page = WikipediaPage(
            title=resolved_title,
            extract=extract,
            url=desktop_url,
            description=description,
            is_disambiguation=is_disambiguation,
            language=language,
        )

        if self._cache is not None:
            try:
                ttl_seconds = self.ttl_days * 86400
                await self._cache.set_json(cache_key, asdict(page), ttl_seconds=ttl_seconds)
            except Exception as exc:
                logger.warning("Redis cache write failed for %s: %s", cache_key, exc)

        return page

    async def get_grounding(
        self,
        topic: str,
        *,
        language: str = "en",
        max_chars: int = 2000,
        timeout: float = 5.0,
    ) -> GroundingResult | None:
        """Resolve topic into sanitized, delimiter-wrapped grounding material.

        Handles direct lookup, disambiguation failover, and fallback search.

        Args:
            topic: Topic name or question subject.
            language: Wikipedia language code.
            max_chars: Max characters for inner grounding content.
            timeout: Per-request timeout.

        Returns:
            GroundingResult with clean source text, or None if topic not found.
        """
        page = await self.get_summary(topic, language=language, timeout=timeout)

        # If page not found or is a disambiguation page, search for closest matching article
        if page is None or page.is_disambiguation:
            candidates = await self.search(topic, language=language, limit=3, timeout=timeout)
            for candidate in candidates:
                is_same_disambig = (
                    candidate.lower() == topic.strip().lower()
                    and page is not None
                    and page.is_disambiguation
                )
                if is_same_disambig:
                    continue  # Skip identical disambiguation title
                cand_page = await self.get_summary(candidate, language=language, timeout=timeout)
                if cand_page is not None and not cand_page.is_disambiguation and cand_page.extract:
                    page = cand_page
                    break

        if page is None or not page.extract:
            return None

        sanitized = sanitize_grounding_content(page.extract, max_chars=max_chars)
        wrapped = wrap_grounding_text(page.extract, source_title=page.title, max_chars=max_chars)

        return GroundingResult(
            title=page.title,
            raw_extract=page.extract,
            sanitized_text=sanitized,
            wrapped_prompt_text=wrapped,
            url=page.url,
            is_disambiguation=page.is_disambiguation,
            language=language,
        )
