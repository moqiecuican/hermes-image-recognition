# Confirmed vision-capable models (user-verified registry)

Append-only log of provider/model pairs whose multimodal capability has been
CONFIRMED by the user and verified via the native path. When the current
session's main model appears here, skip the unknown-model gate question —
the answer is already known and the config record should already exist.

Format: one entry per provider/model. Add new entries at the bottom with
the date, the evidence, and the config key that carries the declaration.

---

## alibaba-cn / qwen3.8-flash
- Confirmed: 2026-09-10, user-verified native multimodal
- Config record: `model_overrides.alibaba-cn.qwen3\.8-flash.supports_vision: true`
  (scoped; global `model.supports_vision` deliberately removed same day)
- Evidence: `models_dev_cache.json` entry has `attachment: true`,
  `modalities.input: [text, image, video]`; checker verdict NATIVE;
  real-image test shows "Image loaded into your context" first line and
  constraint-respecting one-sentence answers.
- Known gap: `PROVIDER_TO_MODELS_DEV` (agent/models_dev.py) lacks the
  `alibaba-cn` alias (upstream bug, still present on main 2026-09-10; the
  alias was missed when PR #73345 registered the CN provider). EVERY model
  under alibaba-cn is affected until upstream fixes it — e.g. qwen3.7-plus
  and qwen3.6-flash are `attachment: true` in cache but resolve to None;
  add scoped overrides for them the same way when they become main models.

## deepseek / deepseek-flash
- Confirmed: 2026-10-08, direct probe (user asked "deepseek flash 能不能触发
  原生多模态")
- Config record: none needed — `agent.image_input_mode: native` + models.dev
  catalog `attachment: true, input: [text, image]` already yield checker
  verdict NATIVE with no override.
- Evidence: checker (`check_vision_path.py deepseek deepseek-flash`) →
  `model vision: True`, path NATIVE; raw `/chat/completions` probe with a
  1×1 red PNG answered "Red".
- Contrast: `deepseek-v4-pro` accepts the image block without erroring but
  answers "Unknown" on the same probe, and models.dev marks it
  `attachment: false` — acceptance ≠ capability, do not list it as
  vision-capable.
- Naming: the official API id is now `deepseek-flash` (a 400 on the older
  `deepseek-v4-flash-0731` id enumerates the two current names:
  `deepseek-flash`, `deepseek-v4-pro`).

## alibaba-cn / qwen3.8-max
- Confirmed: 2026-09-30, user-verified (scoped override applied after a
  mid-session model switch flash→max silently dropped vision to the aux
  paraphrase path)
- Config record: `model_overrides.alibaba-cn.qwen3\.8-max.supports_vision: true`
  (scoped; written via `hermes config set` with escaped dots; yaml read-back
  shows a single literal key, no bogus nesting)
- Evidence: checker verdict flipped `model vision: None → True`,
  `FALLBACK → NATIVE`; real-image test on /tmp/qjz_snack3.png returned the
  "Image loaded into your context" first line and a constraint-respecting
  one-sentence answer (1 snackbar), matching the independent uiautomator
  text scan.
- Same upstream alias gap as qwen3.8-flash above; `models_dev_cache.json`
  records qwen3.8-max under alibaba-cn as vision-capable but the lookup can
  never reach it without this override.

## xiaomi / mimo-v2.6-pro
- Confirmed: 2026-10-10, decisive probe after checker reported FALLBACK
- Config record: none in config.yaml — the blocker was the provider plugin
  profile's `supports_vision_tool_messages=False` in
  `plugins/model-providers/xiaomi/__init__.py`, a STALE veto declaration
  removed the same day (backup + SHA256 manifest kept outside the skill).
- Evidence: `probe_tool_media.py xiaomi mimo-v2.6-pro` → tool-result
  channel 200 AND names the colour "red" (user-message channel also 200
  "Red") — endpoint accepts list-type tool content despite the old
  "400 text is not set" comment. Checker flips FALLBACK → NATIVE after
  the removal. Post-restart real-image acceptance (2026-10-10): after
  restarting the agent host process, `vision_analyze` returned the
  "Image loaded into your context" first line — Step 4 passed, full loop
  closed.
- Note: `mimo-v2-omni` (named in the old plugin comment) now returns
  400 "Unsupported model" on BOTH channels — retired model id, not a
  format rejection; not in use.
- Caveat: `hermes update` may restore the plugin file — re-apply the
  removal after updates (candidate for upstream PR). The agent host
  process keeps the old profile in its module cache until THAT process
  restarts — a new session inside the same process does not reload plugin
  Python, so real-image acceptance must run in the restarted process.
