#!/usr/bin/env python3
"""lanes.py: a register for several AI coding sessions sharing ONE working tree.

One machine, one working tree, one .git, one branch, several agent sessions at once.
Each session that is told it is a LANE registers itself here: a name, the path
prefixes it owns, one line saying what it is doing, and optionally its own session
address. Two guard hooks read this register at runtime and arm themselves the
moment two or more lanes are live. Nothing to switch on, nothing to switch off.

    python lanes.py claim --lane docs --owns docs/ README.md --job "rewrite the README"
    python lanes.py status
    python lanes.py end --lane docs        # the human's call, never the session's
    python lanes.py prune                  # drop registrations from earlier work days
    python lanes.py armed                  # exit 0 if two or more lanes are live
    python lanes.py --selftest

DESIGN RULES, each one bought by an incident (see LANES.md for the incidents):

1. The register REPORTS a state, it never ASSERTS one. Liveness is derived at read
   time from the files: status is live AND the work date is today. No daemon.
2. Fail toward armed. An unreadable registration counts as live. An unreadable
   register directory counts as live. Guards armed when not needed cost one prompt;
   guards disarmed when needed cost another lane's uncommitted work.
3. No idle timeout. A quiet session is usually between prompts, not finished.
   The expiry is the work-day roll (default 05:00 local), and `end` is the exit.
4. `owns` is stored as a JSON array, never a space-joined string, because a
   space-joined string is split back on whitespace and a path with a space in it
   shatters into fragments that the overlap check then compares as if real.
5. The overlap check strips trailing separators before comparing, and treats
   `a` and `a-old` as different trees. Both were bugs once.

No dependencies beyond the standard library. Python 3.9 or later.
"""

import argparse
import datetime as _dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.environ.get("LANES_ROOT", HERE)
REGISTRY = os.environ.get("LANES_REGISTRY", os.path.join(REPO_ROOT, ".lanes"))
ENDED = os.path.join(REGISTRY, "_ended")

ARMED_AT = 2                      # two or more live lanes means parallel
ROLL_HOUR = int(os.environ.get("LANES_DAY_ROLLS_AT", "5"))   # work day rolls at 05:00

FIELDS = ("lane", "owns", "reads", "job", "work-date", "claimed", "last-seen",
          "status", "session", "repartitioned")


# ---------------------------------------------------------------------------
# clock
# ---------------------------------------------------------------------------

def now():
    return _dt.datetime.now().astimezone()


def work_date(moment=None):
    """The date the work day belongs to. Before ROLL_HOUR it is still yesterday.

    A session that opens at 15:00 and runs to 03:00 belongs to the day it started,
    so a registration made at 01:00 does not expire at midnight under a live lane.
    """
    m = moment or now()
    if m.hour < ROLL_HOUR:
        m = m - _dt.timedelta(days=1)
    return m.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# registry io
# ---------------------------------------------------------------------------

def _norm_lane(lane):
    return "".join(c for c in lane.strip().lower() if c.isalnum() or c in "-_")


def _path(registry, lane):
    return os.path.join(registry, "%s.md" % _norm_lane(lane))


def read_lane(path):
    """Parse one registration. An unreadable file is reported as LIVE, never skipped."""
    rec = {"_file": path, "lane": os.path.splitext(os.path.basename(path))[0]}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                key = key.strip().lower()
                if key in FIELDS:
                    rec[key] = value.strip()
    except Exception as exc:  # noqa: BLE001
        rec["_unreadable"] = "%s: %s" % (type(exc).__name__, exc)
        rec.setdefault("status", "live")
        rec.setdefault("work-date", work_date())
    return rec


def all_lanes(registry=REGISTRY):
    """Every registration on file.

    ABSENT (no directory) is a real answer: nobody has ever claimed a lane here, so
    zero lanes and the guards stay inert. UNREADABLE (directory exists, will not
    list) is an unknown, and unknowns fail toward armed.
    """
    if not os.path.isdir(registry):
        return []
    try:
        names = sorted(os.listdir(registry))
    except OSError as exc:
        return [{"lane": "(registry unreadable)", "_unreadable": True,
                 "job": "cannot list %s: %s" % (registry, exc), "owns": "[]"}]
    out = []
    for name in names:
        if not name.endswith(".md") or name.startswith("_"):
            continue
        out.append(read_lane(os.path.join(registry, name)))
    return out


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def is_live(rec, today=None):
    """Live means: not explicitly ended, and claimed on the current work day."""
    if rec.get("_unreadable"):
        return True
    status = (rec.get("status") or "live").strip().strip("\"'").lower()
    if status != "live":
        return False
    m = _DATE_RE.search((rec.get("work-date") or "").strip().strip("\"'"))
    return bool(m) and m.group(0) == (today or work_date())


def live_lanes(registry=REGISTRY, today=None):
    return [r for r in all_lanes(registry) if is_live(r, today)]


def armed(registry=REGISTRY, today=None):
    return len(live_lanes(registry, today)) >= ARMED_AT


# ---------------------------------------------------------------------------
# prefixes and the overlap check
# ---------------------------------------------------------------------------

def encode_owns(items):
    return json.dumps([p.strip() for p in items if p and p.strip()])


def prefixes(rec, field="owns"):
    """Declared prefixes as a list. JSON array preferred; a legacy space-joined
    string is still read so no old registration loses its claim."""
    raw = (rec.get(field) or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            return [str(p) for p in json.loads(raw)]
        except ValueError:
            pass
    return raw.split()


def _norm_prefix(p):
    return (p or "").replace("\\", "/").rstrip("/").lower()


def overlaps(a, b):
    """True if two path prefixes share a subtree.

    `a` and `a-old` are different trees, so no bare startswith(). Trailing
    separators are stripped first: `docs/` against `docs/x.md` must be TRUE, and
    it was FALSE for three weeks because `docs/` + "/" is `docs//`.
    """
    a, b = _norm_prefix(a), _norm_prefix(b)
    if a == b:
        return True
    return b.startswith(a + "/") or a.startswith(b + "/")


def repartition(old, new):
    """What a re-claim changed: (released, added), as normalised prefixes.

    A lane whose scope moves mid-day must say so where every other lane will read it,
    or the others keep writing from a remembered picture. `docs/` and `Docs` are the
    same prefix, so a re-claim that only respells one is not a repartition.
    """
    o = {_norm_prefix(p) for p in old if _norm_prefix(p)}
    n = {_norm_prefix(p) for p in new if _norm_prefix(p)}
    return sorted(o - n), sorted(n - o)


def collisions(records):
    """Every pair of live lanes whose declared prefixes intersect.

    owns against owns is a CONFLICT. owns against reads is a READ note, informational:
    a declared reader beside a writer is harmless, and a report that cries on harmless
    overlaps trains its reader to scroll past a real one. reads against reads is silence.
    Returns (severity, lane_a, prefix_a, lane_b, prefix_b), CONFLICT rows first.
    """
    out = []
    for i, ra in enumerate(records):
        for rb in records[i + 1:]:
            for pa in prefixes(ra, "owns"):
                for pb in prefixes(rb, "owns"):
                    if overlaps(pa, pb):
                        out.append(("CONFLICT", ra["lane"], pa, rb["lane"], pb))
            for pa in prefixes(ra, "owns"):
                for pb in prefixes(rb, "reads"):
                    if overlaps(pa, pb):
                        out.append(("READ", ra["lane"], pa, rb["lane"], pb))
            for pa in prefixes(ra, "reads"):
                for pb in prefixes(rb, "owns"):
                    if overlaps(pa, pb):
                        out.append(("READ", rb["lane"], pb, ra["lane"], pa))
    out.sort(key=lambda t: (t[0] != "CONFLICT", t[1], t[3]))
    return out


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def _write(path, rec):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for k in FIELDS:
            fh.write("%s: %s\n" % (k, rec.get(k, "")))


# ---------------------------------------------------------------------------
# handover: one lane asks the owner of a prefix for it; the owner grants or declines
#
# A request is a file in the register, `_request-<id>.json`. The underscore keeps it out
# of the lane scan, and every lane's next `status` prints it addressed to the owner, so
# the owner finds out without anyone messaging it. A grant is the owner's act: the prefix
# leaves the owner's owns and joins the requester's in one write pair, and the guards see
# the new owner the moment the files land. A decline records the reason where the asker
# reads it. Nothing here touches the hooks; they read the register as they always did.
# ---------------------------------------------------------------------------

REQUEST_PREFIX = "_request-"


def _request_file(registry, req_id):
    return os.path.join(registry, "%s%s.json" % (REQUEST_PREFIX, req_id))


def list_requests(registry=REGISTRY):
    if not os.path.isdir(registry):
        return []
    out = []
    for name in sorted(os.listdir(registry)):
        if not (name.startswith(REQUEST_PREFIX) and name.endswith(".json")):
            continue
        rid = name[len(REQUEST_PREFIX):-len(".json")]
        try:
            with open(os.path.join(registry, name), "r", encoding="utf-8") as fh:
                d = json.load(fh)
            d["id"] = rid
        except Exception as exc:  # noqa: BLE001
            d = {"id": rid, "status": "unreadable", "why": "%s: %s" % (type(exc).__name__, exc)}
        out.append(d)
    return out


def _save_request(registry, req):
    req = dict(req)
    rid = req.pop("id")
    with open(_request_file(registry, rid), "w", encoding="utf-8") as fh:
        json.dump(req, fh, indent=1)
    req["id"] = rid
    return req


def owner_of(path, registry=REGISTRY, today=None):
    """The live lane whose owns overlaps `path`, or None when nobody owns it."""
    for rec in live_lanes(registry, today):
        for p in prefixes(rec, "owns"):
            if overlaps(p, path):
                return rec["lane"]
    return None


def _set_owns(registry, lane, owns_list, stamp):
    path = _path(registry, lane)
    rec = read_lane(path) if os.path.exists(path) else {"lane": _norm_lane(lane)}
    rec["owns"] = encode_owns(owns_list)
    rec["last-seen"] = stamp
    rec.setdefault("status", "live")
    rec.setdefault("work-date", work_date())
    rec.setdefault("claimed", stamp)
    _write(path, rec)


def make_request(registry, lane, path, why, today=None):
    lane = _norm_lane(lane)
    owner = owner_of(path, registry, today)
    if owner == lane:
        raise ValueError("refused: %s already owns %s" % (lane, path))
    if owner is None:
        raise ValueError("refused: nobody owns %s; claim it with `lanes.py claim` instead" % path)
    os.makedirs(registry, exist_ok=True)
    stamp = now().isoformat(timespec="seconds")
    rid = "%s-%s" % (lane, re.sub(r"[^a-z0-9]+", "-", _norm_prefix(path))[:40].strip("-"))
    req = {"id": rid, "from": lane, "path": path, "owner": owner, "why": why or "",
           "at": stamp, "status": "pending", "work-date": today or work_date()}
    return _save_request(registry, req)


def _pending(registry, req_id):
    req = next((r for r in list_requests(registry) if r["id"] == req_id), None)
    if req is None:
        raise ValueError("no request %r" % req_id)
    if req.get("status") != "pending":
        raise ValueError("request %s is %s, not pending" % (req_id, req.get("status")))
    return req


def grant_request(registry, lane, req_id, today=None):
    """Only the CURRENT owner can grant. The prefix leaves its owns and joins the asker's."""
    lane = _norm_lane(lane)
    req = _pending(registry, req_id)
    owner = owner_of(req["path"], registry, today)
    if owner != lane:
        raise ValueError("refused: %s does not own %s (owner is %s)" % (lane, req["path"], owner))
    stamp = now().isoformat(timespec="seconds")
    kept = [p for p in prefixes(read_lane(_path(registry, lane)), "owns") if not overlaps(p, req["path"])]
    _set_owns(registry, lane, kept, stamp)
    asker = _path(registry, req["from"])
    theirs = prefixes(read_lane(asker), "owns") if os.path.exists(asker) else []
    if req["path"] not in theirs:
        theirs.append(req["path"])
    _set_owns(registry, req["from"], theirs, stamp)
    req.update({"status": "granted", "granted_at": stamp, "granted_by": lane})
    return _save_request(registry, req)


def decline_request(registry, lane, req_id, why):
    lane = _norm_lane(lane)
    req = _pending(registry, req_id)
    stamp = now().isoformat(timespec="seconds")
    req.update({"status": "declined", "declined_at": stamp, "declined_by": lane, "decline_why": why or ""})
    return _save_request(registry, req)


def print_requests(registry=REGISTRY, today=None):
    reqs = [r for r in list_requests(registry) if r.get("work-date") in (None, today or work_date())]
    if not reqs:
        return
    print("  HANDOVER REQUESTS. A lane asked another for a prefix; the owner grants or declines.")
    for r in reqs:
        if r.get("status") == "pending":
            owner = owner_of(r.get("path", ""), registry, today) or r.get("owner", "?")
            print("    PENDING  %-12s asks %-12s for %s" % (r.get("from", "?"), owner, r.get("path", "?")))
            if r.get("why"):
                print("             why: %s" % r["why"][:100])
            print("             owner runs: python lanes.py grant --lane %s --request %s" % (owner, r["id"]))
        else:
            print("    %-8s %-12s -> %-12s %s" % (r.get("status", "?").upper(), r.get("from", "?"),
                                                r.get("granted_by") or r.get("declined_by") or "?", r.get("path", "?")))
    print()


def cmd_request(args, registry=REGISTRY):
    try:
        req = make_request(registry, args.lane, args.path, args.why)
    except ValueError as exc:
        print("  %s" % exc)
        return 1
    print("requested %s from %s (id %s). The owner sees it on its next `status`; message it too if it is awake."
          % (req["path"], req["owner"], req["id"]))
    return 0


def cmd_grant(args, registry=REGISTRY):
    try:
        req = grant_request(registry, args.lane, args.request)
    except ValueError as exc:
        print("  %s" % exc)
        return 1
    print("granted: %s left %s and joined %s. Both lanes re-read `status` before writing." % (req["path"], req["granted_by"], req["from"]))
    return 0


def cmd_decline(args, registry=REGISTRY):
    try:
        req = decline_request(registry, args.lane, args.request, args.why)
    except ValueError as exc:
        print("  %s" % exc)
        return 1
    print("declined: %s keeps %s; the reason is in the register for %s." % (req["declined_by"], req["path"], req["from"]))
    return 0


def cmd_claim(args, registry=REGISTRY):
    path = _path(registry, args.lane)
    stamp = now().isoformat(timespec="seconds")
    existing = read_lane(path) if os.path.exists(path) else {}
    rec = {
        "lane": _norm_lane(args.lane),
        "owns": encode_owns(args.owns) if args.owns else existing.get("owns", "[]"),
        "reads": encode_owns(args.reads) if args.reads else existing.get("reads", "[]"),
        "job": args.job or existing.get("job", ""),
        # A re-claim without --session KEEPS the address: a repartition is the
        # commonest reason to re-claim, and losing the address there would make a
        # lane unreachable while the register looked fine.
        "session": (args.session or existing.get("session", "")).strip(),
        "work-date": work_date(),
        "claimed": existing.get("claimed") or stamp,
        "last-seen": stamp,
        "status": "live",
    }
    same_day = existing.get("work-date") == rec["work-date"]
    if existing.get("work-date") and not same_day:
        rec["claimed"] = stamp          # a claim from an earlier day is a NEW claim
    # A same-day re-claim that changes `owns` is a REPARTITION. It is stamped into the
    # register, so every lane's next `status` shows it, and printed here.
    rec["repartitioned"] = existing.get("repartitioned", "") if same_day else ""
    moved = None
    if same_day and args.owns is not None:
        released, added = repartition(prefixes(existing), args.owns)
        if released or added:
            moved = "%s released=%s added=%s" % (
                stamp, ",".join(released) or "-", ",".join(added) or "-")
            rec["repartitioned"] = moved
    _write(path, rec)
    print("claimed lane '%s' for work date %s" % (rec["lane"], rec["work-date"]))
    if moved:
        print("  REPARTITIONED %s" % moved)
        print("  Every other lane re-reads `status` before its next write.")
    print()
    print("  Your lane record for today (write it before you start work):")
    print("     <your owned folder>/_lane-%s-%s.md" % (rec["lane"], rec["work-date"]))
    print("  with this frontmatter, then your own fields:")
    print("     type: lane-record")
    print("     created: %s" % rec["work-date"])
    print("     tags: [lane-record, %s]" % rec["lane"])
    print()
    return cmd_status(args, registry)


def cmd_end(args, registry=REGISTRY):
    """Ending is the HUMAN's act. A session that finishes its job reports, commits its
    own paths, and stays registered; a lane closed early re-claims, misreports the live
    set, and can disarm the guards one session too soon."""
    path = _path(registry, args.lane)
    if not os.path.exists(path):
        print("no registration for lane '%s'" % args.lane)
        return 1
    rec = read_lane(path)
    rec["status"] = "ended"
    rec["last-seen"] = now().isoformat(timespec="seconds")
    _write(path, rec)
    os.makedirs(ENDED, exist_ok=True)
    os.replace(path, os.path.join(ENDED, "%s-%s.md" % (rec["lane"], rec.get("work-date", "undated"))))
    print("ended lane '%s'" % rec["lane"])
    return 0


def cmd_prune(args, registry=REGISTRY):
    today = work_date()
    n = 0
    for rec in all_lanes(registry):
        if rec.get("_unreadable"):
            continue
        if (rec.get("work-date") or "") != today:
            os.makedirs(ENDED, exist_ok=True)
            os.replace(rec["_file"], os.path.join(
                ENDED, "%s-%s.md" % (rec["lane"], rec.get("work-date") or "undated")))
            n += 1
    print("pruned %d registration(s) from earlier work days" % n)
    return 0


def cmd_status(args, registry=REGISTRY):
    today = work_date()
    live = live_lanes(registry, today)
    print()
    print("  LANES, work date %s" % today)
    print("  " + "-" * 72)
    if not live:
        print("  no live lanes. One session, no guards, nothing to do.")
    for rec in live:
        print("  LIVE   %-12s %s" % (rec["lane"], rec.get("job", "") or "(no job line)"))
        owns = " ".join('"%s"' % p if " " in p else p for p in prefixes(rec, "owns"))
        print("         %-12s owns: %s" % ("", owns or "(nothing declared: cannot be checked against anyone)"))
        reads = prefixes(rec, "reads")
        if reads:
            print("         %-12s reads: %s  (shared read)" % ("", " ".join(reads)))
        print("         %-12s message it at: %s" % ("", rec.get("session") or "UNKNOWN"))
        if rec.get("repartitioned"):
            print("         %-12s REPARTITIONED %s" % ("", rec["repartitioned"]))
        if rec.get("_unreadable"):
            print("         %-12s UNREADABLE (%s): counted as live, by design" % ("", rec["_unreadable"]))
    print_requests(registry, today)
    ended = sorted(os.listdir(ENDED)) if os.path.isdir(ENDED) else []
    ended_today = sorted({n.rsplit("-", 3)[0] for n in ended if today in n})
    if ended_today:
        print("  ended today: %s" % ", ".join(ended_today))
    print("  " + "-" * 72)
    hits = collisions(live)
    if hits:
        for sev, la, pa, lb, pb in hits:
            if sev == "CONFLICT":
                print("  OVERLAP  %s owns %s  and  %s owns %s   Repartition before working." % (la, pa, lb, pb))
            else:
                print("  read     %s owns %s  while  %s reads %s   (no repartition owed)" % (la, pa, lb, pb))
    elif len(live) >= 2:
        print("  partition is disjoint: no two lanes own overlapping prefixes.")
    if len(live) >= ARMED_AT:
        print("  ARMED. %d live lanes, so the two guards are on:" % len(live))
        print("         git add -A / add . / add -u / commit -a / commit with no pathspec  DENIED")
        print("         shared-file writes  ASK, capture into your own _lane-<lane>-<date>.md")
    else:
        print("  not armed (%d live lane%s). Guards are inert." % (len(live), "" if len(live) == 1 else "s"))
    print()
    print("  Derived at read time and stored nowhere. Do not save this output.")
    print()
    return 0


def cmd_armed(args, registry=REGISTRY):
    a = armed(registry)
    print("armed" if a else "not armed")
    return 0 if a else 1


# ---------------------------------------------------------------------------
# selftest: fixtures that contradict each other, so a pass could have been a fail
# ---------------------------------------------------------------------------

def selftest():
    import tempfile
    fails = []

    def check(label, got, want):
        if got != want:
            fails.append("%s: got %r, want %r" % (label, got, want))

    # overlap
    check("same prefix", overlaps("a", "a"), True)
    check("parent over child", overlaps("a", "a/b"), True)
    check("child under parent", overlaps("a/b", "a"), True)
    check("disjoint", overlaps("a", "b"), False)
    check("sibling stem is NOT an overlap", overlaps("a", "a-old"), False)
    check("trailing slash parent over file", overlaps("a/b/", "a/b/x.md"), True)
    check("trailing slash both", overlaps("a/", "a/b/"), True)
    check("backslash normalised", overlaps("a\\b", "a/b/c"), True)
    check("case-insensitive", overlaps("Docs/", "docs/x.md"), True)

    # repartition: what a re-claim released and added
    check("same owns is no repartition", repartition(["src/", "docs/"], ["docs/", "src/"]), ([], []))
    check("a respelled prefix is no repartition", repartition(["Docs/"], ["docs"]), ([], []))
    check("a dropped prefix is released", repartition(["src/", "docs/"], ["src/"]), (["docs"], []))
    check("a new prefix is added", repartition(["src/"], ["src/", "tests/"]), ([], ["tests"]))
    check("a swap is both", repartition(["src/"], ["tests/"]), (["src"], ["tests"]))

    # work date roll
    check("00:30 belongs to yesterday",
          work_date(_dt.datetime(2026, 9, 12, 0, 30)), "2026-09-11")
    check("05:00 is today", work_date(_dt.datetime(2026, 9, 12, 5, 0)), "2026-09-12")

    # register round trip, liveness, arming
    with tempfile.TemporaryDirectory() as tmp:
        reg = os.path.join(tmp, ".lanes")
        today = work_date()

        def write(lane, date, status, owns, reads=None):
            _write(os.path.join(reg, "%s.md" % lane), {
                "lane": lane, "owns": encode_owns(owns), "reads": encode_owns(reads or []),
                "job": "t", "work-date": date, "claimed": "x", "last-seen": "x",
                "status": status, "session": ""})

        check("absent registry is zero lanes", all_lanes(reg), [])
        check("absent registry is not armed", armed(reg), False)
        write("a", today, "live", ["src/"])
        check("one lane is not armed", armed(reg, today), False)
        write("b", today, "live", ["docs/"])
        check("two lanes are armed", armed(reg, today), True)
        check("disjoint partition has no collisions", collisions(live_lanes(reg, today)), [])
        write("c", "1999-01-01", "live", ["src/"])
        check("stale lane is not live", [r["lane"] for r in live_lanes(reg, today)], ["a", "b"])
        write("d", today, "ended", ["docs/"])
        check("ended lane is not live", [r["lane"] for r in live_lanes(reg, today)], ["a", "b"])
        write("e", '"%s"' % today, '"live"', ["etc/"])
        check("yaml-quoted status and date still read live",
              "e" in [r["lane"] for r in live_lanes(reg, today)], True)
        write("f", today, "live", ["src/lib/"])
        hits = collisions(live_lanes(reg, today))
        check("nested claim is a CONFLICT", [(h[0], h[1], h[3]) for h in hits if h[0] == "CONFLICT"],
              [("CONFLICT", "a", "f")])
        write("g", today, "live", ["tests/"], reads=["src/"])
        hits = collisions(live_lanes(reg, today))
        check("reader beside writer is a READ note, not a conflict",
              [(h[0], h[1], h[3]) for h in hits if "g" in (h[1], h[3])],
              [("READ", "a", "g"), ("READ", "f", "g")])
        check("a reader never raises a CONFLICT",
              [h for h in hits if h[0] == "CONFLICT" and "g" in (h[1], h[3])], [])
        # a path with a space survives the round trip as ONE prefix
        write("h", today, "live", ["notes/My Folder/"])
        rec = [r for r in all_lanes(reg) if r["lane"] == "h"][0]
        check("space in a path is one prefix", prefixes(rec), ["notes/My Folder/"])
        # an unreadable file counts as live
        bad = os.path.join(reg, "z.md")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write("lane: z\nstatus: live\nwork-date: %s\n" % today)
        os.chmod(bad, 0)
        try:
            recs = [r for r in all_lanes(reg) if r["lane"] == "z"]
            if recs and recs[0].get("_unreadable"):
                check("unreadable file is live", is_live(recs[0], today), True)
        finally:
            os.chmod(bad, 0o644)

    # handover: b asks a for a prefix a owns; a grants; the prefix moves. Then the refusals.
    with tempfile.TemporaryDirectory() as tmp:
        reg = os.path.join(tmp, ".lanes")
        today = work_date()
        for lane, owns in (("a", ["src/", "docs/"]), ("b", ["tests/"])):
            _write(os.path.join(reg, "%s.md" % lane), {
                "lane": lane, "owns": encode_owns(owns), "reads": "[]", "job": "t",
                "work-date": today, "claimed": "x", "last-seen": "x", "status": "live", "session": ""})
        check("owner of a nested path is the lane whose prefix covers it", owner_of("docs/x.md", reg, today), "a")
        check("an unowned path has no owner", owner_of("etc/", reg, today), None)
        req = make_request(reg, "b", "docs/", "b needs docs", today)
        check("request is pending and names the owner", (req["status"], req["owner"]), ("pending", "a"))
        check("request file is not a lane", sorted(r["lane"] for r in all_lanes(reg)), ["a", "b"])
        for label, args_ in (("asking for your own prefix is refused", ("b", "tests/")),
                             ("asking for an unowned prefix is refused", ("b", "etc/"))):
            try:
                make_request(reg, args_[0], args_[1], "", today)
                check(label, "allowed", "refused")
            except ValueError:
                pass
        try:
            grant_request(reg, "b", req["id"], today)
            check("a grant by a non-owner is refused", "allowed", "refused")
        except ValueError:
            pass
        g = grant_request(reg, "a", req["id"], today)
        check("grant stamped by the owner", (g["status"], g["granted_by"]), ("granted", "a"))
        check("prefix left the owner", prefixes(read_lane(os.path.join(reg, "a.md"))), ["src/"])
        check("prefix joined the asker", sorted(prefixes(read_lane(os.path.join(reg, "b.md")))), ["docs/", "tests/"])
        check("the asker is now the owner the guards see", owner_of("docs/x.md", reg, today), "b")
        try:
            grant_request(reg, "a", req["id"], today)
            check("a settled request cannot be granted twice", "allowed", "refused")
        except ValueError:
            pass
        req2 = make_request(reg, "a", "tests/", "a wants tests", today)
        d = decline_request(reg, "b", req2["id"], "still writing there")
        check("a decline keeps the prefix and records why",
              (d["status"], d["decline_why"], owner_of("tests/t.py", reg, today)), ("declined", "still writing there", "b"))

    # repartition end to end: a same-day re-claim with new owns is stamped and printed;
    # a re-claim that changes nothing prints nothing new and keeps the earlier stamp.
    with tempfile.TemporaryDirectory() as tmp:
        import contextlib
        import io
        reg = os.path.join(tmp, ".lanes")

        def claim(owns):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cmd_claim(argparse.Namespace(lane="a", owns=owns, reads=None, job="t", session=None), reg)
            return buf.getvalue(), read_lane(os.path.join(reg, "a.md")).get("repartitioned", "")

        out, field = claim(["src/"])
        check("a first claim is not a repartition", ("REPARTITIONED" in out, field), (False, ""))
        out, field = claim(["src/", "docs/"])
        check("a widened re-claim is printed", "REPARTITIONED" in out, True)
        check("and stamped into the register", field.endswith("released=- added=docs"), True)
        out2, field2 = claim(["docs/", "src"])
        check("an unchanged re-claim keeps the earlier stamp", field2, field)
        check("and announces nothing at the claim", out2.count("REPARTITIONED"), 1)

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print("selftest: all checks passed")
    return 0


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("claim", help="register this session as a lane (re-claim to repartition)")
    c.add_argument("--lane", required=True)
    c.add_argument("--owns", nargs="*", default=None,
                   help="path prefixes this lane writes. Quote each path with a space in it SEPARATELY.")
    c.add_argument("--reads", nargs="*", default=None, help="prefixes this lane reads but does not write")
    c.add_argument("--job", default=None, help="one line: what you are actually doing")
    c.add_argument("--session", default=None, help="this session's own address, so other lanes can reach it")
    sub.add_parser("status", help="who is live, what each owns, whether the guards are armed")
    e = sub.add_parser("end", help="end a lane. The human's call.")
    e.add_argument("--lane", required=True)
    sub.add_parser("prune", help="archive registrations from earlier work days")
    sub.add_parser("armed", help="exit 0 if two or more lanes are live")
    r = sub.add_parser("request", help="ask the lane that owns a prefix to hand it over")
    r.add_argument("--lane", required=True, help="the asking lane, you")
    r.add_argument("--path", required=True, help="the prefix you need to write")
    r.add_argument("--why", default="", help="one line the owner reads before deciding")
    g = sub.add_parser("grant", help="the OWNING lane hands a requested prefix over")
    g.add_argument("--lane", required=True, help="the granting lane, the current owner")
    g.add_argument("--request", required=True, help="the request id from `status`")
    d = sub.add_parser("decline", help="the OWNING lane keeps the prefix and says why")
    d.add_argument("--lane", required=True)
    d.add_argument("--request", required=True)
    d.add_argument("--why", default="")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    return {"claim": cmd_claim, "status": cmd_status, "end": cmd_end,
            "prune": cmd_prune, "armed": cmd_armed,
            "request": cmd_request, "grant": cmd_grant, "decline": cmd_decline,
            }.get(args.cmd, lambda a: ap.print_help() or 0)(args)


if __name__ == "__main__":
    sys.exit(main())
