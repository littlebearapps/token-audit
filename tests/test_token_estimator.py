"""Tests for token estimation module.

Tests the TokenEstimator class which provides token counting for MCP tool calls
on platforms that don't have native per-tool token attribution.
"""

import pytest

from token_audit.token_estimator import (
    FUNCTION_CALL_OVERHEAD,
    TokenEstimator,
    count_tokens,
    estimate_tool_tokens,
    get_estimator_for_platform,
)


class TestTokenEstimatorBasic:
    """Basic TokenEstimator tests."""

    def test_empty_string_returns_zero(self):
        """Empty strings should return 0 tokens."""
        estimator = TokenEstimator()
        assert estimator.estimate_tokens("") == 0

    def test_none_string_returns_zero(self):
        """None values in tool calls should return 0 tokens."""
        estimator = TokenEstimator()
        input_tokens, output_tokens = estimator.estimate_tool_call(None, None)
        # Only overhead for input, 0 for output
        assert input_tokens == FUNCTION_CALL_OVERHEAD
        assert output_tokens == 0

    def test_simple_text_returns_tokens(self):
        """Simple text should return reasonable token count."""
        estimator = TokenEstimator()
        text = "Hello, world!"
        tokens = estimator.estimate_tokens(text)
        assert tokens > 0
        assert tokens < 10  # Reasonable for short string

    def test_json_content(self):
        """JSON should be tokenized correctly."""
        estimator = TokenEstimator()
        json_str = '{"key": "value", "number": 123}'
        tokens = estimator.estimate_tokens(json_str)
        assert 5 <= tokens <= 20

    def test_code_content(self):
        """Code snippets should handle special characters."""
        estimator = TokenEstimator()
        code = "def foo(x):\n    return x * 2"
        tokens = estimator.estimate_tokens(code)
        assert tokens > 0

    def test_large_content(self):
        """Large content should be handled efficiently."""
        estimator = TokenEstimator()
        large_text = "word " * 10000
        tokens = estimator.estimate_tokens(large_text)
        # ~10000 words should be around 10000 tokens (word + space)
        assert 8000 <= tokens <= 12000


class TestFunctionCallOverhead:
    """Test FUNCTION_CALL_OVERHEAD constant and behavior."""

    def test_overhead_constant_value(self):
        """FUNCTION_CALL_OVERHEAD should be 25 tokens."""
        assert FUNCTION_CALL_OVERHEAD == 25

    def test_overhead_included_by_default(self):
        """estimate_tool_call should include overhead by default."""
        estimator = TokenEstimator()
        args = '{"query": "test"}'

        # With overhead (default)
        input_with, _ = estimator.estimate_tool_call(args, "")

        # Without overhead
        input_without, _ = estimator.estimate_tool_call(args, "", include_overhead=False)

        assert input_with == input_without + FUNCTION_CALL_OVERHEAD

    def test_overhead_can_be_disabled(self):
        """include_overhead=False should skip overhead."""
        estimator = TokenEstimator()
        args = '{"query": "test"}'

        input_tokens, _ = estimator.estimate_tool_call(args, "", include_overhead=False)

        # Should just be content tokens, no overhead
        content_tokens = estimator.estimate_tokens(args)
        assert input_tokens == content_tokens

    def test_empty_args_still_has_overhead(self):
        """Empty args should still include overhead."""
        estimator = TokenEstimator()
        input_tokens, _ = estimator.estimate_tool_call("", "")
        assert input_tokens == FUNCTION_CALL_OVERHEAD


class TestToolCallEstimation:
    """Test token estimation for tool calls."""

    def test_estimate_function_call(self):
        """Estimate tokens for function call arguments."""
        estimator = TokenEstimator()
        args = '{"query": "python datetime format", "count": 10}'
        input_tokens, output_tokens = estimator.estimate_tool_call(args, "")
        assert input_tokens > FUNCTION_CALL_OVERHEAD
        assert output_tokens == 0

    def test_estimate_function_result(self):
        """Estimate tokens for function result."""
        estimator = TokenEstimator()
        result = '{"data": [{"title": "Result 1"}, {"title": "Result 2"}]}'
        input_tokens, output_tokens = estimator.estimate_tool_call("{}", result)
        assert input_tokens >= FUNCTION_CALL_OVERHEAD
        assert output_tokens > 0

    def test_estimate_full_tool_call(self):
        """Estimate tokens for complete tool call."""
        estimator = TokenEstimator()
        args = '{"query": "search term"}'
        result = "Search results: Item 1, Item 2, Item 3"
        input_tokens, output_tokens = estimator.estimate_tool_call(args, result)
        assert input_tokens > FUNCTION_CALL_OVERHEAD
        assert output_tokens > 0

    def test_estimate_tool_call_dict(self):
        """Estimate tokens with dict arguments."""
        estimator = TokenEstimator()
        args = {"query": "test query", "limit": 10}
        result = "Result text"
        input_tokens, output_tokens = estimator.estimate_tool_call_dict(args, result)
        assert input_tokens > FUNCTION_CALL_OVERHEAD
        assert output_tokens > 0


class TestPlatformEstimators:
    """Test platform-specific estimator configurations."""

    def test_codex_cli_uses_tiktoken_o200k(self):
        """Codex CLI should use tiktoken o200k_base (~99-100% accuracy)."""
        estimator = TokenEstimator.for_platform("codex-cli")
        assert estimator.method_name == "tiktoken"
        assert estimator.encoding_name == "o200k_base"
        assert not estimator.is_fallback

    def test_gemini_cli_configuration(self):
        """Gemini CLI should use sentencepiece or tiktoken fallback."""
        estimator = TokenEstimator.for_platform("gemini-cli")
        # Either sentencepiece (if tokenizer.model exists) or tiktoken fallback
        assert estimator.method_name in ("sentencepiece", "tiktoken", "character")
        if estimator.method_name == "sentencepiece":
            assert estimator.encoding_name == "sentencepiece:gemma"
        elif estimator.method_name == "tiktoken":
            assert estimator.encoding_name == "cl100k_base"

    def test_claude_code_configuration(self):
        """Claude Code should use tiktoken cl100k_base (for fallback only)."""
        estimator = TokenEstimator.for_platform("claude-code")
        assert estimator.method_name == "tiktoken"
        assert estimator.encoding_name == "cl100k_base"
        assert not estimator.is_fallback

    def test_get_estimator_for_platform_convenience(self):
        """Convenience function should work."""
        estimator = get_estimator_for_platform("codex-cli")
        assert estimator.encoding_name == "o200k_base"


class TestModelEstimators:
    """Test model-specific estimator configurations."""

    def test_gpt4o_uses_o200k(self):
        """GPT-4o should use o200k_base encoding."""
        estimator = TokenEstimator.for_model("gpt-4o-mini")
        assert estimator.encoding_name == "o200k_base"

    def test_gpt5_uses_o200k(self):
        """GPT-5 should use o200k_base encoding."""
        estimator = TokenEstimator.for_model("gpt-5.1")
        assert estimator.encoding_name == "o200k_base"

    def test_o1_uses_o200k(self):
        """o1 model should use o200k_base encoding."""
        estimator = TokenEstimator.for_model("o1-preview")
        assert estimator.encoding_name == "o200k_base"

    def test_claude_uses_cl100k(self):
        """Claude should use cl100k_base encoding."""
        estimator = TokenEstimator.for_model("claude-opus-4-5")
        assert estimator.encoding_name == "cl100k_base"

    def test_unknown_model_uses_default(self):
        """Unknown models should use default encoding."""
        estimator = TokenEstimator.for_model("some-unknown-model")
        assert estimator.encoding_name == TokenEstimator.DEFAULT_ENCODING


class TestFallbackMode:
    """Test character-based fallback behavior."""

    def test_fallback_consistency(self):
        """Fallback should be consistent."""
        estimator = TokenEstimator()
        # Force fallback mode
        estimator._is_fallback = True
        estimator._encoding = None
        estimator._sp_processor = None

        text = "Hello, world!"
        assert estimator.estimate_tokens(text) == estimator.estimate_tokens(text)

    def test_fallback_uses_chars_per_token_ratio(self):
        """Fallback should use ~4 chars per token ratio."""
        estimator = TokenEstimator()
        # Force fallback mode
        estimator._is_fallback = True
        estimator._encoding = None
        estimator._sp_processor = None

        # 12 chars / 4 = 3 tokens
        text = "Hello world!"
        tokens = estimator.estimate_tokens(text)
        assert tokens == len(text) // 4

    def test_fallback_returns_at_least_one(self):
        """Fallback should return at least 1 token for non-empty strings."""
        estimator = TokenEstimator()
        estimator._is_fallback = True
        estimator._encoding = None
        estimator._sp_processor = None

        # Very short string
        tokens = estimator.estimate_tokens("Hi")
        assert tokens >= 1


class TestModuleLevelFunctions:
    """Test module-level convenience functions."""

    def test_count_tokens_without_model(self):
        """count_tokens should work without model."""
        tokens = count_tokens("Hello, world!")
        assert tokens > 0

    def test_count_tokens_with_model(self):
        """count_tokens should work with model."""
        tokens = count_tokens("Hello, world!", model="gpt-4o")
        assert tokens > 0

    def test_estimate_tool_tokens_basic(self):
        """estimate_tool_tokens should work."""
        input_tokens, output_tokens = estimate_tool_tokens(
            '{"query": "test"}',
            "Result text",
        )
        assert input_tokens > 0
        assert output_tokens > 0

    def test_estimate_tool_tokens_with_model(self):
        """estimate_tool_tokens should work with model."""
        input_tokens, output_tokens = estimate_tool_tokens(
            '{"query": "test"}',
            "Result text",
            model="gpt-4o",
        )
        assert input_tokens > 0
        assert output_tokens > 0


class TestAccuracyExpectations:
    """Tests to validate accuracy expectations documented in task 69."""

    @pytest.mark.parametrize(
        "text,expected_min,expected_max",
        [
            ("Hello", 1, 3),
            ("Hello, world!", 3, 6),
            ("The quick brown fox jumps over the lazy dog.", 8, 14),
            ('{"key": "value"}', 4, 12),
        ],
    )
    def test_accuracy_range(self, text, expected_min, expected_max):
        """Estimates should be within acceptable range."""
        estimator = TokenEstimator()
        tokens = estimator.estimate_tokens(text)
        assert (
            expected_min <= tokens <= expected_max
        ), f"Expected {expected_min}-{expected_max}, got {tokens} for {text!r}"

    def test_codex_encoding_matches_openai(self):
        """Codex CLI encoding should match OpenAI's tokenizer exactly."""
        estimator = TokenEstimator.for_platform("codex-cli")
        # Known OpenAI tokenizer results for o200k_base
        text = "Hello, world!"
        tokens = estimator.estimate_tokens(text)
        # With o200k_base, "Hello, world!" should be 4 tokens
        assert 3 <= tokens <= 5


class TestProperties:
    """Test estimator properties."""

    def test_is_fallback_property(self):
        """is_fallback should reflect actual state."""
        estimator = TokenEstimator()
        assert estimator.is_fallback is False

    def test_encoding_name_property(self):
        """encoding_name should return the current encoding."""
        estimator = TokenEstimator(encoding="cl100k_base")
        assert estimator.encoding_name == "cl100k_base"

    def test_method_name_property(self):
        """method_name should return the tokenization method."""
        estimator = TokenEstimator(method="tiktoken")
        assert estimator.method_name == "tiktoken"

    def test_encoding_name_fallback(self):
        """encoding_name should indicate fallback mode."""
        estimator = TokenEstimator()
        estimator._is_fallback = True
        assert estimator.encoding_name == "character-fallback"

    def test_method_name_fallback(self):
        """method_name should indicate character fallback."""
        estimator = TokenEstimator()
        estimator._is_fallback = True
        assert estimator.method_name == "character"


class TestUnicodeAndSpecialCharacters:
    """Test handling of unicode and special characters."""

    def test_unicode_text(self):
        """Unicode text should be tokenized correctly."""
        estimator = TokenEstimator()
        # Japanese text
        text = "こんにちは世界"
        tokens = estimator.estimate_tokens(text)
        assert tokens > 0

    def test_emoji(self):
        """Emojis should be tokenized correctly."""
        estimator = TokenEstimator()
        text = "Hello 🌍 World 🚀"
        tokens = estimator.estimate_tokens(text)
        assert tokens > 0

    def test_mixed_unicode(self):
        """Mixed unicode content should work."""
        estimator = TokenEstimator()
        text = "Hello 你好 مرحبا Привет"
        tokens = estimator.estimate_tokens(text)
        assert tokens > 0

    def test_special_json_characters(self):
        """JSON with special characters should work."""
        estimator = TokenEstimator()
        json_str = '{"path": "C:\\\\Users\\\\test\\\\file.txt", "content": "line1\\nline2"}'
        tokens = estimator.estimate_tokens(json_str)
        assert tokens > 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_single_word(self):
        """Very long single word should be handled."""
        estimator = TokenEstimator()
        long_word = "a" * 10000
        tokens = estimator.estimate_tokens(long_word)
        assert tokens > 0

    def test_whitespace_only(self):
        """Whitespace-only strings should return tokens."""
        estimator = TokenEstimator()
        text = "   \n\t   "
        tokens = estimator.estimate_tokens(text)
        assert tokens >= 0

    def test_newlines_and_tabs(self):
        """Newlines and tabs should be counted."""
        estimator = TokenEstimator()
        text = "line1\nline2\tline3"
        tokens = estimator.estimate_tokens(text)
        assert tokens > 0

    def test_tool_call_with_large_result(self):
        """Large tool results should work."""
        estimator = TokenEstimator()
        args = '{"path": "/some/file"}'
        result = "content " * 5000  # ~5000 words
        input_tokens, output_tokens = estimator.estimate_tool_call(args, result)
        assert input_tokens >= FUNCTION_CALL_OVERHEAD
        assert output_tokens > 1000  # Should be significant

    def test_tool_call_with_empty_result(self):
        """Empty results should work."""
        estimator = TokenEstimator()
        args = '{"query": "test"}'
        result = ""
        input_tokens, output_tokens = estimator.estimate_tool_call(args, result)
        assert input_tokens > FUNCTION_CALL_OVERHEAD
        assert output_tokens == 0


class TestDisplaySnapshotEstimationFields:
    """Test that DisplaySnapshot correctly handles estimation fields."""

    def test_snapshot_has_estimation_fields(self):
        """DisplaySnapshot should have estimation tracking fields."""
        from datetime import datetime
        from token_audit.display import DisplaySnapshot

        snapshot = DisplaySnapshot.create(
            project="test",
            platform="codex-cli",
            start_time=datetime.now(),
            duration_seconds=100.0,
            estimated_tool_calls=5,
            estimation_method="tiktoken",
            estimation_encoding="o200k_base",
        )
        assert snapshot.estimated_tool_calls == 5
        assert snapshot.estimation_method == "tiktoken"
        assert snapshot.estimation_encoding == "o200k_base"

    def test_snapshot_defaults_to_zero_estimates(self):
        """DisplaySnapshot should default to no estimation."""
        from datetime import datetime
        from token_audit.display import DisplaySnapshot

        snapshot = DisplaySnapshot.create(
            project="test",
            platform="claude-code",
            start_time=datetime.now(),
            duration_seconds=100.0,
        )
        assert snapshot.estimated_tool_calls == 0
        assert snapshot.estimation_method == ""
        assert snapshot.estimation_encoding == ""


class TestGemmaTokenizerDownload:
    """Test Gemma tokenizer download functionality."""

    def test_check_gemma_tokenizer_status(self):
        """check_gemma_tokenizer_status should return status dict."""
        from token_audit.token_estimator import check_gemma_tokenizer_status

        status = check_gemma_tokenizer_status()

        # Should have required keys
        assert "installed" in status
        assert "location" in status
        assert "source" in status
        assert "sentencepiece_available" in status
        # New fields from Task 96.5
        assert "version" in status
        assert "downloaded_at" in status

        # Types should be correct
        assert isinstance(status["installed"], bool)
        assert isinstance(status["location"], str)
        assert isinstance(status["source"], str)
        assert isinstance(status["sentencepiece_available"], bool)

        # source should be one of expected values
        assert status["source"] in ("bundled", "cached", "not_found")

    def test_check_status_sentencepiece_available(self):
        """sentencepiece should be available (it's a dependency)."""
        from token_audit.token_estimator import check_gemma_tokenizer_status

        status = check_gemma_tokenizer_status()
        assert status["sentencepiece_available"] is True

    def test_download_returns_tuple(self):
        """download_gemma_tokenizer should return (success, message) tuple."""
        from token_audit.token_estimator import download_gemma_tokenizer

        # Without token, should fail with helpful message
        success, message = download_gemma_tokenizer()

        assert isinstance(success, bool)
        assert isinstance(message, str)
        assert len(message) > 0

    def test_download_without_token_behavior(self):
        """Download without token should either fail with guidance or use cache."""
        from token_audit.token_estimator import download_gemma_tokenizer

        # Use force=True to bypass the "already exists" check
        success, message = download_gemma_tokenizer(force=True)

        # Behavior depends on environment:
        # 1. If huggingface_hub not installed: fails with install guidance
        # 2. If no cached file and no auth: fails with auth guidance
        # 3. If cached file exists: HuggingFace falls back to cache (success)
        #
        # In CI (no cache), this should fail. Locally with cache, may succeed.
        assert isinstance(success, bool)
        assert isinstance(message, str)
        assert len(message) > 0

        if not success:
            # Should provide helpful info about what went wrong
            assert (
                "huggingface" in message.lower()
                or "token" in message.lower()
                or "401" in message
                or "access" in message.lower()
                or "install" in message.lower()
            )

    def test_get_cache_dir(self):
        """get_cache_dir should return a Path object."""
        from pathlib import Path
        from token_audit.token_estimator import TokenEstimator

        cache_dir = TokenEstimator.get_cache_dir()

        assert isinstance(cache_dir, Path)
        assert cache_dir.exists()
        assert "token-audit" in str(cache_dir)


class TestPathTraversalProtection:
    """SECURITY: Tests for tarball path traversal protection (Task 96.7)."""

    def test_rejects_absolute_path(self):
        """Test rejection of absolute paths in tarball."""
        from token_audit.token_estimator import _validate_tarball_member

        assert _validate_tarball_member("/etc/passwd") is False
        assert _validate_tarball_member("/tmp/evil.txt") is False
        assert _validate_tarball_member("/home/user/.ssh/id_rsa") is False

    def test_rejects_path_traversal(self):
        """Test rejection of path traversal attempts."""
        from token_audit.token_estimator import _validate_tarball_member

        assert _validate_tarball_member("../../../etc/passwd") is False
        assert _validate_tarball_member("foo/../../bar") is False
        assert _validate_tarball_member("..") is False
        assert _validate_tarball_member("foo/../bar") is False

    def test_accepts_valid_paths(self):
        """Test acceptance of valid relative paths."""
        from token_audit.token_estimator import _validate_tarball_member

        assert _validate_tarball_member("tokenizer.model") is True
        assert _validate_tarball_member("gemma-tokenizer/tokenizer.model") is True
        assert _validate_tarball_member("dir/subdir/file.txt") is True
        assert _validate_tarball_member("README.txt") is True
        assert _validate_tarball_member("NOTICE") is True


class TestGitHubDownload:
    """Tests for GitHub Release tokenizer download (Task 96.7)."""

    def test_download_from_github_returns_tuple(self):
        """download_gemma_from_github should return (success, message) tuple."""
        from token_audit.token_estimator import download_gemma_from_github

        # Test with existing tokenizer (should be bundled or skip)
        success, message = download_gemma_from_github()

        assert isinstance(success, bool)
        assert isinstance(message, str)
        assert len(message) > 0

    def test_download_already_exists_without_force(self, monkeypatch, tmp_path):
        """Test skip when tokenizer already exists."""
        from token_audit.token_estimator import download_gemma_from_github, TokenEstimator

        # Create fake existing tokenizer
        cache_dir = tmp_path / ".cache" / "token-audit"
        cache_dir.mkdir(parents=True)
        (cache_dir / "tokenizer.model").write_bytes(b"fake tokenizer")

        # Mock get_cache_dir to use tmp_path
        monkeypatch.setattr(
            TokenEstimator,
            "get_cache_dir",
            staticmethod(lambda: cache_dir),
        )

        success, message = download_gemma_from_github(force=False)

        assert success is True
        assert "already" in message.lower()

    def test_download_handles_network_error(self, monkeypatch):
        """Test proper handling of network errors."""
        import urllib.request
        from urllib.error import URLError
        from token_audit.token_estimator import download_gemma_from_github

        def raise_url_error(*args, **kwargs):
            raise URLError("Network unreachable")

        monkeypatch.setattr(urllib.request, "urlopen", raise_url_error)

        # Use force=True to bypass the "already exists" check
        success, message = download_gemma_from_github(force=True)

        assert success is False
        # Should include helpful error info
        assert len(message) > 0


class TestRateLimitHandling:
    """Tests for GitHub API rate limit handling (Task 96.7)."""

    def test_handles_403_rate_limit(self, monkeypatch):
        """Test proper handling of GitHub rate limit (403)."""
        import urllib.request
        from urllib.error import HTTPError
        from token_audit.token_estimator import download_gemma_from_github

        def raise_403(*args, **kwargs):
            raise HTTPError("url", 403, "Forbidden", {}, None)

        monkeypatch.setattr(urllib.request, "urlopen", raise_403)

        # Use force=True to bypass the "already exists" check
        success, message = download_gemma_from_github(force=True)

        assert success is False
        assert "rate limit" in message.lower() or "403" in message

    def test_handles_404_not_found(self, monkeypatch):
        """Test proper handling of missing release (404)."""
        import urllib.request
        from urllib.error import HTTPError
        from token_audit.token_estimator import download_gemma_from_github

        def raise_404(*args, **kwargs):
            raise HTTPError("url", 404, "Not Found", {}, None)

        monkeypatch.setattr(urllib.request, "urlopen", raise_404)

        # Use force=True to bypass the "already exists" check
        success, message = download_gemma_from_github(version="v99.99.99", force=True)

        assert success is False
        assert "not found" in message.lower() or "404" in message


class TestVersionMetadata:
    """Tests for version tracking metadata (Task 96.7)."""

    def test_status_has_version_fields(self):
        """Test status includes version and downloaded_at fields."""
        from token_audit.token_estimator import check_gemma_tokenizer_status

        # Verify the function returns the expected structure
        status = check_gemma_tokenizer_status()
        assert "version" in status
        assert "downloaded_at" in status

    def test_status_source_is_valid(self):
        """Test status source is one of expected values."""
        from token_audit.token_estimator import check_gemma_tokenizer_status

        status = check_gemma_tokenizer_status()
        assert status["source"] in ("bundled", "cached", "not_found")


class TestFallbackBehavior:
    """Tests for tokenizer fallback behavior (Task 96.7)."""

    def test_gemini_fallback_to_tiktoken(self, monkeypatch):
        """Test Gemini CLI falls back to tiktoken when no Gemma tokenizer."""
        # Mock _get_gemma_tokenizer_path to return None
        monkeypatch.setattr(
            TokenEstimator,
            "_get_gemma_tokenizer_path",
            staticmethod(lambda: None),
        )

        estimator = TokenEstimator.for_platform("gemini-cli")

        # Should use tiktoken fallback, not sentencepiece
        assert estimator._encoding is not None
        assert estimator._sp_processor is None
        assert estimator.method_name == "tiktoken"

    def test_estimation_properties_show_fallback(self, monkeypatch):
        """Test estimation properties when using tiktoken fallback for Gemini."""
        monkeypatch.setattr(
            TokenEstimator,
            "_get_gemma_tokenizer_path",
            staticmethod(lambda: None),
        )

        estimator = TokenEstimator.for_platform("gemini-cli")

        # When using tiktoken fallback for Gemini, method should be tiktoken
        assert estimator.method_name == "tiktoken"
        # Encoding should be cl100k_base (fallback encoding for Gemini)
        assert estimator.encoding_name == "cl100k_base"
        # The estimator successfully loaded tiktoken, so it works (even if approximate)
        assert estimator._encoding is not None

    def test_codex_cli_always_uses_tiktoken(self):
        """Test Codex CLI always uses tiktoken (no fallback needed)."""
        estimator = TokenEstimator.for_platform("codex-cli")

        assert estimator.method_name == "tiktoken"
        assert estimator.encoding_name == "o200k_base"
        # Not a fallback - this is the correct tokenizer
        assert estimator.is_fallback is False


class TestCICDPredictability:
    """Tests ensuring the command works well in non-interactive CI/CD environments (Task 96.7)."""

    def test_download_never_prompts_for_input(self, monkeypatch):
        """Test that download command never prompts for user input."""
        from token_audit.token_estimator import download_gemma_from_github
        import token_audit.token_estimator as te_module

        # Track if input() was called
        input_called = []

        def track_input(*args, **kwargs):
            input_called.append(True)
            return ""

        monkeypatch.setattr("builtins.input", track_input)
        monkeypatch.setattr(
            te_module,
            "check_gemma_tokenizer_status",
            lambda: {
                "installed": True,
                "location": "/fake/path",
                "source": "bundled",
                "version": None,
                "downloaded_at": None,
                "sentencepiece_available": True,
            },
        )

        # Run the function
        download_gemma_from_github()

        # Should never call input()
        assert len(input_called) == 0

    def test_functions_return_deterministic_types(self):
        """Test that all functions return expected types (no exceptions)."""
        from token_audit.token_estimator import (
            check_gemma_tokenizer_status,
            download_gemma_from_github,
            download_gemma_tokenizer,
        )

        # All these should return their expected types without raising
        status = check_gemma_tokenizer_status()
        assert isinstance(status, dict)

        github_result = download_gemma_from_github()
        assert isinstance(github_result, tuple)
        assert len(github_result) == 2

        hf_result = download_gemma_tokenizer()
        assert isinstance(hf_result, tuple)
        assert len(hf_result) == 2
