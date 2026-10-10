#!/usr/bin/env python3
"""Hermes vision-path checker: native fast path vs auxiliary fallback.

Read-only diagnostic. Prints which vision path the active (or any given)
provider/model pair will take:

  venv/bin/python check_vision_path.py                       # config main + nearest active session
  venv/bin/python check_vision_path.py zai glm-5.3-flash     # any provider/model pair
  venv/bin/python check_vision_path.py --session <id>        # a session's ACTUAL runtime pair
  venv/bin/python check_vision_path.py --anchor 'text...'    # locate session via log anchor

Run it with the venv that belongs to your Hermes installation
(`venv/bin/python` on Linux/macOS, `venv\\Scripts\\python.exe` on Windows).
If Hermes lives outside the default location, set HERMES_HOME first.

Why --session: a chat `/model` hot-swap is per-session runtime state that
never writes config.yaml, so the no-arg checker reports the CONFIG pair
while the session runs another model entirely. The authoritative runtime
source is <hermes-home>/state.db -> table session_model_usage (model,
billing_provider, last_seen per session+model+task; task='' is the main
conversation). A hot-swap only appears there AFTER the next message is
sent (last_seen marks the last API call, not the intent).
"""
import os
import re
import sys
import glob
import time
import logging
import sqlite3

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

# ---------------------------------------------------------------------------
# Session-runtime model resolution (the /model hot-swap problem)
# ---------------------------------------------------------------------------

_SESSION_USAGE_SQL = (
    "SELECT model, billing_provider, last_seen "
    "FROM session_model_usage "
    "WHERE session_id = ? AND task = '' "
    "ORDER BY last_seen DESC LIMIT 1"
)
_USAGE_SCHEMA = {"session_id", "model", "billing_provider", "task", "last_seen"}
_LOG_TURN_PAT = re.compile(
    r"conversation turn: session=(\S+) model=(\S+) provider=(\S+) platform=(\S+)"
)


def _usage_table_ok(conn) -> bool:
    """Verify session_model_usage exists with the columns we depend on.

    Upstream schema drift (renamed/dropped table or columns) must surface as
    an explicit 'schema mismatch' error, never as silently wrong output.
    """
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(session_model_usage)")}
    except sqlite3.Error:
        return False
    return _USAGE_SCHEMA.issubset(cols)


def _open_state_db_ro():
    """Open state.db read-only. Returns (conn, error_str)."""
    db_path = os.path.join(_home, "state.db")
    if not os.path.isfile(db_path):
        return None, f"no state.db under {db_path}"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
        conn.execute("SELECT 1")
        return conn, None
    except sqlite3.Error as exc:
        return None, f"cannot open state.db read-only ({exc})"


def _fmt_ts(epoch) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(epoch)))
    except (TypeError, ValueError):
        return "?"


def resolve_session_pair(session_id):
    """Return (model, provider, last_seen_ts, note) for a session's main model.

    Layers: state.db session_model_usage (authoritative) -> None on failure.
    """
    conn, err = _open_state_db_ro()
    if conn is None:
        return None, None, None, f"session source unavailable: {err}"
    try:
        if not _usage_table_ok(conn):
            return None, None, None, (
                "schema mismatch: session_model_usage lacks expected columns "
                "(upstream schema change - this resolver needs an update)"
            )
        row = conn.execute(_SESSION_USAGE_SQL, (session_id,)).fetchone()
        if row:
            return row[0], row[1], row[2], None
        return None, None, None, (
            f"session '{session_id}' not in session_model_usage "
            "(unknown id, or no main-conversation API call yet)"
        )
    except sqlite3.Error as exc:
        return None, None, None, f"state.db query failed ({exc})"
    finally:
        conn.close()


def find_session_by_anchor(anchor_text):
    """Grep agent.log[.N] turn_context lines for the anchor text.

    Returns (session_id, model, provider, note). Measured log limits:
    msg= truncates at ~90 chars and keeps only the FIRST line of a multiline
    message; logs rotate at ~5 MB. So the anchor must be a PREFIX of the
    first line, and a hit is a HINT to confirm via session_model_usage.
    """
    if not anchor_text.strip():
        return None, None, None, "empty anchor text"
    first_line = anchor_text.strip().splitlines()[0]
    # msg= truncates ~90 chars; use at most the first 60 to stay safe
    prefix = first_line[:60]
    logs = [os.path.join(_home, "logs", "agent.log")] + sorted(
        glob.glob(os.path.join(_home, "logs", "agent.log.*")), reverse=True
    )
    hits = []
    for path in logs:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "conversation turn:" in line and prefix in line:
                        m = _LOG_TURN_PAT.search(line)
                        if m:
                            hits.append((m.group(1), m.group(2), m.group(3)))
        except OSError:
            continue
    if not hits:
        return None, None, None, (
            f"anchor not found in logs (message may be longer than the ~90-char"
            f" log truncation, multiline, rotated out, or too short/ambiguous)"
        )
    # later files are older; later lines are newer. hits list order:
    # current log first (newest), then .1, .2... within a file, bottom = newest
    # take the LAST hit of the FIRST file that has hits
    sid, model, provider = hits[0]
    return sid, model, provider, f"log anchor matched {len(hits)} turn line(s)"


def most_recent_active_session():
    """Heuristic: the session with the newest last_seen in session_model_usage.

    Not authoritative for 'the session you are in' - only a display hint.
    """
    conn, err = _open_state_db_ro()
    if conn is None:
        return None, err
    try:
        if not _usage_table_ok(conn):
            return None, "schema mismatch in session_model_usage"
        row = conn.execute(
            "SELECT session_id, model, billing_provider, last_seen "
            "FROM session_model_usage WHERE task = '' "
            "ORDER BY last_seen DESC LIMIT 1"
        ).fetchone()
        return (row, None) if row else (None, "no rows in session_model_usage")
    except sqlite3.Error as exc:
        return None, f"state.db query failed ({exc})"
    finally:
        conn.close()


def verdict(provider, model, cfg, explicit_pair: bool):
    """Compute the four-line verdict for a pair (upstream gate)."""
    mode = decide_image_input_mode(provider, model, cfg)
    tool_img = _supports_media_in_tool_results(provider, model)
    vis = _lookup_supports_vision(provider, model, cfg)
    veto = None
    if _profile_rejects_tool_media is not None:
        try:
            veto = bool(_profile_rejects_tool_media(provider, model))
        except Exception:  # noqa: BLE001
            veto = None
    if explicit_pair or _native_gate is not None:
        if _native_gate is not None:
            fast = _native_gate(provider, model, cfg)
        else:
            fast = (mode == "native") and (veto is not True) and (tool_img or vis is True)
    else:
        fast = _should_use_native_vision_fast_path()
    return mode, tool_img, vis, veto, fast


def print_verdict(provider, model, mode, tool_img, vis, veto, fast, prefix=""):
    print(f"{prefix}provider/model    : {provider} / {model}")
    print(f"{prefix}image input route : {mode}")
    print(f"{prefix}tool-result images: {tool_img}")
    print(f"{prefix}model vision      : {vis}")
    print(
        f"{prefix}=> vision path    : "
        + ("NATIVE (pixels enter the main-model context)" if fast
           else "FALLBACK (auxiliary.vision paraphrase, lossy)")
    )
    if veto is True and not fast:
        print()
        print(f"{prefix}note: this provider's profile vetoes tool-result media")
        print(f"{prefix}(supports_vision_tool_messages=False) - images are accepted in user")
        print(f"{prefix}messages, but list-type tool-result content is rejected with HTTP 400")
        print(f"{prefix}(e.g. xiaomi/MiMo). FALLBACK here is forced by that profile veto, not")
        print(f"{prefix}by a missing capability - declaring supports_vision will NOT lift it.")


def _print_vis_none_note(provider, model, vis, fast):
    if not (vis is None and not fast):
        return

def main() -> int:
    args = sys.argv[1:]
    session_id = None
    anchor = None
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--session":
            if i + 1 >= len(args):
                print("--session needs a session id argument")
                return 2
            session_id = args[i + 1]
            i += 2
            continue
        if a == "--anchor":
            if i + 1 >= len(args):
                print("--anchor needs a message-prefix argument")
                return 2
            anchor = args[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            print(f"unknown flag: {a}")
            print("usage: check_vision_path.py [<provider> <model>]")
            print("       check_vision_path.py --session <session-id>")
            print("       check_vision_path.py --anchor '<message prefix>'")
            return 2
        positional.append(a)
        i += 1

    cfg = load_config()

    # --- Mode 1: --session <id> (authoritative runtime pair) ---
    if session_id:
        model, provider, last_seen, note = resolve_session_pair(session_id)
        if model is None:
            print(f"cannot resolve session '{session_id}': {note}")
            print()
            print("fallbacks:")
            print("  - pass the provider/model pair explicitly")
            print("  - --anchor '<message prefix>' greps agent.log turn lines")
            return 1
        if anchor:
            print(f"(--anchor ignored when --session is given)")
        print(f"session            : {session_id}")
        print(f"runtime model      : {model} @ {provider}")
        print(f"last API call      : {_fmt_ts(last_seen)} (hot-swaps appear after the next message)")
        print()
        mode, tool_img, vis, veto, fast = verdict(provider, model, cfg, explicit_pair=True)
        print_verdict(provider, model, mode, tool_img, vis, veto, fast)
        _print_vis_none_note(provider, model, vis, fast)
        return 0

    # --- Mode 2: --anchor '<text>' (log grep -> confirm) ---
    if anchor is not None:
        sid, model, provider, note = find_session_by_anchor(anchor)
        if sid is None:
            print(f"anchor lookup failed: {note}")
            return 1
        print(f"log anchor          : {note}")
        print(f"session (from log)  : {sid}")
        # Confirm against the authoritative table
        r_model, r_provider, last_seen, r_note = resolve_session_pair(sid)
        if r_model is None:
            print(f"session_model_usage could not confirm: {r_note}")
            print("treating the log line as a hint only; verdict below uses the")
            print("log's pair (may be stale after a recent hot-swap).")
        elif r_model != model:
            print(f"DISCREPANCY: log says {model}, session_model_usage says {r_model}")
            print(f"  (session_model_usage is newer - a hot-swap happened after the log")
            print(f"   line was written; using the newer pair)")
            model, provider = r_model, r_provider
        else:
            print(f"confirmed by session_model_usage (as of {_fmt_ts(last_seen)})")
        print()
        mode, tool_img, vis, veto, fast = verdict(provider, model, cfg, explicit_pair=True)
        print_verdict(provider, model, mode, tool_img, vis, veto, fast)
        return 0

    # --- Mode 3: two positional args (any pair) ---
    if len(positional) >= 2:
        provider, model = positional[0], positional[1]
        mode, tool_img, vis, veto, fast = verdict(provider, model, cfg, explicit_pair=True)
        print_verdict(provider, model, mode, tool_img, vis, veto, fast)
        _print_vis_none_note(provider, model, vis, fast)
        return 0

    # --- Mode 4: no args (config pair + active-session dual view) ---
    provider = _read_main_provider() or ""
    model = _read_main_model() or ""
    mode, tool_img, vis, veto, fast = verdict(provider, model, cfg, explicit_pair=False)
    print("=== config main model ===")
    print_verdict(provider, model, mode, tool_img, vis, veto, fast)
    row, err = most_recent_active_session()
    if row:
        a_sid, a_model, a_provider, a_last = row
        same = (a_model == model and a_provider == provider)
        print()
        print("=== most-recent active session (heuristic) ===")
        print(f"session            : {a_sid}")
        print(f"runtime model      : {a_model} @ {a_provider}")
        print(f"last API call      : {_fmt_ts(a_last)}")
        if same:
            print("matches the config pair - no hot-swap detected.")
        else:
            a_mode, a_tool, a_vis, a_veto, a_fast = verdict(
                a_provider, a_model, cfg, explicit_pair=True)
            print("MISMATCH: config says the main model is the pair above, but the")
            print("most-recent active session runs a different pair (hot-swap).")
            print("Its verdict:")
            print()
            print_verdict(a_provider, a_model, a_mode, a_tool, a_vis, a_veto, a_fast, prefix="  ")
            print()
            print("If this is YOUR session, rerun with the session's pair:")
            print(f"  check_vision_path.py {a_provider} {a_model}")
            print(f"  check_vision_path.py --session {a_sid}")
            print("Use --session for the authoritative runtime pair.")
    elif err:
        print()
        print(f"(active-session view unavailable: {err})")
    _print_vis_none_note(provider, model, vis, fast)
    return 0


if __name__ == "__main__":
    sys.exit(main())
