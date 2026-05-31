# 自我改进 harness：架构

**语言:** [English](/self-improving-harness-architecture) · [한국어](/ko/self-improving-harness-architecture) · [日本語](/ja/self-improving-harness-architecture) · 中文 (当前)

*[BLOG-self-improving-harness.md](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.md) 的配套文档。
该博客主张，智能体记忆领域正在优化错误的维度（召回准确率），却忽视了在
生产中真正重要的维度（来源（provenance） + 可审计性）。本文档解释了认真
对待这一问题后所导出的系统 — 不是一个记忆存储，而是一个闭合的**自我改进
循环（self-improvement loop）** — 并诚实地将其与博客所引用的记忆架构进行
比较。*

---

## 1. 我们解决的并不是记忆问题

博客提到的每一个系统 — Mastra、Letta/MemGPT、Zep/Graphiti、Mem0、Cognee、
Hermes Agent — 都是一个**记忆架构**。其职责是：给定一段对话流，*保留*事实
并在日后压力之下将其*召回*。基准是 LongMemEval，维度是检索准确率。

Agented 的自我改进 harness 处于其上一层。记忆是基底（substrate），而非
产品。产品是一个提出不同问题的循环：

> 鉴于智能体在其各次会话中所做的一切，**harness 自身应当如何改变** —
> 它的规则（rule）、钩子（hook）、命令（command）、技能（skill）、MCP
> 绑定 — 并且这一改变能否在无需人类手动编辑某个原语、且*不丢失审计链*
> 的前提下，被评分、批准、回退与传播?

这是一个**自我改进**问题（变异你自己的运行上下文），而非一个**记忆**问题
（召回别人告诉你的内容）。两者常被混为一谈。它们是不同的，而且第二个更难。
一个能召回「部署脚本被移动了」的记忆系统，仍然需要一个人类把它变成一条
规则。自我改进 harness 弥合了这一鸿沟 — 而就在它这么做的那一刻，它继承了
纯召回系统从不面对的安全与审计负担：它现在正基于自身的推断*把可执行的指令
写入磁盘*。

我们的整个架构，正是由拒绝让那次写入在没有评分门、没有批准（操作员或
受策略约束的自主）、没有回退日志、以及没有端到端来源（provenance）的情况
下发生，而被塑造出来的。

---

## 2. 闭合的循环

```
 ┌──────────────────────────────────────────────────────────────────────────┐
 │                                                                            │
 │   (1) CAPTURE            (2) ANNOTATE / EXTRACT        (3) GATHER          │
 │   every session   ──►    two asymmetric evidence  ──►  + KG-seeded        │
 │   → snapshot+events      streams (failures|wins)       evolution inputs    │
 │                                                            │               │
 │                                                            ▼               │
 │   (10) KG FEEDBACK                                    (4) PROPOSE          │
 │   sessions compiled  ◄────────────────────────        Codex in sandboxed  │
 │   into typed graph                                     scratch → patch     │
 │        ▲                                                   │               │
 │        │                                                   ▼               │
 │   (9) PROPAGATE                                       (5) EVAL-GATE        │
 │   proven primitives   ◄───────┐                       static checks +     │
 │   promote cross-project        │                      replay LLM judge     │
 │        ▲                       │                       → EvalVerdict       │
 │        │                       │                           │               │
 │   (8) ROLLBACK            (7) MATERIALIZE             (6) APPLY            │
 │   reverse journal     ◄──  .claude/ + one git    ◄──  operator-approved   │
 │   + git revert            commit per round            OR policy-autonomous │
 │                                                                            │
 └──────────────────────────────────────────────────────────────────────────┘
```

每一个带编号的阶段，都是代码库中一个真实、可审计的工件。这个循环是
**受门控的**，而非自由运行：未跨越一条记录来源的显式边界，任何原语都不会
被变异、落到磁盘上、或被传播。

### (1) 捕获 — `harness_snapshot_service.py`, `session_events.py`
在每一个完成的会话上（横跨*所有*会话种类 — 触发器执行、超级智能体运行、
团队执行、工作流；绝不仅仅是「机器人」），已解析的 harness 包的**快照**会
与原始会话事件流一同被持久化。这是来源台账（ledger）的输入层。博客中
「12 个静默失败」的插曲，正是关于确保这一层不会在下游撒谎 — 每一个抓取器
（fetcher）/解析器（parser）在被信任之前，都要针对 ≥3 条真实生产数据行
进行内部试用（dogfood）。

### (2) 标注 + 抽取 — 两条不对称的证据流
两者都从同一个 `session_complete` 通道分叉而出：

- **失败标注器（failure annotator）**（`harness_failure_annotator.py`）运行
  **Life-Harness 四层分类体系** — `detect_h2`（接口） →
  `detect_h3`（环境契约） → `detect_h4`（轨迹调控） → 通用 — 由
  `_apply_priority_protocol` 排定优先级，并将带类型的事件写入
  `harness_annotations`。
- **要点抽取器（takeaway extractor）**
  （`harness_takeaway_extractor.py`，启发式 + provider-kind LLM）将*正向*
  信号 — 用户偏好、发现的流程、工具模式、约束、领域事实、根本原因、成功
  模式 — 浮现到 `harness_takeaways`（带稳定的 `tk-*` ID、
  `session_kind`/`session_id` 反向指针、抽取器版本、置信度）。

**不对称性正是要点**：失败需要规则与钩子；成功需要技能与命令。大多数记忆
系统只捕获一个方向（通常是正向），并静默地丢失一半信号。

### (3) 汇集（Gather） — `harness_evolver.gather_inputs`
组装演化轮次的输入：项目当前绑定的 Forge 原语、近期轨迹（快照 + 其标注 +
事件）、近期要点，**以及** — 最后一条循环边 — 来自已编译 Tesserae 图谱的
**KG 信号**（`gather_kg_signals`，≤3 个受限的 `ask_tesserae` 发现性问题，
经加权/去重，并被门控以使未启用 Tesserae 的项目零成本）。循环所*产出*的
图谱（阶段 10）现在为循环*播种*（阶段 3）。这正是使它成为一个循环而非
一条流水线的原因。

### (4) 提案（Propose） — 沙箱化暂存工作区中的 Codex
`build_workspace` 将输入写入一个临时目录（`forge/`、`trajectories/`、
`takeaways/`、`KG_SIGNALS.md`、`tesserae_context.md`）；
`codex exec --sandbox workspace-write` 针对它运行；得到的补丁被解析并经过
模式校验。**模型提出一个 diff；它绝不在进程内编辑一个活动的原语。**

### (5) 评估门（Eval-gate） — `harness_evolution_eval.py`
在任何应用（apply）之前，补丁被评分为一个 **`EvalVerdict`**（`passed: bool`、
`score: float ∈ [0,1]`、`per_check: [CheckResult]`）：

- **静态检查（static checks）**（`_static_checks`） — 机械性的：模式有效性、
  前置元数据健全性、空操作（no-op）检测、行锚定（line-anchored）守卫。
- **回归重放裁决者（regression-replay judge）**（`_run_judge`，经由
  `resolve_llm_cmd` 的 provider-kind） — 将代表性会话样本针对*已打补丁的*
  原语集合进行重放，并询问裁决者行为是否发生回退。

`_verdict` 在补丁未通过时把分数压到信任下限（trust floor）以下。一个失败的
门（`eval_failed`）会短路应用。门的*错误*采取 fail-open，但会记录一个
**分数为 0.0 的绕过（bypass）裁决**，因此绕过绝不会与一次真正的通过静默地
无法区分。这正是每一个「自我编辑记忆」系统所缺失的评分层。

### (6) 应用（Apply） — 操作员批准**或**策略自主
轮次的状态机
（`pending → running → evaluating → awaiting_approval → applied`，以及
`eval_failed`/`failed`/`aborted`/`reverted` 出口）针对**同一套**机制支持
两条应用路径：

- **操作员**：试运行轮次停在 `awaiting_approval`；操作员审阅 diff，然后
  `POST /evolution/rounds/{id}/apply`。
- **自主**（`harness_autonomy.py`）：一个 5 分钟周期的调度任务
  （`autonomous_apply_job` → `process_project_autonomy`）*仅当*
  `autonomous_apply_eligible` 通过**九道硬门**时才自动应用 — 终止开关
  （`AGENTED_AUTONOMY=0`）、按项目启用的策略、eval `passed` **且**
  `score ≥ confidence_threshold`（默认 0.85）、爆炸半径 ≤
  `max_ops_per_round`、`allowed_kinds`、`block_deletes`、`cooldown_seconds`、
  `rate_limit_per_day`。默认关闭，按项目选择加入（`project_autonomy_config`）。

自主是操作员路径的一种*受限的*升级，而非一条独立的、未经审计的代码路径。

### (7) 物化（Materialize） — `forge_materialization_service.py`
已应用的原语会被投影到项目真实的 `.claude/` 布局
（commands/rules/hooks + `settings.json`/`mcp.json`/skills），以幂等且
保留操作员改动的方式进行，并作为**每轮一次 git 提交**被提交。harness 的
演化现在就是 `git log`。

### (8) 回退（Rollback） — `harness_evolution_rollback.py`
`apply_patch` 捕获一份 **before-image 应用日志（apply-journal）**。
`revert_round` 在轮次并非带有日志的 `applied` 状态时拒绝执行，检测冲突
（触及同一 `{kind, asset_id}` 的后续轮次），幂等地逆转 DB 操作，然后
git revert 物化提交。部分失败或 git 失败会让轮次连同 `revert_error` 保持在
`applied` — 它绝不*声称*自己达成了并未达成的 `reverted`。这正是博客中
「AuditEval Rollback 维度」的实现。

### (9) 传播（Propagate） — `harness_propagation.py`
一个内容**指纹**（`forge_fingerprint.py`，内容字段的 sha256）赋予原语一个
跨项目的身份。每一个已应用且 **eval-PASSED** 的轮次都记录衰减的晋升证据；
一旦某个指纹的时间衰减分数越过 `PROMOTION_THRESHOLD = 3.0`，一份
**全局作用域副本**就会被晋升（`shared_forge_bindings`），其他项目随之采纳它
（`adopt_shared_binding`，local-wins 冲突策略）。`_PROPAGATABLE = (rule,
hook, command)`。只有 eval 通过的轮次才贡献证据 — 任何强制应用都无法污染
共享层。

### (10) KG 反馈 — `tesserae_integration.py`
每一个完成的会话都会被自动导入项目的 Tesserae 工作区
（`on_session_complete` → `export_sessions_to_tesserae`）；操作员编译一个
带类型的知识图谱（`CodeFile`、`Session`、`SessionTakeaway`、
`SessionDecision`、…）。那个图谱正是阶段 (3) 所查询的基底 — 从而闭合循环。

---

## 3. 是什么让它可审计（贯穿线）

每个阶段都发出一行（row），带有时间戳和反向指针：

- 一个行为 → 产生它的**规则** → 锻造它的**轮次** → 给它评分的
  **eval 裁决** → 促成它的**要点/事件** → 它们被抽取自的**会话** →
  持久的成绩单（transcript）。
- 一条学到的启发式可以按 ID 被**回退（revert）**，而它所源自的会话与要点
  仍然可查询。
- 一个被晋升的原语携带其**指纹**以及越过阈值的那份证据。

这条链中没有任何一环是基于对某个嵌入块的相似度打分的。这正是任何记忆基准
都不测量、而博客假想的 *AuditEval* 会测量的属性。

---

## 4. 与博客所引用架构的比较

诚实的框定：**这些大多并非竞争者 — 它们在不同的维度上运作。**
Mastra/Zep/Mem0/Cognee 是记忆/检索层；Agented 可以*使用*其中之一作为它的
捕获基底。两个拥有真正自我修改故事的系统 — **Letta**（通过工具进行自我
编辑的记忆）与 **Hermes Agent**（`skill_manage`，自主技能生成） — 才是
真正的比较点，而其对比就在于那道*门*。

| 维度 | **Agented 自我改进 harness** | Letta / MemGPT | Hermes Agent | Mastra | Zep / Graphiti | Mem0 | Cognee |
|---|---|---|---|---|---|---|---|
| 主要问题 | 自我改进循环 | 记忆 (LLM-as-OS) | 基于文件的 harness 状态 + 技能生成 | 记忆层 | 双时态 (bi-temporal) KG 记忆 | 混合记忆 | RAG-to-graph |
| 证据流 | **两条，不对称** (失败分类 + 正向要点) | 一条 (正向) | 一条 (正向) | 一条 | 一条 | 一条 | 一条 |
| 自我修改 | **提出的 diff** (沙箱中的 Codex) | 内联，智能体通过工具编辑记忆 | 智能体把新技能写入磁盘 | 不适用 (存储) | 不适用 | 不适用 | 不适用 |
| 应用前评分 | **eval 门** (静态 + 重放裁决 → 评分裁决) | 无 | 无 | 不适用 | 不适用 | 不适用 | 不适用 |
| 批准模型 | **操作员批准，或受策略约束的自主 (9 道门)** | 自主 | 自主 | 不适用 | 不适用 | 不适用 | 不适用 |
| 落盘形态 | **每轮 1 次 git 提交** (`.claude/`) | 记忆行 | 文件 | 存储行 | 图谱 | 存储 | 图谱 |
| 回退 | **before-image 日志 + git revert，冲突感知** | — | — | — | 双时态 (历史视图) | — | — |
| 跨项目传播 | **指纹 → 衰减证据 → 全局晋升 → 采纳** | — | — | — | — | — | — |
| 信念的来源 | **直到源会话的行链，无嵌入猜测** | 工具编辑历史 | 文件历史 | 存储元数据 | 双时态边 | 抽取日志 | 图谱谱系 |
| 威胁模型姿态 | 默认「提案 → 批准」；删除被阻止；绕过 = 分数 0 | 内联编辑 = 内联风险 | **`skill_manage` = 下载的依赖** | 仅存储 | 仅存储 | 仅存储 | 仅存储 |

### 直白地说

- **vs. Letta / MemGPT** — Letta 开创了自我编辑记忆；智能体通过工具调用，
  在进程内、未经审阅地重写自己的核心/归档记忆。我们刻意选择了**提案-审阅**
  变体：模型发出一个 *diff*，eval 门对其*评分*，操作员（或一条受限策略）
  批准它。在一个公开技能中有 36.8% 带有安全缺陷的世界里（Snyk ToxicSkills），
  落地前的 diff 并非锦上添花。我们并不主张内联编辑是*错的* — 我们主张任何
  受监管的部署都将加上这道门，而从第一天就围绕它设计，比日后改造更便宜。
- **vs. Hermes Agent** — Hermes 的 `skill_manage` 让智能体自主地把技能著述到
  磁盘。从结构上说，*一个通过写技能来学习的智能体已经下载了一个依赖。*
  我们的技能路径默认由操作员批准（`AGENTED_TAKEAWAY_AUTOAPPLY` 选择加入），
  并被写入一个**独立的、被 gitignore 的 `.agented-takeaways/` 目录**，
  使其与操作员策划的技能之间的 diff 只在一次 `git status` 之遥，而且每一个
  被应用的技能都反向指向它的要点 + 会话 + 置信度。
- **vs. Mastra / Mem0 / Cognee** — 纯粹的记忆/检索层。它们赢下 LongMemEval；
  那在召回维度上确实是出色的工程。它们没有提案/评分/应用/回退/传播的循环，
  因为那并非它们的问题。Agented 可以坐在它们任何一个之*上*。
- **vs. Zep / Graphiti** — 在*某一个*维度上精神最接近：Graphiti 的双时态
  图谱同时追踪事件时间与摄入时间，这是为**记忆**层提供的真实来源基础设施。
  我们用 Tesserae（带类型、离线编译、在线查询）来做类似的工作，但我们的
  双时态等价物处于*harness 演化*层：一个轮次的应用日志 + git 历史精确记录了
  harness 在何时相信了什么，并让你能够回退它。
- **vs. Life-Harness 论文** ([arXiv 2605.22166](https://arxiv.org/abs/2605.22166))
  — 我们采用它的四层失败分类体系（H2/H3/H4/通用）作为*失败*证据流，并将其
  一般化：论文对出了什么错进行分类，我们则把那种分类接入一个据此行动的
  锻造-评分循环，将其与一条正向证据流配对，并使由此产生的每一处变更都可回退
  且可传播。

---

## 5. 一句话版本

记忆领域正在竞相准确地召回事实；我们构建了那一层 — 它从这些事实中
**决定 harness 应当成为什么** — 并使那个决定*被评分、被批准、可回退、
可传播、并端到端可审计*，因为就在一个智能体通过把指令写入磁盘来改进自身的
那一刻，这些属性中的每一个都不再是可选的。

---

## 源代码映射（上述每一条主张都是树中的一个符号）

| 阶段 | 代码 |
|---|---|
| 捕获 | `app/services/harness_snapshot_service.py`, `app/db/session_events.py`, `harness_snapshots` |
| 标注 | `app/services/harness_failure_annotator.py` (`detect_h2/h3/h4`, `_apply_priority_protocol`), `harness_annotations` |
| 抽取 | `app/services/harness_takeaway_extractor.py`, `harness_takeaways` (`tk-*`) |
| 汇集 | `app/services/harness_evolver.py::gather_inputs`, `app/services/harness_kg_signals.py::gather_kg_signals` |
| 提案 | `harness_evolver.py` (`build_workspace`, `_run_codex_in_workspace`, `parse_patch`, `validate_patch`) |
| 评估门 | `app/services/harness_evolution_eval.py` (`evaluate_patch`, `_static_checks`, `_run_judge`, `_verdict`), `app/models/harness_evolution.py` 中的 `EvalVerdict` |
| 应用 | `harness_evolver.py::apply_patch`; 路由位于 `app_litestar/routes/harness_evolution.py` |
| 自主 | `app/services/harness_autonomy.py` (`autonomous_apply_eligible`, `process_project_autonomy`), `app_litestar/lifecycle.py` 中的 `autonomous_apply_job`, `app/models/autonomy_policy.py`, `project_autonomy_config` |
| 物化 | `app/services/forge_materialization_service.py` |
| 回退 | `app/services/harness_evolution_rollback.py` (`revert_round`, `reverse_apply_journal`, `_git_revert`); `POST /evolution/rounds/{id}/revert` |
| 传播 | `app/services/harness_propagation.py`, `app/services/forge_fingerprint.py`, `forge_promotion` 仓库, `shared_forge_bindings`; `GET /shared-forge`, `POST /projects/{id}/adopt-shared/{sbid}` |
| KG 反馈 | `app/services/tesserae_integration.py` (`on_session_complete`, `export_sessions_to_tesserae`, `ask_tesserae`) |
| 轮次状态 | `harness_evolution_rounds` CHECK: `pending·running·evaluating·awaiting_approval·applied·eval_failed·failed·aborted·reverted` |

*该架构跨 5 个阶段交付（A 证据 · B 锻造 · C 评估+回退 · D 自主 ·
E 传播+KG 源），已于 2026-05-31 合并入 `main`。*
