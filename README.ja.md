<div align="center">

# Agented

**自律型 AI エージェントで仮想スタートアップを運営するためのメタハーネス・エンジニアリング基盤。**

Agented は AI ハーネス・エンジニアリングの最新技術 — ループエンジニアリング、
エージェントのオーケストレーション、スウォーム、自己改善、オートリサーチ、永続
メモリ — を、ひとつのプロダクト・プロジェクト中心のオペレーターコンソールに
まとめます。Hermes 風のエージェントシステムを思い浮かべつつ、より広範で、単に
モデルと会話するのではなく **会社を運営するための** WebUI を備えた形です。

[アーキテクチャ](docs/ja/self-improving-harness-architecture.md) · [チュートリアル](docs/self-improving-harness-tutorial.md) · [変更履歴](CHANGELOG.md) · [セキュリティ](docs/SECURITY.md) · [デプロイ](docs/deploy.md)

**他の言語で読む:** [English](README.md) · [한국어](README.ko.md) · [中文](README.zh.md)

</div>

---

## Agented とは

AI エージェントから実質的で継続的な成果を引き出す方法は、**まさに今** —
カンファレンスの講演、ブログ記事、そしてハーネスを作る人々の作業ノートの中で —
形作られています。Agented の主張は、これらのアイデアが使い捨てのスクリプトや
個人的な仕掛けに散らばっているべきではない、というものです。Agented はそれらを
ひとつの **メタハーネス層** にまとめ、コーディング CLI（Claude Code、Codex、
Gemini CLI、OpenCode など）の上に載せ、それらを **仮想スタートアップ** の労働力に
変えます — **プロダクトとプロジェクト** を中心に組織され、ひとつのコンソールから
運営されます。

まだ **初期段階で、急速に進化中** です。すでに実装されているもの:

- **🔁 ループエンジニアリング** — ひとつの `LoopSpec` スキーマと単一の実行器が
  あらゆるループパターン（goal-loop、Ralph）を駆動します: 終了ラダー（品質ゲート
  → 停滞 → 収束 → 予算）、反復ごとのチェックポイント、再開、ヒューマンゲート。
  → [アーキテクチャ](docs/ja/self-improving-harness-architecture.md)
- **🎛 エージェントのオーケストレーション** — **プロダクト → プロジェクト → チーム
  → エージェント** を第一級のモデルとして扱い、ひとつのダッシュボードから調整し、
  各実行をプロジェクトごとのコンテキスト・アカウント・プリミティブで構成します。
- **🐝 複数の AI アカウントにまたがるスウォーム** — （`ai-accounts` サイドカー経由で）
  複数のプロバイダアカウントに作業をスケジューリング・ハンドオフし、適切な
  バックエンドとモデルへ **自動ルーティング** します。
- **♻️ 自己改善** — ハーネス自身のプリミティブを進化させる、eval ゲート付きで
  git で巻き戻し可能な「life-harness」ループ。
- **🔬 オートリサーチ** — GRD エンジンがリサーチ → 計画 → 実行 → 検証を、自律的で
  マイルストーン計画されたパイプラインとして実行します。
- **🧠 永続メモリ + LLM ウィキ** — Tesserae がコード・ドキュメント・セッション
  履歴の型付き知識グラフ（および生成されたウィキページ）をコンパイルし、すべての
  検索を根拠付けます。
- **⏳ 長期ホライズン・エージェント** — 耐久性のある実行ごとの状態、増分
  チェックポイント、`--resume` により、実行がクラッシュに耐え、数日にまたがります。
- **📊 可観測性** — リアルタイム SSE トレース、セッションイベント、監査証跡、そして
  エージェントが行ったすべての日次・週次 **アクティビティ概要**。
- **🧩 ハーネスの共有と合成** — Forge で **プリミティブ**（スキル・フック・コマンド・
  ルール・サブエージェント）を組織してハーネスを作り、プラグイン・マーケットプレイスで
  共有します。
- **📦 プロダクト・プロジェクト管理** — 競合のモニタリング・発見・戦略立案、
  プロジェクト計画、プロジェクトごとの **ワンクリック・チームハーネス・セットアップ**。
- **🛡 ガバナンスと安全性** — スタック可能なポリシーエンジン、デフォルト遮断の
  egress を伴う OS レベルのサンドボックス、リアルタイムのマルチユーザー協働。

その下では、エージェントのあらゆる動作がチェックポイントされ、出所が帰属され、
予算で統制され、検証可能です — **来歴・監査可能性・ロールバックが後付けではなく
設計に組み込まれています**。

## クイックスタート

```bash
# 新しいマシン — just、uv、Node.js を自動インストールし、全依存関係を導入（再実行安全）
bash scripts/setup.sh

# 前提条件がすでにある場合は？
just setup        # 全依存関係をインストール
just dev-all      # バックエンド :20000 + サイドカー :20001 + フロントエンド :3000
```

コンソールは **http://localhost:3000** で開きます。インタラクティブな API ドキュメント
（Swagger UI）は **http://localhost:20000/schema** にあります。`just dev-backend`、
`just dev-frontend`、`just dev-ai-accounts` で個別に実行できます。

### ビルド済みイメージのデプロイ

**推奨 — まずクローンして確認**（コードを読んで *から* 実行）:

```bash
git clone https://github.com/ca1773130n/Agented && cd Agented
./install.sh                 # ビルド済みイメージを pull + スタックを起動
```

`install.sh` は一緒にクローンされた `docker-compose.yml` を再利用するため、
確認せずに取得・実行されるコードはありません。

<details>
<summary>便利なワンライナー（安全性は低い）</summary>

リモートスクリプトをシェルにパイプすると、読んでいないコードが実行されます。
**不変のリリースタグ** に固定した場合のみ行ってください — その場合、インストーラは
ダウンロードした compose ファイルを SHA-256 で検証し、不一致なら中断します:

```bash
curl -fsSL https://raw.githubusercontent.com/ca1773130n/Agented/v0.10.0/install.sh | bash
```

可変の `main` ブランチから取得することは、`AGENTED_INSTALL_UNVERIFIED=1` を明示的に
設定しない限り拒否されます（この場合チェックサム検証をスキップし、セキュリティ警告を
出力）。[docs/deploy.md](docs/deploy.md#2-single-install-script) 参照。
</details>

```bash
# 既存のインストールを一つのコマンドで更新（イメージが更新単位）
just self-update
```

上の **Deploy to Render** バッジは Blueprint ガイド（web + サイドカー +
`DATABASE_URL` に接続されたマネージド Postgres）を開きます。この単独リポジトリからは
ワンクリックでは **ありません**: イメージビルドに兄弟の `ai-accounts/` ツリーが必要な
ため、Render は `Agented/` と `ai-accounts/` の両方を含む **親モノレポ**（ルートに
`render.yaml`）を接続する必要があります。オプションの Postgres 構成を含む詳細は
**[docs/deploy.md](docs/deploy.md)** にあります。

> **初回実行:** **最初に** 登録したアカウントが管理者になります。登録を終えたら —
> 信頼できないネットワークに公開する前に必ず — `AGENTED_DISABLE_SIGNUP=1` を
> 設定してください。

## 各パーツの噛み合い方

プロダクトとプロジェクトがモデルの最上位、チームとエージェントが作業を行い、
ループ・メモリ・ポリシー・プリミティブが各実行が引き出す機構です。**トリガー**
（Webhook、GitHub イベント、スケジュール、手動実行）は配信メカニズムにすぎません —
プロダクトはトリガーが起動する自律エージェントのワークフローそのものです。

| レイヤー | スタック | ポート |
|---|---|---|
| **バックエンド** | Litestar (gunicorn / UvicornWorker)、生 SQLite（実験的 Postgres）、subprocess + SSE | `:20000` |
| **フロントエンド** | Vue 3 + TypeScript オペレーターコンソール | `:3000` |
| **サイドカー** | `ai-accounts` — AI バックエンドの識別情報・資格情報・ログインフロー | `:20001` |
| **メモリ** | Tesserae 型付き知識グラフ + CodeGraph シンボルインデックス | — |

## 設定

| 変数 | 説明 | デフォルト |
|---|---|---|
| `AGENTED_DISABLE_SIGNUP` | 公開セルフ登録を閉じる（最初の管理者登録後に設定） | unset（開放） |
| `DATABASE_URL` | 実験的 PG アダプタを使う Postgres URL（未設定 ⇒ SQLite） | unset (SQLite) |
| `AGENTED_SANDBOX` | OS レベルのハーネス・サンドボックス（bwrap / seatbelt）を有効化 | unset（オフ） |
| `AI_ACCOUNTS_API_KEY` | `ai-accounts` サイドカーのトークン | 管理者キーを再利用 |

全環境変数リファレンスと規約は [CLAUDE.md](CLAUDE.md) にあります。

## 検証

出荷前に 3 つのゲートすべてが通る必要があります:

```bash
just build                       # vue-tsc 型チェック + vite ビルド
cd backend && uv run pytest      # バックエンド・スイート
cd frontend && npm run test:run  # フロントエンド・スイート
```

## ドキュメント

| トピック | リンク |
|---|---|
| 変更履歴 | [CHANGELOG.md](CHANGELOG.md) |
| 自己改善ハーネス — アーキテクチャ | [docs/ja/self-improving-harness-architecture.md](docs/ja/self-improving-harness-architecture.md) |
| デプロイ — Render Blueprint / インストール / セルフ更新 | [docs/deploy.md](docs/deploy.md) |
| セキュリティ | [docs/SECURITY.md](docs/SECURITY.md) |
| ai-accounts サイドカー | [docs/ai-accounts/ARCHITECTURE.md](docs/ai-accounts/ARCHITECTURE.md) |
| 国際化(i18n) | [docs/i18n.md](docs/i18n.md) |

<div align="center"><sub>一人スタートアップ — そしてその後に続くチーム — のためのハーネス・エンジニアリング。</sub></div>
