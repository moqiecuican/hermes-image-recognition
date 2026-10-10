#!/usr/bin/env python3
"""Hermes vision-path checker: native fast path vs auxiliary fallback.

Read-only diagnostic. Prints which vision path the active (or any given)
provider/model pair will take:

  venv/bin/python check_vision_path.py                       # current main provider/model
  venv/bin/python check_vision_path.py zai glm-5.3-flash     # any provider/model pair

Run it with the venv that belongs to your Hermes installation
(`venv/bin/python` on Linux/macOS, `venv\\Scripts\\python.exe` on Windows).
If Hermes lives outside the default location, set HERMES_HOME first.
"""
import os
import sys
import logging

logging.disable(logging.CRITICAL)


def locate_hermes_home() -> str:
    """Resolve the Hermes data dir: HERMES_HOME env var, then ~/.hermes."""
    home = os.environ.get("HERMES_HOME", "").strip()
    if home and os.path.isdir(home):
        return home
    return os.path.expanduser("~/.hermes")


_home = locate_hermes_home()
_h = os.environ.get("HERMES_HOME", "").strip()
if _h and not os.path.isdir(_h):
    print(f"WARNING: HERMES_HOME does not exist - falling back to ~/.hermes ({_home})")
    print("Note: the Hermes core uses a nonexistent $HERMES_HOME as-is (empty")
    print("config); fix the variable so this verdict matches the runtime.")
    print()
_repo = os.path.join(_home, "hermes-agent")
if os.path.isdir(_repo):
    sys.path.insert(0, _repo)

try:
    from tools.vision_tools import (
        _should_use_native_vision_fast_path,
        _supports_media_in_tool_results,
    )
    from agent.image_routing import decide_image_input_mode, _lookup_supports_vision
    from agent.auxiliary_client import _read_main_provider, _read_main_model
    from hermes_cli.config import load_config
except Exception as exc:  # noqa: BLE001 - friendly guidance beats a traceback
    print(f"Could not import Hermes internals ({exc.__class__.__name__}: {exc})")
    print()
    print("Fix checklist:")
    print("  1. Run this script with the venv that belongs to your Hermes install:")
    print("       Linux/macOS : <hermes-home>/hermes-agent/venv/bin/python")
    print("       Windows     : <hermes-home>\\hermes-agent\\venv\\Scripts\\python.exe")
    print("  2. If Hermes is not at ~/.hermes, point the checker at it first:")
    print("       export HERMES_HOME=/path/to/.hermes   (or set it on Windows)")
    print("  3. Confirm the repo exists: <hermes-home>/hermes-agent/tools/vision_tools.py")
    print()
    print("Note: this checker targets Hermes Agent installations only - it")
    print("imports Hermes-internal APIs and will not work with other agents.")
    sys.exit(1)

# The parameterized upstream gate is the ONLY correct source for an arbitrary
# provider/model pair. Recomputing the predicate locally is the drift bug from
# issue #1: a local formula skips the profile hard veto
# (_profile_rejects_tool_media) and reports NATIVE for providers whose
# tool-result image content is rejected with HTTP 400 (xiaomi/MiMo).
try:
    from tools.vision_tools import _native_tool_result_images as _native_gate
except Exception:  # noqa: BLE001 - older install without the parameterized gate
    _native_gate = None
try:
    from tools.vision_tools import _profile_rejects_tool_media
except Exception:  # noqa: BLE001
    _profile_rejects_tool_media = None

cfg = load_config()
if len(sys.argv) >= 3:
    provider, model = sys.argv[1], sys.argv[2]
else:
    provider = _read_main_provider() or ""
    model = _read_main_model() or ""

mode = decide_image_input_mode(provider, model, cfg)
tool_img = _supports_media_in_tool_results(provider, model)
vis = _lookup_supports_vision(provider, model, cfg)

veto = None
if _profile_rejects_tool_media is not None:
    try:
        veto = bool(_profile_rejects_tool_media(provider, model))
    except Exception:  # noqa: BLE001
        veto = None

if len(sys.argv) >= 3:
    if _native_gate is not None:
        fast = _native_gate(provider, model, cfg)
    else:
        # Older install: recompute in the upstream layer order, with the
        # profile veto explicit (it must be checked BEFORE the capability
        # lookup or xiaomi/MiMo misreport as NATIVE).
        fast = (mode == "native") and (veto is not True) and (tool_img or vis is True)
else:
    fast = _should_use_native_vision_fast_path()

print(f"provider/model    : {provider} / {model}")
print(f"image input route : {mode}")
print(f"tool-result images: {tool_img}")
print(f"model vision      : {vis}")
print(
    "=> vision path    : "
    + ("NATIVE (pixels enter the main-model context)" if fast
       else "FALLBACK (auxiliary.vision paraphrase, lossy)")
)
if veto is True and not fast:
    print()
    print("note: this provider's profile vetoes tool-result media")
    print("(supports_vision_tool_messages=False) - images are accepted in user")
    print("messages, but list-type tool-result content is rejected with HTTP 400")
    print("(e.g. xiaomi/MiMo). FALLBACK here is forced by that profile veto, not")
    print("by a missing capability - declaring supports_vision will NOT lift it.")
if vis is None and not fast:
    print()
    # "unknown" has two very different causes. (a) PROVIDER ALIAS MAPPING GAP:
    # the hermes provider id is missing from PROVIDER_TO_MODELS_DEV, so the
    # lookup can never reach the cache even when the model IS recorded there
    # as vision-capable (upstream bug, e.g. alibaba-cn as of 2026-09).
    # (b) the model is genuinely absent from models.dev.
    alias_gap = False
    try:
        from agent.models_dev import PROVIDER_TO_MODELS_DEV
        alias_gap = bool(provider) and provider not in PROVIDER_TO_MODELS_DEV
    except Exception:
        pass
    cached_vision = False
    try:
        import json
        cache_path = os.path.join(_home, "models_dev_cache.json")
        if provider and os.path.isfile(cache_path):
            with open(cache_path, encoding="utf-8") as fh:
                data = json.load(fh)
            # cache is keyed by models.dev provider ids; under an alias gap the
            # hermes id may still be a valid models.dev key (alibaba-cn: yes)
            entry = (data.get(provider, {}) or {}).get("models", {}).get(model)
            if isinstance(entry, dict):
                cached_vision = bool(entry.get("attachment")) or \
                    "image" in (entry.get("modalities") or {}).get("input", [])
    except Exception:
        pass
    if alias_gap and cached_vision:
        print("PROVIDER ALIAS MAPPING GAP (upstream Hermes bug): models_dev_cache.json")
        print(f"DOES record '{model}' under '{provider}' as vision-capable, but")
        print("PROVIDER_TO_MODELS_DEV has no alias for this provider, so the")
        print("capability lookup can never reach the record. The 'no record'")
        print("wording below does NOT apply - do not chase the cache.")
        print("Persistent per-model workaround (survives cache refresh; beats the")
        print("catalog; ESCAPE dots inside the model id with backslash):")
        print(f"  hermes config set 'model_overrides.{provider}.{model.replace('.', chr(92)+'.')}.supports_vision' true")
        print("then READ BACK the yaml: the model id must appear as ONE key")
        print("(e.g. 'qwen3.8-flash:'), not split into nested bogus levels.")
        print("Consider reporting the missing provider alias upstream.")
    else:
        print("models.dev has no record of this model. If it is truly multimodal,")
        print("declare it explicitly (config override beats the cache):")
        print("  hermes config set model.supports_vision true")
        print("If Hermes is a fresh install, run it once to populate")
        print("<hermes-home>/models_dev_cache.json, then rerun this script.")
