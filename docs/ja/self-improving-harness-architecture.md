# 自己改善ハーネス: アーキテクチャ

**言語:** [English](/self-improving-harness-architecture) · [한국어](/ko/self-improving-harness-architecture) · 日本語 (現在) · [中文](/zh/self-improving-harness-architecture)

*[BLOG-self-improving-harness.md](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.md) の補足ドキュメント。
ブログは、エージェントメモリ分野が誤った軸（想起精度）を最適化しており、
プロダクションで本当に重要な軸（来歴（provenance） + 監査可能性）を
見落としていると論じている。本ドキュメントは、その問題を真剣に受け止めた
ときに導かれるシステム — メモリストアではなく、閉じた**自己改善ループ
（self-improvement loop）** — を説明し、ブログが言及するメモリアーキテクチャ
と正直に比較する。*

---

## 1. 我々が解いたのはメモリの問題ではない

ブログが挙げるすべてのシステム — Mastra、Letta/MemGPT、Zep/Graphiti、Mem0、
Cognee、Hermes Agent — は**メモリアーキテクチャ**である。その役割は、会話の
ストリームが与えられたときに事実を*保持*し、後にプレッシャー下で*想起*する
ことだ。ベンチマークは LongMemEval であり、軸は検索精度である。

Agented の自己改善ハーネスは、その一層上に位置する。メモリは基盤
（substrate）であって、成果物ではない。成果物は、異なる問いを発するループだ:

> エージェントが複数のセッションにわたって行ったすべてを踏まえて、
> **ハーネス自身がどう変わるべきか** — そのルール（rule）、フック（hook）、
> コマンド（command）、スキル（skill）、MCP バインディング — そしてその変更を、
> 人間が手作業でプリミティブを編集することなく、*監査チェーンを失うことなく*
> 採点し、承認し、巻き戻し、伝播させられるか?

これは**自己改善**の問題（自分の動作コンテキストを変異させる）であって、
**メモリ**の問題（言われたことを想起する）ではない。両者は日常的に
混同される。これらは異なるものであり、二番目のほうが難しい。「デプロイ
スクリプトが移動した」を想起するメモリシステムは、それをルールに変える
人間を依然として必要とする。自己改善ハーネスはその隙間を閉じる — そして
その瞬間、純粋な想起システムが決して直面しないセキュリティと監査の負担を
引き受ける: いまやそれは自身の推論にもとづいて*実行可能な指示をディスクに
書き込んでいる*のだ。

我々のアーキテクチャ全体は、その書き込みを、採点ゲート、承認（オペレーター
またはポリシーで制限された自律）、ロールバックジャーナル、そして
エンドツーエンドの来歴（provenance）なしには起こさせないと拒むことに
よって形作られている。

---

## 2. 閉じたループ

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

番号が振られた各ステージは、コードベース内の実在する監査可能なアーティ
ファクトである。このループは自由に走るのではなく、**ゲートで制御される**:
来歴を記録する明示的な境界を越えなければ、いかなるプリミティブも変異せず、
ディスクに着地せず、伝播しない。

### (1) キャプチャ — `harness_snapshot_service.py`, `session_events.py`
完了したすべてのセッションごとに（*すべての*セッション種別にわたって —
トリガー実行、スーパーエージェント実行、チーム実行、ワークフロー。決して
「ボット」だけではない）、解決済みハーネスバンドルの**スナップショット**が
生のセッションイベントストリームとともに永続化される。これが来歴台帳
（ledger）の入力レイヤーだ。ブログの「12 の静かな失敗」の幕間は、まさに
このレイヤーが下流で嘘をつかないようにすることに関する話である — すべての
フェッチャー（fetcher）/パーサー（parser）は、信頼される前に実プロダクション
の行 ≥3 に対してドッグフーディングされる。

### (2) 注釈 + 抽出 — 二つの非対称な証拠ストリーム
どちらも同じ `session_complete` チャネルから分岐する:

- **失敗アノテーター（failure annotator）**（`harness_failure_annotator.py`）は
  **Life-Harness 四層分類体系** — `detect_h2`（インターフェース） →
  `detect_h3`（環境契約） → `detect_h4`（軌道規制） → 一般 — を、
  `_apply_priority_protocol` で順序付けて実行し、型付けされたインシデントを
  `harness_annotations` に書き込む。
- **テイクアウェイ抽出器（takeaway extractor）**
  （`harness_takeaway_extractor.py`、ヒューリスティック + provider-kind LLM）は
  *肯定的*シグナル — ユーザーの好み、発見された手順、ツールパターン、制約、
  ドメイン事実、根本原因、成功パターン — を `harness_takeaways` に表面化する
  （安定した `tk-*` ID、`session_kind`/`session_id` の逆ポインタ、抽出器
  バージョン、信頼度を伴う）。

**非対称性こそが要点だ**: 失敗はルールとフックを求め、成功はスキルと
コマンドを求める。ほとんどのメモリシステムは一方向（通常は肯定）だけを
捉え、シグナルの半分を静かに失う。

### (3) 収集（Gather） — `harness_evolver.gather_inputs`
進化ラウンドの入力を組み立てる: プロジェクトに現在バインドされている Forge
プリミティブ、最近の軌道（スナップショット + その注釈 + インシデント）、
最近のテイクアウェイ、**そして** — 最後のループのエッジ — コンパイル済み
Tesserae グラフから得られる **KG シグナル**（`gather_kg_signals`、≤3 個の
制限された `ask_tesserae` 発見質問、重み付け・重複排除され、Tesserae 無効の
プロジェクトはコストゼロになるようゲートされている）。ループが*生み出す*
グラフ（ステージ 10）が、いまやループに*種を供給する*（ステージ 3）。これが、
これをパイプラインではなくループにするものだ。

### (4) 提案（Propose） — サンドボックス化されたスクラッチワークスペース内の Codex
`build_workspace` は入力を一時ディレクトリ（`forge/`、`trajectories/`、
`takeaways/`、`KG_SIGNALS.md`、`tesserae_context.md`）に書き込む;
`codex exec --sandbox workspace-write` がそれに対して走る; 結果のパッチが
パースされ、スキーマ検証される。**モデルは diff を提案する; ライブの
プリミティブをインプロセスで編集することは決してない。**

### (5) 評価ゲート（Eval-gate） — `harness_evolution_eval.py`
いかなる適用（apply）の前にも、パッチは **`EvalVerdict`**（`passed: bool`、
`score: float ∈ [0,1]`、`per_check: [CheckResult]`）に採点される:

- **静的検査（static checks）**（`_static_checks`） — 機械的: スキーマ妥当性、
  フロントマター健全性、無動作（no-op）検出、行アンカー（line-anchored）
  ガード。
- **回帰リプレイ判定者（regression-replay judge）**（`_run_judge`、
  `resolve_llm_cmd` 経由の provider-kind） — 代表的なセッションサンプルを
  *パッチされた*プリミティブ集合に対してリプレイし、挙動が退行したかを
  判定者に問う。

`_verdict` は、パッチが通過しないときにスコアを信頼下限（trust floor）の
下に抑える。失敗したゲート（`eval_failed`）は適用を短絡させる。ゲートの
*エラー*は fail-open だが、**スコア 0.0 のバイパス（bypass）判定**を記録する
ので、バイパスが実際の通過と静かに区別不能になることは決してない。これが、
あらゆる「自己編集メモリ」システムに欠けている採点レイヤーである。

### (6) 適用（Apply） — オペレーター承認**または**ポリシー自律
ラウンドの状態機械
（`pending → running → evaluating → awaiting_approval → applied`、および
`eval_failed`/`failed`/`aborted`/`reverted` の出口）は、**同一の**機構に
対して二つの適用経路をサポートする:

- **オペレーター**: ドライランのラウンドが `awaiting_approval` に留まり、
  オペレーターが diff をレビューして `POST /evolution/rounds/{id}/apply`。
- **自律**（`harness_autonomy.py`）: 5 分周期のスケジューラジョブ
  （`autonomous_apply_job` → `process_project_autonomy`）が、
  `autonomous_apply_eligible` が**九つのハードゲート**を通過したとき*のみ*
  自動適用する — キルスイッチ（`AGENTED_AUTONOMY=0`）、プロジェクト別
  ポリシー有効化、eval `passed` **かつ** `score ≥ confidence_threshold`
  （デフォルト 0.85）、ブラスト半径 ≤ `max_ops_per_round`、`allowed_kinds`、
  `block_deletes`、`cooldown_seconds`、`rate_limit_per_day`。デフォルトは
  オフで、プロジェクト別のオプトイン（`project_autonomy_config`）。

自律は、オペレーター経路の*制限された*エスカレーションであって、別個の
監査されないコード経路ではない。

### (7) 具現化（Materialize） — `forge_materialization_service.py`
適用されたプリミティブは、プロジェクトの実際の `.claude/` レイアウト
（commands/rules/hooks + `settings.json`/`mcp.json`/skills）へ、冪等かつ
オペレーター保存的に投影され、**ラウンドごとに一つの git コミット**として
コミットされる。ハーネスの進化はいまや `git log` である。

### (8) ロールバック（Rollback） — `harness_evolution_rollback.py`
`apply_patch` は **before-image の適用ジャーナル（apply-journal）**を捕捉する。
`revert_round` は、ラウンドがジャーナルを伴う `applied` 状態でなければ拒否し、
衝突（同一の `{kind, asset_id}` に触れた後続ラウンド）を検出し、DB 操作を
冪等に逆行させてから、具現化コミットを git revert する。部分失敗または git
失敗は、ラウンドを `revert_error` とともに `applied` のまま残す — 達成して
いない `reverted` を*主張する*ことは決してない。これがブログの
「AuditEval Rollback 軸」の実装である。

### (9) 伝播（Propagate） — `harness_propagation.py`
コンテンツ**フィンガープリント**（`forge_fingerprint.py`、コンテンツ
フィールドの sha256）が、プリミティブにプロジェクト横断のアイデンティティを
与える。適用され、**eval-PASSED** された各ラウンドは減衰した昇格証拠を
記録し、あるフィンガープリントの時間減衰スコアが
`PROMOTION_THRESHOLD = 3.0` を超えると、**グローバルスコープのコピー**が
昇格され（`shared_forge_bindings`）、他のプロジェクトがそれを採用する
（`adopt_shared_binding`、local-wins 衝突ポリシー）。`_PROPAGATABLE = (rule,
hook, command)`。eval 通過ラウンドのみが証拠に寄与する — いかなる強制適用も
共有レイヤーを汚染できない。

### (10) KG フィードバック — `tesserae_integration.py`
完了したすべてのセッションは、プロジェクトの Tesserae ワークスペースへ
自動インポートされる（`on_session_complete` → `export_sessions_to_tesserae`）;
オペレーターは型付けされた知識グラフ（`CodeFile`、`Session`、
`SessionTakeaway`、`SessionDecision`、…）をコンパイルする。そのグラフが、
ステージ (3) が問い合わせる基盤である — ループを閉じる。

---

## 3. 何がこれを監査可能にするのか（通底線）

各ステージは、タイムスタンプと逆ポインタを伴う行（row）を放出する:

- ある挙動 → それを生み出した**ルール** → それを鍛えた**ラウンド** →
  それを採点した **eval 判定** → それを動機づけた**テイクアウェイ/
  インシデント** → それらが抽出された**セッション** → 永続的な
  トランスクリプト。
- 学習されたヒューリスティックは ID で**巻き戻す（revert）**ことができ、
  それが由来したセッションとテイクアウェイは依然として問い合わせ可能だ。
- 昇格されたプリミティブは、自身の**フィンガープリント**と、閾値を超えた
  証拠を携える。

このチェーンのいずれも、埋め込みブロブに対する類似度で採点されてはいない。
これが、いかなるメモリベンチマークも測定せず、ブログが仮定した *AuditEval*
が測定するであろう属性だ。

---

## 4. ブログが言及するアーキテクチャとの比較

正直な枠組み: **これらのほとんどは競合ではない — 異なる軸で動作する。**
Mastra/Zep/Mem0/Cognee はメモリ/検索の層であり、Agented はそのうちの一つを
自身のキャプチャ基盤として*使う*こともできる。真の自己変形のストーリーを
持つ二つのシステム — **Letta**（ツールを通じた自己編集メモリ）と
**Hermes Agent**（`skill_manage`、自律的スキル生成） — が実際の比較点であり、
その対比は*ゲート*である。

| 軸 | **Agented 自己改善ハーネス** | Letta / MemGPT | Hermes Agent | Mastra | Zep / Graphiti | Mem0 | Cognee |
|---|---|---|---|---|---|---|---|
| 主要な問題 | 自己改善ループ | メモリ (LLM-as-OS) | ファイルベースのハーネス状態 + スキル生成 | メモリ層 | バイテンポラル (bi-temporal) KG メモリ | ハイブリッドメモリ | RAG-to-graph |
| 証拠ストリーム | **二つ、非対称** (失敗分類 + 肯定テイクアウェイ) | 一つ (肯定) | 一つ (肯定) | 一つ | 一つ | 一つ | 一つ |
| 自己変形 | **提案された diff** (サンドボックス Codex) | インライン、エージェントがツールでメモリ編集 | エージェントが新スキルをディスクに書き込む | 該当なし (ストア) | 該当なし | 該当なし | 該当なし |
| 適用前の採点 | **eval ゲート** (静的 + リプレイ判定 → 採点された判定) | なし | なし | 該当なし | 該当なし | 該当なし | 該当なし |
| 承認モデル | **オペレーター承認、またはポリシーで制限された自律 (9 ゲート)** | 自律 | 自律 | 該当なし | 該当なし | 該当なし | 該当なし |
| ディスク着地の形 | **ラウンドごとに 1 git コミット** (`.claude/`) | メモリ行 | ファイル | ストア行 | グラフ | ストア | グラフ |
| ロールバック | **before-image ジャーナル + git revert、衝突認識** | — | — | — | バイテンポラル (履歴ビュー) | — | — |
| プロジェクト横断の伝播 | **フィンガープリント → 減衰証拠 → グローバル昇格 → 採用** | — | — | — | — | — | — |
| 信念の来歴 | **ソースセッションまでの行チェーン、埋め込み推測なし** | ツール編集履歴 | ファイル履歴 | ストアメタデータ | バイテンポラルエッジ | 抽出ログ | グラフ系譜 |
| 脅威モデルの姿勢 | デフォルトで「提案 → 承認」; 削除はブロック; バイパス = スコア 0 | インライン編集 = インラインリスク | **`skill_manage` = ダウンロードされた依存性** | ストアのみ | ストアのみ | ストアのみ | ストアのみ |

### はっきり述べると

- **vs. Letta / MemGPT** — Letta は自己編集メモリを切り拓いた; エージェントが
  ツール呼び出しを通じて、自身のコア/アーカイバルメモリをインプロセスで、
  レビューなしに書き換える。我々は意図的に**提案レビュー**の変種を取った:
  モデルが *diff* を放出し、eval ゲートがそれを*採点*し、オペレーター
  （または制限されたポリシー）が承認する。公開スキルの 36.8% がセキュリティ
  欠陥を持つ世界（Snyk ToxicSkills）において、着地前の diff は気の利いた
  飾りではない。我々はインライン編集が*間違っている*とは主張しない — どんな
  規制された配備もこのゲートを追加するであろうこと、そして初日からそれを
  中心に設計するほうが後付けより安いことを主張する。
- **vs. Hermes Agent** — Hermes の `skill_manage` は、エージェントが自律的に
  スキルをディスクへ著述することを可能にする。構造的に言えば、*スキルを
  書くことで学習するエージェントは依存性をダウンロードしたのだ。* 我々の
  スキル経路はデフォルトでオペレーター承認であり（`AGENTED_TAKEAWAY_AUTOAPPLY`
  でオプトイン）、オペレーターがキュレートしたスキルとの diff が
  `git status` 一回の距離にあるよう、**別個の gitignore された
  `.agented-takeaways/` ディレクトリ**に書き込まれ、適用されたすべての
  スキルは自身のテイクアウェイ + セッション + 信頼度へ逆ポイントする。
- **vs. Mastra / Mem0 / Cognee** — 純粋なメモリ/検索の層。これらは
  LongMemEval に勝つ; それは想起軸における正真正銘の優れたエンジニアリング
  だ。これらには提案/採点/適用/ロールバック/伝播のループがないが、それは
  彼らの問題ではないからだ。Agented はそのいずれの*上*にも座れる。
- **vs. Zep / Graphiti** — *一つの*軸で精神的に最も近い:
  Graphiti のバイテンポラルグラフはイベント時刻と取り込み時刻の両方を
  追跡し、これは**メモリ**層のための実際の来歴インフラだ。我々は類似の
  仕事のために Tesserae（型付き、オフラインコンパイル、オンライン問い合わせ）
  を使うが、我々のバイテンポラル等価物は*ハーネス進化*の層にある:
  ラウンドの適用ジャーナル + git 履歴が、ハーネスが何をいつ信じたかを正確に
  記録し、それを巻き戻させてくれる。
- **vs. Life-Harness 論文** ([arXiv 2605.22166](https://arxiv.org/abs/2605.22166))
  — 我々はその四層失敗分類体系（H2/H3/H4/一般）を*失敗*証拠ストリームとして
  採用し、一般化する: 論文は何が間違ったかを分類し、我々はその分類を、それに
  応じて行動する鍛造採点ループに配線し、肯定証拠ストリームと組み合わせ、
  結果として生じるすべての変更を巻き戻し可能かつ伝播可能にする。

---

## 5. 一文版

メモリ分野は事実を正確に想起しようと競走している; 我々はそれらの事実から
**ハーネスが何になるべきかを決定する**層を作った — そしてその決定を、
*採点され、承認され、巻き戻し可能で、伝播可能で、エンドツーエンドで監査
可能*にした。なぜなら、エージェントがディスクに指示を書くことで自身を改善
する瞬間、それらの属性の一つ一つが任意であることをやめるからだ。

---

## ソースマップ（上記のすべての主張はツリー内のシンボルである）

| ステージ | コード |
|---|---|
| キャプチャ | `app/services/harness_snapshot_service.py`, `app/db/session_events.py`, `harness_snapshots` |
| 注釈 | `app/services/harness_failure_annotator.py` (`detect_h2/h3/h4`, `_apply_priority_protocol`), `harness_annotations` |
| 抽出 | `app/services/harness_takeaway_extractor.py`, `harness_takeaways` (`tk-*`) |
| 収集 | `app/services/harness_evolver.py::gather_inputs`, `app/services/harness_kg_signals.py::gather_kg_signals` |
| 提案 | `harness_evolver.py` (`build_workspace`, `_run_codex_in_workspace`, `parse_patch`, `validate_patch`) |
| 評価ゲート | `app/services/harness_evolution_eval.py` (`evaluate_patch`, `_static_checks`, `_run_judge`, `_verdict`), `app/models/harness_evolution.py` の `EvalVerdict` |
| 適用 | `harness_evolver.py::apply_patch`; ルートは `app_litestar/routes/harness_evolution.py` |
| 自律 | `app/services/harness_autonomy.py` (`autonomous_apply_eligible`, `process_project_autonomy`), `app_litestar/lifecycle.py` の `autonomous_apply_job`, `app/models/autonomy_policy.py`, `project_autonomy_config` |
| 具現化 | `app/services/forge_materialization_service.py` |
| ロールバック | `app/services/harness_evolution_rollback.py` (`revert_round`, `reverse_apply_journal`, `_git_revert`); `POST /evolution/rounds/{id}/revert` |
| 伝播 | `app/services/harness_propagation.py`, `app/services/forge_fingerprint.py`, `forge_promotion` リポ, `shared_forge_bindings`; `GET /shared-forge`, `POST /projects/{id}/adopt-shared/{sbid}` |
| KG フィードバック | `app/services/tesserae_integration.py` (`on_session_complete`, `export_sessions_to_tesserae`, `ask_tesserae`) |
| ラウンド状態 | `harness_evolution_rounds` CHECK: `pending·running·evaluating·awaiting_approval·applied·eval_failed·failed·aborted·reverted` |

*5 つのフェーズにわたって提供されたアーキテクチャ（A 証拠 · B 鍛造 ·
C 評価+ロールバック · D 自律 · E 伝播+KG ソース）、2026-05-31 に `main` へ
マージ済み。*
