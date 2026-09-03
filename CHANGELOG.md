# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> 🌏 [中文版（CHANGELOG.zh-CN.md）](CHANGELOG.zh-CN.md)

## [0.2.1] - 2026-09-04

### Fixed
- Docs (SKILL.md + both READMEs) quoted an error string the script never
  prints (`Cannot locate Hermes installation`); Troubleshooting now shows
  the real output (`Could not import Hermes internals (...)`) with the two
  likely causes in likelihood order (wrong interpreter / data dir not found)
- SKILL.md referenced `run_agent._prepare_messages_for_api`, which does not
  exist in the Hermes upstream; it now points at the real API-time
  preprocessing (`_preprocess_anthropic_content` / `_strip_images_from_messages`)

### Added
- `check_vision_path.py` prints a warning when `$HERMES_HOME` is set but
  nonexistent: the Hermes core uses such a path as-is (empty config) while
  the checker falls back to `~/.hermes` — the warning makes the asymmetry
  visible so the verdict can be compared against the runtime; both READMEs
  document the new symptom

## [0.2.0] - 2026-09-04

### Added
- Initial public release: bilingual README (English + zh-CN), MIT license
- Portable `HERMES_HOME` detection (`HERMES_HOME` env var → `~/.hermes`
  fallback) and friendly import errors instead of tracebacks
- First-run setup guidance: a five-step decision tree covering every
  configuration combination, including the `auto` + explicit
  `auxiliary.vision` suppression trap and fresh-install cache misses
- Model-switch self-check procedure and an explicit
  "Hermes Agent only" scope declaration

### Changed
- Docs describe the tool-result carrying mechanism functionally, keeping
  the source term (`_multimodal` envelope) as a traceable alias at first
  mention instead of bare jargon

## [0.1.0] - 2026-09-03

- Internal first version (Chinese, machine-local paths, single-language);
  superseded by 0.2.0 and never published
