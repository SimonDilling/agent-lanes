# The lane record

Every lane writes one file per work day, inside its own prefix, named:

```
_lane-<lane>-<YYYY-MM-DD>.md
```

It is the lane's dated record of what happened, what was decided, what is open, what was captured
for the shared files it may not write, and any side-finding with its reasoning. It commits with
the lane's own pathspec, so it needs no new partition. One session reads every lane record at the
end-of-day drain, routes what each holds, and stamps it.

## Frontmatter

The file opens with exactly these three lines, then whatever fields the lane needs:

```
---
type: lane-record
created: 2026-09-11
tags: [lane-record, docs]
---
```

One spelling, no synonyms. For seven weeks the setup this was extracted from had 47 lane files
carrying six spellings of `type:` plus eight blanks, because the register named the filename it
wanted and nothing named the frontmatter. `lanes.py claim` prints these three lines at claim
time so there is nothing to remember.

If your notes follow a closed list of `type:` values that a validator enforces, exempt the
lane record from that list rather than giving it a second spelling. The register and the
drain find a lane record by its filename, never by its type, so the exemption costs no tool
anything, and a synonym is how six spellings happened.

Optional fields, added when the lane has them:

```
lane: docs
owns: [docs/, README.md]
session: <the session's own address>
drained: 2026-09-11 23:40      # written by the DRAIN, never by the lane; date AND time
```

## Body

Same shape as a daily note. Headings that have proven useful:

```
# Lane record: docs, 2026-09-11

**Job:** one line, the same as the register's --job.

## What happened
- timestamps and the acts, in order

## Decided
- anything ruled in this lane's chat, quoted, and whether it has been routed yet

## Open
- what is left, and what blocks it

## Captured for the shared spine
- entries this lane would have written into the daily note, the agenda, the shared task
  list or the log, but did not, because rule 2. The drain moves them.

## Side-findings
- a defect noticed in passing, a cost worth remembering, a fact that has no other home

## Resume point
One current pointer, edited in place, never appended. The exact next action and the file it
is to be taken in.
```

## The drain stamp

`drained: <date> <HH:MM>` is written by the drain session as the last thing it does to the
file. The time is what makes it checkable. A file drained at 14:00 and written to again at
15:00 is UNDRAINED again, and a date-only stamp cannot see that. `lanes.py status` in the
full setup compares the file's mtime against the stamp; this extracted version reports the
files it finds and leaves the comparison to you.

Moving an undrained record into an archive folder marks it drained. If you did not read it in
full this session, leave it where it is.
