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

`vision_analyze` picks the native fast path when **all** of the following
hold (see `tools/vision_tools.py::_should_use_native_vision_fast_path()`):

```
agent.image_input_mode == native
AND (
     provider accepts images inside tool results   ← static allowlist
                                                     (anthropic / openai /
                                                      openai-codex / gemini-3 /
                                                      aggregators; many direct
                                                      providers are NOT listed)
     OR
     models.dev metadata says the model supports vision
       (disk-cached at <hermes-home>/models_dev_cache.json;
        verdicts never require network at runtime)
   )
```

The allowlist is conservative by design — providers such as zai are **not**
on it, so their models pass via the models.dev branch (e.g.
`glm-5.3-flash`). Models absent from the database can be declared manually
with a config override, which takes priority over the cache.

## Features

- **One-command diagnosis** — `check_vision_path.py` prints a four-line
  verdict (image input route / tool-result images / model vision / final
  path) for your active model or any provider+model pair
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

- **`ModuleNotFoundError` from the script** → wrong interpreter. Use the
  venv that belongs to your Hermes install
  (`venv/bin/python` on Linux/macOS, `venv\Scripts\python.exe` on Windows).
- **"Cannot locate Hermes installation"** → set `HERMES_HOME` to your
  Hermes data directory and retry.
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
