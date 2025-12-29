"""Tests for API stability infrastructure.

Verifies:
- API_STABILITY dictionary completeness
- get_api_stability() function behavior
- Deprecation warnings for deprecated APIs
- All stable APIs are importable
"""

import warnings
from typing import get_args

import pytest


class TestAPIStability:
    """Test the API stability infrastructure."""

    def test_api_stability_dict_exists(self) -> None:
        """API_STABILITY dictionary should be importable."""
        from token_audit import API_STABILITY

        assert isinstance(API_STABILITY, dict)
        assert len(API_STABILITY) > 0

    def test_get_api_stability_function(self) -> None:
        """get_api_stability should return correct tiers."""
        from token_audit import get_api_stability

        # Known stable API
        assert get_api_stability("StorageManager") == "stable"
        assert get_api_stability("TokenEstimator") == "stable"

        # Known evolving API
        assert get_api_stability("ClaudeCodeAdapter") == "evolving"
        assert get_api_stability("Session") == "evolving"

        # Known deprecated API
        assert get_api_stability("estimate_tool_tokens") == "deprecated"

        # Unknown API
        assert get_api_stability("NonExistentAPI") == "unknown"

    def test_stability_tier_type(self) -> None:
        """StabilityTier type should include expected values."""
        from token_audit import StabilityTier

        valid_tiers = get_args(StabilityTier)
        assert "stable" in valid_tiers
        assert "evolving" in valid_tiers
        assert "deprecated" in valid_tiers
        assert "unknown" in valid_tiers

    def test_all_exports_have_stability(self) -> None:
        """Every export in __all__ should have a stability classification."""
        from token_audit import API_STABILITY, __all__

        # Exclude metadata and stability-related exports
        excluded = {
            "__version__",
            "__author__",
            "__email__",
            "API_STABILITY",
            "StabilityTier",
            "get_api_stability",
        }

        for export in __all__:
            if export not in excluded:
                assert export in API_STABILITY, f"Missing stability for {export}"

    def test_stability_values_are_valid(self) -> None:
        """All stability values should be valid tiers."""
        from token_audit import API_STABILITY, StabilityTier

        valid_tiers = set(get_args(StabilityTier))

        for name, tier in API_STABILITY.items():
            assert tier in valid_tiers, f"Invalid tier {tier!r} for {name}"


class TestDeprecationWarnings:
    """Test deprecation warning behavior."""

    def test_estimate_tool_tokens_warning(self) -> None:
        """estimate_tool_tokens should emit deprecation warning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            # Import the deprecated function
            from token_audit import estimate_tool_tokens  # noqa: F401

            # Check warning was emitted
            deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
            assert len(deprecation_warnings) >= 1

            # Check warning message content
            warning_msg = str(deprecation_warnings[0].message)
            assert "estimate_tool_tokens" in warning_msg
            assert "deprecated" in warning_msg.lower()
            assert "v1.0.5" in warning_msg

    def test_stable_apis_no_warning(self) -> None:
        """Stable APIs should not emit deprecation warnings."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            # Import stable APIs
            from token_audit import (  # noqa: F401
                PricingConfig,
                SessionIndex,
                StorageManager,
                TokenEstimator,
            )

            # No deprecation warnings should be raised
            deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
            # Filter to only token_audit related warnings
            mcp_warnings = [w for w in deprecation_warnings if "token_audit" in str(w.filename)]
            assert len(mcp_warnings) == 0


class TestStableAPIsImportable:
    """Verify all stable APIs can be imported successfully."""

    @pytest.mark.parametrize(
        "api_name",
        [
            "StorageManager",
            "SessionIndex",
            "PricingConfig",
            "load_pricing_config",
            "get_model_cost",
            "normalize_tool_name",
            "normalize_server_name",
            "extract_server_and_tool",
            "TokenEstimator",
            "count_tokens",
            "get_estimator_for_platform",
            "FUNCTION_CALL_OVERHEAD",
            "DisplayAdapter",
            "DisplaySnapshot",
            "create_display",
            "DisplayMode",
        ],
    )
    def test_stable_api_importable(self, api_name: str) -> None:
        """Each stable API should be importable from token_audit."""
        import token_audit

        assert hasattr(token_audit, api_name), f"Cannot import {api_name}"
        obj = getattr(token_audit, api_name)
        assert obj is not None


class TestEvolvingAPIsImportable:
    """Verify all evolving APIs can be imported successfully."""

    @pytest.mark.parametrize(
        "api_name",
        [
            "BaseTracker",
            "Session",
            "ServerSession",
            "Call",
            "ToolStats",
            "TokenUsage",
            "MCPToolCalls",
            "ClaudeCodeAdapter",
            "CodexCLIAdapter",
            "GeminiCLIAdapter",
            "SmellAggregator",
            "AggregatedSmell",
            "SmellAggregationResult",
        ],
    )
    def test_evolving_api_importable(self, api_name: str) -> None:
        """Each evolving API should be importable from token_audit."""
        import token_audit

        assert hasattr(token_audit, api_name), f"Cannot import {api_name}"
        obj = getattr(token_audit, api_name)
        assert obj is not None


class TestStabilityDocumentation:
    """Verify stability is documented correctly."""

    def test_stable_count(self) -> None:
        """There should be exactly 16 stable APIs."""
        from token_audit import API_STABILITY

        stable_count = sum(1 for tier in API_STABILITY.values() if tier == "stable")
        assert stable_count == 16, f"Expected 16 stable APIs, got {stable_count}"

    def test_evolving_count(self) -> None:
        """There should be exactly 23 evolving APIs (13 core + 3 server + 4 bucket + 3 task)."""
        from token_audit import API_STABILITY

        evolving_count = sum(1 for tier in API_STABILITY.values() if tier == "evolving")
        assert evolving_count == 23, f"Expected 23 evolving APIs, got {evolving_count}"

    def test_deprecated_count(self) -> None:
        """There should be exactly 1 deprecated API."""
        from token_audit import API_STABILITY

        deprecated_count = sum(1 for tier in API_STABILITY.values() if tier == "deprecated")
        assert deprecated_count == 1, f"Expected 1 deprecated API, got {deprecated_count}"
