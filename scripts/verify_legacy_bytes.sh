#!/bin/bash
# 旧タグとの byte 互換検証（v2.0 完了基準2。merge 前に必ず実行する）
# - fixed8 全スイープ（A–D相当） ↔ v0.4.0 タグ
# - sampled60 A–D ↔ v0.5.0 タグ
# 使い方: bash scripts/verify_legacy_bytes.sh
set -eu
cd "$(dirname "$0")/.."
PY=.venv/bin/python
TMP=$(mktemp -d /tmp/legacy_bytes.XXXX)

echo "[1/2] fixed8 を再生成して v0.4.0 タグと比較..."
$PY experiments/run_sweep.py --sweep scenario_seeds --population fixed8 --output-dir "$TMP/fixed8" >/dev/null
$PY experiments/run_sweep.py --sweep tolerance --population fixed8 --output-dir "$TMP/fixed8" >/dev/null
$PY experiments/run_sweep.py --sweep anxiety --population fixed8 --output-dir "$TMP/fixed8" >/dev/null
$PY experiments/run_sweep.py --sweep practical_need --population fixed8 --output-dir "$TMP/fixed8" >/dev/null
for s in scenario_seeds tolerance anxiety practical_need; do
  git show "v0.4.0:outputs/sweeps/$s/results.tsv" | diff -q - "$TMP/fixed8/$s/results.tsv" >/dev/null
  git show "v0.4.0:outputs/sweeps/$s/stats.json" | diff -q - "$TMP/fixed8/$s/stats.json" >/dev/null
  echo "  $s: OK"
done

echo "[2/2] sampled60 A–D を再生成して v0.5.0 タグと比較..."
for s in scenario_seeds tolerance anxiety practical_need; do
  $PY experiments/run_sweep.py --sweep "$s" --output-dir "$TMP/sampled60" >/dev/null
  git show "v0.5.0:outputs/sweeps/$s/results.tsv" | diff -q - "$TMP/sampled60/$s/results.tsv" >/dev/null
  git show "v0.5.0:outputs/sweeps/$s/stats.json" | diff -q - "$TMP/sampled60/$s/stats.json" >/dev/null
  echo "  $s: OK"
done

rm -rf "$TMP"
echo "LEGACY_BYTES_OK: 旧タグとの byte 一致を全16ファイルで確認"
