# Vision channels and provider tool-result vetoes

## Two channels (a routing verdict describes only the second)

| channel | how the image travels | affected by the veto? |
|---|---|---|
| user-message | image part inside the chat message content | no |
| tool-result | image part inside a `vision_analyze` tool message — the "native fast path" this skill diagnoses | yes |

Consequence: a multimodal model can report FALLBACK with no capability
problem at all — its endpoint refuses list-type content in tool messages.

## Providers that veto tool-result media

The flag lives in the provider profile. Enumerate it on the live install
(never trust a remembered list):

```bash
grep -rn "supports_vision_tool_messages" \
  <hermes-home>/hermes-agent/plugins/model-providers/*/__init__.py
```

Known carriers at the time of writing: xiaomi/MiMo, meta-ai, opencode-zen.
The xiaomi declaration carries its own reason inline — *rejects list-type tool
content (400 "text is not set")*: its API accepts images in user messages but
requires string-only content in tool messages.

The declaration is upstream-maintained and can go stale (a vendor may fix the
endpoint). Treat it as evidence, not truth: when a user disputes it, run the
probe below on their key instead of arguing from the profile.

## Decisive probe: two minimal requests

(Ready-made: `scripts/probe_tool_media.py <provider> <model>` implements
exactly this and prints a verdict — prefer it over hand-rolling.)

Same model, tiny `max_tokens`, one 1x1 PNG — vary ONLY the channel:

- **A (tool-result channel):** an assistant turn with `tool_calls`, then a
  `role:"tool"` message whose content is a list:
  `[{"type":"text",...},{"type":"image_url","image_url":{"url":"data:image/png;base64,<1x1>"}}]`
  → on a vetoing endpoint this returns `400` (e.g. `param: text is not set`).
- **B (user-message channel):** the same image inside a `role:"user"`
  content list → expect `200`.

Read the API key from `<hermes-home>/.env` in-process and never print it.
A `200` alone does not prove the model SEES the image: ask what colour the
1x1 pixel is and require the colour to be named before calling the model
multimodal.

## Acceptance test for any checker change: parity with the upstream gate

The checker must agree with the runtime verdict. Compare its two-arg output
against `tools.vision_tools._native_tool_result_images(provider, model, cfg)`
over a matrix that includes at least: a known-vision off-list provider (zai),
a static-table provider (anthropic), a vetoing provider (xiaomi), a custom or
unknown pair, and a provider resolved through a scoped `model_overrides`
record. Acceptance is ZERO drift; a single mismatch is the bug class this
matrix exists to catch.

### Deterministic fixtures when the live machine is too capable

- **Force an import failure:** run the checker with `python3 -S` (no
  site-packages) — it must print the friendly checklist and exit 1, never a
  traceback. Picking a "wrong interpreter" is unreliable: once the system
  python happens to carry the deps, the run succeeds and the test silently
  stops testing anything.
- **Exercise cache/config-dependent branches:** point `HERMES_HOME` at a temp
  dir holding a minimal `config.yaml` plus a copy of
  `models_dev_cache.json`, and create a `hermes-agent` symlink inside it. The
  checker inserts `<hermes-home>/hermes-agent` into `sys.path`, so without
  that symlink the run dies as an import error for the wrong reason.

## Case study: stale veto declaration (xiaomi / mimo-v2.6-pro, 2026-10-09/10)

The profile declared `supports_vision_tool_messages=False` ("400 text is not
set", written for the retired mimo-v2 generation) and both the checker and
the runtime faithfully reported FALLBACK — on a model that was in fact fully
multimodal on BOTH channels. Decisive probe (1×1 red PNG):

- A (tool-result, list content in `role:"tool"`): **200, answered "red"**
- B (user-message): 200, answered "Red"
- `/v1/models` showed the old models (`mimo-v2-pro/flash/omni`) were already
  retired ("Unsupported model"), so the provider-level flip was safe.

Resolution: flip the plugin declaration (see the "stale veto declaration"
flow in SKILL.md Pitfalls) → checker NATIVE → real-image test returns the
"Image loaded into your context" first line.

Lesson: when the verdict is FALLBACK + `model vision: True`, the veto note is
a HYPOTHESIS about the endpoint, not evidence — the probe arbitrates, and a
200 only counts when the model names the probe colour (acceptance ≠
capability). Registry entry: `references/confirmed-vision-models.md`.
