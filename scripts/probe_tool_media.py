#!/usr/bin/env python3
"""Decisive two-request probe: does the endpoint accept images in TOOL results?

Read-only arbitration for the "capability present, channel vetoed" shape
(checker says FALLBACK + model vision: True + profile veto note). The provider
profile declaration (supports_vision_tool_messages) is a HYPOTHESIS about the
endpoint and can go stale; this probe is the ground truth.

  venv/bin/python probe_tool_media.py                     # current main provider/model
  venv/bin/python probe_tool_media.py <provider> <model>  # any provider/model pair

Two minimal requests that vary ONLY the channel (1x1 RED PNG, tiny max_tokens):
  A - tool-result : image inside a role:"tool" message as LIST content
      -> 400 on a vetoing endpoint (e.g. "text is not set"); 200 if accepted
  B - user-message: same image inside a role:"user" content list (control)

Verdict rules (acceptance != capability!):
  - A 200 alone does NOT prove the model sees the image. The answer must NAME
    the colour ("red"); anything else is a blind accept.
  - A 200 + colour named  -> the veto declaration is STALE (fix the profile;
    see the "stale veto declaration" flow in SKILL.md Pitfalls).
  - A 400 rejecting the CONTENT (format errors like "text is not set")
    -> the declaration is still accurate; change nothing.
  - A 400 rejecting the MODEL ID ("Unsupported model", "model not found")
    -> retired/renamed id, NOT channel evidence; resolve the current model
    name and re-probe before judging the veto.

API keys are read in-process from <hermes-home>/.env and never printed.
"""
import base64
import json
import os
import struct
import sys
import urllib.error
import urllib.request
import zlib

# provider -> default OpenAI-compatible base url (extend when needed)
_DEFAULT_BASE_URLS = {
    "xiaomi": "https://api.xiaomimimo.com/v1",
}


def locate_hermes_home() -> str:
    home = os.environ.get("HERMES_HOME", "").strip()
    if home and os.path.isdir(home):
        return home
    return os.path.expanduser("~/.hermes")


def load_env_kv(home: str) -> dict:
    kv = {}
    env_path = os.path.join(home, ".env")
    if not os.path.isfile(env_path):
        return kv
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            kv[k.strip()] = v.strip().strip('"').strip("'")
    return kv


def make_red_png() -> bytes:
    """Deterministic 1x1 pure-red RGB PNG (no PIL needed)."""
    def chunk(typ: bytes, data: bytes) -> bytes:
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = zlib.compress(b"\x00\xff\x00\x00")  # filter byte 0 + RGB(255,0,0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def call_chat(base: str, key: str, model: str, messages: list):
    payload = {"model": model, "max_tokens": 2000, "messages": messages}
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read())
            content = body["choices"][0]["message"].get("content")
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            return resp.status, str(content)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(errors="replace")[:300]
    except Exception as exc:  # noqa: BLE001
        return "ERR", f"{exc.__class__.__name__}: {exc}"[:300]


def _is_model_id_error(body: str) -> bool:
    """400 body rejecting the model NAME (retired/renamed id), not the content."""
    b = body.lower()
    return any(sig in b for sig in (
        "unsupported model", "model not found", "invalid model",
        "model_not_found", "does not exist", "no such model",
    ))


def main() -> int:
    home = locate_hermes_home()
    if len(sys.argv) >= 3:
        provider, model = sys.argv[1], sys.argv[2]
    else:
        repo = os.path.join(home, "hermes-agent")
        if os.path.isdir(repo):
            sys.path.insert(0, repo)
        try:
            from agent.auxiliary_client import _read_main_provider, _read_main_model

            provider = _read_main_provider() or ""
            model = _read_main_model() or ""
        except Exception:  # noqa: BLE001
            provider = model = ""
        if not provider or not model:
            print("usage: probe_tool_media.py <provider> <model>  (or run inside a Hermes install)")
            return 1

    kv = load_env_kv(home)
    up = provider.upper().replace("-", "_")
    key = kv.get(f"{up}_API_KEY") or kv.get(f"{up.upper()}_API_KEY")
    base = kv.get(f"{up}_BASE_URL") or _DEFAULT_BASE_URLS.get(provider)
    if not key:
        print(f"no API key found in {home}/.env (looked for {up}_API_KEY) - refusing to guess")
        return 1
    if not base:
        print(f"no base url known for provider '{provider}' - set {up}_BASE_URL in {home}/.env")
        return 1

    img_url = "data:image/png;base64," + base64.b64encode(make_red_png()).decode()
    img_part = {"type": "image_url", "image_url": {"url": img_url}}
    txt_part = {"type": "text", "text": "What colour is this image? Answer with the colour name only."}

    print(f"provider/model : {provider} / {model}")
    print(f"base url       : {base}")
    print(f"key            : <redacted, read from {home}/.env>")
    print()

    # A: tool-result channel - list content inside a role:"tool" message
    msgs_a = [
        {"role": "user", "content": "Use the tool result to answer."},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "call_1", "type": "function",
                         "function": {"name": "get_image", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": [txt_part, img_part]},
    ]
    # B: user-message channel (control)
    msgs_b = [{"role": "user", "content": [txt_part, img_part]}]

    verdicts = {}
    for label, msgs in (("A tool-result", msgs_a), ("B user-message", msgs_b)):
        status, answer = call_chat(base, key, model, msgs)
        sees = status == 200 and "red" in answer.lower()
        verdicts[label] = (status, sees, answer)
        print(f"--- {label} ---")
        print(f"status : {status}")
        print(f"answer : {answer[:200]}")
        print(f"names the colour 'red': {'YES' if sees else 'NO'}")
        print()

    sA, seesA, ansA = verdicts["A tool-result"]
    print("=> verdict:")
    if sA == 200 and seesA:
        print("   TOOL-RESULT CHANNEL WORKS AND THE MODEL SEES THE IMAGE.")
        print("   If a profile veto (supports_vision_tool_messages=False) is still")
        print("   declared for this model it is STALE - fix the declaration (SKILL.md")
        print("   Pitfalls: 'stale veto declaration' flow), then rerun")
        print("   check_vision_path.py + real-image test.")
    elif sA == 200 and not seesA:
        print("   ACCEPTED BUT BLIND: 200 yet the model did not name the colour.")
        print("   Acceptance != capability - do NOT declare this model multimodal")
        print("   on the tool-result channel and do NOT touch the declaration.")
    elif sA == 400 and _is_model_id_error(ansA):
        print("   MODEL ID REJECTED (HTTP 400), NOT THE CHANNEL: the error body")
        print("   names the model id itself (retired/renamed). This is NOT evidence")
        print("   about tool-media support - the veto question is INCONCLUSIVE for")
        print("   this id. Resolve the current model name first (GET /models or one")
        print("   tiny call; error bodies may list accepted ids), then re-probe.")
    elif sA == 400:
        print("   TOOL-RESULT CHANNEL REJECTED (HTTP 400, content/format error) -")
        print("   the profile veto is still accurate. Change nothing; use the")
        print("   user-message channel or accept the auxiliary transcription.")
    else:
        print(f"   inconclusive (status={sA}); check the endpoint/model id and retry.")
    sB, seesB, _ = verdicts["B user-message"]
    if sB == 200 and not seesB:
        print("   NOTE: even the user-message channel did not name the colour -")
        print("   the model itself may be text-only despite accepting image blocks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
