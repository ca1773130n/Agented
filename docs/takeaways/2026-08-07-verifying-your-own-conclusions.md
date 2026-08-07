# Takeaways — 2026-08-07, Tesserae verification, docs correction, branch cleanup

A verification session: confirming an upstream fix, correcting documentation
against measured state, and settling 43 stale branches.

Lessons already recorded in `CLAUDE.md` are deliberately absent — the no-op
compile, the suite that does not hang, the tolerated-failure list, and the two
distill traps added there today. What follows is what was not written down
anywhere.

## Check patch equivalence, not ancestry, before calling a branch unmerged

**Trigger:** `git branch --merged` leaves a large pile of old branches in a repo
that squash-merges.
**Do:** Classify with `git cherry main origin/<branch>` — `+` is unlanded, `-` is
already in main by patch id.
**Why:** A squash merge puts the content on main without making the branch tip an
ancestor, so ancestry-based checks report merged work as unmerged. The pile looks
like abandoned work and is mostly refs nobody deleted.
**Evidence:** Of 43 branches, `--merged` found 8; `git cherry` found 31 more
already landed.

## Diff a branch's unique lines before treating them as work to save

**Trigger:** A stale branch has commits that are not patch-equivalent to main,
and its name suggests it holds something valuable.
**Do:** `git diff main origin/<branch>` and read the lines present only on the
branch. Decide whether they are newer intent or an older version main has since
fixed.
**Why:** Unique content is not the same as unlanded work. When a branch predates
a fix, its "unique" lines are the defect, and restoring it reintroduces the bug.
**Evidence:** `fix/recover-post-merge-review-fixes` — a branch named for
recovering stranded fixes — held the PATH probe ranked above
`CLAUDE_PLUGIN_ROOT`, which is the exact bug main fixed after three tests sat red
for seven weeks.

## Print the count beside the expected count before any bulk destructive command

**Trigger:** A shell loop builds a list of targets for a delete, restore, or
migration, especially from a scalar variable in zsh.
**Do:** Emit the generated count and the expected count together, and read them,
before the destructive command runs.
**Why:** zsh does not word-split unquoted parameter expansions, so
`for b in $LIST` silently iterates once over the whole list as a single token.
The loop succeeds, exits 0, and produces a plausible-looking artifact.
**Evidence:** A 43-branch restore script generated 1 line instead of 33. Building
the delete command the same way would have removed 33 branches with a one-line
undo file.

## Fact-check a correction as hard as the claim it replaces

**Trigger:** You are about to commit documentation that corrects an earlier
factual error, and the correction feels settled because you just measured it.
**Do:** Have something with fresh context verify the corrected text against the
live artifacts, not against your diff.
**Why:** A correction carries the authority of having been checked, so nobody
checks it again. Being mid-investigation is when you are most likely to restate a
source you have already read and flatten it.
**Evidence:** Two of six claims in a docs-only PR were wrong after verification.
One flattened a two-branch eligibility rule into its child half — from a
docstring read earlier in the same session.

## Read a timeout as unknown, not as failure

**Trigger:** A long-running command returns exit 143, or a harness cuts it at a
fixed limit.
**Do:** Check the artifact and the process table before concluding anything. The
work may have completed, or may still be running.
**Why:** A watchdog shorter than the task kills it every time, at whatever point
it happened to reach, and the kill gets recorded as the task's own failure mode.
This is the same mechanism that made the backend suite "hang" at 40-48%.
**Evidence:** A baseline run timed out at exit 143 having produced no file — but
the log showed it blocked on stdin, never started, and left no process behind.
Three different conclusions, and only checking distinguished them.
