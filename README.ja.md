# MAGI

MAGI は、`Codex`、`Claude Code`、`Gemini CLI` のようなローカル CLI 型の AI を、相談役としてまとめて扱うための軽量オーケストレータです。

複数モデルを自由会話させるのではなく、同じ問いを独立に投げて、結果を保存し、次の内容を整理して返します。

- 一致点
- 相違点
- 未解決点
- 推奨 next step

現在はローカル CLI 前提の MVP で、すぐ試せる `mock` モードも入っています。

## 何ができるか

- 対話シェルでモードを維持しながら相談できる
- `prompt_toolkit` による履歴入力と行編集が使える
- 1 回だけの one-shot 実行もできる
- provider ごとの実行アダプタを差し替えられる
- 実行結果を `runs/` に保存できる
- advisor ごとの出力と統合レポートを残せる
- 前回 run のレポートを次の依頼に handoff できる
- `plan` モードでプロジェクト直下の `plan.md` を更新できる
- 1 provider 限定で agent の再試行 + ローカル検証ループを回せる
- `/ask /plan /debug /agent` のモード切替ができる
- `/model` で provider、model、effort を切り替えられる
- `magi models` や `/models` で model catalog を更新できる
- `/clean` や `magi clean` で古い run を整理できる
- `Esc` で実行中の run を中断できる

## 使いどころ

- 設計方針の比較
- 実装計画の整理
- デバッグの切り分け
- 調査や文章作成の観点比較
- 実装前の意思決定支援

## クイックスタート

このフォルダでそのまま実行できます。

```powershell
python -m magi "小さな CLI ツールの設計案を比較して"
```

ローカルコマンドとして入れる場合:

```powershell
python -m pip install -e .
magi "このプロジェクトの初期構成をレビューして"
```

デフォルトでは `codex`、`claude`、`gemini` という名前の mock provider を使い、出力は `runs/` に保存されます。

## 導入

MAGI 自体は Python パッケージです。連携する AI CLI は別ツールなので、対象PCにそれぞれ入れておく必要があります。

前提:

- Python 3.11 以上
- `git`
- 使いたい外部 CLI を個別にインストール済み
  - `codex`
  - `claude`
  - `gemini`

導入手順:

```powershell
git clone https://github.com/takikomirice/MAGI-CLI_Subscription-Orchestration
cd MAGI-CLI_Subscription-Orchestration
python -m pip install -e .
```

導入確認:

```powershell
magi --help
python -m unittest discover -s tests -v
python -m compileall magi tests docs
```

その後、各 CLI はそのPC上で通常どおりログイン / 認証してください。

必要なら `.magi.toml` をそのPC向けに調整します:

- 各 CLI の正確なコマンド名
- `stdin_prompt = true` が必要かどうか
- インストール済みバージョンで使える model / effort 指定

最初の実行例:

```powershell
magi --mode plan "このプロジェクトの次の実装計画を作って"
```

## 対話モード

シェルを起動:

```powershell
python -m magi
```

`prompt_toolkit` が入り、実コンソール上で動いていれば、上矢印による履歴や行編集が使えます。
実行中に `Esc` を押すと、進行中の provider 実行を停止します。

モードは切り替えるまで維持されます。

```text
MAGI [ask]> /plan
mode: plan
MAGI [plan]> MVP と次フェーズに分けて整理して
MAGI [plan]> /handoff last-plan
handoff set: last-plan -> run 2026-03-15-120000-001 (plan) [D:\...\report.md]
MAGI [plan]> /agent
mode: agent
MAGI [agent]> さっき承認した計画に沿って実装して
MAGI [plan]> /model
MAGI model menu
Enter: descend/select | Esc: back/exit | Space: toggle provider on/off
MAGI [plan]> /clean 20
MAGI [plan]> /debug
MAGI [debug]> provider の出力 parse が失敗する原因を切り分けて
MAGI [debug]> /exit
```

使えるスラッシュコマンド:

- `/ask`
- `/plan`
- `/debug`
- `/agent`
- `/handoff`
- `/model`
- `/models`
- `/clean`
- `/mode`
- `/status`
- `/runs`
- `/last`
- `/help`
- `/exit`

下部ステータスには provider ごとの quota 欄を先に置いてあり、今は `codex: --%` のようなプレースホルダ表示です。

## run handoff

前の MAGI run の統合レポートを、次の依頼の文脈として引き継ぎたいときに使います。特に `plan -> agent` で使う想定です。

one-shot 例:

```powershell
python -m magi --mode plan --project-root C:\work\demo "段階的な実装計画を作って"
python -m magi --mode agent --project-root C:\work\demo --handoff last-plan "承認した計画に沿って実装して"
```

対話モード:

```text
MAGI [plan]> 段階的な実装計画を作って
MAGI [plan]> /handoff last-plan
MAGI [plan]> /agent
MAGI [agent]> 承認した計画に沿って実装して
```

使える selector:

- `last`
- `last-plan`
- `2026-03-15-120000-001` のような run ID
- run ディレクトリのパス

## project plan ファイル

`plan` モードでは、プロジェクト直下の `plan.md` を正式成果物として扱います。

挙動:

- `plan` 実行後に最新の日本語の実装計画を `./plan.md` に書き出す
- すでに `plan.md` がある場合は、その内容を次の `plan` prompt に自動で含めて、計画を育てる形にする
- 上書き前の `plan.md` は `./plans/archive/` に退避する
- 最終 `plan.md` は [`magi/prompts/plan_format.md`](magi/prompts/plan_format.md) の簡易契約と [`docs/plan-style-guide.md`](docs/plan-style-guide.md) の詳細ルールに従う

これで、実装を別 CLI に任せる前提でも、MAGI を「計画の司令塔」として使いやすくなります。

## agent 検証ループ

`agent` モードで active provider が 1 つだけのとき、MAGI は「実装 -> 検証 -> 失敗時はログを渡して再試行」というループを回せます。`agent` は single-provider 前提で、synth 指定は無視します。

流れ:

- MAGI が選択中 provider に依頼する
- provider がプロジェクトを編集し、JSON で作業要約を返す
- MAGI が `.magi.toml` の検証コマンドをローカルで実行する
- 検証が落ちたら、その失敗ログを次の `agent` prompt に差し込んで再試行する

設定例:

```toml
[agent]
max_attempts = 3
verification_timeout_seconds = 300
verification_commands = [
  ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
  ["python", "-m", "compileall", "magi", "tests"],
]
```

今のところ、このループは single-provider のときだけ有効です。`agent` で複数 provider を active にしている場合は、従来どおり advisory 的な fan-out に戻ります。

subscription model を明示して投げる例:

```powershell
python -m magi --mode agent --agent-provider codex --agent-model gpt-5.4 --agent-effort high --handoff last-plan "承認した計画に沿って実装して"
```

対話モード:

```text
/agent codex gpt-5.4 high 承認した計画に沿って実装して
```

## `/model` メニュー

引数なしで `/model` を打つと、キーボード操作のメニューが開きます。

対話セッション中で最初の `/model` を開くときは、メニュー表示前に model catalog の強制更新も 1 回走ります。なので subscription 側で新しい model が増えていても、手で `magi models refresh` を打たずに拾いやすくなります。

操作:

- `Enter`: 1段下に降りる、または現在の選択を確定する
- `Esc`: 1段上に戻る、またはメニューを閉じる
- `Space`: provider の役割を `[×] off` -> `[•] advisor` -> `[○] synthesizer` の順に切り替える
- 矢印キー: カーソル移動

provider の役割:

- `[×]`: 無効
- `[•]`: 通常 advisor
- `[○]`: advisor 兼 最終統合役

`[○]` にできる provider は常に 1 つだけです。
すでに別の provider が `[○]` のとき、他の provider は `[×]` と `[•]` の間だけを切り替えます。

階層:

1. provider 選択
2. その provider の model 選択
3. その provider の effort 選択

文字列で素早く指定することもできます。

```text
MAGI [ask]> /model codex gpt-5.4 high
MAGI [ask]> /model gemini gemini-3.1-pro-preview medium
MAGI [ask]> /model all
MAGI [ask]> /model show
```

## run の整理

run は `runs/` の下に増えていきます。古いものは `clean` で整理できます。

```powershell
magi clean 20
magi clean all
magi clean all --history
```

対話モード内でも同じです。

```text
/clean 20
/clean all
/clean all --history
```

`--history` を付けると、`.magi_history` も一緒に削除します。

## model catalog の更新

固定の model 一覧はすぐ古くなるので、MAGI はローカルの discovery command から provider ごとの model catalog を更新し、`.magi-cache/model_catalogs.json` に cache できます。

前提:

- `model_discovery_command` は model ID を 1 行 1 つずつ出力する
- `model_discovery_regex` を付けると、ノイジーな出力から model ID だけ抜ける
- `model_discovery_ttl_hours` で起動時の自動再取得間隔を決める

例:

```toml
[providers.codex]
type = "cli"
enabled = true
command = ["codex", "exec", "--model", "{model}", "{prompt}"]
model_discovery_command = ["python", "scripts/list_codex_models.py"]
model_discovery_ttl_hours = 24
model_discovery_timeout_seconds = 15
default_model = "gpt-5.4"
default_effort = "high"
```

同梱している discovery helper:

- `scripts/list_codex_models.py`
- `scripts/list_claude_models.py`
- `scripts/list_gemini_models.py`

`claude` はインストール済みの公式 Claude Code bundle から、`gemini` はインストール済みの Gemini CLI core 定数から取得します。`codex` は現時点で公式CLIに公開の model list コマンドが無いため、curated fallback を使います。

使い方:

```powershell
magi models
magi models refresh
magi models refresh codex
```

対話モード内:

```text
/models
/models refresh
/models refresh claude
```

## one-shot 実行

対話モードに入らず 1 回だけ投げることもできます。

```powershell
python -m magi --mode plan --providers codex --models codex=gpt-5.4 --efforts codex=high "この CLI ツールの段階的な実装順を整理して"
python -m magi --mode agent --agent-provider codex --agent-model gpt-5.4 --agent-effort high --handoff last-plan "承認した計画に沿って、まずテストから実装して"
python -m magi --synth-provider gemini "小さな CLI ツールの設計案を比較して"
```

## プロジェクト構成

```text
magi/
  cli.py
  config.py
  io.py
  model_catalog.py
  model_menu.py
  models.py
  pipeline.py
  prompts.py
  runs.py
  synthesis.py
  prompts/
    advisor.md
    plan.md
    debug.md
    agent.md
  providers/
    base.py
    external_cli.py
    mock.py
runs/
.magi-cache/
```

## ローカル設定

各プロジェクトで `.magi.toml` を置けば、provider 設定を差し替えられます。

```toml
project_name = "my-project"
runs_dir = "runs"

[providers.codex]
type = "cli"
enabled = true
command = ["codex", "exec", "{prompt}"]
model_discovery_command = ["python", "scripts/list_codex_models.py"]
model_discovery_ttl_hours = 24
model_discovery_timeout_seconds = 15
# model_discovery_regex = "(gpt-[A-Za-z0-9.-]+)"
default_model = "gpt-5.4"
model_options = ["gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.2", "gpt-5.1-codex-max", "gpt-5.1-codex-mini"]
default_effort = "high"
effort_options = ["default", "low", "medium", "high", "xhigh"]

[providers.claude]
type = "cli"
enabled = true
command = ["claude", "-p", "--model", "{model}", "--effort", "{effort}", "{prompt}"]
model_discovery_command = ["python", "scripts/list_claude_models.py"]
model_discovery_ttl_hours = 24
model_discovery_timeout_seconds = 15
default_model = "claude-sonnet-4-6"
model_options = ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-1"]
default_effort = "default"
effort_options = ["default", "low", "medium", "high"]

[providers.gemini]
type = "cli"
enabled = true
command = ["gemini", "-m", "{model}", "-p", "{prompt}"]
model_discovery_command = ["python", "scripts/list_gemini_models.py"]
model_discovery_ttl_hours = 24
model_discovery_timeout_seconds = 15
default_model = "gemini-3.1-pro-preview"
model_options = ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-3-pro-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
default_effort = "default"
effort_options = ["default", "low", "medium", "high"]
```

`default_model` / `model_options` / `default_effort` / `effort_options` は、`command` 側で `{model}` や `{effort}` を実際に使ってはじめて外部 CLI に渡されます。`command` にそれらのプレースホルダが無い場合、`/model` で切り替えても外部 CLI には反映されません。

CLI が標準入力を読む場合は `stdin_prompt = true` を使います。

```toml
[providers.codex]
type = "cli"
enabled = true
command = ["codex", "exec"]
stdin_prompt = true
default_model = "gpt-5.4"
default_effort = "high"
```

CLI が model や effort の指定フラグを受けるなら、`command` に `{model}` と `{effort}` を入れておくと、そのまま流せます。

```toml
[providers.codex]
type = "cli"
enabled = true
command = ["codex", "exec", "--model", "{model}", "--reasoning-effort", "{effort}", "{prompt}"]
default_model = "gpt-5.4"
default_effort = "high"
```

## 今入っているもの

- CLI エントリーポイント
- 永続モード付き対話シェル
- 実コンソールでの履歴入力
- provider 抽象
- mock provider
- 外部 CLI provider adapter
- ファイル保存ベースの run 管理
- 基本的な比較と統合レポート
- 実行中の provider、model、effort 切替
- プロジェクト直下 `plan.md` の生成 / 更新
- 1 provider 限定の agent 検証 / 再試行ループ
- run 整理コマンド

## まだ入っていないもの

- 差分に対する再質問ループ
- worker 実行オーケストレーション
- provider ごとの実 quota 取得
- ローカル LLM / SLM provider
- GUI

## ライセンス

MIT。詳細は [LICENSE](LICENSE) を参照してください。
