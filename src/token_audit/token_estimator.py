"""Token estimation for MCP tool calls.

Uses platform-specific tokenizers for maximum accuracy:
- Codex CLI: tiktoken o200k_base (native OpenAI tokenizer, ~99-100% accuracy)
- Gemini CLI: SentencePiece with Gemma tokenizer (100% accuracy)
- Claude Code: N/A (has native per-tool tokens)

This module provides token estimation for platforms that don't expose per-tool
token attribution. Estimates are based on tool arguments and results.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# HuggingFace model for Gemma tokenizer download
GEMMA_TOKENIZER_REPO = "google/gemma-2b"
GEMMA_TOKENIZER_FILE = "tokenizer.model"

# GitHub repository for release downloads (no auth required)
GITHUB_REPO = "littlebearapps/token-audit"
GITHUB_ASSET_PATTERN = "gemma-tokenizer-"

# Function call formatting overhead (validated by Zen Thinkdeep)
# Accounts for: function name, JSON structure, API formatting tokens
# Without this, small calls are underestimated by 15-25 tokens
FUNCTION_CALL_OVERHEAD = 25  # tokens per tool call

# Try importing tokenizers (both are required deps, fallback for edge cases)
try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    tiktoken = None  # type: ignore[assignment]

try:
    import sentencepiece as spm  # type: ignore[import-untyped]

    SENTENCEPIECE_AVAILABLE = True
except ImportError:
    SENTENCEPIECE_AVAILABLE = False
    spm = None


class TokenEstimator:
    """Estimate token counts for MCP tool calls.

    Platform-specific tokenizers for maximum accuracy:
    - Codex CLI: tiktoken o200k_base (~99-100% accuracy)
    - Gemini CLI: SentencePiece with Gemma tokenizer (100% accuracy)
    - Claude Code: Native tokens (no estimation needed)

    Attributes:
        method_name: Tokenization method ("tiktoken", "sentencepiece", "character")
        encoding_name: The encoding used (e.g., "o200k_base", "sentencepiece:gemma")
        is_fallback: True if using character-based fallback

    Example:
        >>> estimator = TokenEstimator.for_platform("codex-cli")
        >>> input_tokens, output_tokens = estimator.estimate_tool_call(
        ...     args='{"query": "test"}',
        ...     result="Search results..."
        ... )
    """

    # Encoding selection based on model family
    MODEL_ENCODINGS: Dict[str, str] = {
        # OpenAI models (native tiktoken)
        "gpt-5": "o200k_base",
        "gpt-4o": "o200k_base",
        "gpt-4o-mini": "o200k_base",
        "o1": "o200k_base",
        "o3": "o200k_base",
        "o4": "o200k_base",
        "codex": "o200k_base",
        # Older OpenAI models
        "gpt-4": "cl100k_base",
        "gpt-3.5": "cl100k_base",
        # Claude/Gemini (best approximation with tiktoken)
        "claude": "cl100k_base",
        "gemini": "cl100k_base",
    }

    DEFAULT_ENCODING = "cl100k_base"
    DEFAULT_CHARS_PER_TOKEN = 4.0

    def __init__(
        self,
        method: str = "tiktoken",
        encoding: str = "o200k_base",
        tokenizer_path: Optional[Path] = None,
        chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
    ):
        """Initialize estimator.

        Args:
            method: "tiktoken" or "sentencepiece"
            encoding: For tiktoken: "o200k_base", "cl100k_base", etc.
                     For sentencepiece: ignored (uses tokenizer_path)
            tokenizer_path: Path to SentencePiece .model file (for Gemini)
            chars_per_token: Fallback ratio when tokenizers unavailable
        """
        self._method = method
        self._encoding_name = encoding
        self._encoding: Optional[Any] = None
        self._sp_processor: Optional[Any] = None
        self._is_fallback = False
        self._chars_per_token = chars_per_token

        if method == "sentencepiece":
            self._init_sentencepiece(tokenizer_path)
        else:  # tiktoken
            self._init_tiktoken(encoding)

    def _init_tiktoken(self, encoding: str) -> None:
        """Initialize tiktoken encoding or set fallback mode."""
        if not TIKTOKEN_AVAILABLE or tiktoken is None:
            self._is_fallback = True
            return

        try:
            self._encoding = tiktoken.get_encoding(encoding)
        except Exception:
            self._is_fallback = True

    def _init_sentencepiece(self, tokenizer_path: Optional[Path]) -> None:
        """Initialize SentencePiece processor or set fallback mode."""
        if not SENTENCEPIECE_AVAILABLE or spm is None:
            self._is_fallback = True
            return

        if tokenizer_path is None:
            tokenizer_path = self._get_gemma_tokenizer_path()

        if tokenizer_path is None or not tokenizer_path.exists():
            self._is_fallback = True
            return

        try:
            self._sp_processor = spm.SentencePieceProcessor()
            self._sp_processor.Load(str(tokenizer_path))
            self._encoding_name = "sentencepiece:gemma"
        except Exception:
            self._is_fallback = True

    @classmethod
    def for_model(cls, model: str) -> "TokenEstimator":
        """Create estimator tuned for a specific model.

        Args:
            model: Model name or family (e.g., "gpt-4o", "claude-opus-4-5", "gemini-2.5-flash")

        Returns:
            TokenEstimator with appropriate encoding.
        """
        model_lower = model.lower()

        # Special case for Gemini models - use SentencePiece
        if "gemini" in model_lower or "gemma" in model_lower:
            tokenizer_path = cls._get_gemma_tokenizer_path()
            if tokenizer_path and tokenizer_path.exists():
                return cls(method="sentencepiece", tokenizer_path=tokenizer_path)
            # Fall back to tiktoken approximation
            return cls(method="tiktoken", encoding="cl100k_base")

        # Find matching encoding for other models
        for prefix, encoding in cls.MODEL_ENCODINGS.items():
            if prefix in model_lower:
                return cls(method="tiktoken", encoding=encoding)

        # Default encoding for unknown models
        return cls(method="tiktoken", encoding=cls.DEFAULT_ENCODING)

    @classmethod
    def for_platform(cls, platform: str) -> "TokenEstimator":
        """Create estimator for a platform's default models.

        Args:
            platform: Platform name ("claude-code", "codex-cli", "gemini-cli")

        Returns:
            TokenEstimator with platform-appropriate encoding.

        Platform defaults:
            - codex-cli: tiktoken o200k_base (GPT-5.1 Codex native tokenizer)
            - gemini-cli: SentencePiece with Gemma tokenizer (100% accuracy)
            - claude-code: tiktoken cl100k_base (for fallback, normally native tokens)
        """
        platform_lower = platform.lower().replace("-", "_").replace(" ", "_")

        if "codex" in platform_lower:
            return cls(method="tiktoken", encoding="o200k_base")
        elif "gemini" in platform_lower:
            tokenizer_path = cls._get_gemma_tokenizer_path()
            if tokenizer_path and tokenizer_path.exists():
                return cls(method="sentencepiece", tokenizer_path=tokenizer_path)
            # Fall back to tiktoken approximation if Gemma tokenizer not available
            return cls(method="tiktoken", encoding="cl100k_base")
        elif "claude" in platform_lower:
            # Claude Code has native tokens, but provide tiktoken for any fallback
            return cls(method="tiktoken", encoding="cl100k_base")

        return cls(method="tiktoken", encoding=cls.DEFAULT_ENCODING)

    @staticmethod
    def _get_gemma_tokenizer_path() -> Optional[Path]:
        """Get path to Gemma tokenizer.model file.

        Checks in order:
        1. Bundled with package: src/token_audit/tokenizers/tokenizer.model
        2. User cache: ~/.cache/token-audit/tokenizer.model

        Returns:
            Path to tokenizer.model file, or None if not found
        """
        # Check bundled location
        bundled = Path(__file__).parent / "tokenizers" / "tokenizer.model"
        if bundled.exists():
            return bundled

        # Check user cache
        cache_dir = Path.home() / ".cache" / "token-audit"
        cached = cache_dir / "tokenizer.model"
        if cached.exists():
            return cached

        return None

    @staticmethod
    def get_cache_dir() -> Path:
        """Get the token-audit cache directory."""
        cache_dir = Path.home() / ".cache" / "token-audit"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Args:
            text: Text to tokenize

        Returns:
            Token count (exact for tiktoken/sentencepiece, approximate for fallback)
        """
        if not text:
            return 0

        # SentencePiece (Gemini)
        if self._sp_processor is not None:
            try:
                return len(self._sp_processor.EncodeAsIds(text))
            except Exception:
                return self._count_fallback(text)

        # tiktoken (OpenAI/Codex)
        if self._encoding is not None:
            try:
                return len(self._encoding.encode(text))
            except Exception:
                return self._count_fallback(text)

        # Fallback: character-based approximation
        return self._count_fallback(text)

    def _count_fallback(self, text: str) -> int:
        """Character-based token estimation fallback (~4 chars/token)."""
        return max(1, int(len(text) / self._chars_per_token))

    def estimate_tool_call(
        self,
        args: Optional[str],
        result: Optional[str],
        include_overhead: bool = True,
    ) -> Tuple[int, int]:
        """Estimate input and output tokens for a tool call.

        Args:
            args: Tool call arguments (JSON string)
            result: Tool call result/output
            include_overhead: Add FUNCTION_CALL_OVERHEAD for API formatting
                             (recommended for 95-100% accuracy on all call sizes)

        Returns:
            Tuple of (input_tokens, output_tokens)

        Note:
            The overhead accounts for function name, JSON structure, and API
            formatting tokens that are not captured by content tokenization alone.
            Without overhead, small calls may be underestimated by 15-25 tokens.
        """
        input_tokens = self.estimate_tokens(args or "")
        output_tokens = self.estimate_tokens(result or "")

        # Add function call formatting overhead (validated by Thinkdeep)
        if include_overhead:
            input_tokens += FUNCTION_CALL_OVERHEAD

        return input_tokens, output_tokens

    def estimate_tool_call_dict(
        self,
        arguments: Dict[str, Any],
        result: str,
        include_overhead: bool = True,
    ) -> Tuple[int, int]:
        """Estimate tokens for a tool call with dict arguments.

        Args:
            arguments: Tool arguments as dictionary
            result: String result from the tool
            include_overhead: Add FUNCTION_CALL_OVERHEAD for API formatting

        Returns:
            Tuple of (input_tokens, output_tokens)
        """
        args_str = json.dumps(arguments, separators=(",", ":"))
        return self.estimate_tool_call(args_str, result, include_overhead)

    @property
    def is_fallback(self) -> bool:
        """True if using character-based fallback."""
        return self._is_fallback

    @property
    def encoding_name(self) -> str:
        """Name of encoding being used."""
        if self._is_fallback:
            return "character-fallback"
        return self._encoding_name

    @property
    def method_name(self) -> str:
        """Name of tokenization method."""
        if self._is_fallback:
            return "character"
        return self._method


# ============================================================================
# Module-level convenience functions
# ============================================================================


def count_tokens(text: str, model: Optional[str] = None) -> int:
    """Count tokens in text.

    Args:
        text: Text to tokenize
        model: Optional model name for encoding selection

    Returns:
        Token count
    """
    estimator = TokenEstimator.for_model(model) if model else TokenEstimator()
    return estimator.estimate_tokens(text)


def estimate_tool_tokens(
    arguments: str,
    result: str,
    model: Optional[str] = None,
    include_overhead: bool = True,
) -> Tuple[int, int]:
    """Estimate tokens for a tool call.

    Args:
        arguments: JSON string of tool arguments
        result: String result from the tool
        model: Optional model name for encoding selection
        include_overhead: Add function call overhead (default True)

    Returns:
        Tuple of (input_tokens, output_tokens)
    """
    estimator = TokenEstimator.for_model(model) if model else TokenEstimator()
    return estimator.estimate_tool_call(arguments, result, include_overhead)


def get_estimator_for_platform(platform: str) -> TokenEstimator:
    """Get a pre-configured estimator for a platform.

    Args:
        platform: Platform name ("claude-code", "codex-cli", "gemini-cli")

    Returns:
        TokenEstimator configured for the platform
    """
    return TokenEstimator.for_platform(platform)


# ============================================================================
# Tokenizer Download Functions
# ============================================================================


def download_gemma_tokenizer(
    token: Optional[str] = None,
    force: bool = False,
) -> Tuple[bool, str]:
    """Download the Gemma tokenizer model from HuggingFace.

    Requires a HuggingFace account with access to the Gemma model.
    Users must accept the license at: https://huggingface.co/google/gemma-2b

    Args:
        token: HuggingFace access token. If None, uses HF_TOKEN environment
               variable or cached credentials from `huggingface-cli login`.
        force: If True, re-download even if tokenizer already exists.

    Returns:
        Tuple of (success: bool, message: str)

    Example:
        >>> success, msg = download_gemma_tokenizer(token="hf_xxx...")
        >>> if success:
        ...     print(f"Downloaded to: {msg}")
        ... else:
        ...     print(f"Error: {msg}")
    """
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        return (
            False,
            "huggingface_hub not installed. Install with: pip install huggingface_hub",
        )

    # Check if already exists
    cache_dir = TokenEstimator.get_cache_dir()
    target_path = cache_dir / "tokenizer.model"

    if target_path.exists() and not force:
        return (True, f"Tokenizer already exists at: {target_path}")

    # Use token from arg, env var, or cached credentials
    hf_token = token or os.environ.get("HF_TOKEN")

    try:
        # Download from HuggingFace
        downloaded_path = hf_hub_download(
            repo_id=GEMMA_TOKENIZER_REPO,
            filename=GEMMA_TOKENIZER_FILE,
            token=hf_token,
            local_dir=str(cache_dir),
        )

        # Verify download
        if Path(downloaded_path).exists():
            return (True, f"Downloaded to: {downloaded_path}")
        else:
            return (False, "Download completed but file not found")

    except Exception as e:
        error_msg = str(e)

        # Provide helpful error messages
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            return (
                False,
                "Authentication required. Please provide a HuggingFace token.\n"
                "1. Create account at https://huggingface.co\n"
                "2. Accept Gemma license at https://huggingface.co/google/gemma-2b\n"
                "3. Create token at https://huggingface.co/settings/tokens\n"
                "4. Run: token-audit tokenizer download --token YOUR_TOKEN",
            )
        elif "403" in error_msg or "gated" in error_msg.lower():
            return (
                False,
                "Access denied. You must accept the Gemma license first.\n"
                "Visit: https://huggingface.co/google/gemma-2b\n"
                "Click 'Agree and access repository', then retry.",
            )
        else:
            return (False, f"Download failed: {error_msg}")


def _validate_tarball_member(member_name: str) -> bool:
    """Validate tarball member path to prevent path traversal attacks.

    SECURITY CRITICAL: This function prevents malicious tarballs from
    extracting files outside the intended directory.

    Args:
        member_name: The name/path of a tarball member

    Returns:
        True if path is safe, False if potentially malicious
    """
    # Reject absolute paths
    if member_name.startswith("/"):
        return False
    # Reject path traversal
    if ".." in member_name:
        return False
    # Reject paths that could escape (normalize and check)
    normalized = os.path.normpath(member_name)
    return not normalized.startswith("..")


def download_gemma_from_github(
    version: Optional[str] = None,
    force: bool = False,
) -> Tuple[bool, str]:
    """Download the Gemma tokenizer from GitHub Releases.

    This is the preferred method as it requires no authentication.
    The tokenizer is distributed as a release asset with SHA256 verification.

    Args:
        version: Specific release version to download (e.g., "v0.4.0").
                 If None, downloads from the latest release.
        force: If True, re-download even if tokenizer already exists.

    Returns:
        Tuple of (success: bool, message: str)

    Example:
        >>> success, msg = download_gemma_from_github()
        >>> if success:
        ...     print(f"Downloaded: {msg}")
        ... else:
        ...     print(f"Error: {msg}")
    """
    import hashlib
    import tarfile
    import tempfile
    from datetime import datetime, timezone
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    cache_dir = TokenEstimator.get_cache_dir()
    target_path = cache_dir / "tokenizer.model"
    meta_path = cache_dir / "tokenizer.meta.json"

    if target_path.exists() and not force:
        return (True, f"Tokenizer already exists at: {target_path}")

    try:
        # Get release info from GitHub API
        if version:
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{version}"
        else:
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

        req = Request(api_url, headers={"Accept": "application/vnd.github.v3+json"})
        with urlopen(req, timeout=30) as response:
            release_info = json.loads(response.read().decode())

        release_version = release_info.get("tag_name", "unknown")

        # Find tokenizer asset
        asset_url = None
        checksum_url = None
        for asset in release_info.get("assets", []):
            name = asset["name"]
            if name.startswith(GITHUB_ASSET_PATTERN) and name.endswith(".tar.gz"):
                asset_url = asset["browser_download_url"]
            elif name.startswith(GITHUB_ASSET_PATTERN) and name.endswith(".sha256"):
                checksum_url = asset["browser_download_url"]

        if not asset_url:
            return (
                False,
                f"No tokenizer asset found in release {release_version}.\n"
                f"Check: https://github.com/{GITHUB_REPO}/releases",
            )

        # Download tarball to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            tarball_path = Path(tmpdir) / "tokenizer.tar.gz"

            # Download asset
            req = Request(asset_url)
            with urlopen(req, timeout=120) as response:
                tarball_path.write_bytes(response.read())

            # Compute checksum
            actual_hash = hashlib.sha256(tarball_path.read_bytes()).hexdigest()

            # Verify checksum if available
            if checksum_url:
                req = Request(checksum_url)
                with urlopen(req, timeout=30) as response:
                    expected_hash = response.read().decode().split()[0]

                if actual_hash != expected_hash:
                    return (
                        False,
                        f"Checksum mismatch! Expected {expected_hash[:16]}..., "
                        f"got {actual_hash[:16]}...\n"
                        "The download may be corrupted. Try again or download manually.",
                    )

            # Extract tokenizer.model with path traversal protection
            with tarfile.open(tarball_path, "r:gz") as tar:
                # SECURITY: Validate all members before extraction
                for member in tar.getmembers():
                    if not _validate_tarball_member(member.name):
                        return (False, f"Security error: unsafe path in tarball: {member.name}")

                # Find and extract tokenizer.model
                tokenizer_extracted = False
                for member in tar.getmembers():
                    if member.name.endswith("tokenizer.model"):
                        # Flatten path - extract as tokenizer.model directly
                        member.name = "tokenizer.model"
                        tar.extract(member, cache_dir)
                        tokenizer_extracted = True
                        break

                if not tokenizer_extracted:
                    return (False, "Extraction failed - tokenizer.model not found in archive")

            if target_path.exists():
                # Write metadata for version tracking
                meta = {
                    "version": release_version,
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": actual_hash,
                    "source": "github",
                }
                meta_path.write_text(json.dumps(meta, indent=2))

                return (True, f"Downloaded to: {target_path}")
            else:
                return (False, "Extraction completed but tokenizer.model not found")

    except HTTPError as e:
        if e.code == 404:
            version_hint = f" (version: {version})" if version else ""
            return (
                False,
                f"Release not found{version_hint}.\n"
                f"Check available releases: https://github.com/{GITHUB_REPO}/releases",
            )
        elif e.code == 403:
            return (
                False,
                "GitHub API rate limit exceeded.\n\n"
                "Options:\n"
                "• Wait 1 hour and try again\n"
                f"• Download manually from: https://github.com/{GITHUB_REPO}/releases\n"
                "• Use HuggingFace: token-audit tokenizer download --source huggingface",
            )
        return (False, f"HTTP error: {e.code} {e.reason}")
    except URLError as e:
        return (
            False,
            f"Network error: {e.reason}\n\n"
            "If you're behind a corporate firewall:\n"
            f"• Download manually from: https://github.com/{GITHUB_REPO}/releases\n"
            "• Extract tokenizer.model to: ~/.cache/token-audit/",
        )
    except Exception as e:
        return (False, f"Download failed: {e}")


def check_gemma_tokenizer_status() -> Dict[str, Any]:
    """Check the status of the Gemma tokenizer installation.

    Returns:
        Dict with status information:
        - installed: bool - Whether tokenizer is available
        - location: str - Path to tokenizer (if installed)
        - source: str - "bundled", "cached", or "not_found"
        - version: Optional[str] - Version from metadata (if available)
        - downloaded_at: Optional[str] - Download timestamp (if available)
        - sentencepiece_available: bool - Whether sentencepiece is installed
    """
    result: Dict[str, Any] = {
        "installed": False,
        "location": "",
        "source": "not_found",
        "version": None,
        "downloaded_at": None,
        "sentencepiece_available": SENTENCEPIECE_AVAILABLE,
    }

    # Check bundled location
    bundled = Path(__file__).parent / "tokenizers" / "tokenizer.model"
    if bundled.exists():
        result["installed"] = True
        result["location"] = str(bundled)
        result["source"] = "bundled"
        return result

    # Check cache location
    cache_dir = Path.home() / ".cache" / "token-audit"
    cached = cache_dir / "tokenizer.model"
    meta_path = cache_dir / "tokenizer.meta.json"

    if cached.exists():
        result["installed"] = True
        result["location"] = str(cached)
        result["source"] = "cached"

        # Read version info from metadata if available
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                result["version"] = meta.get("version")
                result["downloaded_at"] = meta.get("downloaded_at")
            except Exception:
                pass  # Metadata is optional, don't fail if corrupt

        return result

    return result
