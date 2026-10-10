# image-recognition — a vision skill for Hermes Agent

**A [Hermes Agent](https://github.com/NousResearch/hermes-agent) skill that
lets a natively multimodal main model see images directly (pixels in
context), with a built-in diagnostic for the native-vs-fallback vision
path.**

> 🌏 [中文说明（README.zh-CN.md）](README.zh-CN.md)

---

## What it does

Hermes routes vision through two channels:

1. **Native fast path** — the image rides back from `vision_analyze` as a
   structured tool result carrying the image data itself (a `_multimodal`
   envelope in Hermes' source) — so the main model *sees the pixels
   itself*. No aux call, no information loss.
2. **Aux fallback path** — a separate `auxiliary.vision` model looks at
   the image and returns a **text paraphrase**. Pixels never enter the
   main model's context. Lossy: layout, small text, and exact colors
   degrade.

The catch: Hermes' default `auto` mode **suppresses the native path
whenever an explicit `auxiliary.vision` is configured** — even when the
main model is perfectly multimodal. Many users therefore get paraphrased,
degraded image descriptions without knowing why. This skill exists to fix
that in one command, and to give you a reliable way to check which path is
active at any time.

## Compatibility

| Agent | Supported |
|---|---|
| **Hermes Agent** (Nous Research) | ✅ this is what it is built for |
| Claude Code, Codex, OpenClaw, other agent frameworks | ❌ not compatible |

This skill hooks Hermes-internal APIs (`tools/vision_tools.py`,
`agent/image_routing.py`, `agent/auxiliary_client.py`,
`hermes_cli.config`) and Hermes-managed state (`config.yaml`, the
models.dev disk cache). Verified against Hermes Agent v0.21.x; internal
APIs may shift between versions — rerun the diagnostic after upgrading.

## How the path decision works

`vision_analyze` picks the native fast path only when **all** of the
following hold (see `tools/vision_tools.py::_native_tool_result_images(
provider, model, cfg)` — one gate, shared by
`_should_use_native_vision_fast_path()`):

```
1. agent.image_input_mode == native
2. the provider's profile does not veto tool-result media
   (`_profile_rejects_tool_media`: a profile declaring
    supports_vision_tool_messages=False accepts images in user messages
    but rejects list-type tool-result content with HTTP 400 — xiaomi/MiMo;
    supports_vision alone must NOT override this veto)
3. AND either
     provider accepts images inside tool results   ← 13 explicit ids in
                                                     _TOOL_RESULT_MEDIA_PROVIDERS
                                                     (openrouter, nous, vertex,
                                                      bedrock, anthropic-vertex,
                                                      google-vertex, anthropic,
                                                      claude, anthropic-direct,
                                                      openai, openai-chat,
                                                      openai-codex,
                                                      azure-openai), or the
                                                     _GEMINI_PROVIDERS gemini-3
                                                     model-tag check
                                                     ("aggregators" is not a
                                                      literal table value; many
                                                      direct providers are NOT
                                                      listed)
     OR
     the per-model capability lookup says vision-capable
       (config override → catalog; disk-cached at
        <hermes-home>/models_dev_cache.json;
        verdicts never require network at runtime)
   )
```

The static table is conservative by design — providers such as zai are **not**
on it, so their models pass via the capability branch (e.g. `glm-5.3-flash`).
Profiles that veto tool-result media (xiaomi/MiMo) fall back no matter what
the capability lookup says. Models absent from the database can be declared
manually with a config override, which takes priority over the cache.

Probe/checker note: call the gate — never re-derive the predicate locally.
A local formula misses layer 2 and reports NATIVE for providers whose
tool-result image content 400s.

## Features

- **One-command diagnosis** — `check_vision_path.py` prints a four-line
  verdict (image input route / tool-result images / model vision / final
  path) for your active model or any provider+model pair
- **Session runtime model** — after a mid-session `/model` hot-swap, the
  checker resolves the session's ACTUAL pair: `--session <id>` (read from
  the session usage database, authoritative), `--anchor '<message
  prefix>'` (locates the session via the log, then confirms), and a
  no-args dual view that flags config-vs-session mismatches unprompted
- **Delivery-proof methodology** — the native "first line" is a
  declaration, not delivery proof: in a hot-swapped session the runtime
  gate reads the config pair and can misroute. Verify with in-session
  evidence (answer reflects pixels + next API call grows by image-size
  tokens) and treat every `supports_vision` override as an assumption to
  test, never as evidence
- **Endpoint arbitration** — `probe_tool_media.py` runs the decisive
  two-request probe (1×1 red PNG, both image channels) that proves or
  disproves a provider tool-result veto at the endpoint instead of
  trusting the declaration (acceptance requires the model to name the
  probe colour)
- **First-run guidance** — a decision tree covering every combination of
  misconfiguration, including the aux-suppression trap and fresh-install
  cache misses
- **Model-switch self-check** — after changing provider/model, confirm
  vision still runs natively before you rely on it
- **Cross-platform** — Linux, macOS, Windows (portable `HERMES_HOME`
  detection; friendly import errors instead of tracebacks)
- **Read-only** — the diagnostic never mutates any configuration

## Installation

Copy this directory into your Hermes skills folder:

```bash
# default Hermes home
git clone https://github.com/moqiecuican/hermes-image-recognition.git \
  ~/.hermes/skills/autonomous-ai-agents/image-recognition

# custom Hermes home
git clone https://github.com/moqiecuican/hermes-image-recognition.git \
  "$HERMES_HOME/skills/autonomous-ai-agents/image-recognition"
```

The skill becomes visible to new Hermes sessions (the session skill loader
is cached at startup).

## Quick start

Run the diagnostic with the venv that belongs to your Hermes install:

```bash
# Linux / macOS
~/.hermes/hermes-agent/venv/bin/python \
  ~/.hermes/skills/autonomous-ai-agents/image-recognition/scripts/check_vision_path.py

# Windows
%USERPROFILE%\.hermes\hermes-agent\venv\Scripts\python.exe ^
  %USERPROFILE%\.hermes\skills\autonomous-ai-agents\image-recognition\scripts\check_vision_path.py
```

No arguments checks your **current** main provider/model; two arguments
check any pair:

```bash
check_vision_path.py zai glm-5.3-flash
```

### Endpoint probe — arbitrate a veto

When the verdict is FALLBACK because of a profile veto
(`supports_vision_tool_messages=False`), the declaration itself may be
stale. The probe settles it at the endpoint level (same arg convention;
API keys are read in-process and never printed):

```bash
~/.hermes/hermes-agent/venv/bin/python \
  ~/.hermes/skills/autonomous-ai-agents/image-recognition/scripts/probe_tool_media.py <provider> <model>
```

Verdict rules: a tool-result-channel answer that NAMES the probe colour
means the veto is stale — follow the "stale veto declaration" flow in
SKILL.md Pitfalls. A 200 that fails to name the colour is
accepted-but-blind; a 400 means the declaration is still accurate
(content/format error body) or the model id is retired (model-id error
body — not channel evidence).

### Reading the verdict — decision matrix

| image input route | model vision | meaning | action |
|---|---|---|---|
| `native` | `True` | ✅ native path active | none — verify once with a real image |
| `native` | `None` | ⚠️ fresh install (no cache) or unknown model | run Hermes once to populate the cache, or declare explicitly (below) |
| `native` | `False` | model classified text-only | truly text → keep the fallback; actually multimodal → declare explicitly (below) |
| `auto` + explicit `auxiliary.vision` | any | ❌ **native vision suppressed** (most common trap) | `hermes config set agent.image_input_mode native` |
| `auto` (no aux config) | `True` | ✅ native path active | none |
| `text` | any | fallback forced deliberately | leave as-is unless unintentional |
| any | declared but provider 400s | declaration mismatches reality | `hermes config unset model.supports_vision` |

### The two fixes that matter

```bash
# Trap: explicit auxiliary.vision suppresses native vision in auto mode
hermes config set agent.image_input_mode native

# Unknown / self-hosted multimodal model absent from models.dev
hermes config set model.supports_vision true
```

Both are re-read every turn — no restart needed. Roll back with
`hermes config unset <key>`.

### Acceptance test

Call `vision_analyze(image_url=<a local image>, question=...)` and read the
first line of the tool result:

- `Image loaded into your context — you can see it natively now.` → native
- `{"success": true, "analysis": "..."}` → still on the fallback path

## Troubleshooting

- **`Could not import Hermes internals (ModuleNotFoundError: ...)`** → the
  script could not load Hermes APIs: either wrong interpreter (use the
  venv that belongs to your Hermes install — `venv/bin/python` on
  Linux/macOS, `venv\Scripts\python.exe` on Windows) or the Hermes data
  dir was not found (set `HERMES_HOME=/path/to/.hermes` and retry; the
  script falls back to `~/.hermes` when the variable points nowhere).
- **`HERMES_HOME does not exist - falling back to ~/.hermes`** → you set
  `HERMES_HOME` to a nonexistent path. The Hermes core uses such a path
  as-is (empty config) while this checker falls back — fix the variable
  so the verdict matches the runtime.
- **Verdict `None` on a known multimodal model** → fresh install: run
  Hermes once to populate `models_dev_cache.json`; still missing: use the
  `model.supports_vision true` override (independent of the cache).
- **HTTP 400 after declaring `supports_vision`** → the declaration does not
  match the model; undo with `hermes config unset model.supports_vision`.
- **Still seeing paraphrase-style results** → rerun the diagnostic; if it
  says NATIVE, the old-style result is stale output from before the change.
- **Agent file tools refuse to edit config.yaml** → by design (security
  guard). Use `hermes config set/unset`; keep a backup if editing manually.
- **Multiple profiles** → each profile has its own `config.yaml`; apply per
  profile as needed.
- **Token cost spikes in long vision-heavy sessions** → native images are
  re-sent every turn by design; downscale inputs or accept the fallback
  when fidelity does not matter.

## FAQ

**Does the first-run guidance run on every image view?**
No. The skill text loads once when relevant; the script is manual (install,
model switch, troubleshooting). At runtime Hermes re-evaluates the path on
every call by itself — milliseconds, purely local, no network, no extra
tokens. Setup is a one-time exit process, not a per-image tax.

**If I switch models, does vision adapt automatically?**
Yes — path decisions are stateless and recomputed against the current main
model every turn. Multimodal → native, text-only → aux fallback, images
already in history are converted/stripped safely for text-only models. The
only manual case: a model absent from models.dev needs the one-line
`supports_vision` override.

**Why keep `auxiliary.vision` configured?**
It is the safety net, not redundancy: fallback paraphrase for text-only
models, the legacy path when the fast path does not fire, and auto-describe
for images already in history. Delete it and you lose the degradation
chain.

**Does `native` crash on a text-only model?**
No — a last-chance text fallback converts/strips image parts at API time.

## Limitations — please tell me when this fails

Hermes's vision subsystem is still relatively primitive and imperfect by
design: two image channels, capability tables, plugin profiles, per-model
quirks — and it all moves as upstream Hermes changes, which it does often.
Against that moving target, two honest caveats:

- **This skill may not cover every situation.** The diagnosis method
  (verdict → probe → evidence) is designed to stay valid when details
  shift, but no document can anticipate every provider, endpoint, or
  model quirk in advance.
- **Updates may lag behind reality.** Upstream can change first; flows
  verified today may be stale tomorrow.

If anything does not work, does not match the docs, or puzzles you —
please open an issue and describe what you saw. Every report is welcome,
including "this worked fine" notes.

This release is developed and tested against **Hermes 0.21.5**. Findings
from other versions are especially valuable.

## Contributing

Issues and PRs welcome. Please run the diagnostic script before and after
any proposed change and include its output.

## License

[MIT](LICENSE) © moqiecuican

## Acknowledgements

- The two-path vision mechanism, the fast-path switch, and the
  tool-result mechanism that carries the image itself (not a text
  paraphrase) back into the main model's context are part of
  [Hermes Agent](https://github.com/NousResearch/hermes-agent)
  by Nous Research — this skill packages diagnosis and setup guidance
  around them; it ships no private logic of its own.
- [models.dev](https://models.dev) — the community-maintained model
  capability database Hermes integrates for vision-capability verdicts.
