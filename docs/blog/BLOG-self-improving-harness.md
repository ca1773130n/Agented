# Your Agent Doesn't Have a Memory Problem. It Has a Provenance Problem.

**Languages:** English (canonical) · [한국어](./BLOG-self-improving-harness.ko.md)

*The memory benchmarks are settled. [Mastra OM](https://github.com/mastra-ai/mastra) ships 94.87% on LongMemEval, [Letta](https://www.letta.com/blog/letta-v1-agent) ~83.2%, [Zep/Graphiti](https://arxiv.org/abs/2501.13956) beats MemGPT by 18.5% with 90% latency reduction. Pick by your budget. The problem is that LongMemEval is to agent memory what BLEU is to translation — a proxy metric the field is collectively winning at the expense of the thing operators actually need. The agents that pass these benchmarks will not survive their first audit. Here is why, and what's coming next.*

## The benchmarks the field is celebrating

A non-trivial percentage of public agent-memory engineering in 2026 is now optimization against [LongMemEval](https://www.emergentmind.com/topics/longmemeval-benchmark) — 500 curated questions, six categories (single-session recall, preference recall, knowledge update, temporal reasoning, multi-session recall, etc.), with accuracy as the headline metric. The leaderboard moves quickly. Per [Mem0's State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026), [Mastra OM](https://github.com/mastra-ai/mastra) sits at 94.87% — the highest recorded — followed by Letta at roughly 83.2%, and Mem0 itself at around 49% on the temporal sub-task. [Zep's Graphiti paper](https://arxiv.org/abs/2501.13956) (arXiv 2501.13956) reports an 18.5% accuracy improvement over MemGPT with a 90% latency reduction on the LongMemEval variant, via a bi-temporal knowledge graph that tracks both when an event occurred and when it was ingested.

The shape of the leaderboard, drawn honestly:

<p align="center"><img src="assets/01-benchmark-vs-auditeval.png" alt="LongMemEval scores versus a non-existent AuditEval axis" width="720"></p>

This is real engineering. The architectures behind those bars on the left are sophisticated. [Letta](https://docs.letta.com/concepts/letta/) pioneered the LLM-as-an-Operating-System framing with core memory (always-in-prompt) and archival memory (queried on demand), self-editable by the agent via tool calls. [Mastra](https://deepwiki.com/mastra-ai/mastra/7-memory-and-storage-architecture) ships working memory (resource-scoped or thread-scoped), semantic recall, and pluggable storage adapters. [Cognee](https://www.cognee.ai/blog/fundamentals/how-cognee-builds-ai-memory) does RAG-to-graph with custom graph models per domain. [Hermes Agent](https://github.com/NousResearch/hermes-agent) — 95.6K stars, one of the most-watched agent projects of 2025 — runs file-based harness state (SOUL.md / MEMORY.md / USER.md / skill documents per the [agentskills.io](https://agentskills.io/home) open standard) with SQLite + FTS5 underneath. The work is good. The benchmarks are getting saturated for a reason.

Here is the problem nobody wants to say out loud: **the benchmarks are measuring the wrong thing**, and the projects winning them are getting the wrong thing right.

## What LongMemEval doesn't measure (and why it matters)

LongMemEval tests whether an agent can correctly recall a fact it was told, possibly several sessions ago, under varying memory pressure. It is a *retrieval* benchmark — sophisticated, well-constructed, useful for what it measures. What it does not measure is the failure mode that destroys agents in production. Call it **provenance rot**.

An agent recalls correctly that the deploy script lives at `scripts/deploy.sh`. Perfect score. But the operator asks the obvious next question: *where did that come from?* The audit chain a regulator actually needs looks like this:

<p align="center"><img src="assets/02-provenance-chain.png" alt="Provenance audit chain" width="720"></p>

LongMemEval scores the agent that says "scripts/deploy.sh" identically whether the chain above resolves end-to-end or the recall is hallucinated from semantic similarity against a half-stale embedding chunk. Was the rule later superseded — did somebody refactor and move the script to `scripts/release/`? Did the takeaway that produced the rule come from a session that actually happened, or from a parser that silently lied? If a regulator, six months from now, asks "what did the agent know about the deploy procedure on the day it triggered the outage," can the system answer?

LongMemEval does not test any of this. It scores the agent that says "scripts/deploy.sh" identically whether the recall is grounded in a verifiable event with a timestamp and a session ID, or hallucinated from semantic similarity against a half-stale embedding chunk. The benchmark optimizes the surface property (correct retrieval) while remaining structurally blind to the production property (auditable retrieval). This is exactly the situation machine translation lived in for a decade with [BLEU](https://en.wikipedia.org/wiki/BLEU): a proxy metric that the field optimized successfully for years before realizing the gains had been gains *in the proxy*, not in the underlying capability. Fluency on the n-gram axis improved while faithfulness to source meaning lagged. Everyone congratulated themselves until someone tried to deploy the systems for real work.

The same shape is happening now. We have agents that recall 94.87% of facts under retrieval pressure and that, the moment you ask them to justify a single one of those facts to an auditor, become a black box. Memory at high accuracy with zero provenance is not memory in any sense an enterprise can trust. It is a fluent stochastic parrot with a longer leash. The field is optimizing the surface property because the surface property is what the leaderboard rewards.

## Why this matters more in May 2026 than it did six months ago

If the only consequence of provenance rot were a regulatory inconvenience, we could put it on the roadmap and ship next year. The consequence got more concrete in February.

On February 5, 2026, [Snyk Labs published the ToxicSkills audit](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/) — the first large-scale security audit of AI agent skills under the agentskills.io open standard. The breakdown of what they found across 3,984 publicly listed skills:

<p align="center"><img src="assets/03-toxicskills-breakdown.png" alt="ToxicSkills audit findings across 3,984 skills" width="720"></p>

Of the 3,984: 1,467 (36.8%) had at least one security flaw. 534 (13.4%) had critical-level issues. **76 contained confirmed malicious payloads** — deliberate credential theft, reverse shells, data exfiltration. 91% of the malicious skills combined traditional malware patterns with prompt injection, a convergence that defeats both LLM safety mechanisms and conventional MCP security scanners. Two weeks later, [the first coordinated skill malware campaign](https://www.agensi.io/learn/toxicskills-clawhavoc-agent-skills-security-crisis-2026) — distributed via the ClawHub registry — used 30+ weaponized skills to target Claude Code and OpenClaw users. Researchers at Cornell have already proposed [SkillSieve](https://arxiv.org/html/2604.06550v1), a hierarchical triage framework for detecting malicious skills, because the existing ecosystem has no answer. The barrier to publishing a skill on ClawHub is a SKILL.md and a one-week-old GitHub account. No signing. No review. No sandbox by default.

This changes the provenance question from "can you audit your agent" to "*do you know which of the things your agent has internalized is malicious*." Skills are no longer just procedural knowledge the agent loaded into context. They are an attack surface with read access to your filesystem and write access to your shell, distributed via package registries with the security maturity of npm in 2015 and the threat model of npm in 2025. Every platform racing to add autonomous skill creation — Hermes Agent's `skill_manage` tool, Letta's self-editing memory, the half-dozen others — owns this risk by default. An agent that "learns" by writing a new skill to disk has, structurally, downloaded a dependency.

The npm parallel is not subtle. It took the JavaScript ecosystem more than a decade to develop signing, audits, lockfiles, supply-chain attestation, and even now an unmaintained transitive dependency can compromise a Fortune 500 build. The agent-skill ecosystem is repeating the trajectory at LLM speed, with the added complication that the artifact is markdown-with-instructions executed by a tool that interprets natural language, so static analysis is meaningfully harder. The benchmarks the field is optimizing — accuracy on a curated chat history — do not measure any of this. They cannot. The benchmarks predate the threat model.

## What an auditable architecture actually looks like

I want to walk through one specific answer to this — not as the hero of the story, but as a concrete example of what falls out of the architecture when you take provenance seriously from day one. We built [Agented](https://github.com/ca1773130n/Agented) as a meta-orchestration layer above existing harnesses ([Claude Code](https://github.com/anthropics/claude-code), [Codex CLI](https://github.com/openai/codex), [Cline](https://github.com/cline/cline), Hermes Agent) and a few months ago started taking the provenance problem seriously after watching, twelve times in one ninety-minute window, our test-passing extractor pipeline lie to us about what was happening in production. The result is a system that is not particularly impressive on LongMemEval (we have not measured) but that solves a problem nobody has named yet. The pattern, abstracted:

Start with the spine of it: every retained belief is tagged with its source event. When a session produces a takeaway, it lands in `session_takeaways` with a stable `tk-*` ID, a `session_kind` + `session_id` pointer back to the originating conversation, the extractor version that produced it, and a confidence score. When that takeaway becomes a rule or a skill or a knowledge-graph node, the asset carries `source_takeaway_id` in its properties. The relationship is queryable in both directions. A regulator asks "why did the agent do X" and the answer chains backward: agent invoked rule R → rule R was created by evolution round E → round E was motivated by takeaways T1, T2, T3 → those takeaways were extracted from sessions S1, S2, S3 → those sessions are durable records in the database with full transcripts. Every link in the chain is a row in a table with a timestamp. Nothing is similarity-scored over an embedding blob.

Two evidence streams feed that spine, asymmetric and both audited. The Life-Harness paper proposed a four-layer failure taxonomy (H2 interface / H3 environment contract / H4 trajectory regulation / general) for classifying what went wrong in a session. We run that classifier as the *failure annotator* on every completed session. We also run a *takeaway extractor* — heuristic + Codex LLM — that surfaces seven kinds of positive signal (preferences, procedures, tool patterns, constraints, domain facts, root causes, success patterns). Both feed downstream from the same `session_complete` event channel:

<p align="center"><img src="assets/04-two-evidence-streams.png" alt="Two evidence streams" width="720"></p>

The asymmetry matters: failures want rules and hooks; successes want skills and commands. Most agent-memory projects pick one direction, almost always positive, and silently lose half the signal. Provenance does not work if you only audit what went well.

Skill creation, meanwhile, is operator-approved rather than autonomous. When the takeaway extractor surfaces a high-confidence procedural pattern (≥ 0.85 confidence, with `suggested_target = skill`), the artifact is written as a `SKILL.md` package under `.claude/skills/.agented-takeaways/<name>/` — a *separate* directory, gitignored by default, kept apart from operator-curated skills so the diff between the two is one git status away. Before that, the takeaway sits in a queue. The operator either runs `AGENTED_TAKEAWAY_AUTOAPPLY=1` in their environment (opt-in, never default) or reviews the takeaway in the Memory System Settings tab and clicks Apply. If we are sitting in Snyk's ToxicSkills threat model — and we are — the only safe default is "the agent proposes, the operator approves." Every applied skill carries a frontmatter pointer back to the takeaway ID, the session ID, and the confidence. Trace any malicious behavior backward and the source session is in the database. Trace any *un*-applied takeaway and it shows up in the queue, never executed.

Harness evolution runs as a separate proposal cycle for the same reason. When we want to mutate the project's harness primitives (rules, hooks, commands, MCP servers), we don't have an agent edit them in-process. We invoke a separate evolver loop: gather the project's current Forge primitives + recent trajectories + recent takeaways into an ephemeral scratch workspace, run `codex exec --sandbox workspace-write` against it, parse the resulting patch, validate it against schemas, and present a diff to the operator. The pattern is code review for agent behavior. The model proposes; the human approves; the change becomes a `git log` entry on the project's `.claude/` directory. Hermes Agent and Letta both ship variants where the agent edits its own memory in-line; we chose the proposal-review variant explicitly because in a world where 36% of public skills have security flaws, you want a diff before the change lands. We are not arguing the inline-edit pattern is wrong. We are arguing that any team running these systems in regulated environments will end up adding the review gate, and architecting around it from day one is cheaper than retrofitting.

And compilation is kept separate from query. [Tesserae](https://github.com/ca1773130n/Tesserae) — a typed knowledge-graph compiler — ingests code, docs, and agent-session history per project and produces a single `graph.json` with typed nodes (`CodeFile`, `CodeMethod`, `Session`, `SessionDecision`, `SessionInsight`, `SessionTakeaway`). The compile is offline (after N sessions or M minutes). The query is online via an MCP stdio server that we auto-bind as a per-project Forge primitive the moment the operator enables Tesserae. The team-leader super-agent for the project gains `tesserae_ask`, `search_facts`, `graph_ppr`, `find_session_findings` in its tool list. When the operator asks the leader a question, the leader's answer streams back with two attribution rows: *Queried* (the typed `tool_use` events propagated through a `Union[str, ToolUseEvent]` stream, dispatched as a dedicated `tool_use` delta on the chat state service) and *Cited* (file paths, `kge-*` graph IDs, `sess-*` session IDs, `tk-*` takeaway IDs extracted from the synthesized text). The operator sees both what the leader queried and what the answer ended up referencing. The behavior is auditable because the store it queried is structured.

The aggregate effect, none of which is captured in any benchmark currently in use: every behavior the agent takes is traceable backward to a session, every belief the agent holds is traceable backward to an evidence event, every skill the agent has is traceable backward to either an operator decision or an approved evolution round. Provenance is not a feature we layered on top. It is what falls out of the architecture when you make it the design constraint.

## What the 12 silent failures taught us about provenance

A short interlude, because the dogfood story is the part that convinced me the provenance problem starts earlier than I had thought.

In one ninety-minute window of running this system against six months of our own production data, we found twelve silent failures. The pattern was uniform: the pipeline succeeded, the tests passed, the dashboards stayed green, the database stored exactly what the parser told it to store — and the data was wrong. A parser expected newline-delimited Claude JSONL while the actual storage format was a JSON array of role/content objects. The parser returned zero events. The takeaway extractor faithfully extracted nothing. The dashboard reported "no takeaways this week." A bot had been scheduled-running every Sunday for 22 weeks, the trigger referenced an unregistered slash command, Claude exited 0, the result event in the stream literally contained the string *"Unknown command: /vulnerability-scan"* — but nothing parsed the result event, so nothing surfaced it, so the dashboard reported a green checkmark every Sunday for five months.

The discipline that came out: every fetcher, parser, and extractor in this pipeline must be run against ≥3 real production rows before being declared done. Unit tests built around hand-crafted inputs pass for the same reason the bugs exist — the inputs were shaped exactly like what the parser expected.

The reason this matters for provenance: **observation is the provenance ledger's input layer.** If the observation step lies to the downstream pipeline, the audit trail is built on fiction. The agent confidently cites session S1 as the source of belief B; the audit chain looks pristine; the actual session S1 was a silent no-op the parser missed. Provenance is not just "tag every belief with a source ID." It is "make sure the source IDs point at events that actually happened." The benchmarks do not test this either, and they cannot. Synthetic chat histories cannot replicate the failure modes of production observation pipelines, which is what makes the dogfood pass — running real production data through every link in the chain before believing any of them — non-negotiable.

## What the next benchmark needs to measure

LongMemEval will not last as the field's headline metric. Something will replace it, and the form of the replacement is partly visible from the gap. An auditability benchmark — call it AuditEval, somebody is going to write it — needs at least five axes that no current memory benchmark tests:

The first is **source attribution**: given a retained belief, can the agent produce the originating event — session ID, transcript span, timestamp? Cosine similarity over an embedding does not pass; the agent that recalls correctly but cannot point at the source fails. Next to it sits **supersession tracking**: when fact B replaces fact A — a file got renamed, a procedure changed, the operator explicitly overrode an earlier belief — can the system represent that A is now historical, and does the agent reach for A under recall pressure or know to use B? And **confidence calibration**: does the agent know what it is uncertain about? A retrieved fact with an attached confidence interval that correlates with downstream accuracy is more useful in production than a high-accuracy point estimate the agent cannot grade.

The last two axes come straight from the threat model. **Provenance under skill load**: when the agent loads a skill — possibly a third-party skill from a package registry — does the knowledge that skill injects carry provenance metadata, and can the operator distinguish, in audit, between "the agent knew this from a session" and "the agent knew this because a skill of unknown origin told it"? And **rollback**: can an operator revert a learned heuristic — specifically, given a rule the system learned three weeks ago, identify the takeaways and sessions it came from, revert the rule, and have downstream behavior change accordingly without restarting the agent? Production deployments need this. No current benchmark tests it.

The field can decide whether AuditEval lives in academia or in a security firm's marketing — I suspect both — but the existence of something like it is now inevitable. The first regulated industry to deploy these systems at scale will pull the rest of the field forward, the way GDPR pulled adtech forward whether the adtech firms were ready or not. The optimization frontier is going to move. The projects whose architectures were never designed for it are going to discover they shipped the right thing in the wrong layer.

## What's coming

A prediction, made specifically so it can be falsified.

In the next 12 to 18 months:

<p align="center"><img src="assets/05-forecast-timeline.png" alt="Forecast timeline" width="720"></p>

The first regulated industry (finance, healthcare, defense) deploys long-running agents at scale and the audit requirements documented in their procurement RFPs become the de facto spec for what production agent memory means; at least one of the named memory-architecture startups discovers that their architecture cannot retrofit provenance without a ground-up rebuild, and either pivots, gets acquired, or quietly stops shipping the leaderboard numbers.

The piece of this nobody is yet saying clearly: **memory and provenance are not the same problem, and the projects that conflate them are about to discover that the second problem is the harder one**. The agent-memory wave got the analogy from cognitive science — agents should remember like people remember. Provenance comes from a different analogy: agents are colleagues, and a colleague who cannot tell you where they learned a fact is not someone you let make decisions on your behalf. We built [Agented](https://github.com/ca1773130n/Agented) around the second analogy. The architecture decisions are open-source; the rationale, including the parts that have not been articulated as cleanly as they should have been, is in this essay.

The race the field has been running was the wrong race. The one that's about to start is the one that matters.

## References

### The platform and ideas referenced
- **Agented** — meta-orchestration layer driving multiple harnesses against shared per-project state. [github.com/ca1773130n/Agented](https://github.com/ca1773130n/Agented)
- **Tesserae** — typed knowledge-graph compiler used as Agented's query tier. [github.com/ca1773130n/Tesserae](https://github.com/ca1773130n/Tesserae)
- **Life-Harness** — the four-layer failure taxonomy this work builds on. Paper: [arxiv.org/abs/2605.22166](https://arxiv.org/abs/2605.22166) · Code: [github.com/Tianshi-Xu/Life-Harness](https://github.com/Tianshi-Xu/Life-Harness)
- **Model Context Protocol** — the tool-calling protocol every harness referenced here speaks. [github.com/modelcontextprotocol](https://github.com/modelcontextprotocol)

### Memory architectures discussed (not strawmanned — read them)
- **Mastra** — 94.87% LongMemEval, working / thread / semantic memory tiers. [github.com/mastra-ai/mastra](https://github.com/mastra-ai/mastra) · [Memory architecture deep-dive](https://deepwiki.com/mastra-ai/mastra/7-memory-and-storage-architecture)
- **Letta** (formerly MemGPT) — LLM-as-OS, self-editing memory via tools. [github.com/letta-ai/letta](https://github.com/letta-ai/letta) · [Agent Memory blog](https://www.letta.com/blog/agent-memory)
- **Zep / Graphiti** — bi-temporal knowledge graph. [Paper: arxiv.org/abs/2501.13956](https://arxiv.org/abs/2501.13956) · [github.com/getzep/zep](https://github.com/getzep/zep)
- **Mem0** — hybrid vector / graph / key-value, LLM-powered fact extraction. [github.com/mem0ai/mem0](https://github.com/mem0ai/mem0) · [State of AI Agent Memory 2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Cognee** — RAG-to-graph with custom domain models. [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee)
- **Hermes Agent** (NousResearch) — file-based harness state with autonomous skill creation. [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) · [Architecture docs](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture)

### Skill ecosystem and the security crisis
- **Agent Skills standard** (agentskills.io) — Anthropic-originated, December 2025, 26+ platforms. [agentskills.io](https://agentskills.io/home) · [Specification](https://github.com/agentskills/agentskills)
- **Snyk ToxicSkills audit** — 36.8% flaw rate, 76 confirmed malicious payloads. [snyk.io/blog/toxicskills](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/)
- **The skill-malware coordinated campaign** — 30+ weaponized skills, Feb 2026. [agensi.io coverage](https://www.agensi.io/learn/toxicskills-clawhavoc-agent-skills-security-crisis-2026)
- **SkillSieve** — hierarchical triage for malicious skills. [arxiv.org/html/2604.06550v1](https://arxiv.org/html/2604.06550v1)

### Benchmarks and the field
- **LongMemEval benchmark** — current memory leaderboard. [Overview](https://www.emergentmind.com/topics/longmemeval-benchmark)
- **Harness Engineering as a field** — awesome list: [github.com/ai-boost/awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering) · [Survey](https://picrew.github.io/LLM-Harness/) · [O'Reilly Radar](https://www.oreilly.com/radar/agent-harness-engineering/)
- **The AI Control Plane framing** — [Agent Harness Engineering: The Rise of the AI Control Plane](https://medium.com/@adnanmasood/agent-harness-engineering-the-rise-of-the-ai-control-plane-938ead884b1d)

### Harnesses for context
- [Claude Code](https://github.com/anthropics/claude-code) · [Codex CLI](https://github.com/openai/codex) · [Cline](https://github.com/cline/cline) · [OpenHands](https://github.com/All-Hands-AI/OpenHands) · [Aider](https://github.com/Aider-AI/aider) · [Continue](https://github.com/continuedev/continue) · [Devin](https://devin.ai)
