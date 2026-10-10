# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> 🌏 [中文版（CHANGELOG.zh-CN.md）](CHANGELOG.zh-CN.md)

## [0.5.0] - 2026-10-10

### Added
- Session runtime model resolution in `check_vision_path.py` — the /model
  hot-swap trap is now a solved problem instead of a documented caveat:
  - `--session <id>`: authoritative runtime pair from
    `<hermes-home>/state.db` → `session_model_usage` (task='' is the main
    conversation; read-only connection + schema validation; explicit
    "schema mismatch" error on upstream drift, never silently wrong
    output).
  - `--anchor '<message prefix>'`: greps `agent.log` turn_context lines
    with the message prefix, then CONFIRMS against session_model_usage;
    on log/DB discrepancy prints DISCREPANCY and uses the newer pair.
  - No-args dual view: config main model + most-recent active session
    side by side; a MISMATCH block flags hot-swaps unprompted (heuristic
    for display; multiple concurrent TUI windows = multiple sessions).
  - Robustness: read-only DB open (WAL-safe), explicit errors with
    fallback suggestions for every failure mode (unknown session, anchor
    miss, bad flags), measured log limits respected (msg= truncates ~90
    chars / first line only / ~5 MB rotation).
- Two new Pitfalls from the 2026-10-10 live incident (a config override
  declared a text-only model as vision-capable):
  - "The native first line is a declaration, not delivery proof": the
    runtime tool gate also reads the CONFIG pair, so in a hot-swapped
    session it can wrap images for a model that cannot see them — the
    first line says `Image loaded` while the send path silently drops
    the pixels. In-session evidence rules: the answer must reflect the
    pixels, and the next API call must grow by image-size tokens
    (thousands for a real 0.2 MB image vs hundreds for a stripped note).
  - "`supports_vision` overrides are assumptions — test before trusting
    them": a false `true` is the mirror image of a stale veto (xiaomi
    case): a stale veto honestly blocks a working path, a false true
    actively misroutes. Endpoint-qualified naming required — the same
    family can be multimodal on one endpoint and text-only on another
    (deepseek-flash @ deepseek vs deepseek-v4-flash-0731 /
    glm-5.3-class on aggregators).
- Registry: negative entry for intern-inkstone/glm-5.3 (override removed
  2026-10-10 after two failed real-image tests; models.dev confirms
  text-only across 30+ providers) and an UNVERIFIED entry for
  intern-inkstone/deepseek-v4-flash-vision (declared, but the model
  could not issue valid tool calls to complete verification).
- `probe_tool_media.py`: non-standard env-var key fallback (e.g.
  `INTER_INKSTONE_API_KEY` for intern-inkstone) + base-url default for
  intern-inkstone.

### Changed
- Bumped 0.4.1 → 0.5.0 before release: the scope (new CLI modes, new
  document section, new verification methodology) is a minor bump, not a
  patch.

### Added
- Session runtime model resolution in `check_vision_path.py` — the /model
  hot-swap trap is now a solved problem instead of a documented caveat:
  - `--session <id>`: authoritative runtime pair from
    `<hermes-home>/state.db` → `session_model_usage` (task='' is the main
    conversation; read-only connection + schema validation; explicit
    "schema mismatch" error on upstream drift, never silently wrong
    output).
  - `--anchor '<message prefix>'`: greps `agent.log` turn_context lines
    with the message prefix, then CONFIRMS against session_model_usage;
    on log/DB discrepancy prints DISCREPANCY and uses the newer pair.
  - No-args dual view: config main model + most-recent active session
    side by side; a MISMATCH block flags hot-swaps unprompted (heuristic
    for display; multiple concurrent TUI windows = multiple sessions).
  - Freshness boundary documented in output and docs: `last_seen` marks
    the last API call — a hot-swap appears only after the next message.
  - Robustness: read-only DB open (WAL-safe), explicit errors with
    fallback suggestions for every failure mode (unknown session, anchor
    miss, bad flags), measured log limits respected (msg= truncates ~90
    chars / first line only / ~5 MB rotation).

## [0.4.0] - 2026-10-10

### Added
- `scripts/probe_tool_media.py`: decisive two-request endpoint probe (1×1
  red PNG, tool-result vs user-message channel) that ARBITRATES a profile
  veto instead of trusting the declaration — the declaration is a
  hypothesis about the endpoint, the probe is ground truth. Built-in
  verdict rules: a 200 alone is not enough (the model must name the probe
  colour — acceptance ≠ capability); a 400 is classified as a
  content/format error (declaration accurate) vs a model-id error (retired
  id, not channel evidence). Keys are read in-process and never printed.
- "Stale veto declaration" flow in Pitfalls: when the probe contradicts
  `supports_vision_tool_messages=False`, correct the plugin profile itself —
  backup + hash manifest → census every model still in use under the
  provider → flip the flag → restart processes → layered verification →
  registry entry. Config cannot lift a veto; the plugin profile can.
- Unknown-model gate: new branch for FALLBACK + `model vision: True` +
  veto note ("capability present, channel vetoed") that routes to the
  probe before any decision.
- Case study in `references/vision-channels-and-vetoes.md`: a stale veto
  held a fully multimodal model on the lossy fallback path until the probe
  disproved the declaration (plus the probe section now links the script).
- `references/confirmed-vision-models.md`: registry entry documenting the
  full probe → fix → post-restart acceptance evidence chain.
- Operational worked examples so no agent has to re-explore: concrete
  agent-host restart recipes (TUI `/exit` + `hermes --tui`, dashboard
  stop/start, external gateway restart; multi-window note; mtime-vs-`ps`
  staleness check), a concrete model-census procedure for the flip safety
  check (config grep + `GET /models` + probe each id), and a
  worked-example pointer on the gate branch.

### Changed
- Small-text misreads are path-neutral: confident wrong reads happen
  on BOTH paths (observed: native read "8" in a "80" subtitle on a 421×249
  frame while the aux transcription got it right). Never build a
  path-quality argument on a single small-text read — re-view a crop
  (`region=`) first; treat both paths' opinions as hypotheses.
- Plugin profile changes take effect only when the agent host PROCESS
  restarts (module-level `sys.modules` cache in the provider loader): a
  gateway restart alone is not enough, and a new session inside the same
  TUI/dashboard process does not reload plugin Python. The checker (fresh
  subprocess) verifies disk state immediately; the real-image acceptance
  test only counts inside the restarted process.
- The "veto is the cause" guidance now says to arbitrate with the probe
  first and only then fall back to the user-message channel / aux
  transcription.

## [0.3.1] - 2026-10-09

### Fixed
- `check_vision_path.py` two-argument branch now calls the upstream gate
  `_native_tool_result_images(provider, model, cfg)` instead of recomputing
  the predicate locally (issue #1). The old formula skipped the profile hard
  veto (`_profile_rejects_tool_media`), so it reported NATIVE for providers
  whose tool-result image content is rejected with HTTP 400 (xiaomi/MiMo) —
  a user trusting the verdict got an error instead of pixels. Older installs
  without the parameterized gate now fall back to an explicit veto check.
- Both READMEs: the decision tree shows the three upstream layers in order
  (routing → profile veto → static table / capability lookup), names the 13
  explicit `_TOOL_RESULT_MEDIA_PROVIDERS` ids ("aggregators" is not a literal
  table value) and the `_GEMINI_PROVIDERS` gemini-3 model-tag check.
- SKILL.md: `_describe_image_for_anthropic_fallback` path corrected to
  `agent/vision_message_prep.py` (the old `run_agent.py` location no longer
  resolves).

### Added
- The checker prints a note when a profile veto forces FALLBACK, so a
  400-rejecting provider is not mistaken for a missing capability.

## [0.3.0] - 2026-09-10

### Added
- "Procedure: first image call in a session (unknown-model gate)" and
  "Quick verdict" sections in SKILL.md: gate once per session / after a model
  switch. When the verdict is FALLBACK and the capability lookup returns None
  (unknown model), ask the user whether the model is multimodal and register
  it before trusting vision output — the session that produced this release
  lost ~13 verification rounds to a silently lossy fallback.
- `references/confirmed-vision-models.md` — append-only registry of
  user-confirmed vision-capable models (evidence + config record per entry).
- `check_vision_path.py` detects the provider-alias mapping gap
  (`PROVIDER_TO_MODELS_DEV` missing an alias while the disk cache holds a
  vision-capable record) and prints the escaped-dot
  `model_overrides.<provider>.<model>.supports_vision` workaround.

### Notes
- Prefer scoped `model_overrides.<provider>.<model>.supports_vision` over a
  global `model.supports_vision` (the global flag misdeclares text-only
  models after a switch). Model ids containing dots need `\.` escaping in
  `hermes config set`; the on-disk models.dev cache is NOT hand-editable
  (the TTL refresh discards manual entries).

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
  briefly used for small-scale internal testing before deployment;
  superseded by 0.2.0 and never published
