#!/usr/bin/env python3
"""
Test suite for pricing_config module

Tests pricing configuration loading, validation, and cost calculation.
"""

import pytest
from pathlib import Path
from token_audit.pricing_config import PricingConfig, load_pricing_config, get_model_cost


class TestPricingConfigLoading:
    """Tests for configuration file loading"""

    def test_load_default_config(self) -> None:
        """Test loading default token-audit.toml"""
        config = PricingConfig()
        assert config.loaded == True
        assert len(config.pricing_data) > 0

    def test_load_specific_path(self) -> None:
        """Test loading from specific path"""
        config_path = Path("token-audit.toml")
        config = PricingConfig(config_path)
        assert config.loaded == True

    def test_missing_config_falls_back_to_defaults(self) -> None:
        """Test that missing config file falls back to DEFAULT_PRICING (task-67)"""
        config = PricingConfig(Path("nonexistent.toml"))
        # Should load defaults, not fail
        assert config.loaded == True
        assert config._source == "defaults"


class TestModelPricingLookup:
    """Tests for model pricing retrieval"""

    def test_get_claude_pricing(self) -> None:
        """Test getting Claude model pricing"""
        config = PricingConfig()
        pricing = config.get_model_pricing("claude-sonnet-4-5-20250929")

        assert pricing is not None
        assert "input" in pricing
        assert "output" in pricing
        assert pricing["input"] == 3.0
        assert pricing["output"] == 15.0

    def test_get_openai_pricing(self) -> None:
        """Test getting OpenAI model pricing"""
        config = PricingConfig()
        pricing = config.get_model_pricing("gpt-4o")

        assert pricing is not None
        assert "input" in pricing
        assert pricing["output"] == 10.0

    def test_get_pricing_with_vendor(self) -> None:
        """Test getting pricing with specific vendor"""
        config = PricingConfig()
        pricing = config.get_model_pricing("gpt-4o", vendor="openai")

        assert pricing is not None
        assert pricing["input"] == 2.5

    def test_unknown_model(self) -> None:
        """Test unknown model returns None with warning"""
        config = PricingConfig()

        with pytest.warns(RuntimeWarning, match="No pricing configured"):
            pricing = config.get_model_pricing("unknown-model")

        assert pricing is None

    def test_cache_pricing_fields(self) -> None:
        """Test models with cache pricing"""
        config = PricingConfig()
        pricing = config.get_model_pricing("claude-sonnet-4-5-20250929")

        assert "cache_create" in pricing
        assert "cache_read" in pricing
        assert pricing["cache_create"] == 3.75
        assert pricing["cache_read"] == 0.30


class TestCostCalculation:
    """Tests for cost calculation"""

    def test_basic_cost_calculation(self) -> None:
        """Test basic input/output token cost"""
        # Use nonexistent path and disable API to test against DEFAULT_PRICING flat rates
        config = PricingConfig(Path("nonexistent.toml"), api_enabled=False)
        cost = config.calculate_cost(
            "claude-sonnet-4-5-20250929", input_tokens=1_000_000, output_tokens=1_000_000
        )

        # 1M input @ $3.0 + 1M output @ $15.0 = $18.0
        assert cost == 18.0

    def test_cost_with_cache(self) -> None:
        """Test cost calculation with cache tokens"""
        config = PricingConfig()
        cost = config.calculate_cost(
            "claude-sonnet-4-5-20250929",
            input_tokens=10_000,
            output_tokens=5_000,
            cache_read_tokens=50_000,
        )

        # 10K input @ $3.0/1M + 5K output @ $15.0/1M + 50K cache @ $0.30/1M
        # = 0.03 + 0.075 + 0.015 = 0.12
        assert cost == pytest.approx(0.12, rel=1e-4)

    def test_zero_tokens(self) -> None:
        """Test cost calculation with zero tokens"""
        config = PricingConfig()
        cost = config.calculate_cost("claude-sonnet-4-5-20250929")

        assert cost == 0.0

    def test_unknown_model_returns_zero(self) -> None:
        """Test unknown model returns zero cost"""
        config = PricingConfig()

        with pytest.warns(RuntimeWarning):
            cost = config.calculate_cost("unknown-model", input_tokens=10_000, output_tokens=5_000)

        assert cost == 0.0

    def test_model_without_cache_pricing(self) -> None:
        """Test model without cache pricing fields"""
        config = PricingConfig()

        # gpt-4o has cache_read but not cache_create
        cost = config.calculate_cost(
            "gpt-4o",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_created_tokens=100_000,
            cache_read_tokens=100_000,
        )

        # Should only include input, output, and cache_read
        # 1M @ $2.5 + 1M @ $10.0 + 100K @ $1.25/1M = 2.5 + 10.0 + 0.125
        assert cost == pytest.approx(12.625, rel=1e-4)


class TestModelListing:
    """Tests for listing available models"""

    def test_list_all_models(self) -> None:
        """Test listing all configured models"""
        config = PricingConfig()
        models = config.list_models()

        assert len(models) > 0
        assert "claude-sonnet-4-5-20250929" in models
        assert "gpt-4o" in models

    def test_list_claude_models(self) -> None:
        """Test listing Claude models only"""
        config = PricingConfig()
        models = config.list_models("claude")

        assert len(models) >= 3  # At least Opus, Sonnet, Haiku
        assert "claude-sonnet-4-5-20250929" in models
        assert "gpt-4o" not in models

    def test_list_openai_models(self) -> None:
        """Test listing OpenAI models only"""
        config = PricingConfig()
        models = config.list_models("openai")

        assert len(models) >= 5  # At least GPT-4o variants and O series
        assert "gpt-4o" in models
        assert "claude-sonnet-4-5-20250929" not in models

    def test_list_custom_models(self) -> None:
        """Test listing custom models (empty by default)"""
        config = PricingConfig()
        models = config.list_models("custom")

        # Should be empty list (no custom models configured)
        assert isinstance(models, list)


class TestValidation:
    """Tests for configuration validation"""

    def test_validate_valid_config(self) -> None:
        """Test validation of valid configuration"""
        config = PricingConfig()
        result = config.validate()

        assert result["valid"] == True
        assert len(result["errors"]) == 0

    def test_validate_checks_required_fields(self) -> None:
        """Test validation warns about missing required fields"""
        config = PricingConfig()
        result = config.validate()

        # All models should have input and output pricing
        # So no warnings about missing fields
        assert "input" not in str(result.get("warnings", []))


class TestConvenienceFunctions:
    """Tests for convenience functions"""

    def test_load_pricing_config(self) -> None:
        """Test convenience function for loading config"""
        config = load_pricing_config()

        assert config.loaded == True
        assert isinstance(config, PricingConfig)

    def test_get_model_cost(self) -> None:
        """Test convenience function for cost calculation"""
        cost = get_model_cost(
            "claude-sonnet-4-5-20250929", input_tokens=10_000, output_tokens=5_000
        )

        # 10K @ $3.0/1M + 5K @ $15.0/1M = 0.03 + 0.075 = 0.105
        assert cost == pytest.approx(0.105, rel=1e-4)


class TestMetadata:
    """Tests for metadata handling"""

    def test_metadata_loaded(self) -> None:
        """Test metadata is loaded from config"""
        config = PricingConfig()

        assert "currency" in config.metadata
        assert config.metadata["currency"] == "USD"

    def test_exchange_rates(self) -> None:
        """Test exchange rates in metadata"""
        config = PricingConfig()

        if "exchange_rates" in config.metadata:
            rates = config.metadata["exchange_rates"]
            assert "USD_to_AUD" in rates


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_model_name_case_sensitivity(self) -> None:
        """Test that model names are case-sensitive"""
        config = PricingConfig()

        # Correct case
        pricing1 = config.get_model_pricing("claude-sonnet-4-5-20250929")
        assert pricing1 is not None

        # Wrong case - should fail with warning
        with pytest.warns(RuntimeWarning):
            pricing2 = config.get_model_pricing("CLAUDE-SONNET-4-5-20250929")
        assert pricing2 is None

    def test_empty_vendor_namespace(self) -> None:
        """Test handling of empty vendor namespace"""
        config = PricingConfig()
        models = config.list_models("nonexistent-vendor")

        assert models == []

    def test_negative_tokens(self) -> None:
        """Test cost calculation with negative tokens (edge case)"""
        config = PricingConfig()

        # Negative tokens should still work (though invalid in practice)
        cost = config.calculate_cost(
            "claude-sonnet-4-5-20250929", input_tokens=-1000, output_tokens=5000
        )

        # Should calculate: -1000 * 3.0/1M + 5000 * 15.0/1M
        assert cost < 0.1


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for complete workflows"""

    def test_complete_workflow(self) -> None:
        """Test complete workflow: load → lookup → calculate"""
        # Load config
        config = load_pricing_config()

        # Validate
        validation = config.validate()
        assert validation["valid"] == True

        # List models
        models = config.list_models()
        assert len(models) > 0

        # Get pricing
        model = models[0]
        pricing = config.get_model_pricing(model)
        assert pricing is not None

        # Calculate cost
        cost = config.calculate_cost(model, input_tokens=1000, output_tokens=500)
        assert cost >= 0.0

    def test_all_configured_models_have_pricing(self) -> None:
        """Test that all configured models have valid pricing"""
        config = PricingConfig()

        for vendor, models in config.pricing_data.items():
            # Skip API configuration section (not pricing data)
            if vendor == "api":
                continue

            for model_name, pricing in models.items():
                # Each model should have at least input and output
                assert (
                    "input" in pricing or "output" in pricing
                ), f"{vendor}.{model_name} missing input/output pricing"

                # Prices should be numeric
                for key in ["input", "output", "cache_create", "cache_read"]:
                    if key in pricing:
                        assert isinstance(
                            pricing[key], (int, float)
                        ), f"{vendor}.{model_name}.{key} is not numeric"
                        assert pricing[key] >= 0, f"{vendor}.{model_name}.{key} is negative"


class TestDefaultPricingFallback:
    """Tests for DEFAULT_PRICING fallback when no config file exists (task-67)"""

    def test_source_attribute_file(self) -> None:
        """Test _source is 'file' when loaded from config file"""
        config = PricingConfig(Path("token-audit.toml"))
        assert config._source == "file"
        assert config.loaded == True

    def test_source_attribute_defaults(self) -> None:
        """Test _source is 'defaults' when using fallback"""
        config = PricingConfig(Path("definitely-does-not-exist.toml"))
        assert config._source == "defaults"
        assert config.loaded == True

    def test_default_pricing_has_claude_models(self) -> None:
        """Test DEFAULT_PRICING includes Claude models"""
        config = PricingConfig(Path("nonexistent.toml"))

        # Check Claude Opus 4.5
        opus_pricing = config.get_model_pricing("claude-opus-4-5-20251101")
        assert opus_pricing is not None
        assert "input" in opus_pricing
        assert "output" in opus_pricing
        assert opus_pricing["input"] > 0

        # Check Claude Sonnet 4.5
        sonnet_pricing = config.get_model_pricing("claude-sonnet-4-5-20250929")
        assert sonnet_pricing is not None

        # Check Claude Haiku 4.5
        haiku_pricing = config.get_model_pricing("claude-haiku-4-5-20251001")
        assert haiku_pricing is not None

    def test_default_pricing_has_openai_models(self) -> None:
        """Test DEFAULT_PRICING includes OpenAI/Codex models"""
        config = PricingConfig(Path("nonexistent.toml"))

        # Check GPT-5.1 Codex Max
        codex_max = config.get_model_pricing("gpt-5.1-codex-max")
        assert codex_max is not None
        assert "input" in codex_max
        assert "output" in codex_max

        # Check GPT-5.1
        gpt51 = config.get_model_pricing("gpt-5.1")
        assert gpt51 is not None

    def test_default_pricing_has_gemini_models(self) -> None:
        """Test DEFAULT_PRICING includes Gemini models"""
        config = PricingConfig(Path("nonexistent.toml"))

        # Check Gemini 2.5 Flash
        flash = config.get_model_pricing("gemini-2.5-flash")
        assert flash is not None
        assert "input" in flash
        assert "output" in flash

        # Check Gemini 2.5 Pro
        pro = config.get_model_pricing("gemini-2.5-pro")
        assert pro is not None

    def test_default_pricing_cost_calculation(self) -> None:
        """Test cost calculation works with DEFAULT_PRICING"""
        # Disable API pricing to test against DEFAULT_PRICING flat rates
        config = PricingConfig(Path("nonexistent.toml"), api_enabled=False)

        # Calculate cost with Claude Sonnet 4.5
        cost = config.calculate_cost(
            "claude-sonnet-4-5-20250929",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )

        # 1M input @ $3.0 + 1M output @ $15.0 = $18.0
        assert cost == pytest.approx(18.0, rel=1e-4)

    def test_default_pricing_has_metadata(self) -> None:
        """Test DEFAULT_PRICING includes proper metadata"""
        config = PricingConfig(Path("nonexistent.toml"))

        assert config.metadata is not None
        assert config.metadata.get("currency") == "USD"
        assert config.metadata.get("source") == "hardcoded defaults (task-67)"

    def test_default_pricing_validation_passes(self) -> None:
        """Test DEFAULT_PRICING passes validation"""
        config = PricingConfig(Path("nonexistent.toml"))
        result = config.validate()

        assert result["valid"] == True
        assert len(result["errors"]) == 0

    def test_unknown_model_warning_mentions_config_creation(self) -> None:
        """Test unknown model warning suggests creating config file"""
        config = PricingConfig(Path("nonexistent.toml"))

        with pytest.warns(RuntimeWarning, match="Create.*token-audit.toml"):
            config.get_model_pricing("unknown-future-model")


class TestTieredPricing:
    """Tests for tiered pricing support (v0.9.1 #54)"""

    def test_tiered_cost_below_threshold(self) -> None:
        """Test tiered cost calculation when tokens are below threshold"""
        config = PricingConfig(api_enabled=False)

        # Test _calculate_tiered_cost directly
        cost = config._calculate_tiered_cost(
            tokens=100_000,  # Below 200k threshold
            base_rate=3.0,  # $3/M tokens
            tiered_rate=4.0,  # $4/M tokens (above threshold)
            threshold=200_000,
        )

        # Should use only base rate: 100K @ $3.0/M = $0.30
        assert cost == pytest.approx(0.30, rel=1e-4)

    def test_tiered_cost_at_threshold(self) -> None:
        """Test tiered cost calculation when tokens are exactly at threshold"""
        config = PricingConfig(api_enabled=False)

        cost = config._calculate_tiered_cost(
            tokens=200_000,  # Exactly at 200k threshold
            base_rate=3.0,
            tiered_rate=4.0,
            threshold=200_000,
        )

        # Should use only base rate: 200K @ $3.0/M = $0.60
        assert cost == pytest.approx(0.60, rel=1e-4)

    def test_tiered_cost_above_threshold(self) -> None:
        """Test tiered cost calculation when tokens exceed threshold"""
        config = PricingConfig(api_enabled=False)

        cost = config._calculate_tiered_cost(
            tokens=300_000,  # 100k above 200k threshold
            base_rate=3.0,
            tiered_rate=4.0,
            threshold=200_000,
        )

        # 200K @ $3.0/M = $0.60 + 100K @ $4.0/M = $0.40 = $1.00
        assert cost == pytest.approx(1.00, rel=1e-4)

    def test_tiered_cost_no_tiered_rate(self) -> None:
        """Test tiered cost calculation when tiered_rate is None (uses flat rate)"""
        config = PricingConfig(api_enabled=False)

        cost = config._calculate_tiered_cost(
            tokens=300_000,  # Above threshold
            base_rate=3.0,
            tiered_rate=None,  # No tiered rate available
            threshold=200_000,
        )

        # Should use flat rate for all tokens: 300K @ $3.0/M = $0.90
        assert cost == pytest.approx(0.90, rel=1e-4)

    def test_calculate_cost_claude_model_with_tiered_data(self) -> None:
        """Test calculate_cost applies tiered pricing for Claude models"""
        config = PricingConfig(api_enabled=False)

        # Mock pricing data with tiered fields
        mock_pricing = {
            "input": 3.0,
            "output": 15.0,
            "input_above_200k": 4.0,
            "output_above_200k": 20.0,
        }

        # Patch get_model_pricing to return our mock
        config.get_model_pricing = lambda _model, _vendor=None: mock_pricing

        cost = config.calculate_cost(
            "claude-sonnet-4-5-20250929",
            input_tokens=300_000,  # 100k above threshold
            output_tokens=400_000,  # 200k above threshold
        )

        # Input: 200K @ $3/M + 100K @ $4/M = $0.60 + $0.40 = $1.00
        # Output: 200K @ $15/M + 200K @ $20/M = $3.00 + $4.00 = $7.00
        # Total = $8.00
        assert cost == pytest.approx(8.00, rel=1e-4)

    def test_calculate_cost_gemini_model_with_tiered_data(self) -> None:
        """Test calculate_cost applies tiered pricing for Gemini models"""
        config = PricingConfig(api_enabled=False)

        # Mock pricing data with tiered fields for Gemini (128k threshold)
        mock_pricing = {
            "input": 1.25,
            "output": 10.0,
            "input_above_128k": 2.50,
            "output_above_128k": 15.0,
        }

        config.get_model_pricing = lambda _model, _vendor=None: mock_pricing

        cost = config.calculate_cost(
            "gemini-2.5-pro",
            input_tokens=256_000,  # 128k above threshold
            output_tokens=128_000,  # Exactly at threshold
        )

        # Input: 128K @ $1.25/M + 128K @ $2.50/M = $0.16 + $0.32 = $0.48
        # Output: 128K @ $10/M = $1.28 (at threshold, no tiered rate applied)
        # Total = $1.76
        assert cost == pytest.approx(1.76, rel=1e-4)

    def test_calculate_cost_openai_model_no_tiered_pricing(self) -> None:
        """Test calculate_cost uses flat rate for OpenAI models (no tiering)"""
        config = PricingConfig(api_enabled=False)

        # Mock pricing without tiered fields (OpenAI doesn't use tiered pricing)
        mock_pricing = {
            "input": 1.25,
            "output": 10.0,
        }

        config.get_model_pricing = lambda _model, _vendor=None: mock_pricing

        cost = config.calculate_cost(
            "gpt-5.1-codex-max",
            input_tokens=500_000,
            output_tokens=200_000,
        )

        # Flat rate: 500K @ $1.25/M + 200K @ $10/M = $0.625 + $2.00 = $2.625
        assert cost == pytest.approx(2.625, rel=1e-4)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
