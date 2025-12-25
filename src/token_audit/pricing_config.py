#!/usr/bin/env python3
"""
Pricing Configuration Module - Model pricing loader and validator

Loads pricing data from LiteLLM API (primary) or token-audit.toml (fallback).
Provides validation and warnings for missing pricing.
"""

import logging
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .pricing_api import PricingAPI

logger = logging.getLogger(__name__)

# Try Python 3.11+ built-in tomllib, fall back to toml package
try:
    import tomllib

    HAS_TOMLLIB = True
except ImportError:
    try:
        import toml as tomllib  # type: ignore

        HAS_TOMLLIB = True
    except ImportError:
        HAS_TOMLLIB = False
        warnings.warn(
            "TOML support not available. Install 'toml' package: pip install toml",
            RuntimeWarning,
            stacklevel=2,
        )


class PricingConfig:
    """
    Pricing configuration loader and validator.

    Loads model pricing from token-audit.toml and provides
    utilities for cost calculation and validation.

    If no config file is found, falls back to DEFAULT_PRICING with
    common models for Claude, OpenAI/Codex, and Gemini.
    """

    # Standard locations to search for config (in priority order)
    CONFIG_SEARCH_PATHS = [
        Path("token-audit.toml"),  # CWD (project-specific override)
        Path.home() / ".token-audit" / "token-audit.toml",  # User config
        Path(__file__).parent.parent.parent / "token-audit.toml",  # Package root
    ]

    # Default pricing fallback for pip-installed users without config file (task-67)
    # Prices in USD per million tokens (verified 2025-12-04)
    DEFAULT_PRICING: Dict[str, Dict[str, Dict[str, float]]] = {
        "claude": {
            # Claude Opus 4.5 (most capable)
            "claude-opus-4-5-20251101": {
                "input": 5.0,
                "output": 25.0,
                "cache_create": 6.25,
                "cache_read": 0.50,
            },
            # Claude Sonnet 4.5 (balanced)
            "claude-sonnet-4-5-20250929": {
                "input": 3.0,
                "output": 15.0,
                "cache_create": 3.75,
                "cache_read": 0.30,
            },
            # Claude Haiku 4.5 (fast/cheap)
            "claude-haiku-4-5-20251001": {
                "input": 1.0,
                "output": 5.0,
                "cache_create": 1.25,
                "cache_read": 0.10,
            },
        },
        "openai": {
            # GPT-5.1 Codex Max (Codex CLI default)
            "gpt-5.1-codex-max": {
                "input": 1.25,
                "output": 10.0,
                "cache_read": 0.125,
            },
            # GPT-5.1
            "gpt-5.1": {
                "input": 1.25,
                "output": 10.0,
                "cache_read": 0.125,
            },
            # GPT-5.1 Codex
            "gpt-5.1-codex": {
                "input": 1.25,
                "output": 10.0,
                "cache_read": 0.125,
            },
            # GPT-5.1 Codex Mini
            "gpt-5.1-codex-mini": {
                "input": 0.25,
                "output": 2.0,
                "cache_read": 0.025,
            },
        },
        "gemini": {
            # Gemini 2.5 Flash (Gemini CLI default)
            "gemini-2.5-flash": {
                "input": 0.30,
                "output": 2.50,
                "cache_create": 0.03,
                "cache_read": 0.03,
            },
            # Gemini 2.5 Pro
            "gemini-2.5-pro": {
                "input": 1.25,
                "output": 10.0,
                "cache_create": 0.3125,
                "cache_read": 0.125,
            },
            # Gemini 2.0 Flash
            "gemini-2.0-flash": {
                "input": 0.10,
                "output": 0.40,
                "cache_create": 0.025,
                "cache_read": 0.025,
            },
        },
    }

    DEFAULT_METADATA: Dict[str, Any] = {
        "currency": "USD",
        "pricing_unit": "per_million_tokens",
        "source": "hardcoded defaults (task-67)",
        "exchange_rates": {"USD_to_AUD": 1.54},
    }

    def __init__(
        self,
        config_path: Optional[Path] = None,
        api_enabled: Optional[bool] = None,
    ):
        """
        Initialize pricing configuration.

        Args:
            config_path: Path to token-audit.toml. If None, searches standard locations:
                        1. ./token-audit.toml (CWD - project override)
                        2. ~/.token-audit/token-audit.toml (user config)
                        3. Package root (bundled default)
                        4. Falls back to DEFAULT_PRICING if no file found (task-67)
            api_enabled: Override API pricing (None = use config, True/False = force)
        """
        self.config_path = config_path or self._find_config()
        self.pricing_data: Dict[str, Dict[str, Any]] = {}
        self.metadata: Dict[str, Any] = {}
        self.loaded = False
        self._source = "none"  # Track pricing source: "file", "defaults", "api", etc.

        # API pricing configuration (task-108.3.3)
        self._pricing_api: Optional[PricingAPI] = None
        self._api_enabled = api_enabled if api_enabled is not None else True
        self._api_ttl_hours = 24
        self._api_offline_mode = False

        # Load TOML config first (to get API settings)
        if self.config_path and self.config_path.exists():
            self.load()
            self._load_api_config()
            self._source = "file"
        else:
            # Fall back to default pricing (task-67)
            self._load_defaults()

        # Try API pricing if enabled (task-108.3.3)
        if self._api_enabled and not self._api_offline_mode:
            self._try_load_api()

    def _find_config(self) -> Optional[Path]:
        """Search standard locations for config file."""
        for path in self.CONFIG_SEARCH_PATHS:
            if path.exists():
                return path
        return None

    def _load_defaults(self) -> None:
        """Load hardcoded default pricing when no config file is found (task-67)."""
        self.pricing_data = self.DEFAULT_PRICING.copy()
        self.metadata = self.DEFAULT_METADATA.copy()
        self.loaded = True
        self._source = "defaults"

    def _load_api_config(self) -> None:
        """Load API configuration from TOML file (task-108.3.3)."""
        if not self.config_path or not self.config_path.exists():
            return

        try:
            with open(self.config_path, "rb") as f:
                config = tomllib.load(f)

            api_config = config.get("pricing", {}).get("api", {})
            if api_config:
                # Only override if not already set via constructor
                if api_config.get("enabled") is not None:
                    self._api_enabled = api_config.get("enabled", True)
                self._api_ttl_hours = api_config.get("cache_ttl_hours", 24)
                self._api_offline_mode = api_config.get("offline_mode", False)
        except Exception as e:
            logger.debug(f"Failed to load API config from TOML: {e}")

    def _try_load_api(self) -> None:
        """Try to initialize and load pricing from API (task-108.3.3)."""
        try:
            from .pricing_api import PricingAPI

            self._pricing_api = PricingAPI(
                cache_ttl_hours=self._api_ttl_hours,
                enabled=True,
            )
            # Trigger data loading
            self._pricing_api._load_pricing()

            if self._pricing_api._pricing_data:
                logger.debug(f"API pricing available: {self._pricing_api.model_count} models")
        except ImportError:
            logger.debug("PricingAPI not available")
        except Exception as e:
            logger.debug(f"Failed to load API pricing: {e}")

    def load(self) -> None:
        """Load pricing configuration from TOML file."""
        if not HAS_TOMLLIB:
            raise RuntimeError(
                "Cannot load pricing config: TOML support not available. "
                "Install 'toml' package: pip install toml"
            )

        if not self.config_path:
            raise RuntimeError("Cannot load pricing config: No config path set")

        with open(self.config_path, "rb") as f:
            config = tomllib.load(f)

        # Extract pricing data
        self.pricing_data = config.get("pricing", {})
        self.metadata = config.get("metadata", {})
        self.loaded = True

    def get_model_pricing(
        self, model_name: str, vendor: Optional[str] = None
    ) -> Optional[Dict[str, float]]:
        """
        Get pricing for a specific model.

        Checks in order:
        1. LiteLLM API (if enabled and available)
        2. TOML config file
        3. Default pricing

        Args:
            model_name: Model identifier (e.g., 'claude-sonnet-4-5-20250929')
            vendor: Vendor namespace (e.g., 'claude', 'openai', 'custom')
                   If None, searches all namespaces

        Returns:
            Dictionary with pricing keys: input, output, cache_create, cache_read
            Returns None if model not found
        """
        # Try API pricing first (task-108.3.3)
        if self._pricing_api and self._api_enabled:
            api_pricing = self._pricing_api.get_pricing(model_name)
            if api_pricing:
                return api_pricing

        # Fall back to TOML/defaults
        return self._get_toml_pricing(model_name, vendor)

    def _get_toml_pricing(
        self, model_name: str, vendor: Optional[str] = None
    ) -> Optional[Dict[str, float]]:
        """Get pricing from TOML config or defaults (internal fallback)."""
        if not self.loaded:
            warnings.warn(
                f"Pricing config not loaded. Missing file: {self.config_path}",
                RuntimeWarning,
                stacklevel=2,
            )
            return None

        # Search specific vendor if provided
        if vendor:
            vendor_pricing: Dict[str, Dict[str, float]] = self.pricing_data.get(vendor, {})
            if model_name in vendor_pricing:
                result: Dict[str, float] = vendor_pricing[model_name]
                return result
            return None

        # Search all vendors
        for _vendor_name, models in self.pricing_data.items():
            if model_name in models:
                result_model: Dict[str, float] = models[model_name]
                return result_model

        # Model not found - provide helpful guidance based on pricing source
        if self._source == "defaults":
            warnings.warn(
                f"No pricing for model: {model_name}. "
                f"Create ~/.token-audit/token-audit.toml with [pricing.custom] section.",
                RuntimeWarning,
                stacklevel=2,
            )
        else:
            warnings.warn(
                f"No pricing configured for model: {model_name}. "
                f"Add pricing to {self.config_path} under [pricing.custom]",
                RuntimeWarning,
                stacklevel=2,
            )
        return None

    def calculate_cost(
        self,
        model_name: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_created_tokens: int = 0,
        cache_read_tokens: int = 0,
        vendor: Optional[str] = None,
    ) -> float:
        """
        Calculate cost for token usage.

        Args:
            model_name: Model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            cache_created_tokens: Number of cache creation tokens
            cache_read_tokens: Number of cache read tokens
            vendor: Optional vendor namespace

        Returns:
            Cost in USD (0.0 if pricing not found)
        """
        pricing = self.get_model_pricing(model_name, vendor)
        if not pricing:
            return 0.0

        cost = 0.0

        # Detect tiered pricing threshold (v0.9.1 #54)
        # Claude models: 200k threshold
        # Gemini models: 128k threshold
        threshold: Optional[int] = None
        input_tiered_key: Optional[str] = None
        output_tiered_key: Optional[str] = None

        model_lower = model_name.lower()
        if "claude" in model_lower or model_lower.startswith("anthropic"):
            threshold = 200_000
            input_tiered_key = "input_above_200k"
            output_tiered_key = "output_above_200k"
        elif "gemini" in model_lower or model_lower.startswith("google"):
            threshold = 128_000
            input_tiered_key = "input_above_128k"
            output_tiered_key = "output_above_128k"

        # Input tokens (with tiered pricing if available)
        if "input" in pricing:
            if threshold and input_tiered_key and input_tiered_key in pricing:
                cost += self._calculate_tiered_cost(
                    input_tokens,
                    pricing["input"],
                    pricing.get(input_tiered_key),
                    threshold,
                )
            else:
                cost += (input_tokens / 1_000_000) * pricing["input"]

        # Output tokens (with tiered pricing if available)
        if "output" in pricing:
            if threshold and output_tiered_key and output_tiered_key in pricing:
                cost += self._calculate_tiered_cost(
                    output_tokens,
                    pricing["output"],
                    pricing.get(output_tiered_key),
                    threshold,
                )
            else:
                cost += (output_tokens / 1_000_000) * pricing["output"]

        # Cache creation tokens
        if "cache_create" in pricing:
            cost += (cache_created_tokens / 1_000_000) * pricing["cache_create"]

        # Cache read tokens
        if "cache_read" in pricing:
            cost += (cache_read_tokens / 1_000_000) * pricing["cache_read"]

        return cost

    def _calculate_tiered_cost(
        self,
        tokens: int,
        base_rate: float,
        tiered_rate: Optional[float],
        threshold: int,
    ) -> float:
        """Calculate cost with token threshold tiering (v0.9.1 #54).

        Args:
            tokens: Number of tokens to price
            base_rate: Price per million tokens for tokens below threshold
            tiered_rate: Price per million tokens for tokens above threshold
            threshold: Token threshold (e.g., 200000 for Claude, 128000 for Gemini)

        Returns:
            Cost in USD
        """
        if tiered_rate is None or tokens <= threshold:
            return (tokens / 1_000_000) * base_rate

        base_cost = (threshold / 1_000_000) * base_rate
        tiered_cost = ((tokens - threshold) / 1_000_000) * tiered_rate
        return base_cost + tiered_cost

    def list_models(self, vendor: Optional[str] = None) -> List[str]:
        """
        List all configured models.

        Args:
            vendor: Filter by vendor namespace (None = all vendors)

        Returns:
            List of model names
        """
        if not self.loaded:
            return []

        if vendor:
            return list(self.pricing_data.get(vendor, {}).keys())

        # All models from all vendors
        models: list[str] = []
        for vendor_models in self.pricing_data.values():
            models.extend(vendor_models.keys())
        return models

    def validate(self) -> Dict[str, Any]:
        """
        Validate pricing configuration.

        Returns:
            Dictionary with validation results:
            - valid: bool
            - errors: List[str]
            - warnings: List[str]
        """
        result: Dict[str, Any] = {"valid": True, "errors": [], "warnings": []}

        if not self.loaded:
            result["valid"] = False
            result["errors"].append(f"Config file not found: {self.config_path}")
            return result

        if not self.pricing_data:
            result["warnings"].append("No pricing data configured")

        # Validate each model's pricing structure
        # Skip 'api' key as it contains configuration, not pricing data
        for vendor, models in self.pricing_data.items():
            if vendor == "api":
                continue  # Skip API configuration section

            for model_name, pricing in models.items():
                if not isinstance(pricing, dict):
                    result["errors"].append(f"Invalid pricing format for {vendor}.{model_name}")
                    result["valid"] = False
                    continue

                # Check required fields
                if "input" not in pricing:
                    result["warnings"].append(f"Missing 'input' pricing for {vendor}.{model_name}")

                if "output" not in pricing:
                    result["warnings"].append(f"Missing 'output' pricing for {vendor}.{model_name}")

                # Validate numeric values
                for key in ["input", "output", "cache_create", "cache_read"]:
                    if key in pricing:
                        try:
                            float(pricing[key])
                        except (ValueError, TypeError):
                            result["errors"].append(
                                f"Invalid numeric value for {vendor}.{model_name}.{key}"
                            )
                            result["valid"] = False

        return result

    @property
    def pricing_source(self) -> str:
        """Return the active pricing source (task-108.3.3).

        Returns:
            - 'api': Fresh from LiteLLM API
            - 'cache': Cached API data
            - 'cache-stale': Expired API cache
            - 'file': TOML configuration file
            - 'defaults': Hardcoded default pricing
            - 'none': No pricing available
        """
        if self._pricing_api and self._pricing_api.source != "none":
            return self._pricing_api.source
        return self._source

    @property
    def api_model_count(self) -> int:
        """Return number of models available from API."""
        if self._pricing_api:
            return self._pricing_api.model_count
        return 0


# ============================================================================
# Convenience Functions
# ============================================================================


def load_pricing_config(config_path: Optional[Path] = None) -> PricingConfig:
    """
    Convenience function to load pricing configuration.

    Args:
        config_path: Path to token-audit.toml

    Returns:
        PricingConfig instance
    """
    return PricingConfig(config_path)


def get_model_cost(
    model_name: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_created_tokens: int = 0,
    cache_read_tokens: int = 0,
    config_path: Optional[Path] = None,
) -> float:
    """
    Convenience function to calculate model cost.

    Args:
        model_name: Model identifier
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cache_created_tokens: Number of cache creation tokens
        cache_read_tokens: Number of cache read tokens
        config_path: Path to pricing config

    Returns:
        Cost in USD
    """
    config = PricingConfig(config_path)
    return config.calculate_cost(
        model_name, input_tokens, output_tokens, cache_created_tokens, cache_read_tokens
    )


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    print("Pricing Configuration Module Tests")
    print("=" * 60)

    # Test loading
    config = PricingConfig()

    if config.loaded:
        print(f"✓ Loaded config from {config.config_path}")

        # Validate
        validation = config.validate()
        print(f"\nValidation: {'✓ PASS' if validation['valid'] else '✗ FAIL'}")

        if validation["errors"]:
            print("\nErrors:")
            for error in validation["errors"]:
                print(f"  - {error}")

        if validation["warnings"]:
            print("\nWarnings:")
            for warning in validation["warnings"]:
                print(f"  - {warning}")

        # List models
        print(f"\nConfigured models: {len(config.list_models())}")
        print("\nClaude models:")
        for model in config.list_models("claude"):
            print(f"  - {model}")

        print("\nOpenAI models:")
        for model in config.list_models("openai"):
            print(f"  - {model}")

        # Test pricing lookup
        print("\nPricing lookup test:")
        model = "claude-sonnet-4-5-20250929"
        pricing = config.get_model_pricing(model)
        print(f"  Model: {model}")
        print(f"  Pricing: {pricing}")

        # Test cost calculation
        print("\nCost calculation test:")
        cost = config.calculate_cost(
            model, input_tokens=10000, output_tokens=5000, cache_read_tokens=50000
        )
        print(f"  10K input + 5K output + 50K cache read = ${cost:.4f}")
    else:
        print(f"✗ Config file not found: {config.config_path}")
