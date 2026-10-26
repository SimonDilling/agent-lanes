# LANES.md, several agent sessions, one working tree

**One machine, one working tree, one `.git`, one branch. Several AI coding sessions at once.**
This file is the contract that stops them corrupting each other's work. Two permission hooks
read the live state at runtime, so it binds rather than advises.

**Parallel is a standing capability, not a mode you switch on.** A session registers itself,
any session can see who else is awake, and the guards arm themselves the moment a second
lane appears. Nothing to remember at the start, nothing to remember at the end.

Every rule below carries the incident that bought it. Keep those attached. Nearly three months in,
the incidents are the most valuable lines in this file. They are what stop a future reader
from optimising a rule away on a quiet afternoon when nothing has gone wrong in a while.

---

## The one command

```
python lanes.py status
```

Who is live, what each lane owns, what each lane is doing, whether the guards are armed, and
whether any two lanes have overlapping paths. **Derived at read time and stored nowhere.**

Do not save its output anywhere. A saved copy is a photograph that goes stale silently while
looking like the current picture. Run it again instead; it is instant.

## Registering

The first thing a session does when you tell it that it is a lane:

```
python lanes.py claim --lane docs --owns docs/ README.md --job "rewrite the install guide" --session <its own address>
```

`--owns` takes path prefixes relative to the repository root. **Declare them even when they
seem obvious**. They are what lets `status` prove the partition is disjoint rather than assume
it. A lane with no declared prefix cannot be checked against anyone.

`--session` is the session's own address in your harness's session list, if it has one.
Optional. A missing one prints as `UNKNOWN`, never as a
guess, because a message sent to the wrong session starts a turn in a lane that did not ask
for one.

**Quote any path with a space in it, and quote each path separately, never the whole list.**
`--owns` takes a list of arguments. Wrapping several prefixes in one pair of quotes passes
one argument containing spaces, and the lane is recorded as owning a single nonsense prefix:

```
--owns "docs/ src/"        WRONG: one prefix, containing a space
--owns docs/ src/          right: two prefixes
--owns "notes/My Folder/"  right: one prefix that happens to contain a space
```

> **Incident, 5 August 2026.** Two lanes each claimed a path with a space in it, unquoted. The shell split
> each into three fragments before the tool saw it. Both lanes' real claims were never
> registered, so nothing would have caught a third lane taking them, and the overlap check
> went on reporting confidently. Both happened to produce the fragment `and`, which collided
> with itself and printed a FALSE overlap. The first fix ("quote them") did nothing, because
> the tool stored `owns` as a space-joined string and split it back on read, a round trip
> that destroyed its own input. `owns` is a JSON array now. A fix verified by reasoning about
> the input is not verified; this one was caught only because it was applied.

**A re-claim on the same day with different `--owns` is a repartition, and it announces
itself.** The claim prints `REPARTITIONED released=... added=...`, the line is stamped into the
register, and every lane's next `status` shows it under that lane. A scope change is then a
property of the register, not of a lane remembering to say so.

**Claim the paths the job touches, not the folders the job lives in.** A folder claim
silently asserts ownership of every other lane's surface that happens to sit beside it.

> **Incident, 4 August 2026.** A lane took two whole top-level folders for a job touching three files in
> one and three subtrees in the other. Five overlaps fired, all five from the two folder-wide
> claims. The detector working five times is the system succeeding; the five collisions were
> avoidable by claiming narrower.

**A session never ends its own lane. The human ends lanes.**

```
python lanes.py end --lane docs
```

A lane that finishes its stated job is not a lane that is over. Report the job done, commit
your own paths, write your resume point, and stay registered. When the human says end, run
the command above. Not before.

> **Incident, three times, 6 and 10 August 2026.** The operational how-to at the top of an earlier version of this
> file told a finishing lane to run `lanes.py end`, flatly contradicting the ruling 200 lines
> below it. Sessions read the how-to and never reached the ruling. Two lanes ended themselves
> in one afternoon with work outstanding, and a third finished its deliverable, read "that is
> all" as the exit condition, and ended a lane that still had a second, larger phase waiting.
> Two copies of one rule drift, and the copy a session actually reads is the one it follows.

**Forgetting to register is the unsurvivable one.** A registration expires on its own at the
work-day roll (05:00 by default; set `LANES_DAY_ROLLS_AT`), so a lane left open costs one
`lanes.py prune`. The worst case for a missing registration is another lane's uncommitted work
inside someone else's commit. **The asymmetry is the whole design. A lane left open is free; a
lane closed early re-claims, misreports the live set, and can disarm the guards around live
work.**

## When the guards are armed

**Two or more live registrations.** That is the whole rule, and it is a fact rather than a
setting. One live lane is a normal session and changes nothing.

| Registered lanes | What happens |
|---|---|
| 0 or 1 | Nothing. The tree behaves exactly as it always has. |
| 2 or more | Both guards arm, for every session including the one that started first. |

**The asymmetry that sets every default here:**

> Guards armed when they were not needed cost one extra prompt.
> Guards disarmed when they were needed cost another lane's uncommitted work.

Those are not comparable. So every judgement in `lanes.py` fails toward armed. A registration
with no date counts as live, an unreadable one counts as live, an unreadable register directory
counts as live. Nothing can force the guards off.

## The four rules. Every lane obeys all four

### 1. Never `git add -A`, `git add .`, `git add -u`, or `git commit -a`

This is the one that would actually destroy work. One working tree means `add -A` from lane A
stages lane B's half-finished files with no prompt. The commit message then lies about its
contents, and a `git revert` on it destroys another lane's work.

**Put the pathspec on the commit as well as the add. Staging discipline is not commit
discipline.**

```
git add -- docs/
git commit -m "docs: rewrite the install guide" -- docs/
```

A careful `git add -- <path>` followed by a bare `git commit` commits the whole shared index,
including anything another lane staged and has not yet committed. The add was scoped; the
commit was not.

> **Incident, 2 August 2026.** One lane staged its own folder only, ran a bare `git commit`, and its commit
> carried six files, five of its own plus a rename staged by another lane. Nothing was lost,
> and that is luck rather than design. The foreign change was a content-free rename. Had it
> been a half-finished edit, the commit message would have lied about its contents and a
> revert on it would have destroyed another lane's work. The rule "pathspec on both halves"
> had been written into this file by that same lane four hours earlier. The guard denied
> three of the four ways to break the rule and not the bare commit, because a bare commit
> does not look like a stage-everything command. **The enforcement was attached to a narrower
> trigger than the rule it enforces.** Documentation of a rule is not enforcement of it.
>
> **It happened again the next day, 3 August 2026.** A second lane scoped its add, committed
> with no paths, swept another lane's staged files into its own commit and pushed. The bytes
> were identical, so the cost was attribution and not data. The guard has denied the bare
> commit since that day.

**And the pathspec'd commit is structurally safe, not merely disciplined.** When `git commit`
is given pathspecs, `--only` is git's default mode. The commit takes the working-tree contents
of the named paths, disregarding anything staged for other paths, and the other lanes' staged
content is not lost, merely held back (git-scm.com, `git-commit`, read 22 August 2026). So a
correctly pathspec'd commit cannot sweep another lane's staged files even in principle. This is
why no worktree or second clone is needed. Either would buy isolation this architecture
already has, at the price of a second working copy.

**Never `git commit --amend` under live lanes.** A pathspec scopes the content and nothing
scopes the target. `--amend` rewrites HEAD, and under parallel lanes HEAD may no longer be your
own commit by the time you run it.

> **Incident, 22 August 2026.** A lane committed while alone, noticed a stray character in its message, and
> amended. Between those two acts three lanes went live and another lane committed on top. The
> amend, with a correct pathspec on both halves, rewrote the OTHER lane's commit message with
> the first lane's text. Their tree, another lane's words. The push was rejected because the
> amend rewrote an already-pushed commit, and that rejection is the only thing that limited
> it. A stray character in a message costs nothing; this cost another lane's commit message.
> Write a new commit instead, or leave the typo.

**Write the message as `-m` flags or via `git commit -F -` with a heredoc, never as a shell
here-string the guard cannot parse.** The guard strips quoted regions and heredoc bodies before
judging, so prose about a command is not the command; a commit message may say "never use
git add -A".

### 1b. A rejected push is usually bookkeeping, and the obvious fix is the destructive one

> **Incident, 20 August 2026, and again on 4 September.** A push failed with `cannot lock ref 'refs/heads/master': is at 70a74a4 but
> expected 8cde76d`, and the work had already shipped. The lane committed, its push ran a
> pre-push hook for about 25 seconds, and inside that window another lane committed on top and
> pushed, carrying the first lane's commit to the remote as its parent. The compare-and-swap
> then failed against a stale expected value.

**The hazard is the remedy.** A rejected push reads as "my work did not land", and the two
moves that look right, `push --force` and `reset --hard`, would each destroy another lane's
commit to fix a problem that did not exist. An alarm is not evidence; the response is more
reading, never a faster write. Three read-only commands settle it:

```
git ls-remote origin refs/heads/master
git log --oneline -5
git ls-tree -r --name-only origin/master -- <your paths>
```

If your commit is an ancestor of the remote head, you are done. Only then consider a pull and
rebase. When a push is reported, name the evidence ("remote verified at `<sha>` by
`ls-remote`"), never a bare "pushed" and never "push failed" on a rejection nobody has read.

### 2. Do not write the shared spine. Capture into your own lane file instead

The spine is the set of files all lanes would otherwise write at once, such as a daily note, an agenda,
a shared task list, an append-only log, a run ledger. **Name them in `.lanes-spine`, one
pattern per line, and nowhere else**; the spine guard reads that file.

> **Incident, 4 August 2026.** Four different surfaces each carried a different enumeration of the same
> ledger list. Only one file may enumerate it.

**Instead, every lane writes `_lane-<lane>-<date>.md` inside its own prefix.** Same shape as
a daily note, with what happened, what was decided, what is open, and any side-findings with their
reasoning. It commits with your lane's existing pathspec, so it needs no new partition. The
schema is in `LANE-RECORD.md`.

**A side-finding goes in the lane record too.** A mid-session finding that is not a question
has no other home; write it into your lane record in the moment and keep working. The drain
routes it or lets it die there, which is a legitimate outcome for most of them.

**And the pathspec rule cannot protect a file two lanes both legitimately write. It is
structurally incapable of it.** Rule 1 stops lane A staging lane B's other files. It cannot stop
lane A staging lane B's uncommitted edits to a file A also owns, because `git add -- <path>`
takes the whole working-tree state of that path, not the subset of hunks the adding lane
authored.

> **Incident, 17 August 2026, twice in fifteen minutes.** Two lanes obeyed both rules correctly. At 15:45 one
> edited the shared observation log and had not committed; at 15:52 the other committed that
> log with an explicit pathspec, legitimately, for its own entry. The commit carried 78
> insertions, most of them the first lane's, under a message describing only its own. Nothing
> was lost and the commit misdescribes its own contents.

So **on any file two lanes both append to, append-and-commit is one action.** A lane that
appends an entry commits that file before doing anything else; the exposure window is the
whole cost and the only variable a writer controls. At close, read `git status` for your own
uncommitted spine files before staging anything, and if another lane's edits sit in a file you
are about to stage, say so in the commit message rather than silently absorbing them.

**Identifier allocation is the collision the guards cannot see (22 August 2026, twice within
minutes).** If the human overrides this
rule for a day and several lanes write one shared numbered list, read-the-maximum-and-add-one is
not atomic. Two lanes will allocate the same number, then collide again on the renumber. Under
such an override a lane takes its numbers from a reserved block (the next free multiple of ten)
instead of max-plus-one.

### 3. Run the end-of-day close once, never per lane

Three closes means three commits and three rewrites of the same note. A lane ends by writing its
own lane file and committing its own paths. One session runs the close afterwards, and the first
step of that close is the drain. It reads every lane file, routes what it holds, and stamps each one
`drained: <date> <HH:MM>` in its frontmatter.

**The time is what makes the stamp checkable.** A file drained at 14:00 and written to again at
15:00 carries a stamp dated today and reads DRAINED, because a date-only stamp cannot see a
same-day refill. A false DRAINED buries a dated commitment; a false UNDRAINED costs one look.

**Moving an undrained file to an archive marks it drained.** A tidy-up pass that sweeps the
folder does not clean the report, it falsifies it, silently and permanently. If you did not read
it in full this session, leave it where it is.

### 4. Your prompt names your lane. If it does not, stop and ask

Read this file, register, and work only your own prefix. A session that cannot identify its own
lane must not guess, because every rule above depends on knowing which prefix it owns.

**The opening line must name the session's OWN lane.** The first three drafts of the opening
line each named the other two lanes and never their own. "Accounting and building are running"
told a session nothing about which prefix IT owned. The general form:

```
You are the <NAME> lane, running parallel to other live sessions. Read LANES.md, register yourself with lanes.py, and obey your lane contract. My job for you is below.
```

**And a session nobody tells will find out anyway**, which is the property that makes this safe
rather than merely tidy. The moment a second lane registers, the first session's next
`git add -A` is denied with a message naming every live lane and its job. The permission layer
holds the rule, so it does not depend on any session having been briefed.

---

## Messaging another lane, if your harness has it

Lanes may interrupt each other. The protocol exists so it is smooth, not so it is frequent.

**The cost, priced once. A cross-session message starts a turn in the other lane.** It spends
that lane's tokens, and it lands wherever that lane happens to be, which may be mid-write.

Four cases, and only four:

1. **You need to write inside a prefix another lane owns.** Ask its lane, never write.
2. **You release a prefix another lane is waiting on.** Tell it.
3. **You find something that invalidates another lane's work.** Tell it, with the evidence.
4. **The human rules something in your chat that changes another lane's job.** Relay it, quoting.

Never for anything else, and the test is mechanical. Could a `lanes.py status` read have
answered it? Status pings, "are you there", progress reports and FYIs are all register reads
wearing a message. When the address reads `UNKNOWN`, do not guess and do not send; capture into
your lane record and let the drain carry it.

On receiving one, finish the current item first; answer, or say you will not and why, in one line;
record the exchange in your own lane record. A cross-lane agreement that exists only in two chat
logs is exactly the thing the drain cannot find.

---

## Handing a prefix over, without a message

Case 1 above ("you need to write inside a prefix another lane owns") has a file path as well
as a message path, because the owner may be between prompts, and because a message is not a
record. Three commands, all in `lanes.py`:

1. **The asking lane files a request.**
   `python lanes.py request --lane <me> --path <prefix> --why "<one line>"`
   The request is a file in the register (`.lanes/_request-<id>.json`). The underscore keeps it
   out of the lane scan; every lane's next `status` prints it under HANDOVER REQUESTS, addressed
   to the owner, with the grant line to run. Two shapes are refused. One is a prefix you already own,
   the other a prefix nobody owns (that is a `claim`, not a request).
2. **Message the owner too, if your harness has messaging and the owner is awake.** One line,
   the path and the request id. The file is the record either way.
3. **The owner decides on its next turn.**
   `python lanes.py grant --lane <owner> --request <id>` moves the prefix. It leaves the
   owner's `owns` and joins the asker's in one write pair. From that moment the hooks see the
   asker as the owner and nobody else. Only the current owner can grant; anyone else is refused.
   `python lanes.py decline --lane <owner> --request <id> --why "<one line>"` keeps the prefix
   and writes the reason where the asker reads it.
4. **Both lanes re-read `status` before their next write.** The partition just changed.
5. **Both record it in their lane record.** What moved, which way, the request id.

Before granting, the owner asks itself one thing. Is there an uncommitted edit under that prefix?
Commit it first. A granted prefix with the old owner's staged file under it is the swept-commit
failure from rule 1 waiting to happen.

A request is not permission, and neither is a message. The write is legal when `status` shows
the prefix in your `owns`, and at no other moment. A grant hands over a prefix, never a lane;
ending a lane stays the human's call.

---

## What was deliberately not used, so nobody proposes it later

**A hand-flipped switch.** Version one, on the first morning (2 August 2026), lasted a day. `LANES-ACTIVE: yes`
armed the guards and `no` disarmed them. It worked, and it had three manual steps. Flip it on,
hand-write the lane table, flip it back off. Three manual steps are three ways to be stale, and
the last is the dangerous one. Left at `yes` it nags a solo session into ignoring it; left at
`no` it protects nothing while three sessions run. **The file asserted a state instead of
reporting one.** The register replaces it because a count of live sessions cannot be forgotten.

**Git worktrees.** The obvious answer to "several agents, one tree" is to give each agent its
own tree, and if your folder can be duplicated safely, do that; it is the simpler design and
every harness ships it. This contract exists for the case where it cannot, a folder holding
several confidentiality boundaries, where a second complete copy on disk, indexed by your
tools and visible to git, is the danger. The path-prefix partition achieves the same isolation
with no second copy.

**Binding the contract only through a launch flag.** `--append-system-prompt` is stronger than
a first message, because a first message decays by turn forty while a system prompt is re-read
every turn. But it is CLI-only, and a session launched from a desktop app would silently not
have it. A file that every session re-reads on every surface, plus a hook, binds however the
session was started. Use the flag as well if you launch from the CLI; it costs nothing.

**An idle timeout on a registration.** A lane quiet for thirty minutes is usually between
prompts, not finished, and expiring it would silently disarm the guards around live work. The
work-date roll is the expiry and `end` is the clean exit. A ghost lane costs one `lanes.py end`;
a prematurely expired lane costs a commit that swept up someone else's files.

**Live messages as the binding.** The primitive exists in some harnesses now. It is used for the
four cases above and no more, because a message into another session starts a turn there.
Checking a file costs nothing and interrupts nobody.

---

## What this does not solve

**The register knows what has been declared, not what is alive.** A session that dies without
tidying up still reports as live until the roll. The operating system knows the truth; writing
the session address into the register at claim time is what lets you check the one against the
other, and a lane that will not answer and has not written its record in hours may simply be
gone.

**An actor trying to get past the guards.** The guards are a nudge against careless commands,
not a boundary. The git guard reads command text, statement by statement (split on `;`, `&`,
`|` and newline), so anything that hides the literal word `git` escapes it: `G=git; $G commit`,
a shell alias, a git alias, a wrapper script. That is the inherent limit of a guard over text,
and this one does not try to see through indirection. It catches the mistake a well-meaning
session makes, which is the mistake every incident in this file was.

**Sub-agents inside one session.** An orchestrator with several sub-agents inherits one
permission surface and one git identity, so "which agent made this write" has no enforceable
answer at all. The answer there is not a smaller partition. Make the sub-agents non-writing and
let the parent do every write, which removes the second writer instead of policing it.

---

## The parts

| Piece | Path | What it does |
|---|---|---|
| The register | `.lanes/` | One file per lane. Gitignored, because it is runtime state, not repository knowledge |
| The tool | `lanes.py` | `claim`, `status`, `request`, `grant`, `decline`, `end`, `prune`, `armed`, `--selftest` |
| Git guard | `hooks/git_scope_guard.py` | Denies stage-everything and the bare commit while armed. `--selftest` |
| Spine guard | `hooks/spine_guard.py` | Asks on shared-file writes while armed. `--selftest` |
| The spine list | `.lanes-spine` | The only enumeration of the shared files |
| Hook wiring | `hooks/settings.example.json` | Copy into your harness's hook settings |
| Lane record schema | `LANE-RECORD.md` | The frontmatter every lane file opens with |

**Both guards fail OPEN on an internal error, loudly on stderr.** A broken guard must not brick
the session, so a guard that cannot read the register or parse its input allows the call and
says why. The cost is that a guard which is quietly broken protects nothing, and the self-test
is the only thing that stops that staying hidden; run it after any edit to the hooks. The
author runs his own private guards the other way, fail closed, because in that setup a silent
pass is the costlier error: a crashing guard there blocks the write and names the error. Either
is a valid choice; pick by which error costs you more, and write the choice down.

**All three self-tests are falsifiable and that is the point.** Each carries fixtures that
contradict each other. A guard that blocked everything fails the must-pass cases, one that
blocked nothing fails the must-block cases. A detector is only worth acting on to the degree
its passing could have been a failing.
