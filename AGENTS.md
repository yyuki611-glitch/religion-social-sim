# religion-social-sim

> **状態: 休眠中（最終更新 2026-06）**。凍結スナップショット。再開前にこのファイルと README を読むこと。

## 目的

日本の宗教伝播・衰退を扱う公開の社会シミュレーションプロトタイプ。コアエンジンはドメイン非依存に保ち、日本の宗教に関する事実・シナリオ・バリデーションは `domain_packs/japan_religion` 配下に置く。

## 状態

休眠中。積極開発は停止している。現行の到達点・仮説判定・再現方法は README と `CHANGELOG.md` が正。

## 再開時に読む場所

- `README.md`（正・全体像と再現方法）
- `CHANGELOG.md`（バージョン履歴と主張の変遷）
- `docs/hypotheses.md` / `docs/references.md`（仮説と出典）

## 触ってはいけない点

- 宣言済みの仮説判定基準を後から変えない。
- `docs/references.md` に出典を追加せずに歴史的正確性を主張しない。
- 生成物は `outputs/runs/` に置き、大きな生成物はコミットしない。

## 公開リポジトリの注意

このリポジトリは public。秘密情報・私的メモ・個人コンテキスト・トークン・API キー・非公開トランスクリプトをコミットしない。

## Guidance Pair

`AGENTS.md`（Codex）と `CLAUDE.md`（Claude Code）は対で維持する。片方だけ更新しない。README が正。
