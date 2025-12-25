#!/usr/bin/env python3
"""
Test suite for pricing_api module

Tests LiteLLM pricing API integration, caching, and fallback behavior.
"""

import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import URLError

from token_audit.pricing_api import PricingAPI, LITELLM_PRICING_URL


class TestPricingAPICacheLayer:
    """Tests for cache layer methods (task-108.3.2)"""

    @pytest.fixture
    def temp_cache_file(self, tmp_path: Path) -> Path:
        """Create a temporary cache file path."""
        return tmp_path / ".token-audit" / "pricing-cache.json"

    @pytest.fixture
    def api_with_temp_cache(self, temp_cache_file: Path) -> PricingAPI:
        """Create PricingAPI with temporary cache location."""
        return PricingAPI(cache_file=temp_cache_file, enabled=False)

    def test_load_cache_creates_directory(self, temp_cache_file: Path) -> None:
        """Test that save_cache creates parent directory if missing."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        api._pricing_data = {"test-model": {"input_cost_per_token": 0.00001}}
        api._fetched_at = datetime.now(timezone.utc)
        api._expires_at = api._fetched_at + timedelta(hours=24)

        result = api._save_cache()

        assert result is True
        assert temp_cache_file.parent.exists()
        assert temp_cache_file.exists()

    def test_save_cache_format(self, temp_cache_file: Path) -> None:
        """Test cache file has correct format (ttl_hours, source, data key)."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False, cache_ttl_hours=48)
        api._pricing_data = {"model-a": {"input_cost_per_token": 0.000001}}
        api._fetched_at = datetime.now(timezone.utc)
        api._expires_at = api._fetched_at + timedelta(hours=48)

        api._save_cache()

        with open(temp_cache_file) as f:
            cache_data = json.load(f)

        assert "fetched_at" in cache_data
        assert "ttl_hours" in cache_data
        assert cache_data["ttl_hours"] == 48
        assert "expires_at" in cache_data
        assert "source" in cache_data
        assert cache_data["source"] == "litellm"
        assert "model_count" in cache_data
        assert cache_data["model_count"] == 1
        assert "data" in cache_data
        assert "model-a" in cache_data["data"]

    def test_load_cache_reads_new_format(self, temp_cache_file: Path) -> None:
        """Test loading cache with new format (data key)."""
        temp_cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "fetched_at": "2025-12-11T10:00:00+00:00",
            "ttl_hours": 24,
            "expires_at": "2025-12-12T10:00:00+00:00",
            "source": "litellm",
            "model_count": 1,
            "data": {"test-model": {"input_cost_per_token": 0.00001}},
        }
        with open(temp_cache_file, "w") as f:
            json.dump(cache_data, f)

        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        result = api._load_cache()

        assert result is True
        assert api._pricing_data is not None
        assert "test-model" in api._pricing_data
        assert api._fetched_at is not None
        assert api._expires_at is not None

    def test_load_cache_backwards_compatible(self, temp_cache_file: Path) -> None:
        """Test loading cache with old format (pricing_data key)."""
        temp_cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {
            "fetched_at": "2025-12-11T10:00:00+00:00",
            "expires_at": "2025-12-12T10:00:00+00:00",
            "model_count": 1,
            "pricing_data": {"old-model": {"input_cost_per_token": 0.00002}},
        }
        with open(temp_cache_file, "w") as f:
            json.dump(cache_data, f)

        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        result = api._load_cache()

        assert result is True
        assert api._pricing_data is not None
        assert "old-model" in api._pricing_data

    def test_load_cache_nonexistent_file(self, api_with_temp_cache: PricingAPI) -> None:
        """Test loading cache when file doesn't exist."""
        result = api_with_temp_cache._load_cache()
        assert result is False

    def test_load_cache_corrupt_json(self, temp_cache_file: Path) -> None:
        """Test loading cache with corrupt JSON."""
        temp_cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_cache_file, "w") as f:
            f.write("not valid json {{{")

        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        result = api._load_cache()

        assert result is False

    def test_load_cache_empty_data(self, temp_cache_file: Path) -> None:
        """Test loading cache with null/empty data."""
        temp_cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_data = {"fetched_at": "2025-12-11T10:00:00+00:00", "data": None}
        with open(temp_cache_file, "w") as f:
            json.dump(cache_data, f)

        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        result = api._load_cache()

        # Should return False because data is None
        assert result is False

    def test_is_cache_valid_not_expired(self, temp_cache_file: Path) -> None:
        """Test cache validity when not expired."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        api._expires_at = datetime.now(timezone.utc) + timedelta(hours=12)

        assert api._is_cache_valid() is True

    def test_is_cache_valid_expired(self, temp_cache_file: Path) -> None:
        """Test cache validity when expired."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        api._expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        assert api._is_cache_valid() is False

    def test_is_cache_valid_no_expiry(self, temp_cache_file: Path) -> None:
        """Test cache validity when no expiry set."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        api._expires_at = None

        assert api._is_cache_valid() is False

    def test_is_cache_valid_timezone_naive(self, temp_cache_file: Path) -> None:
        """Test cache validity handles timezone-naive datetime."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        # Naive datetime (no timezone) - should be treated as UTC
        api._expires_at = datetime.now() + timedelta(hours=12)

        # Should not raise, should handle gracefully
        result = api._is_cache_valid()
        assert isinstance(result, bool)

    def test_clear_cache_removes_file(self, temp_cache_file: Path) -> None:
        """Test clear_cache removes cache file."""
        temp_cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_cache_file, "w") as f:
            json.dump({"data": {}}, f)

        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        api._pricing_data = {"model": {}}
        api._fetched_at = datetime.now(timezone.utc)
        api._source = "cache"

        result = api.clear_cache()

        assert result is True
        assert not temp_cache_file.exists()
        assert api._pricing_data is None
        assert api._fetched_at is None
        assert api._source == "none"

    def test_clear_cache_nonexistent_file(self, api_with_temp_cache: PricingAPI) -> None:
        """Test clear_cache when file doesn't exist."""
        result = api_with_temp_cache.clear_cache()
        assert result is False


class TestPricingAPIProperties:
    """Tests for PricingAPI properties"""

    @pytest.fixture
    def temp_cache_file(self, tmp_path: Path) -> Path:
        return tmp_path / "pricing-cache.json"

    def test_source_property_none(self, temp_cache_file: Path) -> None:
        """Test source is 'none' initially."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        assert api.source == "none"

    def test_freshness_property_unknown(self, temp_cache_file: Path) -> None:
        """Test freshness is 'unknown' initially."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        assert api.freshness == "unknown"

    def test_model_count_zero_when_no_data(self, temp_cache_file: Path) -> None:
        """Test model_count is 0 when no data."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        assert api.model_count == 0

    def test_expires_in_none_when_no_expiry(self, temp_cache_file: Path) -> None:
        """Test expires_in is None when no expiry set."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        assert api.expires_in is None

    def test_expires_in_positive(self, temp_cache_file: Path) -> None:
        """Test expires_in returns positive timedelta."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        api._expires_at = datetime.now(timezone.utc) + timedelta(hours=5)

        expires_in = api.expires_in
        assert expires_in is not None
        assert expires_in.total_seconds() > 0

    def test_expires_in_zero_when_expired(self, temp_cache_file: Path) -> None:
        """Test expires_in returns zero timedelta when expired."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        api._expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        expires_in = api.expires_in
        assert expires_in is not None
        assert expires_in.total_seconds() == 0


class TestPricingAPIModelLookup:
    """Tests for model pricing lookup"""

    @pytest.fixture
    def api_with_data(self, tmp_path: Path) -> PricingAPI:
        """Create API with mock pricing data."""
        api = PricingAPI(cache_file=tmp_path / "cache.json", enabled=False)
        api._pricing_data = {
            "claude-opus-4-5-20251101": {
                "input_cost_per_token": 0.000005,
                "output_cost_per_token": 0.000025,
                "cache_creation_input_token_cost": 0.00000625,
                "cache_read_input_token_cost": 0.0000005,
            },
            "anthropic/claude-sonnet-4-5-20250929": {
                "input_cost_per_token": 0.000003,
                "output_cost_per_token": 0.000015,
            },
        }
        api._source = "cache"
        return api

    def test_get_pricing_direct_match(self, api_with_data: PricingAPI) -> None:
        """Test getting pricing with direct model name match."""
        pricing = api_with_data.get_pricing("claude-opus-4-5-20251101")

        assert pricing is not None
        assert pricing["input"] == 5.0  # $5/1M tokens
        assert pricing["output"] == 25.0  # $25/1M tokens
        assert pricing["cache_create"] == 6.25
        assert pricing["cache_read"] == 0.5

    def test_get_pricing_with_provider_prefix(self, api_with_data: PricingAPI) -> None:
        """Test finding model with provider prefix."""
        pricing = api_with_data.get_pricing("claude-sonnet-4-5-20250929")

        assert pricing is not None
        assert pricing["input"] == 3.0

    def test_get_pricing_unknown_model(self, api_with_data: PricingAPI) -> None:
        """Test getting pricing for unknown model."""
        pricing = api_with_data.get_pricing("unknown-model-xyz")

        assert pricing is None

    def test_list_models(self, api_with_data: PricingAPI) -> None:
        """Test listing available models."""
        models = api_with_data.list_models()

        assert len(models) == 2
        assert "claude-opus-4-5-20251101" in models


class TestPricingAPIRefresh:
    """Tests for API refresh functionality"""

    @pytest.fixture
    def temp_cache_file(self, tmp_path: Path) -> Path:
        return tmp_path / "cache.json"

    def test_refresh_when_disabled(self, temp_cache_file: Path) -> None:
        """Test refresh returns False when API is disabled."""
        api = PricingAPI(cache_file=temp_cache_file, enabled=False)
        result = api.refresh()

        assert result is False

    @patch("token_audit.pricing_api.urlopen")
    def test_refresh_success(self, mock_urlopen: MagicMock, temp_cache_file: Path) -> None:
        """Test successful refresh from API."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"test-model": {"input_cost_per_token": 0.00001}}
        ).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        api = PricingAPI(cache_file=temp_cache_file, enabled=True)
        result = api.refresh()

        assert result is True
        assert api.source == "api"
        assert api.model_count == 1
        assert temp_cache_file.exists()

    @patch("token_audit.pricing_api.urlopen")
    def test_refresh_network_error(self, mock_urlopen: MagicMock, temp_cache_file: Path) -> None:
        """Test refresh handles network error gracefully."""
        mock_urlopen.side_effect = URLError("Network unreachable")

        api = PricingAPI(cache_file=temp_cache_file, enabled=True)
        result = api.refresh()

        assert result is False


class TestPricingAPIIntegration:
    """Integration tests (may require network)"""

    @pytest.fixture
    def temp_cache_file(self, tmp_path: Path) -> Path:
        return tmp_path / "cache.json"

    @pytest.mark.network
    def test_fetch_real_pricing_data(self, temp_cache_file: Path) -> None:
        """Test fetching real pricing data from LiteLLM.

        Mark with @pytest.mark.network to skip in CI without network.
        """
        api = PricingAPI(cache_file=temp_cache_file, enabled=True)
        pricing = api.get_pricing("claude-opus-4-5-20251101")

        # Should have fetched data
        assert api.model_count > 100  # LiteLLM has many models
        assert pricing is not None
        assert pricing["input"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
