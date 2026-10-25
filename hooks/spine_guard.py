#!/usr/bin/env python3
"""spine_guard.py: PreToolUse hook. Asks before a write to a SHARED file while lanes are live.

Wire it on the file-editing tools (Write, Edit, MultiEdit, NotebookEdit; see
hooks/settings.example.json). Inert with fewer than two live lanes.

THE SPINE is the set of files every session would otherwise write at once: a daily
note, an agenda, a shared task list, an append-only log. Under parallel lanes two
sessions editing one of them collide and one silently wins. So while two or more lanes
are live, a write to a spine file is an ASK, not a deny: one session (the "drain")
legitimately needs to write all of them at the end, and everyone else is told to
capture into their own dated lane file instead.

WHICH FILES ARE THE SPINE is read from `.lanes-spine` at the repo root, one pattern
per line, gitignore-style (a trailing `/` matches a directory, `*` and `**` work,
`#` starts a comment). Keep that list in ONE place: this file reads it and nothing
else enumerates it. Four surfaces each carrying a different copy of the same list
was a measured defect in the setup this was extracted from.

Fails OPEN on an internal error, loudly, and has a self-test.
"""

import fnmatch
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
try:
    import lanes  # noqa: E402
except ImportError:  # pragma: no cover
    lanes = None

SPINE_FILE = os.environ.get("LANES_SPINE", os.path.join(lanes.REPO_ROOT if lanes else ROOT, ".lanes-spine"))
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def load_patterns(path=SPINE_FILE):
    pats = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    pats.append(line.replace("\\", "/"))
    except OSError:
        pass
    return pats


def _rel(target, root):
    t = os.path.abspath(target).replace("\\", "/")
    r = os.path.abspath(root).replace("\\", "/").rstrip("/") + "/"
    return t[len(r):] if t.lower().startswith(r.lower()) else t


def is_spine(target, patterns, root):
    rel = _rel(target, root)
    for pat in patterns:
        if pat.endswith("/"):
            if rel.lower().startswith(pat.lower()) or ("/" + pat.lower()) in ("/" + rel.lower()):
                return True
            continue
        if fnmatch.fnmatch(rel.lower(), pat.lower()) or fnmatch.fnmatch(os.path.basename(rel).lower(), pat.lower()):
            return True
        if "**" in pat and fnmatch.fnmatch(rel.lower(), pat.replace("**/", "").lower()):
            return True
    return False


def decide(tool, target, live, patterns, root):
    if tool not in FILE_TOOLS or not target or len(live) < 2:
        return "allow", ""
    if not is_spine(target, patterns, root):
        return "allow", ""
    who = "; ".join("%s (%s)" % (r.get("lane"), r.get("job") or "no job line") for r in live)
    return "ask", (
        "SHARED SPINE, and %d lanes are live: %s. `%s` is written by every lane, so concurrent "
        "edits collide and one silently wins. Unless you are the drain session, capture into "
        "your own _lane-<lane>-<date>.md inside your own prefix instead; the drain merges the "
        "lane files afterwards. Run `python lanes.py status`." % (len(live), who, _rel(target, root))
    )


def main():
    try:
        payload = json.load(sys.stdin)
        tool = payload.get("tool_name") or ""
        target = (payload.get("tool_input") or {}).get("file_path") or (payload.get("tool_input") or {}).get("notebook_path") or ""
        live = lanes.live_lanes() if lanes else []
        root = lanes.REPO_ROOT if lanes else ROOT
        decision, reason = decide(tool, target, live, load_patterns(), root)
    except Exception as exc:  # noqa: BLE001  fail OPEN, loudly
        decision, reason = "allow", "spine_guard internal error, failing open: %s" % exc
        print(reason, file=sys.stderr)
    if decision == "allow" and not reason:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason}}))
    return 0


def selftest():
    fails = []
    root = "/repo"
    pats = ["AGENDA.md", "daily/", "logs/observations.md", "**/TASKS.md"]
    live2 = [{"lane": "a", "job": "x"}, {"lane": "b", "job": "y"}]

    def check(label, got, want):
        if got != want:
            fails.append("%s: got %r, want %r" % (label, got, want))

    check("spine exact, armed", decide("Write", "/repo/AGENDA.md", live2, pats, root)[0], "ask")
    check("spine exact, disarmed", decide("Write", "/repo/AGENDA.md", live2[:1], pats, root)[0], "allow")
    check("spine dir, armed", decide("Edit", "/repo/daily/2026-09-11.md", live2, pats, root)[0], "ask")
    check("nested pattern", decide("Edit", "/repo/work/TASKS.md", live2, pats, root)[0], "ask")
    check("non-spine file, armed", decide("Edit", "/repo/src/x.py", live2, pats, root)[0], "allow")
    check("lane record is never spine", decide("Write", "/repo/docs/_lane-a-2026-09-11.md", live2, pats, root)[0], "allow")
    check("non-file tool ignored", decide("Bash", "/repo/AGENDA.md", live2, pats, root)[0], "allow")
    check("sibling stem is not the dir", decide("Edit", "/repo/daily-old/x.md", live2, pats, root)[0], "allow")
    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print("spine_guard selftest: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
