---
name: Release Checklist
about: Track release preparation for a new version (maintainers only)
title: 'Release v[VERSION]'
labels: 'release'
assignees: ''
---

## Release v[VERSION]

**Target Date**: [DATE]
**Milestone**: [Link to milestone]

---

### Pre-Release Checklist

#### Code Readiness
- [ ] All planned features for this release are merged
- [ ] All bug fixes for this release are merged
- [ ] No critical issues remain open for this milestone
- [ ] All tests passing on main branch

#### Documentation
- [ ] CHANGELOG.md updated with all changes
- [ ] README.md updated if needed (new features, breaking changes)
- [ ] ROADMAP.md updated (move completed items, update status)
- [ ] Platform guides updated if CLI integrations changed

#### Validation
- [ ] Run release test workflow:
  ```bash
  gh workflow run release-test.yml -f version=[VERSION]
  ```
- [ ] Review test results - all jobs should pass
- [ ] Verify tokenizer assets exist in `src/token_audit/tokenizers/`

---

### Release Execution

#### Bump Version
- [ ] Update version in `pyproject.toml` to `[VERSION]`
- [ ] Commit: `git commit -m "chore: bump version to [VERSION]"`
- [ ] Push: `git push origin main`

#### Monitor Automated Release
- [ ] `auto-tag.yml` creates tag v[VERSION]
- [ ] `release-pipeline.yml` triggered automatically
- [ ] Master GitHub Release created with tokenizer assets
- [ ] Public repo synced and tagged
- [ ] `publish-pypi.yml` triggered in public repo
- [ ] PyPI publish successful
- [ ] Release announcement Discussion created

---

### Post-Release Verification

#### Verify Artifacts
- [ ] Check PyPI: https://pypi.org/project/token-audit/[VERSION]/
- [ ] Check master release: https://github.com/littlebearapps/token-audit-master/releases/tag/v[VERSION]
- [ ] Check public release: https://github.com/littlebearapps/token-audit/releases/tag/v[VERSION]
- [ ] Verify tokenizer download works:
  ```bash
  pip install token-audit
  token-audit tokenizer download
  ```

#### Verify Announcement
- [ ] Check Discussion: https://github.com/littlebearapps/token-audit/discussions
- [ ] CHANGELOG content appears in announcement

---

### Rollback (if needed)

If release fails, follow these steps:

1. **Delete tags** (both repos):
   ```bash
   git tag -d v[VERSION]
   git push origin --delete v[VERSION]
   gh api -X DELETE /repos/littlebearapps/token-audit/git/refs/tags/v[VERSION]
   ```

2. **Delete releases**:
   ```bash
   gh release delete v[VERSION] --repo littlebearapps/token-audit-master --yes
   gh release delete v[VERSION] --repo littlebearapps/token-audit --yes
   ```

3. **PyPI**: Cannot delete, but can yank:
   - Go to https://pypi.org/manage/project/token-audit/releases/
   - Select version and click "Yank"

---

### Notes

<!-- Add any release-specific notes here -->
