<div align="center">

# Agented

**用于运营虚拟创业公司的元harness工程平台，由自主 AI 智能体驱动。**

Agented 将 AI harness 工程的前沿技术 —— 循环工程、智能体编排、蜂群、自我改进、
自动研究、持久记忆 —— 汇集到一个以产品和项目为中心的操作员控制台中。可以把它想象成
Hermes 风格的智能体系统，但更为宽广，并且拥有一个用于**运营一家公司**的 WebUI，
而不仅仅是与模型对话。

[架构](docs/zh/self-improving-harness-architecture.md) · [教程](docs/self-improving-harness-tutorial.md) · [更新日志](CHANGELOG.md) · [安全](docs/SECURITY.md) · [部署](docs/deploy.md)

**以其他语言阅读:** [English](README.md) · [한국어](README.ko.md) · [日本語](README.ja.md)

</div>

---

## Agented 是什么

如何从 AI 智能体那里获得实质且持续的产出，正在**此刻** —— 在大会演讲、博客文章，
以及构建 harness 的人们的工作笔记中 —— 被摸索出来。Agented 的主张是：这些想法不应
散落在一次性脚本和私人装置里。它将这些想法汇聚成单一的**元harness层**，置于编码
CLI（Claude Code、Codex、Gemini CLI、OpenCode 等）之上，并把它们变成一家
**虚拟创业公司**的员工 —— 以**产品与项目**为中心组织，从一个控制台运营。

它仍处于**早期阶段，且发展迅速**。已经实现的部分:

- **🔁 循环工程** —— 一个 `LoopSpec` 模式和单一执行器驱动所有循环模式
  （goal-loop、Ralph）：退出阶梯（质量门 → 停滞 → 收敛 → 预算）、逐次迭代的
  检查点、恢复、以及人工闸门。
  → [架构](docs/zh/self-improving-harness-architecture.md)
- **🎛 智能体编排** —— 将**产品 → 项目 → 团队 → 智能体**作为一等模型，从一个
  仪表盘协调，每次运行都由项目级上下文、账号与原语组合而成。
- **🐝 跨多个 AI 账号的蜂群** —— （通过 `ai-accounts` 边车）在多个提供商账号之间
  调度与交接工作，并**自动路由**到正确的后端与模型。
- **♻️ 自我改进** —— 一个由评估门控、可用 git 回退的 “life-harness” 循环，用于
  演化 harness 自身的原语。
- **🔬 自动研究** —— GRD 引擎将研究 → 规划 → 执行 → 验证作为一条自主的、按里程碑
  规划的流水线来运行。
- **🧠 持久记忆 + LLM 维基** —— Tesserae 编译代码、文档与会话历史的类型化知识图谱
  （以及生成的维基页面），为每一次检索提供依据。
- **⏳ 长时程智能体** —— 持久的逐次运行状态、增量检查点与 `--resume`，使一次运行
  能够在崩溃后存续并跨越数天。
- **📊 可观测性** —— 实时 SSE 轨迹、会话事件、审计追踪，以及智能体所做一切的
  每日/每周**活动摘要**。
- **🧩 harness 共享与组合** —— 在 Forge 中组织**原语**（技能、钩子、命令、规则、
  子智能体）来构建 harness，并通过插件市场共享。
- **📦 产品与项目管理** —— 竞争对手监控、发现与策略制定；项目规划；以及每个项目的
  **一键团队-harness 设置**。
- **🛡 治理与安全** —— 可堆叠的策略引擎、默认拒绝出站的 OS 级沙箱、实时多用户协作。

在底层，智能体的每一个动作都会被检查点记录、归因到来源、受预算管控且可验证 ——
**来源可溯、可审计、可回滚是设计之内，而非事后附加**。

## 快速开始

```bash
# 全新机器 —— 自动安装 just、uv 和 Node.js，然后安装所有依赖（可安全重复运行）
bash scripts/setup.sh

# 已经具备前置条件？
just setup        # 安装所有依赖
just dev-all      # 后端 :20000 + 边车 :20001 + 前端 :3000
```

在 **http://localhost:3000** 打开控制台。交互式 API 文档（Swagger UI）位于
**http://localhost:20000/schema**。可用 `just dev-backend`、`just dev-frontend`、
`just dev-ai-accounts` 分别运行各部分。

### 部署预构建镜像

**推荐 —— 先克隆并检查**（先读代码，*再*运行）:

```bash
git clone https://github.com/ca1773130n/Agented && cd Agented
./install.sh                 # 拉取预构建镜像 + 启动整个栈
```

`install.sh` 复用随它一起克隆的 `docker-compose.yml`，因此不会有未经查看即被拉取
并执行的代码。

<details>
<summary>便捷单行命令（安全性较低）</summary>

将远程脚本管道到 shell 会执行你尚未阅读的代码。仅在固定到**不可变的发布标签**时
才这样做 —— 届时安装程序会用 SHA-256 校验其下载的 compose 文件，不匹配则中止:

```bash
curl -fsSL https://raw.githubusercontent.com/ca1773130n/Agented/v0.10.0/install.sh | bash
```

除非显式设置 `AGENTED_INSTALL_UNVERIFIED=1`（这会跳过校验和验证并打印安全警告），
否则将拒绝从可变的 `main` 分支获取。参见
[docs/deploy.md](docs/deploy.md#2-single-install-script)。
</details>

```bash
# 用一条命令更新现有安装（镜像即更新单位）
just self-update
```

上方的 **Deploy to Render** 徽章会打开 Blueprint 指南（web + 边车 + 连接到
`DATABASE_URL` 的托管 Postgres）。从这个独立仓库并**非**一键完成：镜像构建需要同级的
`ai-accounts/` 目录，因此 Render 必须连接一个同时包含 `Agented/` 与 `ai-accounts/`
的**父级 monorepo**（根目录含 `render.yaml`）。包含可选 Postgres 方案的完整设置见
**[docs/deploy.md](docs/deploy.md)**。

> **首次运行:** **第一个**注册的账号将成为管理员。完成注册后 —— 并且务必在将实例
> 暴露到不受信任的网络之前 —— 请设置 `AGENTED_DISABLE_SIGNUP=1`。

## 各部分如何协作

产品与项目是模型的顶层；团队与智能体负责工作；循环、记忆、策略与原语是每次运行所
调用的机制。**触发器**（webhook、GitHub 事件、计划任务或手动运行）只是交付机制 ——
产品是它们启动的自主智能体工作流本身。

| 层 | 技术栈 | 端口 |
|---|---|---|
| **后端** | Litestar (gunicorn / UvicornWorker)，原生 SQLite（实验性 Postgres），subprocess + SSE | `:20000` |
| **前端** | Vue 3 + TypeScript 操作员控制台 | `:3000` |
| **边车** | `ai-accounts` —— AI 后端身份、凭据与登录流程 | `:20001` |
| **记忆** | Tesserae 类型化知识图谱 + CodeGraph 符号索引 | — |

## 配置

| 变量 | 说明 | 默认值 |
|---|---|---|
| `AGENTED_DISABLE_SIGNUP` | 关闭开放的自助注册（首个管理员注册后设置） | 未设置（开放） |
| `DATABASE_URL` | 使用实验性 PG 适配器的 Postgres URL（未设置 ⇒ SQLite） | 未设置 (SQLite) |
| `AGENTED_SANDBOX` | 启用 OS 级 harness 沙箱（bwrap / seatbelt） | 未设置（关闭） |
| `AI_ACCOUNTS_API_KEY` | `ai-accounts` 边车的令牌 | 复用管理员密钥 |

完整的环境变量参考与约定见 [CLAUDE.md](CLAUDE.md)。

## 验证

发布前应通过全部三个门:

```bash
just build                       # vue-tsc 类型检查 + vite 构建
cd backend && uv run pytest      # 后端测试套件
cd frontend && npm run test:run  # 前端测试套件
```

## 文档

| 主题 | 链接 |
|---|---|
| 更新日志 | [CHANGELOG.md](CHANGELOG.md) |
| 自我改进 harness —— 架构 | [docs/zh/self-improving-harness-architecture.md](docs/zh/self-improving-harness-architecture.md) |
| 部署 —— Render Blueprint / 安装 / 自更新 | [docs/deploy.md](docs/deploy.md) |
| 安全 | [docs/SECURITY.md](docs/SECURITY.md) |
| ai-accounts 边车 | [docs/ai-accounts/ARCHITECTURE.md](docs/ai-accounts/ARCHITECTURE.md) |
| 国际化(i18n) | [docs/i18n.md](docs/i18n.md) |

<div align="center"><sub>为一人创业公司 —— 以及随后而来的团队 —— 而生的 harness 工程。</sub></div>
