# Several agents, one working tree

Simon Dilling, October 2026

I run four or five AI coding sessions at the same time, on one laptop, against one folder. One working tree, one `.git`, one branch. They are not building a product. They are doing my week, which means the books, a client's catalogue, my own writing and the build of the system itself.

For about a day in August this worked because I was lucky.

Then it stopped working, and the way it stopped is the reason I now have a written contract between sessions that almost never speak to each other.

## The failure was not the one I was watching for

I expected the collision to be dramatic. Two agents editing the same file, one overwriting the other, something I would notice.

What actually happened, on 3 August 2026, is that one session staged its own files correctly, with the paths spelled out, and then committed with no paths at all. A bare commit takes the whole index. It took the other session's staged work with it and pushed.

Nothing was lost. The bytes were identical. What I lost was the ability to say which session did which piece of work, in a system whose whole value is that every claim carries its source.

The interesting part is not the mistake. It is that my written rule already said "explicit paths on the add and on the commit", and the enforcement covered three of the four ways to break it. It denied `git add -A`. It denied `git add .`. It denied `git commit -a`. It did not deny a bare `git commit`, because a bare commit does not look like a stage-everything command.

I met that shape three times that day, on three unrelated parts of the system. The enforcement is attached to a narrower trigger than the rule it enforces. The rule reads fine. The check reads fine. The gap between them is invisible until it costs something.

## Version one lasted a day

My first attempt was a single line at the top of a file. Set to yes, it turned the guards on. Set to no, it turned them off.

It worked. I used it for one day and threw it away, and the reason generalises further than this problem.

It had three manual steps. Flip it on, write the table of who is running, flip it back off when finished. Three manual steps are three ways to go stale, and the last one is the dangerous one. Left at yes, it nags a session working alone until that session learns to ignore it. Left at no, it protects nothing while three sessions run.

The file asserted a state. It did not report one.

Everything I have built since is a version of that lesson. If a fact can be derived at the moment it is needed, derive it. A stored copy of a fact is a copy that can be wrong, and it will be wrong at the exact moment nobody is checking.

## What the contract actually is

Version two is four sentences long and one command.

A session that I tell is a lane registers itself. It declares a name, the path prefixes it owns, one line saying what it is doing, and its own session address so another lane can reach it. That registration expires by itself at 05:00 the next morning, which is when my working day rolls over.

While two or more lanes are registered, four rules bind:

1. Write only inside your own prefixes.
2. Never stage everything. Always name the paths, on the add and on the commit.
3. Do not write the shared files that every session touches. Capture what you would have written into your own dated lane file instead, and let one session merge them later.
4. Do not run the end-of-day close. One session does that, once, afterwards.

One command answers everything I need to know:

```
python lanes.py status
```

It prints who is live, what each one owns, what each is doing, whether the guards are on, and whether any two lanes have overlapping paths. It computes all of that at the moment I ask and stores none of it.

That is the whole system. There is no dashboard, no daemon, no message bus between sessions.

## The rule lives in the permission layer, not in the sessions

This is the part I would argue for hardest.

Two hooks sit in front of the agent's tool calls. One denies any stage-everything git command and any commit that names no paths. The other asks before any write to a shared file. Both are completely inert while fewer than two lanes are registered, so working alone costs nothing and feels like nothing.

The reason to put the rule there rather than in the instructions is not that agents forget, although they do. It is that a session nobody briefed still finds out. When the guard refuses, its refusal names every live lane and what each one is doing. A session that was started without being told any of this discovers the contract at the exact moment the contract becomes relevant to it, from a source that cannot have drifted.

Instructions in a file decay. A first message decays fastest of all, and by turn forty it is ancient history. A hook does not decay, because it runs again on every call.

## The asymmetry that decides every default

Every ambiguous case in that code falls the same way, and it falls that way on purpose.

Guards armed when they were not needed cost one extra prompt.

Guards disarmed when they were needed cost another session's uncommitted work.

Those two are not comparable, so every unknown fails toward armed. A registration with no date counts as live. A registration I cannot parse counts as live. A clock that will not read counts everything as live. There is still a manual switch that can force the guards on for a session that cannot register itself, and there is deliberately no switch that can force them off.

I think most safety design goes wrong by treating the two directions of error as if they were the same size. They almost never are, and which one is bigger is usually obvious once you write both sentences down.

## When one lane needs what another lane owns

This is the question people ask first, and for almost six weeks my answer was "it waits".

Now it asks. One command files a request in the register. The request is a file, so the owner sees it at its next status read even if it is between prompts, addressed to it, with the exact line to run. The owner answers with a grant or a decline. A grant moves the path out of the owner's list and into the asker's in one write, and the hooks follow the register, so the new owner can write immediately. A decline carries a reason, and the asker reads it in the same place.

Only the current owner can grant. A grant moves a path, never a whole lane. And a request is not permission. The write is legal when the register shows the path as yours, and at no other moment.

## The refusals are the interesting half

Four things I considered and did not build as the answer, each for a reason I would give again.

**Git worktrees.** The obvious answer to "several agents, one tree" is to give each agent its own tree. I refused it, because my folder holds four separate confidentiality boundaries. My company, a startup I co-own, client work, personal. A worktree puts a second complete copy of all four somewhere on disk where my note-taking app indexes it and git can see it. The duplication is the danger, not the disk space. Partitioning by path prefix gets the same isolation with no second copy. If your folder can be duplicated safely, use worktrees. They are the simpler design.

**An idle timeout on a registration.** Tempting, and wrong in the direction that matters. A session that has written nothing for thirty minutes is usually waiting for me, not finished. Expiring it would silently disarm the guards around live work. A ghost registration costs one command to clear. A prematurely expired one costs a commit that swept up someone else's files, which is the thing I built all of this to stop.

**Binding the contract only through the command-line launch flag.** There is a flag that injects text into every turn, and it is genuinely stronger than a first message. But it only exists on the command line, and I sometimes start a session from the desktop app, where a contract that lived only in that flag would silently not apply. So the contract lives in a file that every session re-reads, on every surface, however it was started.

**Live messages between sessions as the binding.** I refused this for five weeks and then adopted it for four narrow cases. A lane needs to write inside another lane's paths. A lane releases a path another is waiting on. A lane finds something that invalidates another lane's work. I rule something in one chat that changes another lane's job. For those four, a message is right. As the thing that holds the contract together it is still wrong, because a message into another session starts a turn there. It spends that session's budget and lands wherever that session happens to be, which may be mid-write. Checking a file costs nothing and interrupts nobody. The test I use is mechanical. If reading the register would have answered it, it was not a message.

## What it does not solve

Two things, and I would rather say them than have someone find them.

The register knows what has been declared, not what is alive. A session that dies without tidying up still reports as live until the morning roll. The operating system knows the truth. Since September each lane writes its own session address into the register when it claims, so a lane that will not answer can be checked against the list of sessions that are actually running. That makes the gap checkable. It does not close it.

And the whole design assumes sessions. Inside a single session, an orchestrator with several sub-agents inherits one permission surface and one git identity, so "which agent made this write" has no enforceable answer at all. The answer there is not a smaller partition. It is to make the sub-agents non-writing and let the parent do every write, which removes the second writer instead of policing it. Different problem, different shape, and worth being explicit that the lane contract does not reach it.

## What I would tell someone starting

Register, do not announce. A state that is computed cannot be forgotten and a state that is typed can.

Put the rule where the tool call passes, not where the instructions live.

Write both error sentences before choosing a default, and let the expensive one decide.

And keep the incident that bought each rule attached to the rule. Nearly three months in, the most valuable thing in my contract file is not the rules. It is the two lines under each one saying what went wrong on which date, because that is what stops a future version of me optimising the rule away on a quiet afternoon when nothing has gone wrong in a while.

The contract, the register and both hooks are in this repository, with the dated incident under each rule. Start with the [README](README.md), then read [`LANES.md`](LANES.md).
