#!/usr/bin/env python3
"""git_scope_guard.py: PreToolUse hook. Denies stage-everything git while lanes are live.

Wire it on the Bash tool (see hooks/settings.example.json). It reads the tool call as
JSON on stdin and answers with a permissionDecision. Inert with fewer than two live
lanes, so a solo session never sees it.

WHAT IT DENIES, only while `lanes.py armed` is true:

    git add -A / --all / -u / --update / .  / :/       stage everything
    git commit -a / -am / --all                          stage everything, then commit
    git commit with no `--` pathspec                     COMMITS THE WHOLE INDEX
    git commit --amend                                   rewrites HEAD, which under
                                                         parallel lanes may be another
                                                         lane's commit

THE FOURTH LINE IS THE ONE THAT COST SOMETHING. The first three are obvious. A bare
`git commit` after a careful `git add -- <paths>` looks careful and commits every path
anyone else has staged. The message then misdescribes its own contents, and a revert
on it destroys another lane's work. The rule said "pathspec on both halves" before the
guard did; documentation of a rule is not enforcement of it.

QUOTED REGIONS AND HEREDOC BODIES ARE STRIPPED FIRST. A commit message legitimately
says "never use git add -A". Prose about a command is not the command.

A NEWLINE ENDS A STATEMENT. The command is split on ; & | and newline, and every rule
is checked per statement, so a `--` on one line is never another line's pathspec.

WHAT IT IS NOT. This is a nudge against careless commands, not a boundary against an
actor who is trying to get past it. It reads command text with regexes, so anything
that hides the literal word `git` escapes it: `G=git; $G commit`, a shell alias, a
git alias (`git ci`), a wrapper script. A guard over text cannot see through
indirection, and this one does not try.

POLARITY. This guard fails OPEN on an internal error (a broken guard must not brick
the session), and the self-test is what stops it failing open silently forever. The
fixtures contradict each other: a guard that blocked everything fails the must-pass
cases, one that blocked nothing fails the must-block cases.

The refusal names every live lane and its job, so a session that started alone learns
from the block itself that it became parallel.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
try:
    import lanes  # noqa: E402
except ImportError:  # pragma: no cover
    lanes = None

_HEREDOC = re.compile(r"(?s)<<-?[ \t]*['\"]?(\w+)['\"]?[ \t]*\r?\n.*?\r?\n\1\b")
_DQ = re.compile(r'"[^"]*"')
_SQ = re.compile(r"'[^']*'")

_ADD_ALL = re.compile(r"(?i)\bgit\b[^;&|]*\badd\b[^;&|]*(\s-A\b|\s--all\b|\s-u\b|\s--update\b|\s\.(\s|$)|\s:/)")
_COMMIT_ALL = re.compile(r"(?i)\bgit\b[^;&|]*\bcommit\b[^;&|]*(\s--all\b|\s-\w*a\w*\b)")
_COMMIT = re.compile(r"(?i)\bgit\b[^;&|]*(?<![=\-])\bcommit\b")
_COMMIT_PATHSPEC = re.compile(r"(?i)(?<![=\-])\bcommit\b[^;&|]*\s--\s")
_AMEND = re.compile(r"(?i)\bgit\b[^;&|]*\bcommit\b[^;&|]*\s--amend\b")


def strip_data_regions(cmd):
    s = _HEREDOC.sub(" ", cmd)
    s = _DQ.sub(" ", s)
    s = _SQ.sub(" ", s)
    return s


_CONTINUATION = re.compile(r"[\\`][ \t]*\r?\n")


def statements(s):
    """Split a command into statements on ; & | AND newline.

    A newline ends a statement in every shell. Splitting only on ;&| let a `--` on a
    later line stand in as a bare commit's pathspec: `git commit -m x` NEWLINE
    `git diff -- src/` was allowed (security audit, 25 Oct 2026). A trailing backslash
    or PowerShell backtick continues the line, so those are joined first.
    """
    return [seg for seg in re.split(r"[;&|\r\n]+", _CONTINUATION.sub(" ", s)) if seg.strip()]


def violation(cmd):
    """Return a short reason if the command breaks the lane git rules, else None."""
    s = strip_data_regions(cmd)
    if not re.search(r"(?i)\bgit\b", s):
        return None
    for segment in statements(s):
        if _ADD_ALL.search(segment):
            return "stages everything (add -A / --all / -u / . / :/)"
        if _AMEND.search(segment):
            return "commit --amend rewrites HEAD, which may be another lane's commit"
        if _COMMIT_ALL.search(segment):
            return "commit -a / --all stages everything"
        # a commit with no `--` pathspec takes the whole index
        if _COMMIT.search(segment) and not _COMMIT_PATHSPEC.search(segment):
            return "commit carries no `--` pathspec, so it commits the WHOLE index"
    return None


def decide(cmd, live):
    """(decision, reason). live is the list of live lane records."""
    if len(live) < 2:
        return "allow", ""
    why = violation(cmd)
    if not why:
        return "allow", ""
    who = "; ".join("%s (%s)" % (r.get("lane"), r.get("job") or "no job line") for r in live)
    reason = (
        "LANE GIT SCOPE, DENIED: %s. %d lanes are live on this working tree: %s. "
        "Use an explicit pathspec on BOTH halves: `git add -- <your paths>` then "
        "`git commit -m \"...\" -- <the same paths>`. With pathspecs, --only is git's "
        "default, so the commit cannot sweep another lane's staged files. "
        "Run `python lanes.py status` to see the partition." % (why, len(live), who)
    )
    return "deny", reason


def main():
    try:
        payload = json.load(sys.stdin)
        cmd = (payload.get("tool_input") or {}).get("command") or ""
        live = lanes.live_lanes() if lanes else []
        decision, reason = decide(cmd, live)
    except Exception as exc:  # noqa: BLE001  fail OPEN, loudly
        decision, reason = "allow", "git_scope_guard internal error, failing open: %s" % exc
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
    live2 = [{"lane": "a", "job": "x"}, {"lane": "b", "job": "y"}]
    live1 = [{"lane": "a", "job": "x"}]

    def must_block(cmd):
        d, _ = decide(cmd, live2)
        if d != "deny":
            fails.append("MUST BLOCK, was allowed: %s" % cmd)

    def must_pass(cmd, live=live2):
        d, r = decide(cmd, live)
        if d != "allow":
            fails.append("MUST PASS, was denied: %s  (%s)" % (cmd, r))

    must_block("git add -A")
    must_block("git add --all && git commit -m x -- src/")
    must_block("git add . ")
    must_block("git add -u")
    must_block("git add :/")
    must_block("git commit -a -m 'x' -- src/")
    must_block("git commit -am 'x' -- src/")
    must_block("git add -- src/ && git commit -m 'careful add, bare commit'")
    must_block("git commit -m x")
    must_block("git add -- docs/ ; git commit --amend -m x -- docs/")
    must_block("git commit -F - -- src/ <<'EOF'\nmsg\nEOF\n && git add -A")
    # security audit 25 Oct 2026: a later line's `--` must not count as the pathspec
    must_block("git commit -m x\ngit diff -- src/")
    must_block("git commit -m x\r\ngit diff -- src/")
    must_block("git add -- src/\ngit commit -m x\necho -- done")
    must_block("git status\ngit add -A")

    must_pass("git add -- src/ && git commit -m 'never use git add -A' -- src/")
    must_pass("git commit -m \"git commit -a is banned\" -- docs/")
    must_pass("git status")
    must_pass("git log --grep=commit --oneline -5")
    must_pass("git diff -- src/")
    must_pass("git push origin master")
    must_pass("git commit -F - -- src/ <<'EOF'\nsubject\n\ngit add -A in the body is prose\nEOF")
    must_pass("echo 'git add -A' > /dev/null")
    must_pass("git add -- src/\ngit commit -m x -- src/")
    must_pass("git commit -m x \\\n  -- src/")          # bash line continuation
    must_pass("git commit -m x `\n  -- src/")           # PowerShell line continuation
    must_pass("git commit -m x -- src/\nls -a")         # -a on another line is not commit -a
    must_pass("git add -A", live=live1)          # inert below two lanes
    must_pass("git commit -m x", live=[])        # inert with no lanes

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print("git_scope_guard selftest: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
