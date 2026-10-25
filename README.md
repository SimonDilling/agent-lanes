# agent-lanes

**Several AI coding sessions, one working tree, no worktrees.** A four-rule contract, a
register that arms two permission hooks by itself, and the incidents that bought each rule.

I run four or five Claude Code sessions at the same time on one laptop against one folder. One
working tree, one `.git`, one branch. Every guide says "use worktrees". My folder is not a
codebase, it is a private corpus with several confidentiality boundaries inside it, and a
worktree puts a second complete copy of all of them on disk where my note app indexes it and
git sees it.

So the question this repo answers is not "how do I isolate agents" but **"how do several
agents share one tree without me losing the ability to say which one did what"**.

If your folder can be duplicated safely, use worktrees. Every harness ships them and they are
the simpler design. This is for the case where you cannot, or will not. Not related to lanes.sh,
whose lanes are worktrees; this is the opposite design.

## What is in it

| File | What it is |
|---|---|
| [`LANES.md`](LANES.md) | The contract. Four rules, one command, the refusals, and the incident under each rule. Read this first. |
| [`lanes.py`](lanes.py) | The register, with `claim`, `status`, `request`, `grant`, `decline`, `end`, `prune`, `armed` and `--selftest`. Standard library only. |
| [`hooks/git_scope_guard.py`](hooks/git_scope_guard.py) | PreToolUse hook on Bash. Denies `git add -A`, `add .`, `add -u`, `commit -a`, `commit --amend` and any commit with no `--` pathspec, only while two or more lanes are live. Fails open on an internal error, loudly. |
| [`hooks/spine_guard.py`](hooks/spine_guard.py) | PreToolUse hook on file edits. Asks before a write to a shared file listed in `.lanes-spine`, only while two or more lanes are live. Fails open on an internal error, loudly. (Both guards fail open here; the author's own private guards fail closed. Either is valid, see `LANES.md`, "The parts".) |
| [`hooks/settings.example.json`](hooks/settings.example.json) | The hook wiring for Claude Code. |
| [`.lanes-spine`](.lanes-spine) | The shared-file list, the only place it lives. |
| [`LANE-RECORD.md`](LANE-RECORD.md) | The schema of the dated file each lane writes instead of the shared ones. |
| [`ESSAY.md`](ESSAY.md) | The long version. Why the contract exists, what version one got wrong, and the four things I refused to build. |

## The contract in four sentences

A session you tell is a lane registers itself with a name, the path prefixes it owns, one line
saying what it is doing, and its own session address. The registration expires by itself at
the work-day roll. While two or more lanes are registered, four rules bind:

1. Write only inside your own prefixes.
2. Never stage everything. Name the paths on the add **and** on the commit.
3. Do not write the shared files every session touches. Capture into your own dated lane
   file and let one session merge afterwards.
4. Do not run the end-of-day close. One session does that, once.

One command answers everything:

```
python lanes.py status
```

When a lane needs a prefix another lane owns, it does not write and it does not only ask in
chat. `lanes.py request` files a request in the register, every lane's next `status` shows it
to the owner, and the owner answers with `grant` (the prefix moves to the asker, the hooks
follow) or `decline` (with a reason). The full sequence is in `LANES.md`, "Handing a prefix
over". A lane that re-claims with a different `--owns` on the same day is announced the same
way. The claim prints what it released and what it added, and every lane's next `status`
shows the line.

## Install

1. Copy this folder into your repository (or add it as a submodule) as `agent-lanes/`.
2. Add `.lanes/` to your `.gitignore`. The register is runtime state, never committed.
3. Edit `.lanes-spine` to name your shared files.
4. Copy the `hooks` block from `hooks/settings.example.json` into `.claude/settings.json`
   (committable) or `.claude/settings.local.json` (private). Adjust the paths if the folder
   lives elsewhere. Other harnesses with a pre-tool hook that can return deny or ask can
   run the same two scripts; each reads the tool call as JSON on stdin.
5. Run the three self-tests:

```
python lanes.py --selftest
python hooks/git_scope_guard.py --selftest
python hooks/spine_guard.py --selftest
```

## Use

Open each session with a line that names its **own** lane:

```
You are the DOCS lane, running parallel to other live sessions. Read LANES.md, register yourself with lanes.py, and obey your lane contract. My job for you is below.
```

The session's first act:

```
python lanes.py claim --lane docs --owns docs/ README.md --job "rewrite the install guide" --session <its address>
```

From the second live lane on, the guards are armed for every session, including the one that
started first. A session nobody briefed finds out from the refusal, which names every live lane
and its job.

When a lane's job is done it reports, commits its own paths, writes its resume point, and
**stays registered**. You end it:

```
python lanes.py end --lane docs
```

## The asymmetry that decides every default

Guards armed when they were not needed cost one extra prompt. Guards disarmed when they were
needed cost another session's uncommitted work. Not comparable, so every unknown fails toward
armed, and nothing can force the guards off.

## What it does not solve

The register knows what was declared, not what is alive; a dead session reads live until the
roll. And inside one session, sub-agents share one permission surface, so "which agent wrote
this" has no enforceable answer there. The fix for that is to make sub-agents non-writing and
let the parent do every write.

## Provenance

Extracted from a private setup that has run this contract since 2 August 2026. In the 85 days
to 25 October 2026, lanes left a dated record on 67 days, and on 52 of those days two or more
lanes did. Every incident in `LANES.md` happened; dates are kept, names and paths are not. The code here is a
clean, minimal reimplementation of the mechanism, not a copy of the original files, which are
tied to that setup's folder layout and clock.

## Licence

MIT. See `LICENSE`.
