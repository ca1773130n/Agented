# Autonomy Is Not Unattendedness: We Let the Harness Ship Its Own Milestone

**Languages:** English (canonical) · [한국어](./BLOG-shipping-a-milestone-autonomously.ko.md)

*We pointed [Agented](https://github.com/ca1773130n/Agented)'s own planning harness at a six-phase milestone — design spec to merged PRs — and let it run. It planned, built, code-reviewed, and merged all six phases across three dependency waves without a human writing a line of feature code. It also stopped twice. Both halts were the orchestrator failing on its own git plumbing, not the feature work failing. That asymmetry is the whole story: in a self-improving harness, the hardest bugs are not in what it builds, they are in the layer that does the building.*

## The run

The milestone was v0.8.0 of Agented — "Team Harness & Self-Improvement," the layer that lets a project create its own harness primitives, run every super-agent conversation through [GetResearchDone](https://github.com/ca1773130n/Agented) (GRD) by default, and turn repeated operator requests into skills automatically. Six phases, twenty-six requirements, one approved design spec.

We invoked `gd autopilot 17-22` and walked away from the keyboard. The orchestrator computed a dependency graph from the roadmap and grouped the phases into three waves:

```
Wave 1:  [17]              forge creation surface
Wave 2:  [18, 19, 22]      sketch routing · GRD driver · auto-skill
Wave 3:  [20, 21]          GRD frontend wiring · one-click setup
```

Independent phases inside a wave run in parallel, each in its own git worktree so their file mutations never collide. Each phase ran the same pipeline: plan → execute → simplify → open PR → code review → rebase & merge → finalize. Six phases, six PRs (#213–#218), every review warnings-only, no blockers. The gates held: the targeted backend suite finished **1222 passed, 0 failed**; the frontend suite came back with exactly its seven known-baseline failures and no new ones. A milestone that would have been a week of human work merged itself in an afternoon.

That is the part that sounds like the future. Here is the part that is actually instructive.

## The two places it stopped

Both halts happened in the post-execution pipeline — the merge step — and neither had anything to do with the code being merged.

**The first one killed the whole run.** Phase 17 built cleanly, passed review, and the pipeline went to merge its PR with `gh pr merge --delete-branch`, running inside the phase's worktree. `gh`'s branch cleanup checks out the repository's default branch to delete the merged branch locally — and you cannot check out `main` from inside a linked worktree that isn't the one holding `main`. Git refused: `fatal: 'main' is already used by worktree`. The PR had already merged on GitHub; the orchestrator, seeing a non-zero exit, declared the phase failed and stopped all six phases. The feature was fine. The harness tripped over its own feet on the way out the door.

**The second one was quieter and worse, because it corrupted state instead of stopping.** When a phase finalizes, it stamps its roadmap row to "complete." The stamper used a positional regex that assumed a fixed column layout — `| Phase | Name | Status | Date |`. Our roadmap table is wider (it carries Requirements and Depends-on columns), so the stamp landed in the wrong cells and overwrote real data with the word "Complete." A run that "succeeded" left its own planning ledger quietly wrong. This is the failure mode we have written about before: [the green checkmark over the broken thing](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.md). The pipeline reported success while silently degrading the record of what it had done.

A third, milder one surfaced after we fixed the first: the post-merge step that reconciles the local `main` with the freshly merged remote uses an auto-stashing rebase, which only protects *tracked* files. Scratch files the orchestrator itself had written into the working tree blocked the checkout, so the reconcile aborted with a warning and left `main` lagging the remote. Non-fatal, but it means the run cannot fully close its own loop without a human fast-forward at the end.

## The human's job moved up a layer

None of these are feature bugs. You could review the diffs of all six phases and never find them, because they do not live in the diffs — they live in the machinery that produces diffs. So the work this run actually demanded of a human was not "write the feature" and not even "review the feature." It was: read the orchestrator's own source, find why its merge step is worktree-unsafe, fix it, and re-launch. Then find why its state-stamper is column-blind, fix that, and repair the rows it had already mangled.

We fixed both in GRD's source — merge without the worktree-hostile flag and delete the remote branch directly; make the stamper find its target column by header instead of by position — committed the fixes, and re-ran. Auto-resume skipped the four already-merged phases and carried the last two to completion. The loop closed. But notice *who* closed it. The self-improving harness did not repair its own orchestrator. A human did, in the orchestrator's repository, in between two runs of the orchestrator. The autonomy was real at the feature layer and entirely absent at the meta layer.

This is the distinction the word "autonomous" papers over. The autopilot was autonomous in the sense that it made every product decision, wrote every test, and merged every PR without us. It was not *unattended*, because the moment its own plumbing failed, only a human standing outside the loop could fix the thing running the loop. A harness can build features all day. It cannot yet notice that its own merge command is incompatible with its own worktree strategy, diagnose that, and patch itself. The gap between those two capabilities is exactly the gap between "autonomous" and "unattended," and almost everyone shipping agent autopilots today is quietly relying on a human to stand in it.

## What it shipped is more of the same machinery

The recursion runs deeper than the anecdote, because the milestone the harness shipped is *itself* self-improvement machinery. Phase 22 — built autonomously in Wave 2 — is a repeated-request detector: it watches completed sessions across all five session kinds, embeds the operator's requests, and when the same ask recurs three times against a verified-successful episode, it proposes a new skill. It is modeled on [Hermes Agent](https://github.com/NousResearch/hermes-agent)'s self-authored skills, but gated the way the [ToxicSkills threat model](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/) demands: a confidence floor, a verification requirement, a prompt-injection and invisible-Unicode scan before anything is written, and a provenance hash so the loop never overwrites an operator-edited skill. The harness built, autonomously, a slightly more autonomous version of itself — and we made sure the part that writes new behavior to disk ships locked down, because an agent that learns by writing a skill has, structurally, [downloaded a dependency](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.md).

That is the right shape. The feature layer compounds: each milestone makes the next one cheaper to build. But the meta layer does not compound on its own yet. The auto-skill loop will propose skills tomorrow that it could not propose today. The orchestrator will hit the same class of plumbing bug tomorrow that it hit today, unless a human teaches it otherwise — which is exactly what we did to the merge step and the stamper this week.

## The prediction

Made so it can be falsified.

The next frontier for agent autopilots is not a higher pass rate on the work. It is the meta-layer self-heal: an orchestrator that, when its own merge step fails on its own worktree invariant, treats that failure as a task — diagnoses it in its own source, proposes the fix as a reviewable diff, and resumes — rather than halting for a human. We will know the frontier has been crossed when an autopilot fixes a bug in itself, mid-run, and the operator finds out by reading the commit afterward.

Within twelve to eighteen months, the first autopilot to do this credibly will make every "autonomous" agent that still halts on its own plumbing look like what it is: a feature-builder with a human quietly holding its merge strategy together. The teams that win this will be the ones who, like us this week, treated the orchestrator's own bugs as first-class work product instead of incidental friction — and who logged every one of those bugs with the same provenance discipline they apply to the agent's beliefs. The orchestrator is part of the system under audit, too. The day it can audit and repair itself is the day "autonomous" finally means "unattended." It does not mean that yet. Anyone who tells you otherwise has a human standing in the gap, same as we did.

## References

### The platform and the run
- **Agented** — the meta-orchestration layer whose own milestone is described here. [github.com/ca1773130n/Agented](https://github.com/ca1773130n/Agented)
- **GetResearchDone (GRD)** — the planning/execution harness (`gd autopilot`) that planned, built, and merged the six phases; the two halt-bugs were fixed in its source mid-run.
- **The v0.8.0 design spec** — the approved blueprint the autopilot executed: forge creation surface, sketch→primitive routing, GRD-as-default-driver, full GRD frontend wiring, one-click team harness setup, repeated-request auto-skill.

### The series this extends
- **Your Agent Doesn't Have a Memory Problem. It Has a Provenance Problem.** — the provenance argument and the twelve-silent-failures dogfood. [BLOG-self-improving-harness.md](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.md)
- **Porting Harness-1** — adversarial verification as a first-class build step. The research report it shipped with now lives at [harness-1-integration.md](./harness-1-integration.md).

### The machinery the milestone shipped or referenced
- **Hermes Agent** (NousResearch) — self-authored skills, the model for the auto-skill loop. [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- **Snyk ToxicSkills audit** — why the auto-skill loop ships gated by default. [snyk.io/blog/toxicskills](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/)
- **Voyager** — the embedding-similarity skill-retrieval prior art behind the detector. [arxiv.org/abs/2305.16291](https://arxiv.org/abs/2305.16291)
