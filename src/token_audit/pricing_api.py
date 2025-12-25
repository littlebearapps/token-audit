"""
LiteLLM Pricing API Client

Fetches and caches model pricing from LiteLLM's public pricing JSON.
Provides automatic updates for model pricing without manual TOML maintenance.

Usage:
    api = PricingAPI()
    pricing = api.get_pricing("claude-opus-4-5-20251101")
    if pricing:
        print(f"Input: ${pricing['input']}/M tokens")
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/" "model_prices_and_context_window.json"
)

DEFAULT_CACHE_TTL_HOURS = 24
DEFAULT_TIMEOUT_SECONDS = 10


class PricingAPI:
    """Client for fetching dynamic model pricing from LiteLLM.

    Supports:
    - Fetching latest pricing from LiteLLM's GitHub repository
    - Local caching with configurable TTL
    - Graceful fallback to stale cache when API unavailable
    - Model name variant lookup (handles different naming conventions)

    Data Quality Integration:
    - `source` property indicates where pricing came from
    - `freshness` property indicates cache state

    Example:
        >>> api = PricingAPI()
        >>> pricing = api.get_pricing("claude-opus-4-5-20251101")
        >>> print(f"Source: {api.source}, Freshness: {api.freshness}")
    """

    def __init__(
        self,
        cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        cache_file: Optional[Path] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        enabled: bool = True,
    ):
        """Initialize pricing API client.

        Args:
            cache_ttl_hours: Hours before cache expires (default: 24)
            cache_file: Path to cache file (default: ~/.token-audit/pricing-cache.json)
            timeout_seconds: HTTP request timeout (default: 10)
            enabled: Whether to enable API fetching (default: True)
        """
        self.cache_ttl_hours = cache_ttl_hours
        self.cache_file = cache_file or (Path.home() / ".token-audit" / "pricing-cache.json")
        self.timeout_seconds = timeout_seconds
        self.enabled = enabled
        self._pricing_data: Optional[Dict[str, Any]] = None
        self._source: str = "none"
        self._fetched_at: Optional[datetime] = None
        self._expires_at: Optional[datetime] = None

    def get_pricing(self, model_name: str) -> Optional[Dict[str, float]]:
        """Get pricing for a model.

        Tries in order:
        1. Fresh API data (if enabled and cache expired)
        2. Valid cache
        3. Stale cache (if API fails)

        Args:
            model_name: Model identifier (e.g., 'claude-opus-4-5-20251101')

        Returns:
            Dict with 'input', 'output', 'cache_create', 'cache_read' prices
            (per million tokens), or None if model not found.
        """
        # Ensure pricing data is loaded
        if self._pricing_data is None:
            self._load_pricing()

        if self._pricing_data is None:
            return None

        # Look up model
        model_data = self._pricing_data.get(model_name)
        if not model_data:
            # Try alternate naming conventions
            model_data = self._find_model_variant(model_name)

        if not model_data:
            logger.debug(f"Model not found in pricing data: {model_name}")
            return None

        # Convert per-token to per-million-tokens
        return self._convert_pricing(model_data)

    def list_models(self) -> List[str]:
        """List all available model names with pricing.

        Returns:
            Sorted list of model identifiers.
        """
        if self._pricing_data is None:
            self._load_pricing()

        if self._pricing_data is None:
            return []

        return sorted(self._pricing_data.keys())

    def refresh(self) -> bool:
        """Force refresh pricing from API.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        if not self.enabled:
            logger.warning("Pricing API is disabled, cannot refresh")
            return False

        try:
            self._fetch_from_api()
            self._source = "api"
            self._save_cache()
            logger.info(f"Refreshed pricing data: {self.model_count} models")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh pricing: {e}")
            return False

    def _load_pricing(self) -> None:
        """Load pricing from cache or API."""
        # Check cache first
        if self._load_cache() and self._is_cache_valid():
            self._source = "cache"
            logger.debug(f"Loaded valid cache with {self.model_count} models")
            return

        # Try fetching from API
        if self.enabled:
            try:
                self._fetch_from_api()
                self._source = "api"
                self._save_cache()
                self._save_fallback()  # v0.9.1 (#53): Persistent fallback
                logger.info(f"Fetched pricing from API: {self.model_count} models")
                return
            except URLError as e:
                logger.warning(f"Network error fetching pricing: {e}")
            except Exception as e:
                logger.warning(f"Failed to fetch pricing from API: {e}")

        # v0.9.1 (#53): Try fallback file before stale cache
        if self._load_fallback():
            self._source = "fallback"
            logger.info(f"Using fallback pricing: {self.model_count} models")
            return

        # Fall back to stale cache
        if self._pricing_data is not None:
            self._source = "cache-stale"
            logger.info("Using stale cached pricing")
        else:
            logger.warning("No pricing data available (no cache, no fallback, API failed)")

    def _fetch_from_api(self) -> None:
        """Fetch pricing from LiteLLM API."""
        request = Request(
            LITELLM_PRICING_URL,
            headers={"User-Agent": "token-audit"},
        )

        with urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))

        self._pricing_data = data
        self._fetched_at = datetime.now(timezone.utc)
        self._expires_at = self._fetched_at + timedelta(hours=self.cache_ttl_hours)

    def _load_cache(self) -> bool:
        """Load pricing from cache file.

        Handles both old format (pricing_data key) and new format (data key)
        for backwards compatibility.

        Returns:
            True if cache was loaded successfully, False otherwise.
        """
        if not self.cache_file.exists():
            return False

        try:
            with open(self.cache_file) as f:
                cache_data = json.load(f)

            # Support both old format (pricing_data) and new format (data)
            self._pricing_data = cache_data.get("data") or cache_data.get("pricing_data")
            fetched_str = cache_data.get("fetched_at")
            expires_str = cache_data.get("expires_at")

            if fetched_str:
                self._fetched_at = datetime.fromisoformat(fetched_str)
            if expires_str:
                self._expires_at = datetime.fromisoformat(expires_str)

            logger.debug(f"Loaded cache from {self.cache_file}")
            return self._pricing_data is not None
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning(f"Failed to load cache: {e}")
            return False

    def _save_cache(self) -> bool:
        """Save pricing to cache file.

        Cache format:
            {
                "fetched_at": "2025-12-11T10:00:00+00:00",
                "ttl_hours": 24,
                "expires_at": "2025-12-12T10:00:00+00:00",
                "source": "litellm",
                "model_count": 342,
                "data": { ... }
            }

        Returns:
            True if cache was saved successfully, False otherwise.
        """
        try:
            # Ensure directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)

            cache_data = {
                "fetched_at": (self._fetched_at.isoformat() if self._fetched_at else None),
                "ttl_hours": self.cache_ttl_hours,
                "expires_at": (self._expires_at.isoformat() if self._expires_at else None),
                "source": "litellm",
                "model_count": len(self._pricing_data) if self._pricing_data else 0,
                "data": self._pricing_data,
            }

            with open(self.cache_file, "w") as f:
                json.dump(cache_data, f)

            logger.debug(f"Saved cache to {self.cache_file}")
            return True
        except OSError as e:
            logger.warning(f"Failed to save cache: {e}")
            return False

    def _save_fallback(self) -> bool:
        """Save pricing to persistent fallback file (no TTL).

        Fallback file is saved alongside cache but without expiration.
        Used when cache is stale and API is unavailable.

        Fallback file: ~/.token-audit/fallback-pricing.json

        Returns:
            True if fallback was saved successfully, False otherwise.
        """
        if self._pricing_data is None:
            return False

        fallback_file = self.cache_file.parent / "fallback-pricing.json"
        try:
            fallback_data = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "source": "litellm",
                "model_count": len(self._pricing_data) if self._pricing_data else 0,
                "data": self._pricing_data,
            }

            with open(fallback_file, "w") as f:
                json.dump(fallback_data, f)

            logger.debug(f"Saved fallback pricing to {fallback_file}")
            return True
        except OSError as e:
            logger.warning(f"Failed to save fallback pricing: {e}")
            return False

    def _load_fallback(self) -> bool:
        """Load pricing from persistent fallback file.

        Returns:
            True if fallback was loaded successfully, False otherwise.
        """
        fallback_file = self.cache_file.parent / "fallback-pricing.json"
        if not fallback_file.exists():
            return False

        try:
            with open(fallback_file) as f:
                fallback_data = json.load(f)

            self._pricing_data = fallback_data.get("data")
            logger.debug(f"Loaded fallback pricing from {fallback_file}")
            return self._pricing_data is not None
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.warning(f"Failed to load fallback pricing: {e}")
            return False

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid (not expired).

        Returns:
            True if cache is valid, False if expired or no expiry info.
        """
        if self._expires_at is None:
            return False

        now = datetime.now(timezone.utc)
        # Ensure expires_at is timezone-aware
        expires_at = self._expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        return now < expires_at

    def _convert_pricing(self, model_data: Dict[str, Any]) -> Dict[str, float]:
        """Convert LiteLLM per-token pricing to per-million-tokens.

        Args:
            model_data: Raw pricing data from LiteLLM.

        Returns:
            Dict with standardized pricing keys (per million tokens).
            Includes tiered pricing fields if available (v0.9.1 #54).
        """

        def to_per_million(per_token: Optional[float]) -> float:
            return (per_token or 0) * 1_000_000

        result = {
            "input": to_per_million(model_data.get("input_cost_per_token")),
            "output": to_per_million(model_data.get("output_cost_per_token")),
            "cache_create": to_per_million(model_data.get("cache_creation_input_token_cost")),
            "cache_read": to_per_million(model_data.get("cache_read_input_token_cost")),
        }

        # v0.9.1 (#54): Tiered pricing for Claude (200k) and Gemini (128k)
        tiered_fields = {
            "input_above_200k": "input_cost_per_token_above_200k_tokens",
            "output_above_200k": "output_cost_per_token_above_200k_tokens",
            "input_above_128k": "input_cost_per_token_above_128k_tokens",
            "output_above_128k": "output_cost_per_token_above_128k_tokens",
        }

        for key, litellm_key in tiered_fields.items():
            value = model_data.get(litellm_key)
            if value is not None:
                result[key] = to_per_million(value)

        return result

    def _find_model_variant(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Try to find model under alternate naming conventions.

        LiteLLM uses various naming patterns for models:
        - Direct name: claude-opus-4-5-20251101
        - Provider prefix: anthropic/claude-opus-4-5-20251101
        - Underscores vs hyphens: claude_opus_4_5_20251101

        Args:
            model_name: Original model name to search for.

        Returns:
            Model pricing data if found, None otherwise.
        """
        if self._pricing_data is None:
            return None

        # Try common prefixes/suffixes
        variants = [
            model_name,
            f"anthropic/{model_name}",
            f"openai/{model_name}",
            f"google/{model_name}",
            f"vertex_ai/{model_name}",
            model_name.replace("-", "_"),
            model_name.replace("_", "-"),
        ]

        # Also try without date suffix for some models
        # e.g., claude-opus-4-5-20251101 -> claude-opus-4-5
        if len(model_name) > 8 and model_name[-8:].isdigit():
            base_name = model_name[:-9]  # Remove -YYYYMMDD
            variants.extend(
                [
                    base_name,
                    f"anthropic/{base_name}",
                ]
            )

        for variant in variants:
            if variant in self._pricing_data:
                logger.debug(f"Found model variant: {model_name} -> {variant}")
                result: Dict[str, Any] = self._pricing_data[variant]
                return result

        return None

    @property
    def source(self) -> str:
        """Return pricing source.

        Returns:
            - 'api': Fresh from LiteLLM API
            - 'cache': Valid cached data
            - 'fallback': Persistent fallback file (v0.9.1 #53)
            - 'cache-stale': Expired cache (last resort)
            - 'none': No pricing data available
        """
        return self._source

    @property
    def model_count(self) -> int:
        """Return number of models with pricing."""
        return len(self._pricing_data) if self._pricing_data else 0

    @property
    def freshness(self) -> str:
        """Return pricing freshness: 'fresh', 'cached', 'stale', 'unknown'.

        Returns:
            - 'fresh': Just fetched from API
            - 'cached': Valid cache
            - 'stale': Expired cache
            - 'unknown': No data
        """
        if self._source == "api":
            return "fresh"
        elif self._source == "cache":
            return "cached"
        elif self._source == "cache-stale":
            return "stale"
        return "unknown"

    @property
    def expires_in(self) -> Optional[timedelta]:
        """Return time until cache expires.

        Returns:
            timedelta until expiry, or None if not available.
        """
        if self._expires_at is None:
            return None

        now = datetime.now(timezone.utc)
        expires_at = self._expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        remaining = expires_at - now
        return remaining if remaining.total_seconds() > 0 else timedelta(0)

    @property
    def fetched_at(self) -> Optional[datetime]:
        """Return when pricing was last fetched."""
        return self._fetched_at

    def clear_cache(self) -> bool:
        """Clear the pricing cache file.

        Returns:
            True if cache was cleared, False if no cache existed.
        """
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
                logger.info(f"Cleared pricing cache: {self.cache_file}")
                # Reset in-memory state
                self._pricing_data = None
                self._fetched_at = None
                self._expires_at = None
                self._source = "none"
                return True
            except OSError as e:
                logger.warning(f"Failed to clear cache: {e}")
                return False
        return False
