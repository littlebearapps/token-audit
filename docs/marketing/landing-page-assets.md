# Token Audit Landing Page Assets

**Last Updated:** 2025-12-14

Asset checklist for littlebearapps.com/token-audit landing page.

---

## Hero Assets

| Asset | Filename | Specs | How to Create |
|-------|----------|-------|---------------|
| Demo GIF | `hero-demo.gif` | 800x500px, 3-5s loop, <2MB | Record `token-audit collect` with active session |
| Demo MP4 (fallback) | `hero-demo.mp4` | 800x500px, 3-5s, H.264 | Convert from GIF or record directly |

### Demo GIF Content
Show the TUI tracking a live Claude Code session:
1. Session starts with 0 tokens
2. MCP tool calls appear in real-time
3. Token counts increment
4. Smell detection triggers (optional)

**Recording command:**
```bash
# Terminal 1: Start token-audit
token-audit collect --platform claude-code

# Terminal 2: Use Claude Code normally
# Record Terminal 1 with screen capture tool
```

---

## Feature Screenshots

| Asset | Filename | Specs | Content |
|-------|----------|-------|---------|
| Token breakdown | `feature-tokens.png` | 600x400px | TUI main view with session table |
| Smell detection | `feature-smells.png` | 600x400px | TUI showing detected smells |
| Multi-model view | `feature-models.png` | 600x400px | Session with model switching |
| Report output | `feature-report.png` | 600x400px | `token-audit report` terminal output |

### Screenshot Guidelines
- Use dark terminal theme (consistent with TUI)
- Crop to relevant content area
- Include realistic data (not placeholder)
- Highlight key information if needed

---

## Platform Logos

| Platform | Filename | Source | Notes |
|----------|----------|--------|-------|
| Claude Code | `logo-claude-code.svg` | Anthropic brand assets | Check usage guidelines |
| Codex CLI | `logo-codex.svg` | OpenAI brand assets | Check usage guidelines |
| Gemini CLI | `logo-gemini.svg` | Google brand assets | Check usage guidelines |
| Ollama | `logo-ollama.svg` | Ollama brand assets | "Coming Soon" badge |

### Logo Usage
- Uniform sizing (64x64px recommended)
- Grayscale or full color (match page design)
- Include alt text for accessibility

---

## Icons

| Icon | Purpose | Suggestion |
|------|---------|------------|
| Real-time | Feature 1 | Line chart with pulse indicator |
| Smell detection | Feature 2 | Warning triangle or magnifying glass |
| Multi-model | Feature 3 | Stacked circles or model icons |
| Privacy | Feature 4 | Lock or shield |
| Cross-platform | Feature 5 | Grid of platform icons |

**Icon style:** Outline icons, consistent stroke width, monochrome or accent color

---

## Trust Badges

| Badge | Source | Display |
|-------|--------|---------|
| PyPI version | shields.io | `https://img.shields.io/pypi/v/token-audit` |
| Python versions | shields.io | `https://img.shields.io/pypi/pyversions/token-audit` |
| License | shields.io | `https://img.shields.io/github/license/littlebearapps/token-audit` |
| Socket.dev | socket.dev | Security badge (if available) |

---

## Social/OG Images

| Asset | Filename | Specs | Content |
|-------|----------|-------|---------|
| OG Image | `og-image.png` | 1200x630px | Logo + tagline + demo preview |
| Twitter Card | `twitter-card.png` | 1200x600px | Same as OG or variant |

### OG Image Content
- Token Audit logo (top left)
- Tagline: "Real-time MCP token profiler"
- TUI screenshot preview (right side)
- Dark background matching brand

---

## Directory Structure

```
docs/marketing/
├── landing-page-copy.md      # This file
├── landing-page-assets.md    # Asset checklist
└── assets/                   # Asset files (when created)
    ├── hero-demo.gif
    ├── hero-demo.mp4
    ├── feature-tokens.png
    ├── feature-smells.png
    ├── feature-models.png
    ├── feature-report.png
    ├── logo-claude-code.svg
    ├── logo-codex.svg
    ├── logo-gemini.svg
    ├── logo-ollama.svg
    ├── og-image.png
    └── twitter-card.png
```

---

## Asset Creation Priority

### P0 - Required for Launch
1. `hero-demo.gif` - Hero section demo
2. `og-image.png` - Social sharing
3. Platform logos (or use text placeholders)

### P1 - Nice to Have
4. Feature screenshots (4)
5. Custom icons (5)
6. Trust badges

### P2 - Future Enhancement
7. Video walkthrough
8. Animated feature demos
9. User testimonial photos

---

## Tools for Asset Creation

| Task | Recommended Tool |
|------|------------------|
| Screen recording | macOS Screenshot, OBS, Kap |
| GIF conversion | ffmpeg, Gifski |
| Screenshots | macOS Screenshot, CleanShot X |
| Image editing | Figma, Photoshop |
| SVG optimization | SVGO, Figma export |
