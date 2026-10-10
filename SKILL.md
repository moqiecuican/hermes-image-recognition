---
name: image-recognition
description: "View images natively and diagnose vision path issues."
version: 0.4.0
author: moqiecuican
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [vision, images, multimodal, diagnostics, config]
    related_skills: [hermes-agent]
---

# Image Recognition Skill

> **Scope: Hermes Agent only.** This skill is built exclusively for
> [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Nous
> Research). It hooks into Hermes-internal APIs
> (`tools/vision_tools.py`, `agent/image_routing.py`,
> `agent/auxiliary_client.py`, `hermes_cli.config`) and Hermes-managed
> state (`config.yaml`, the models.dev cache). It will **not** work with
> other agent frameworks (Claude Code, Codex, OpenClaw, ...).

Hermes vision has two channels plus an automatic fallback chain: a natively
multimodal main model gets pixels pushed straight into its context (native
fast path); anything else falls back to an `auxiliary.vision` model that
describes images in text (lossy). This skill covers everyday image viewing,
path diagnosis, first-run setup, and model-switch self-checks. It does NOT
handle video (`video_analyze` is a separate tool) or OCR-heavy document
parsing (use an OCR skill if one is available).

## When to Use
- Viewing any image: local path, URL, browser / computer-use screenshots
- Symptom: "my main model is multimodal, but image details are lost / it
  reads like a paraphrase" → check which path is active first
- After switching provider/model, verify vision still runs natively
- New or self-hosted models absent from models.dev → declare vision manually
- First image task of a session on a model with no models.dev verdict →
  run the unknown-model gate below BEFORE relying on vision_analyze output
- Don't use for: video; OCR-style document extraction

## Prerequisites & First-Run Setup

`<hermes-home>` below means your Hermes data directory: `~/.hermes` by
default, or the value of `HERMES_HOME` if you set one. All commands work on
Linux, macOS, and Windows (Windows uses `venv\Scripts\python.exe` instead of
`venv/bin/python`).

**Step 0 — Run the diagnostic script** (read-only, never mutates anything):

```bash
# Linux / macOS
<hermes-home>/hermes-agent/venv/bin/python \
  <skill-dir>/scripts/check_vision_path.py
# Windows
<hermes-home>\hermes-agent\venv\Scripts\python.exe <skill-dir>\scripts\check_vision_path.py
```

Completion criterion: a four-line verdict (provider/model, image input
route, tool-result images, model vision verdict, final path). Do not guess
your setup — read the output and fix line by line:

**Step 1 — `image input route` is `auto` or `text`** (most common trap):
In `auto` mode, an explicitly configured `auxiliary.vision` (any of
provider/model/base_url set) SUPPRESSES the main model's native vision —
every attached image gets paraphrased by the aux model even when the main
model is multimodal. Fix:

```bash
hermes config set agent.image_input_mode native
```

Rerun the script; expect `native`. (Alternative: remove the explicit
`auxiliary.vision` item instead — but keeping it is recommended, see
Pitfalls. If `text` was set deliberately, leave it.)

**Step 2 — `model vision verdict` is `None`** (fresh installs and
custom models): vision routing never touches the network, so a brand-new
install has no models.dev disk cache yet and known-multimodal models can
read as `None`. Three sub-cases:
- Fresh install → run Hermes normally once (any conversation) to populate
  `<hermes-home>/models_dev_cache.json`, then rerun the script.
- Provider alias missing from `PROVIDER_TO_MODELS_DEV` (e.g. `alibaba-cn`,
  2026-09): the cache may hold a perfect vision record the lookup can never
  reach. The checker flags this explicitly — use the scoped
  `model_overrides.<provider>.<model>` form (see unknown-model gate).
- Model is genuinely multimodal but absent from the database (self-hosted,
  renamed, brand-new) → declare it explicitly:

```bash
hermes config set model.supports_vision true
```

Rerun; expect `True`. The config override has the highest priority and does
NOT depend on the cache — it is the most reliable channel for custom models.

**Step 3 — `model vision verdict` is `False`**: the model is classified as
text-only. If it is actually multimodal (new name, stale catalog), apply the
same `model.supports_vision true` override. If it is truly a text model,
change nothing — the auxiliary fallback is the designed behavior.

**Step 4 — Real-image acceptance test**: call
`vision_analyze(image_url=<a local image>, question=...)` and check the tool
result's first line:
- `Image loaded into your context — you can see it natively now.` → native
  path active; pixels are in context.
- `{"success": true, "analysis": "..."}` → still on the aux-fallback path;
  revisit Steps 1–2.

**Step 5 — Rollback / cost awareness**: undo with
`hermes config unset agent.image_input_mode`. Native images live in the
immutable conversation history and are re-sent every turn — long sessions
cost more tokens (that is the tradeoff for zero information loss).

## Core mechanism: two paths (identify by tool-result first line)

1. **Native fast path**: first line
   `Image loaded into your context — you can see it natively now.`
   The image rides back as a `_multimodal` envelope straight into the main
   model's context — no aux call, no information loss.
2. **Aux fallback path**: returns `{"success": true, "analysis": "..."}`
   — the `auxiliary.vision` model describes the image; pixels never enter
   the main-model context (lossy: layout / small text / exact colors).

The switch is `tools/vision_tools.py::_native_tool_result_images(provider,
model, cfg)` — one gate, shared by `_should_use_native_vision_fast_path()`
(active main model) and the parameterized form for any pair. Three layers,
in order:

1. `agent.image_input_mode` resolves to `native`, AND
2. the provider's profile does not veto tool-result media
   (`_profile_rejects_tool_media`: a profile declaring
   `supports_vision_tool_messages=False` accepts images in user messages but
   rejects list-type tool-result content with HTTP 400 — xiaomi/MiMo;
   `supports_vision` alone must NOT override this veto), AND
3. `_accepts_tool_result_images` says yes, via either
   - one of the 13 explicit ids in `_TOOL_RESULT_MEDIA_PROVIDERS`
     (openrouter, nous, vertex, bedrock, anthropic-vertex, google-vertex,
     anthropic, claude, anthropic-direct, openai, openai-chat, openai-codex,
     azure-openai — "aggregators" is not a literal table value; many direct
     providers are NOT on it), or the `_GEMINI_PROVIDERS` gemini-3 model-tag
     check, or
   - the per-model capability lookup (config override → catalog, e.g.
     `glm-5.3-flash` passes this way despite its provider being off-list).

**Two image channels — a verdict describes the TOOL-RESULT channel only.**
1. **User-message channel** — the image rides inside the chat message itself.
   Works on any multimodal model and is NOT affected by a provider veto.
2. **Tool-result channel** — the image rides back inside a `vision_analyze`
   tool message (the "native fast path" this skill diagnoses). A provider
   profile declaring `supports_vision_tool_messages=False` rejects list-type
   tool content with HTTP 400, closing this channel regardless of what the
   model itself can do.
So FALLBACK on a model the user knows is multimodal is NOT a contradiction —
check the veto before debating capability. When the veto is the cause, FIRST
arbitrate whether it is still accurate with the decisive probe (gate step 4
below): a veto can go stale, and a stale one gets corrected via the "stale
veto declaration" flow in Pitfalls. Only when the veto is confirmed accurate,
fall back to: attach the image in the message (channel 1) or accept the aux
transcription; never force the tool-result envelope, and never try to lift
the veto with `supports_vision` (that yields the 400, not pixels).
Provider list + a decisive two-request probe: `references/vision-channels-and-vetoes.md`.

## Procedure: first image call in a session (unknown-model gate)

Vision verdicts are cheap to check and expensive to get wrong: a silently
lossy fallback path degrades every image judgement in the session (real case:
13 acceptance rounds on one SVG animation flip-flopping 3↔7 on the same
frame, all caused by the aux paraphrase path — one config line would have
prevented it). Gate once per session / after any model switch, not per call.

1. Run `scripts/check_vision_path.py` (see Quick Reference).
2. Verdict NATIVE → proceed. If `references/confirmed-vision-models.md`
   already lists this provider/model with a date, you may skip step 1 this
   session.
3. Verdict FALLBACK + `model vision: False` → designed degradation for a
   text-only model. Do NOT ask the user whether it is multimodal; just make
   sure `auxiliary.vision.model` names a strong vision model.
4. Verdict FALLBACK + `model vision: True` + the verdict note names a
   provider profile veto (`supports_vision_tool_messages=False`) → the
   "capability present, channel vetoed" shape. The veto is a DECLARATION
   about the endpoint and can go stale — neither trust nor argue from it;
   arbitrate with the decisive probe:
   `scripts/probe_tool_media.py <provider> <model>` (1×1 red PNG, both
   channels). Probe A (tool-result) 200 AND names the colour → the
   declaration is STALE → run the "stale veto declaration" flow in Pitfalls
   (state change: get user consent first). Probe A 400 with a CONTENT/
   format error body (e.g. "text is not set", "content did not match") →
   the declaration is still accurate: change nothing; tell the user to
   attach images in the chat message (user-message channel) or accept the
   aux transcription. Probe A 400 with a MODEL-ID error body ("Unsupported
   model", "model not found") → retired/renamed id, NOT channel evidence;
   the veto question is inconclusive — resolve the current model name
   first, then re-probe.
   Probe A 200 but no colour named → accepted-but-blind, change nothing.
   Worked example (discovery → probe → fix → restart → acceptance): the
   case study in `references/vision-channels-and-vetoes.md`.
5. Verdict FALLBACK + `model vision: None` → STOP and ask the user:
   "当前主模型是否原生多模态？" (check the confirmed-models registry first).
   If the user confirms multimodal, the checker now distinguishes two causes:
   - **PROVIDER ALIAS MAPPING GAP** (message says the cache DOES record the
     model but PROVIDER_TO_MODELS_DEV lacks the provider alias — an upstream
     Hermes bug, e.g. alibaba-cn as of 2026-09): the "no record" wording is
     misleading; do not chase the cache. Fix persistently per model:
     `hermes config set 'model_overrides.<provider>.<model-with-\.escaped-dots>.supports_vision' true`
     — survives cache refresh, beats the catalog, and also repairs
     context-window resolution for that provider. Then READ BACK the yaml:
     the dotted model id must land as ONE literal key, never split into
     bogus nesting (unescaped dots DO get split on first creation).
   - **Model genuinely absent from models.dev** (self-hosted/renamed):
     `hermes config set model.supports_vision true` (global shortcut) or the
     per-model providers form.
   If the user says text-only → keep fallback; ensure the aux model is good.
6. After any config change: rerun the checker (expect NATIVE) AND do the
   real-image test (Step 4 of Prerequisites). Then append the confirmed
   provider/model + evidence to `references/confirmed-vision-models.md`.
7. Mid-session tells that you are on the lossy path anyway: vision_analyze
   returns `{"success": true, "analysis": ...}` (no "Image loaded into your
   context" first line) AND the answer ignores output-format constraints
   ("one sentence" → 600 words) because an aux model is re-describing.

## Quick verdict: "can model X see images natively?"
For any provider/model pair — no model switch needed — run the checker with
two args and read the four-line verdict:

```bash
<hermes-home>/hermes-agent/venv/bin/python <skill-dir>/scripts/check_vision_path.py <provider> <model>
```

Do this BEFORE hand-deriving routing from source code or hand-writing API
probes — the script is meant to implement the full decision chain (config
override → catalog → probes). Trust it only while its two-arg branch calls
the upstream gate rather than re-deriving it (see Pitfalls). Only fire a raw `/chat/completions` image
probe when you need endpoint-level proof beyond the routing verdict (e.g. a
model the catalog has never seen).

Acceptance ≠ capability: an endpoint may accept an `image_url` block without
erroring and still fail to see the image (deepseek-v4-pro: 200 OK, answered
"Unknown" on a solid-red 1×1 PNG; models.dev marks it `attachment: false`).
A color-question probe must actually name the color before you call the
model multimodal.

## How to Run
Standard image-viewing moves:
1. `vision_analyze(image_url=<absolute path or URL>, question=...)`
2. Read the tool-result first line to know which path fired (see above)
3. Oversized images are auto-downscaled to ≤1568px with a coordinate
   multiplier note; for small text / fine detail re-view a crop via
   `region=[x1,y1,x2,y2]` (original-image pixel coordinates) to keep
   full resolution — and never judge path quality from a single
   small-text read (see Pitfalls)

User-attached images (CLI / TUI / messaging platforms) follow
`agent.image_input_mode` too: `native` = pixels enter context directly.

## Quick Reference
```bash
# No args = current main provider/model; two args = any provider/model pair
<hermes-home>/hermes-agent/venv/bin/python <skill-dir>/scripts/check_vision_path.py
<hermes-home>/hermes-agent/venv/bin/python <skill-dir>/scripts/check_vision_path.py zai glm-5.3-flash
# Endpoint-level arbitration when a profile veto looks stale (same args)
<hermes-home>/hermes-agent/venv/bin/python <skill-dir>/scripts/probe_tool_media.py <provider> <model>
```

## Procedure: self-check after switching models
1. Run the diagnostic script → completion criterion: the four-line verdict
2. Verdict native + model actually has vision → done; confirm once with a
   real image (Step 4)
3. Verdict fallback with `model vision verdict: None` while the model IS
   multimodal → `hermes config set model.supports_vision true` → rerun
   script = native
4. Verdict fallback and the model is text-only → nothing to do; confirm
   `auxiliary.vision.model` is non-empty so the fallback has a backend

## Pitfalls
- **Never re-derive the routing decision inside a probe or checker script —
  call the upstream gate.** A locally recomputed predicate
  (`mode == "native" and (tool_img or vis is True)`) drifts from
  `_native_tool_result_images(provider, model, cfg)`: it skips the profile
  hard veto (`_profile_rejects_tool_media`), so it reports NATIVE for
  providers whose tool-result image content is rejected with HTTP 400 — the
  user trusts the verdict and gets an error instead of pixels. The
  parameterized gate accepts an arbitrary provider/model pair, so there is
  nothing to re-implement; on an older install that lacks it, recompute AND
  add the explicit veto check.
- Upstream refactors this area: conditions sink into helper functions,
  signatures gain parameters, symbols move between files. Before editing the
  checker, re-locate the current symbols (`grep -n "def <symbol>"
  tools/vision_tools.py`) and re-verify each claim of a bug report against
  the CURRENT source — an item valid when filed may already be fixed by a
  later refactor.
- **A provider-level veto cannot be un-vetoed by config**:
  `supports_vision_tool_messages=False` (xiaomi/MiMo, meta-ai, opencode-zen)
  is an endpoint FORMAT limit, not a capability gap — declaring
  `supports_vision` makes the call 400, it does not make pixels arrive. Use
  the user-message channel, or accept the aux transcription.
  BUT the veto itself is a declaration that can go stale (a vendor fixes
  the endpoint without Hermes noticing). When the decisive probe
  (`scripts/probe_tool_media.py`) returns 200 AND names the probe colour,
  the declaration is dead — config cannot lift a veto, but correcting the
  plugin profile can ("stale veto declaration" flow):
  1. back up the provider plugin file(s) + hash manifest (rollback =
     restore the backup);
  2. probe EVERY model still in use under that provider first — the flag is
     provider-level, one still-400 model breaks after the flip. Enumerate
     concretely: `grep -n <provider>` in config.yaml (main model, aux
     models, and any fallback-chain entries all count);
     `GET <base_url>/models` for the vendor's current directory (error
     bodies quote legal ids verbatim); then probe each id in turn. A 400
     "Unsupported model" is a retired id, not channel evidence — it does
     not block the flip;
  3. flip `supports_vision_tool_messages=False` → `True` (or drop the
     argument) in `<hermes-home>/hermes-agent/plugins/model-providers/
     <provider>/__init__.py`;
  4. restart EVERY agent host process that must pick this up — plugin
     Python is module-cached (the loader's `sys.modules` guard means an
     already-imported plugin is never re-read), so it loads once per process
     start. Restarting the gateway from an EXTERNAL shell (`hermes gateway
     restart`) reloads only the gateway's own plugins; the TUI/dashboard
     process keeps the old profile in memory and a NEW SESSION inside the
     same process does NOT reload anything — exit and relaunch the host
     process itself (config, by contrast, is re-read every turn);
  5. verify in layers: the checker runs in any fresh subprocess and
     confirms the on-disk state immediately (expect NATIVE); the real-image
     acceptance test (expect the "Image loaded into your context" first
     line) is only meaningful INSIDE a restarted agent host process —
     vision_analyze in a pre-restart process still runs the old profile and
     returns aux JSON; that is stale module cache, not a failed fix;
  6. register provider/model + probe evidence in
     `references/confirmed-vision-models.md`.
  Concrete restart recipes (the agent CANNOT restart its own host process —
  send the instruction to the user):
  - TUI: the user types `/exit` (or Ctrl+D) in that TUI window, then
    re-runs `hermes --tui` in the terminal. History persists in the
    session DB; resuming the same conversation or opening a new one BOTH
    pick up the new plugin — what matters is a new PROCESS, not a new
    session.
  - dashboard (embedded chat agents): the user runs
    `hermes dashboard --stop` then `hermes dashboard` from an external
    shell.
  - gateway-side bots: the user runs `hermes gateway restart` from an
    external shell.
  - Multiple TUI windows = multiple processes; each window started before
    the edit keeps the old profile until its own restart.
  When unsure which process is stale: compare the plugin file's mtime
  (`stat <plugin-file>`) against process start times
  (`ps -eo pid,lstart,cmd | grep -E 'tui_gateway|dashboard'`), or just run
  one `vision_analyze` and read the first line — the empirical test doubles
  as the staleness check.
  `hermes update` can overwrite the plugin edit — re-apply after updates,
  and consider sending the probe evidence upstream as a PR/issue.
- **Capability and endpoint format are different questions.** models.dev
  `attachment: true` / profile `supports_vision=True` answers "can this model
  read images"; it says NOTHING about whether the endpoint accepts images
  inside tool messages. When a user insists their model is multimodal, check
  the channel first — the disagreement is usually about which channel, not
  about the model.
- **`auto` mode + explicit `auxiliary.vision`** (any of provider/model/
  base_url set) overrides native vision — a maintainer decision recorded in
  `agent/image_routing.py` ("a user who named a dedicated vision model
  wants it used"). Fix with `image_input_mode: native` or by removing the
  explicit aux item.
- **`model.supports_vision` is a GLOBAL shortcut** — it asserts the CURRENT
  main model sees images. Switch to a text-only model and the stale `true`
  misroutes images into a model that cannot read them. Prefer the scoped
  `model_overrides.<provider>.<model>.supports_vision` record for stable
  per-model facts; keep the global flag only as a temporary unblock.
- **Dots inside model ids** (`qwen3.8-flash`, `glm-4.5`): `hermes config set`
  splits on unescaped dots when CREATING a key (yields bogus nesting like
  `qwen3: {8-flash: ...}`); greedy literal matching only helps once the
  dotted key already exists. Always `\.`-escape and always read the yaml
  back after writing.
- **A confident vision verdict on small text can be wrong on EITHER path.**
  Aux re-descriptions drop small detail and ignore format constraints;
  native pixel reads misread small text just as confidently (observed:
  native read "8" in a "80" subtitle that the aux transcription got right;
  repeated verdicts can also contradict each other — 3/10 vs 7/10 on the
  same frame). Never build a path-quality argument on a single small-text
  read: re-view a crop (`region=`) first and treat both paths' opinions as
  hypotheses. For geometry/coverage acceptance, prefer objective pixel
  sampling or frame hashing over any vision-model opinion.
- **Do not delete `auxiliary.vision`**: it backs the fallback paraphrase
  for text-only models, the legacy path when the fast path does not fire,
  and auto-describing images already in history
  (`agent/vision_message_prep.py::_describe_image_for_anthropic_fallback`). It is a
  safety net, not redundancy.
- The verdict data is cached on disk at `<hermes-home>/models_dev_cache.json`
  (usable at any age; hot paths never hit the network) → verdicts survive
  new sessions and offline use. Cache deleted AND offline → graceful
  fallback to aux paraphrase (no crash).
- Providers off the tool-result allowlist rely entirely on the models.dev
  verdict (or a manual `model.supports_vision` override).
- Fetching `https://models.dev/api.json` directly (urllib, no headers)
  returns 403 from this box — go through the local proxy with a browser UA:
  `curl -s -x http://127.0.0.1:10808 -A 'Mozilla/5.0' https://models.dev/api.json`.
  Usually unnecessary: read the local `<hermes-home>/models_dev_cache.json`
  copy first (verdict data is cached there).
- Vendor model ids churn — before probing, GET the provider's `/models`
  (or send one tiny call) and use the CURRENT official name; error bodies
  list the accepted names verbatim (e.g. DeepSeek deprecated
  `deepseek-v4-flash-0731` in favor of `deepseek-flash`), so a "model not
  found" 400 is free directory info, not a dead end.
- Browser / computer-use screenshots travel through their own `_multimodal`
  envelope paths (`tools/browser_use_cli.py`,
  `tools/computer_use/vision_routing.py`) — same
  "pixels into the main model" mechanism. The `vision_analyze` tool itself
  stays available in every `image_input_mode`.
- Agent file tools (patch / write_file) are blocked from editing
  `<hermes-home>/config.yaml` by a security guard — configure via
  `hermes config set/unset` instead; manual editors: keep a backup and
  2-space YAML indentation.
- Profiles are isolated: each Hermes profile has its own `config.yaml`
  (e.g. a bot profile) — apply these settings per profile as needed.
- The session's skill loader is cached at startup: a newly installed skill
  becomes visible in the NEXT session, not the current one.
- `native` with a text-only main model does not crash: API-time
  preprocessing strips/converts image parts (last-chance text fallback in
  `agent/vision_message_prep.py::_preprocess_anthropic_content` /
  `agent/message_sanitization.py::_strip_images_from_messages`).

## Troubleshooting
- **`Could not import Hermes internals (ModuleNotFoundError: ...)`** → the
  script could not load Hermes APIs. Two causes, in likelihood order:
  wrong interpreter — use the venv that belongs to your Hermes install
  (`venv/bin/python` on Linux/macOS, `venv\Scripts\python.exe` on
  Windows); or the Hermes data dir was not found — set
  `HERMES_HOME=/path/to/.hermes` and retry (the script falls back to
  `~/.hermes` when `$HERMES_HOME` does not exist).
- **`HERMES_HOME does not exist - falling back to ~/.hermes`** → you set
  `HERMES_HOME` to a path that is not there. Mind the asymmetry: the
  Hermes core uses such a path as-is (empty config), while this checker
  falls back and keeps diagnosing — fix the variable so the verdict
  matches the runtime.
- **Config edits not taking effect** → settings are re-read every turn, but
  mid-session capability overrides like `model.supports_vision` only apply
  on the next model resolution; rerun the script to confirm.
- **Provider rejects image content (HTTP 400) after declaring
  `supports_vision`** → the declaration does not match reality; undo with
  `hermes config unset model.supports_vision`.
- **Still seeing paraphrase-style results after native setup** → rerun the
  script; if it says native but a FRESH vision_analyze call still returns
  aux JSON, the agent host process cached the provider profile at startup
  (a plugin-file change) — the fix is already working on disk; verify the
  native first line after restarting THAT process (a new session inside
  the same process does not reload plugin Python) instead of re-editing
  anything. Only config.yaml changes apply without restart.
- **Token cost spike in long vision-heavy sessions** → expected: native
  images re-send every turn. Downscale inputs or drop back to the fallback
  path when fidelity does not matter.

## Verification
- Diagnostic script output matches the decision matrix (multimodal = native;
  text-only or unknown = fallback)
- Real-image test: native first line present, no aux round-trip
- config.yaml changes apply without restart (re-read every turn); plugin
  profile changes need the agent host PROCESS restarted before the
  real-image test can show the native first line (a new session inside
  the same process is not enough)
