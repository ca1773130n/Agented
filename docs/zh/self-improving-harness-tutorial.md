# 教程：观看 harness 自我改进（搭配 wiki 式记忆）

**语言:** [English](../self-improving-harness-tutorial.md) · [한국어](../ko/self-improving-harness-tutorial.md) · 中文 (当前)

*一份动手实操的演练。在大约 30 分钟内，你将运行几个智能体会话，观看
Agented 把它们转化为带类型的记忆，把那份记忆编译成可浏览的
**LLM-wiki**，然后观看 harness 提出、评分、应用、并（如果你愿意）回退一处
对**其自身规则**的变更 — 同时附带一条从新规则一直追溯回促成它的那个会话的
来源（provenance）链。*

> 这是两份参考文档的*实地演示*配套文档。当你想了解「为什么」和「是什么」时，
> 请阅读它们：
> - **[自我改进 harness：架构](self-improving-harness-architecture.md)** — 闭合循环，逐阶段讲解，映射到真实符号。
> - **[博客：你的智能体没有记忆问题。它有来源问题。](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.md)** — 本系统由之导出的论证。

---

## 你将对什么建立起感觉

两个截然不同的层，以及它们如何彼此喂养：

1. **wiki 式记忆** — 每一个完成的会话都被编译成一个带类型的知识图谱
   （Tesserae），并被投影为一个**可浏览的 wiki / Obsidian vault**。你像读
   wiki 一样读它；智能体像查图谱一样查它。
2. **自我改进循环** — harness 读取那份记忆外加一条失败/成功证据流，
   **对其自身原语**（规则、钩子、命令、技能、MCP 绑定）**提出一个 diff**，
   对它**评分**，作为**一次 git 提交**将它**应用**，并能够将它**回退**或
   **传播**。

你将在结尾看到的点睛之笔：循环所*产出*的图谱，正是循环所*消费*的基底
（substrate）。正是那条边使它成为一个循环，而非一条流水线。

---

## 0. 先决条件

```bash
# from the repo root
just deploy            # builds + starts backend (:20000), sidecar (:20001), frontend (:3000)
# …or, for iteration:
just dev-backend &     # :20000
just dev-frontend      # :3000
```

在 `http://localhost:3000` 打开操作员控制台。

你还需要 **Tesserae** CLI + MCP 可用（智能体记忆系统）。
确认：

```bash
tesserae --version
```

在控制台中选择（或创建）一个**项目** — Projects → New。以下所有内容都
被限定在一个项目的作用域内。

> **内部机制：** 项目、产品、团队和智能体都是带前缀 ID 的行（`proj-…`、
> `agent-…`）。后端通过 `subprocess.Popen` 驱动每一个 harness，并将输出
> SSE 流式传输到控制台。

---

## 1. 为项目打开 wiki 式记忆

在控制台中：**Settings → Memory System →** 为这个项目启用 Tesserae 并将其
指向一个工作区路径。（如果你更喜欢，等效的 SQL 为：
`UPDATE projects SET tesserae_project_root = '/abs/path' WHERE id = 'proj-…';`）

一旦启用，**每一个完成的会话都会被自动导入**这个项目的 Tesserae 工作区 —
你无需为每个会话单独接线。

> **内部机制：** `app/services/tesserae_integration.py`
> （`on_session_complete → export_sessions_to_tesserae`）。这是循环的
> **(10)** 阶段。

---

## 2. 生成一些证据（运行几个会话）

在智能体*做*了一些事情之前，循环没有任何可学习的东西。运行 3–5 个真实任务，
这样才会有信号 — 成功与失败的混合是最理想的（系统会**两者**都捕获，且是
不对称地；见第 4 步）。

从控制台启动任何正常的工作：一次触发器执行、一次超级智能体运行、一次团队
执行，或一个工作流。例如，让一个智能体去处理一个小 bug 并让它修复；然后让
另一个智能体去做一件它第一次会*做错*的事（一个过时的路径、一个缺失的环境
变量）。两者都有用。

> **内部机制：** 在**每一个**完成的会话上 — 不只是「机器人」 — 一份已解析
> harness 包的快照会与原始事件流一同被持久化（`harness_snapshot_service.py`、
> `session_events.py`）。这是 **(1) 捕获**阶段 — 来源台账的输入层。

---

## 3. 观看记忆形成：两条不对称的流

打开项目的 **Activity** 仪表盘泳道。你会看到，从你刚刚运行的会话中累积出来：

- **要点（Takeaways）**（正向信号） — 用户偏好、发现的流程、工具模式、约束、
  领域事实、根本原因、成功模式。每一条都有一个稳定的 `tk-…` ID，并反向指向
  它所源自的会话。
- **失败事件（Failure incidents）**（负向信号） — 由一套四层分类体系
  （接口 → 环境契约 → 轨迹 → 通用）进行类型化。

**不对称性正是要点**：失败需要*规则与钩子*；成功需要*技能与命令*。大多数
记忆系统只捕获一个方向，并丢失一半信号。

> **内部机制：** `harness_takeaway_extractor.py` → `harness_takeaways`
> （阶段 2，正向），以及 `harness_failure_annotator.py`
> （`detect_h2/h3/h4`） → `harness_annotations`（阶段 2，负向）。两者都从同一个
> `session_complete` 通道分叉而出。

---

## 4. 编译 wiki — 并像读 wiki 一样读你项目的记忆

这就是 **LLM-wiki** 时刻。把累积的会话、文档和代码编译成一个带类型的图谱，
然后将它投影为一个可浏览的站点：

```bash
tesserae status                 # sanity: node/edge/session counts, last compile
tesserae project compile        # extract typed graph + write vault + site artifacts
tesserae build-site             # render the static wiki
tesserae serve                  # browse it locally
```

打开被服务的站点。你现在正在读一个**你项目记忆的 wiki** — 关于代码文件、
会话、决策、要点和概念的页面，由带类型的边交叉链接。从一个会话点击到它所
产生的决策，再点击到它所触及的代码。

用自然语言向它提问（CLI 或捆绑的 MCP 工具）：

```bash
tesserae ask "what did we decide about retry/backoff?"
tesserae ask "which sessions touched the cost dashboard, and what broke?"
```

想在你的编辑器里看它？把 vault 同步进 Obsidian：

```bash
tesserae obsidian-sync
```

> **内部机制：** 图谱类型是 `CodeFile`、`Session`、`SessionTakeaway`、
> `SessionDecision`、…。MCP 表面（`tesserae_ask`、`search_facts`、
> `graph_ppr`、`wiki_page`、`find_session_findings`）正是*智能体*在任务进行
> 当中读取这同一份记忆的方式 — 见 `CLAUDE.md` 的 Tesserae 章节。在大改动后用
> `tesserae refresh` 刷新。

---

## 5. 运行一轮演化（试运行）：提案 → 评分

现在进入循环。在控制台中，打开项目的 **Harness Evolution** 卡片（Activity
泳道）并启动一轮**试运行（dry-run）**。（等效的 API：
`POST /projects/{project_id}/evolution/dry-run`。）

三件事按顺序发生，轮次的状态机走过
`pending → running → evaluating → awaiting_approval`：

1. **汇集（Gather）** — 轮次组装它的输入：当前绑定的原语、近期轨迹 + 其事件、
   近期要点，**以及从你刚刚编译的 wiki 中回查的 KG 信号**（≤3 个受限的发现性
   问题）。记忆喂养提案者。
2. **提案（Propose）** — 输入被写入一个临时工作区，**Codex 在沙箱中**针对它
   运行。它发出一个 **diff**；它绝不在进程内编辑一个活动的原语。
3. **评估门（Eval-gate）** — 在任何东西能够应用之前，补丁被评分为一个
   **`EvalVerdict`**（`passed`、`score ∈ [0,1]`、逐项检查结果）：静态检查
   （模式/前置元数据/空操作/锚点）**外加**一个回归重放裁决者，它将代表性
   会话针对*已打补丁的*原语进行重放。

卡片向你展示**提议的 diff** 和**裁决**。一道失败的门会短路 — 什么都不会落地。

> **内部机制：** `harness_evolver.py`（`gather_inputs`、`build_workspace`、
> `_run_codex_in_workspace`、`parse_patch`、`validate_patch`）、
> `harness_kg_signals.py::gather_kg_signals`，以及
> `harness_evolution_eval.py`（`evaluate_patch`、`_static_checks`、`_run_judge`、
> `_verdict`）。门的*错误*会 fail closed，并记录一个分数为 0.0 的绕过裁决 —
> 一次绕过绝不会与一次真正的通过无法区分。

---

## 6. 应用，并观看它成为一次 git 提交

对 diff 满意吗？**批准**它（轮次停在 `awaiting_approval`；批准即
`POST /evolution/rounds/{id}/apply`）。

在应用时，原语会被**物化**进项目真实的 `.claude/` 布局
（commands/rules/hooks + `settings.json`/`mcp.json`/skills），以幂等且保留
操作员改动的方式进行，并作为**每轮一次 git 提交**被提交。确认它：

```bash
git -C <project_root> log --oneline -1     # the round's materialization commit
git -C <project_root> status               # see which .claude/ primitives changed
```

harness 的演化现在就是字面意义上的 `git log`。

> **内部机制：** `forge_materialization_service.py`。轮次转变为 `applied`。

---

## 7. 追踪来源（任何记忆基准都不测量的那部分）

挑出刚刚落地的那条规则，并将它向后追溯。每一跳都是一行，带有时间戳和反向
指针：

```
a behavior
  → the RULE that produced it
    → the ROUND that forged it           (harness_evolution_rounds)
      → the EVAL VERDICT that graded it  (EvalVerdict)
        → the TAKEAWAYS / INCIDENTS      (tk-… / harness_annotations)
          → the SESSIONS they came from  (durable transcripts)
```

这条链中没有任何一环是基于对某个嵌入块的相似度打分。你可以用 ID 而非猜测来
回答「*为什么 harness 相信这一点，又是什么给它评了分?*」。这正是博客中假想的
*AuditEval* 会测试的属性。

---

## 8. 回退它

改变主意了？回退这一轮（`POST /evolution/rounds/{id}/revert`）：

```bash
# from the console's Harness Evolution card, or the API
```

回退会捕获一份 **before-image 日志**，除非轮次处于带日志的 `applied` 状态
否则拒绝执行，检测冲突（一个触及同一 `{kind, asset_id}` 的后续轮次），幂等地
逆转 DB 操作，然后 **git-revert** 物化提交。如果 git 或某个部分步骤失败，
轮次会连同一个 `revert_error` 保持在 `applied` — 它绝不*声称*自己达成了并未
达成的 `reverted`。

> **内部机制：** `harness_evolution_rollback.py`（`revert_round`、
> `reverse_apply_journal`、`_git_revert`）。

---

## 9.（可选）让它自主应用 — 在九道门之后

操作员批准是默认值。要让经过验证的变更自我应用，把一个项目选择加入自主模式
（**Settings → … → Autonomy**，或 `PUT /projects/{id}/autonomy`）。一个 5 分钟
的调度任务会*仅当* `autonomous_apply_eligible` 通过**九道硬门**时才自动应用：

1. 终止开关关闭（`AGENTED_AUTONOMY` ≠ `0`）
2. 按项目启用的策略
3. eval `passed`
4. `score ≥ confidence_threshold`（默认 **0.85**）
5. 爆炸半径 ≤ `max_ops_per_round`
6. `allowed_kinds`
7. `block_deletes`
8. `cooldown_seconds`
9. `rate_limit_per_day`

它默认关闭，并且是*操作员路径的一种受限升级*，而非一条独立的、未经审计的
代码路径。全局终止开关：

```bash
export AGENTED_AUTONOMY=0      # hard-stop all autonomous applies
```

> **内部机制：** `harness_autonomy.py`
> （`autonomous_apply_eligible`、`process_project_autonomy`）、
> `lifecycle.py` 中的 `autonomous_apply_job`、`project_autonomy_config`。

---

## 10.（可选）观看一个经验证的原语跨项目传播

在第二个项目中运行循环。一旦某个原语的内容**指纹**累积了足够多的衰减后、
**eval 通过**的晋升证据（`score ≥ PROMOTION_THRESHOLD = 3.0`），一份全局
作用域的副本就会被晋升，其他项目随之可以**采纳**它
（`POST /projects/{id}/adopt-shared/{sbid}`；local-wins 冲突策略）。只有
`rule`、`hook`、`command` 会传播，并且只有 eval 通过的轮次才贡献证据 —
任何强制应用都无法污染共享层。

> **内部机制：** `harness_propagation.py`、`forge_fingerprint.py`、
> `shared_forge_bindings`；`GET /shared-forge`。

---

## 循环闭合了

重新运行 `tesserae project compile`。*正是这次演练*中的会话 — 包括那些演化
轮次 — 现在已成为 wiki 中的节点。下一次试运行的**汇集**步骤（5.1）将会查询
它们。循环所产出的图谱现在为循环播种。

```
 sessions ──► takeaways + incidents ──► gather (KG-seeded) ──► propose (Codex)
     ▲                                                              │
     │                                                              ▼
  KG feedback ◄── git commit ◄── materialize ◄── apply ◄── eval-gate (scored)
 (Tesserae wiki)                                  │
                                                  └─ revert / propagate
```

---

## 故障排查 & 各部分所在位置

| 症状 | 查看此处 |
|---|---|
| 会话后没有要点/事件 | 确认会话*已完成*；检查 Activity 泳道；`harness_takeaways` / `harness_annotations` 行 |
| wiki 为空 / 陈旧 | `tesserae status`，然后 `tesserae project compile`（或 `tesserae refresh`） |
| 试运行什么都不提议 | 需要近期证据；运行更多会话。一个空操作会被 `_static_checks` 抓到 |
| 轮次卡在 `awaiting_approval` | 那就是门 — 批准它，或启用自主（§9） |
| 轮次无法回退 | 只有带日志的 `applied` 轮次才能回退；检查是否有冲突的后续轮次 |
| 自主从不触发 | 走一遍九道门（§9）；确认 `AGENTED_AUTONOMY` ≠ `0` 且 `score ≥ 0.85` |

完整的符号映射：[架构文档](self-improving-harness-architecture.md#source-map-every-claim-above-is-a-symbol-in-the-tree)中的 **Source map** 表。

---

## 下一步

- 阅读**[架构](self-improving-harness-architecture.md)**，了解与 Letta/MemGPT、
  Hermes Agent、Mastra、Zep/Graphiti、Mem0、Cognee 的诚实比较。
- 把 Tesserae MCP 工具接入你的智能体，让它们在任务进行当中*查询* wiki，而不是
  重新推导 — `tesserae_ask`、`find_session_findings`、`graph_ppr`、`wiki_page`。
- 为一个低风险项目打开自主，观看一周的 `git log` 自我书写 — 每一次提交都可
  回退，每一个信念都可追溯到一个会话。
