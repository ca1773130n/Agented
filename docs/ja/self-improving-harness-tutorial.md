# チュートリアル: ハーネスが自己改善する様子を見る（ウィキ型メモリとともに）

**言語:** [English](../self-improving-harness-tutorial.md) · [한국어](../ko/self-improving-harness-tutorial.md) · 日本語 (現在)

*手を動かすウォークスルーである。約 30 分で、エージェントセッションをいくつか
実行し、Agented がそれを型付けされたメモリへ変える様子を見て、そのメモリを
探索可能な **LLM-ウィキ**へコンパイルし、続いてハーネスが**自身のルール**への
変更を提案・採点・適用し、（望むなら）巻き戻す様子を — 新しいルールから、それを
動機づけたセッションまで遡る来歴（provenance）チェーンとともに — 見ることになる。*

> これは二つのリファレンスドキュメントに対する *実演で見せる* 同伴ドキュメント
> である。「なぜ」と「何を」が知りたくなったら、そちらを読むとよい:
> - **[自己改善ハーネス: アーキテクチャ](self-improving-harness-architecture.md)** — 閉じたループを、ステージごとに、実在するシンボルへマッピングする。
> - **[ブログ: あなたのエージェントはメモリの問題を抱えていない。来歴の問題を抱えているのだ。](https://github.com/ca1773130n/Agented/blob/main/BLOG-self-improving-harness.md)** — このシステムが導かれる論証。

---

## 何についての感覚をつかむことになるか

二つの異なるレイヤーと、それらが互いをどう養うか:

1. **ウィキ型メモリ** — 完了したすべてのセッションは、型付けされた知識グラフ
   （Tesserae）へコンパイルされ、**探索可能なウィキ / Obsidian ボルト**として
   投影される。人間はウィキのように読み、エージェントはグラフのように問い合わせる。
2. **自己改善ループ** — ハーネスは、そのメモリに加えて失敗/成功の証拠ストリームを
   読み、**自身のプリミティブ**（ルール、フック、コマンド、スキル、MCP バインディング）
   **への diff を提案**し、**採点**し、**一つの git コミット**として**適用**し、
   それを**巻き戻したり**、**伝播させたり**できる。

最後に見ることになる落ちは: ループが*生み出す*グラフが、ループが*消費する*基盤
（substrate）である、ということだ。まさにそのエッジが、これをパイプラインではなく
ループにするものだ。

---

## 0. 事前準備

```bash
# リポジトリのルートから
just deploy            # バックエンド(:20000)、サイドカー(:20001)、フロントエンド(:3000) をビルド + 起動
# …または、反復作業用に:
just dev-backend &     # :20000
just dev-frontend      # :3000
```

オペレーターコンソールを `http://localhost:3000` で開く。

また、**Tesserae** CLI + MCP（エージェントメモリシステム）が利用可能である必要が
ある。次で確認する:

```bash
tesserae --version
```

コンソールで**プロジェクト**を選ぶ（または作成する） — Projects → New。以下の内容は
すべて一つのプロジェクトにスコープされる。

> **内部の仕組み:** プロジェクト、プロダクト、チーム、エージェントは接頭辞付き ID
> の行（`proj-…`、`agent-…`）である。バックエンドはあらゆるハーネスを
> `subprocess.Popen` で駆動し、出力をコンソールへ SSE ストリーミングする。

---

## 1. プロジェクトでウィキ型メモリを有効にする

コンソールで: **Settings → Memory System →** このプロジェクトに対して Tesserae を
有効化し、ワークスペースパスを指定する。（好みなら同等の SQL:
`UPDATE projects SET tesserae_project_root = '/abs/path' WHERE id = 'proj-…';`）

有効化されると、**完了したすべてのセッションが自動的にインポートされ**、この
プロジェクトの Tesserae ワークスペースへ入る — セッションごとに何かを配線する必要は
ない。

> **内部の仕組み:** `app/services/tesserae_integration.py`
> （`on_session_complete → export_sessions_to_tesserae`）。これはループのステージ
> **(10)** である。

---

## 2. 証拠を生み出す（セッションをいくつか実行する）

エージェントが何かを*行う*まで、ループには学ぶものがない。シグナルが立つよう、
実際のタスクを 3〜5 個実行する — 成功とつまずきが混ざっていると理想的だ（システムは
**両方**を、非対称に捕捉する。ステップ 4 を参照）。

コンソールから、普段どおりの作業を何でもキックオフする: トリガー実行、スーパー
エージェント実行、チーム実行、またはワークフロー。たとえば、小さなバグにエージェント
を向けて修正させ、それから別のエージェントに、最初は*間違える*であろうこと（古い
パス、欠けた環境変数）をやらせてみる。どちらも有用だ。

> **内部の仕組み:** **すべての**完了セッションごとに — 「ボット」だけではなく —
> 解決済みハーネスバンドルのスナップショットが、生のイベントストリームとともに
> 永続化される（`harness_snapshot_service.py`、`session_events.py`）。これは
> ステージ **(1) キャプチャ** — 来歴台帳の入力レイヤーである。

---

## 3. メモリが形成される様子を見る: 二つの非対称なストリーム

プロジェクトの **Activity** ダッシュボードのレーンを開く。たった今実行した
セッションから、蓄積されていくものが見える:

- **テイクアウェイ**（肯定シグナル） — ユーザーの好み、発見された手順、ツール
  パターン、制約、ドメイン事実、根本原因、成功パターン。それぞれ安定した
  `tk-…` ID を持ち、由来となったセッションへ逆ポイントする。
- **失敗インシデント**（否定シグナル） — 四層の分類体系（インターフェース →
  環境契約 → 軌道 → 一般）で型付けされる。

**非対称性こそが要点だ**: 失敗は*ルールとフック*を求め、成功は*スキルとコマンド*を
求める。ほとんどのメモリシステムは一方向だけを捉え、シグナルの半分を失う。

> **内部の仕組み:** `harness_takeaway_extractor.py` → `harness_takeaways`
> （ステージ 2、肯定）および `harness_failure_annotator.py`
> （`detect_h2/h3/h4`） → `harness_annotations`（ステージ 2、否定）。どちらも
> 同じ `session_complete` チャネルから分岐する。

---

## 4. ウィキをコンパイルする — そしてプロジェクトのメモリをウィキのように読む

これが **LLM-ウィキ**の瞬間だ。蓄積されたセッション、ドキュメント、コードを
型付けされたグラフへコンパイルし、続いて探索可能なサイトとして投影する:

```bash
tesserae status                 # 健全性チェック: ノード/エッジ/セッション数、最終コンパイル
tesserae project compile        # 型付けグラフを抽出 + ボルト + サイト成果物を書き出す
tesserae build-site             # 静的ウィキをレンダリングする
tesserae serve                  # ローカルで閲覧する
```

サーブされたサイトを開く。いまやあなたは**プロジェクトのメモリのウィキ**を読んで
いる — コードファイル、セッション、決定、テイクアウェイ、概念のためのページが、
型付けされたエッジで相互リンクされている。あるセッションから、それが生み出した
決定へ、そしてそれが触れたコードへとクリックして辿る。

自然言語で問いかける（CLI または同梱の MCP ツール）:

```bash
tesserae ask "リトライ/バックオフについて我々は何を決めたか?"
tesserae ask "どのセッションがコストダッシュボードに触れ、何が壊れたか?"
```

エディタで見たい? ボルトを Obsidian へ同期する:

```bash
tesserae obsidian-sync
```

> **内部の仕組み:** グラフの型は `CodeFile`、`Session`、`SessionTakeaway`、
> `SessionDecision`、… である。MCP 面（`tesserae_ask`、`search_facts`、
> `graph_ppr`、`wiki_page`、`find_session_findings`）は、*エージェント*がタスクの
> 途中でこの同じメモリを読む方法だ — `CLAUDE.md` の Tesserae セクションを参照。
> 大きな変更の後は `tesserae refresh` でリフレッシュする。

---

## 5. 進化ラウンドを実行する（ドライラン）: 提案 → 採点

いよいよループだ。コンソールで、プロジェクトの **Harness Evolution** カード
（Activity レーン）を開き、**ドライラン**ラウンドを開始する。（API 同等:
`POST /projects/{project_id}/evolution/dry-run`。）

三つのことが順に起こり、ラウンドの状態機械は
`pending → running → evaluating → awaiting_approval` を歩む:

1. **収集（Gather）** — ラウンドは入力を組み立てる: 現在バインドされている
   プリミティブ、最近の軌道 + そのインシデント、最近のテイクアウェイ、**そして
   たった今コンパイルしたウィキから問い返された KG シグナル**（≤3 個の制限された
   発見質問）。メモリが提案者を養う。
2. **提案（Propose）** — 入力が一時ワークスペースへ書き込まれ、**Codex が
   サンドボックスで**それに対して実行される。それは **diff** を放出する; ライブの
   プリミティブをインプロセスで編集することは決してない。
3. **評価ゲート（Eval-gate）** — 何かが適用される前に、パッチは **`EvalVerdict`**
   （`passed`、`score ∈ [0,1]`、チェックごとの結果）へ採点される: 静的検査
   （スキーマ/フロントマター/no-op/アンカー）**に加えて**、代表的なセッションを
   *パッチされた*プリミティブに対してリプレイする回帰リプレイ判定者。

カードは**提案された diff**と**判定**を表示する。失敗したゲートは短絡する —
何も着地しない。

> **内部の仕組み:** `harness_evolver.py`（`gather_inputs`、`build_workspace`、
> `_run_codex_in_workspace`、`parse_patch`、`validate_patch`）、
> `harness_kg_signals.py::gather_kg_signals`、そして
> `harness_evolution_eval.py`（`evaluate_patch`、`_static_checks`、`_run_judge`、
> `_verdict`）。ゲートの*エラー*は、スコア 0.0 の記録されたバイパス判定とともに
> fail closed する — バイパスが本物の通過と区別不能になることは決してない。

---

## 6. 適用し、それが git コミットになる様子を見る

diff が気に入ったか? それを**承認**する（ラウンドは `awaiting_approval` に留まって
おり、承認は `POST /evolution/rounds/{id}/apply` である）。

適用時、プリミティブはプロジェクトの実際の `.claude/` レイアウト
（commands/rules/hooks + `settings.json`/`mcp.json`/skills）へ**具現化（materialize）**
され、冪等かつオペレーター保存的に、そして**ラウンドごとに一つの git コミット**として
コミットされる。確認する:

```bash
git -C <project_root> log --oneline -1     # ラウンドの具現化コミット
git -C <project_root> status               # どの .claude/ プリミティブが変わったか
```

ハーネスの進化は、いまや文字どおり `git log` である。

> **内部の仕組み:** `forge_materialization_service.py`。ラウンドは `applied` へ
> 遷移する。

---

## 7. 来歴を辿る（どのメモリベンチマークも測定しない部分）

たった今着地したルールを選び、それを逆向きに歩く。すべてのホップは、タイムスタンプと
逆ポインタを伴う行である:

```
ある挙動
  → それを生み出したルール(RULE)
    → それを鍛えたラウンド(ROUND)             (harness_evolution_rounds)
      → それを採点した評価判定(EVAL VERDICT)  (EvalVerdict)
        → テイクアウェイ / インシデント        (tk-… / harness_annotations)
          → それらが由来したセッション(SESSIONS)  (永続的なトランスクリプト)
```

このチェーンのいずれも、埋め込みブロブに対する類似度スコアではない。「*なぜ
ハーネスはこれを信じ、何がそれを採点したのか?*」を、推測ではなく ID で答えられる。
これが、ブログの仮定上の *AuditEval* が試すであろう属性だ。

---

## 8. 巻き戻す

気が変わったか? ラウンドを巻き戻す（`POST /evolution/rounds/{id}/revert`）:

```bash
# コンソールの Harness Evolution カードから、または API で
```

ロールバックは **before-image ジャーナル**を捕捉し、ラウンドがジャーナルを伴う
`applied` でなければ拒否し、衝突（同じ `{kind, asset_id}` に触れた後続ラウンド）を
検出し、DB 操作を冪等に逆行させてから、具現化コミットを **git-revert** する。git
または部分ステップが失敗した場合、ラウンドは `revert_error` とともに `applied` の
ままになる — 達成していない `reverted` を*主張する*ことは決してない。

> **内部の仕組み:** `harness_evolution_rollback.py`（`revert_round`、
> `reverse_apply_journal`、`_git_revert`）。

---

## 9. （任意）自律的に適用させる — 九つのゲートの背後で

オペレーター承認がデフォルトである。検証された変更が自分自身を適用するように
したいなら、プロジェクトを自律にオプトインする（**Settings → … → Autonomy**、
または `PUT /projects/{id}/autonomy`）。5 分周期のスケジューラジョブは、
`autonomous_apply_eligible` が**九つのハードゲート**をクリアしたとき**のみ**
自動適用する:

1. キルスイッチがオフ（`AGENTED_AUTONOMY` ≠ `0`）
2. プロジェクト別ポリシーが有効
3. eval が `passed`
4. `score ≥ confidence_threshold`（デフォルト **0.85**）
5. ブラスト半径 ≤ `max_ops_per_round`
6. `allowed_kinds`
7. `block_deletes`
8. `cooldown_seconds`
9. `rate_limit_per_day`

これはデフォルトでオフであり、別個の監査されないコード経路ではなく、*オペレーター
経路の制限されたエスカレーション*である。グローバルなキルスイッチ:

```bash
export AGENTED_AUTONOMY=0      # すべての自律適用をハードストップする
```

> **内部の仕組み:** `harness_autonomy.py`
> （`autonomous_apply_eligible`、`process_project_autonomy`）、
> `lifecycle.py` の `autonomous_apply_job`、`project_autonomy_config`。

---

## 10. （任意）検証されたプリミティブがプロジェクト間で伝播する様子を見る

二つ目のプロジェクトでループを回す。あるプリミティブのコンテンツ
**フィンガープリント**が、十分に減衰した、**eval 通過済み**の昇格証拠
（`score ≥ PROMOTION_THRESHOLD = 3.0`）を蓄積すると、グローバルスコープのコピーが
昇格され、他のプロジェクトがそれを**採用（adopt）**できる
（`POST /projects/{id}/adopt-shared/{sbid}`; local-wins 衝突ポリシー）。`rule`、
`hook`、`command` のみが伝播し、eval 通過ラウンドのみが寄与する — いかなる強制適用も
共有レイヤーを汚染できない。

> **内部の仕組み:** `harness_propagation.py`、`forge_fingerprint.py`、
> `shared_forge_bindings`; `GET /shared-forge`。

---

## ループが閉じた

`tesserae project compile` を再実行する。*まさにこのウォークスルー*のセッション —
進化ラウンドを含む — が、いまやウィキのノードである。次のドライランの**収集**
ステップ（5.1）が、それらを問い合わせることになる。ループが生み出したグラフが、
いまやループに種を供給する。

```
 セッション ──► テイクアウェイ + インシデント ──► 収集(KG シード) ──► 提案(Codex)
     ▲                                                              │
     │                                                              ▼
  KG フィードバック ◄── git コミット ◄── 具現化 ◄── 適用 ◄── 評価ゲート(採点済み)
 (Tesserae ウィキ)                                  │
                                                  └─ 巻き戻し / 伝播
```

---

## トラブルシューティング & どこに何があるか

| 症状 | ここを見る |
|---|---|
| セッション後にテイクアウェイ/インシデントがない | セッションが*完了*したか確認; Activity レーンをチェック; `harness_takeaways` / `harness_annotations` の行 |
| ウィキが空 / 古い | `tesserae status`、その後 `tesserae project compile`（または `tesserae refresh`） |
| ドライランが何も提案しない | 最近の証拠が必要; セッションをもっと実行する。no-op は `_static_checks` が捕捉する |
| ラウンドが `awaiting_approval` で止まる | それがゲートだ — 承認するか、自律を有効化する（§9） |
| ラウンドが巻き戻らない | ジャーナルを伴う `applied` ラウンドのみ巻き戻る; 衝突する後続ラウンドがないか確認する |
| 自律が決して発火しない | 九つのゲート（§9）を歩く; `AGENTED_AUTONOMY` ≠ `0` および `score ≥ 0.85` を確認する |

完全なシンボルマップ:
[アーキテクチャドキュメント](self-improving-harness-architecture.md#source-map-every-claim-above-is-a-symbol-in-the-tree)の
**Source map** 表。

---

## 次のステップ

- Letta/MemGPT、Hermes Agent、Mastra、Zep/Graphiti、Mem0、Cognee との正直な
  比較については、**[アーキテクチャ](self-improving-harness-architecture.md)**を
  読むとよい。
- Tesserae MCP ツールをエージェントに配線し、再導出する代わりにタスクの途中で
  ウィキを*問い合わせる*ようにする — `tesserae_ask`、`find_session_findings`、
  `graph_ppr`、`wiki_page`。
- 低リスクのプロジェクトを一つ選んで自律をオンにし、一週間分の `git log` が自身を
  書いていく様子を見る — すべてのコミットは巻き戻し可能で、すべての信念は
  セッションへ辿れる。
