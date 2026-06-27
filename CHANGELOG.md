# Changelog

## Unreleased

### Added
- Added `python doctor.py --markdown` to generate a GitHub issue-ready diagnostic report.

## v1.1.0 - 2026-06-23

### Added
- Added the Blindbox experiment engine, maintenance flow, reporting helpers, scheduler support, and Streamlit UI module.
- Added the full upgrade/backtest pipeline with scheduler utilities and command-line runners.
- Added capability registry integrations for AutoGen/AG2, Composio, browser-use, Letta, and Agent Lightning adapters.
- Added loop health, execution coverage, and upgrade reporting helpers for daily maintenance.
- Added regression tests covering the new scheduler, blindbox, metrics, strategy display, trade simulator, and agent helper behavior.

### Changed
- Synced the repository with the latest local project snapshot from `C:\Users\1\Desktop\KIMIstock\gemini`.
- Expanded dashboard modules and agent tooling to expose the new maintenance and experiment workflows.
- Updated runtime/config examples and requirements for the upgraded agent stack.

### Removed
- Removed the old local license-gating scripts and checks that are no longer part of the current project snapshot.

### Verification
- `python -m unittest discover -s tests -v` passed: 63 tests.
- `python -m compileall -q core modules skills ui tests tools dashboard.py doctor.py` passed.
- `git diff --check` passed after whitespace cleanup.
