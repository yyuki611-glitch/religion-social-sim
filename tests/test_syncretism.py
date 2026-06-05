"""graded 習合メカニズム（v0.6.0、tasks/todo.md rev3）の完了基準4をテストとして固定する。

境界例は設計 rev3 で事前宣言したもの:
(1) keep_score == drop_score の同値 → drop（完全改宗）
(2) tolerance=0 でも strength+tradition で keep が勝ちうる
(3) gap >= GAP_REF で drop 項が 1.0 で頭打ち
"""
import sys
from pathlib import Path

import pytest

from sim_core.engine import (
    GAP_REF,
    keep_decision,
    run_scenario,
    syncretism_openness,
)

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domain_packs" / "japan_religion"
sys.path.insert(0, str(ROOT / "experiments"))

import run_sweep as sweep_mod  # noqa: E402


# --- keep/drop スコアの境界例（設計宣言済み） ---


def test_equal_scores_means_drop():
    """(1) 同値は drop（完全改宗）。> 比較であることの固定。"""
    keep, ks, ds = keep_decision(0.0, 0.0, 0.0, 0.0, 0.0)
    assert ks == ds == 0.0
    assert keep is False


def test_zero_tolerance_can_still_keep():
    """(2) tolerance=0 でも愛着+伝統で keep が勝ちうる（toleranceは要因の1つにすぎない）。"""
    keep, ks, ds = keep_decision(0.0, 0.9, 0.9, 0.0, 0.05)
    assert ks == pytest.approx(0.45)
    assert ds == pytest.approx(0.05 / GAP_REF)
    assert keep is True


def test_gap_term_caps_at_gap_ref():
    """(3) gap >= GAP_REF では drop 項が 1.0 で頭打ち。"""
    _, _, ds_at_ref = keep_decision(0.5, 0.5, 0.5, 0.2, GAP_REF)
    _, _, ds_far = keep_decision(0.5, 0.5, 0.5, 0.2, GAP_REF * 10)
    assert ds_at_ref == ds_far == pytest.approx(1.0 + 0.35 * 0.2)


def test_typical_farmer_table_from_design():
    """設計 rev3 の典型値テーブル（gap 0.10→keep / 0.18→drop / 0.29→drop）の固定。"""
    cases = {0.10: True, 0.18: False, 0.29: False}
    for gap, expect_keep in cases.items():
        keep, _, _ = keep_decision(0.55, 0.40, 0.78, 0.30, gap)
        assert keep is expect_keep, f"gap={gap}"


def test_syncretism_openness_caps_at_half():
    """副次取り込み確率は全特性最大でも 0.50（意図的頭打ち）。"""
    assert syncretism_openness(1.0, 1.0, 1.0) == pytest.approx(0.50)


# --- エンジン統合 ---


def test_unknown_syncretism_mode_raises(tmp_path):
    with pytest.raises(ValueError, match="syncretism_mode"):
        run_scenario(DOMAIN, "baseline.yaml", tmp_path, seed=1, syncretism_mode="bogus")


def test_graded_is_deterministic(tmp_path):
    r1 = run_scenario(DOMAIN, "famine.yaml", tmp_path / "a", seed=5, syncretism_mode="graded")
    r2 = run_scenario(DOMAIN, "famine.yaml", tmp_path / "b", seed=5, syncretism_mode="graded")
    assert r1 == r2
    assert (tmp_path / "a" / "conversions.tsv").read_bytes() == (
        tmp_path / "b" / "conversions.tsv"
    ).read_bytes()


def test_graded_differs_from_threshold(tmp_path):
    """graded はメカニズムとして threshold と異なる挙動を持つこと（スモーク）。

    8人村 famine seed=42 は両モードが偶然一致する（保持判定がどちらも否）ため、
    確実に分岐が踏まれる60人サンプリング村で比較する。
    """
    import random

    from sim_core.domain_pack import read_tsv, read_yaml
    from sim_core.population import generate_agents

    spec = read_yaml(DOMAIN / "data" / "population.yaml")
    beliefs = read_tsv(DOMAIN / "data" / "beliefs.tsv")
    rows = generate_agents(spec, random.Random(10**6 + 1), beliefs)
    t = run_scenario(
        DOMAIN, "famine.yaml", tmp_path / "t", seed=1, agents_rows=rows, syncretism_mode="threshold"
    )
    g = run_scenario(
        DOMAIN, "famine.yaml", tmp_path / "g", seed=1, agents_rows=rows, syncretism_mode="graded"
    )
    assert (t["conversions"], t["syncretisms"]) != (g["conversions"], g["syncretisms"])


def test_threshold_default_unchanged(tmp_path):
    """syncretism_mode 未指定 = threshold = v0.2.0 既知結果（後方互換のピン留め）。"""
    result = run_scenario(DOMAIN, "famine.yaml", tmp_path, seed=42)
    assert result["conversions"] == 2
    assert result["retention_rate"] == 0.75


# --- スイープ E ---


def test_sweep_e_determinism_and_stats_keys(tmp_path):
    sweep_mod.run_sweep("tolerance_graded", tmp_path / "r1", seeds=[1, 2])
    sweep_mod.run_sweep("tolerance_graded", tmp_path / "r2", seeds=[1, 2])
    for fname in ["results.tsv", "stats.json"]:
        assert (tmp_path / "r1" / "tolerance_graded" / fname).read_bytes() == (
            tmp_path / "r2" / "tolerance_graded" / fname
        ).read_bytes()
    import json

    stats = json.loads((tmp_path / "r1" / "tolerance_graded" / "stats.json").read_text())
    for cond in stats["conditions"]:
        # 宣言済みキー（設計 rev3 / evaluator MEDIUM-A）
        assert "syncretism_share" in cond
        assert "mean" in cond["syncretism_share"] and "std" in cond["syncretism_share"]
        assert "final_secondary_holders" in cond
        assert "mean" in cond["final_secondary_holders"]


def test_sweep_a_to_d_stats_have_no_graded_keys(tmp_path):
    """A–D（threshold）の stats.json に graded 用キーが混入しないこと（v0.5.0 byte互換の前提）。"""
    sweep_mod.run_sweep("tolerance", tmp_path, seeds=[1])
    import json

    stats = json.loads((tmp_path / "tolerance" / "stats.json").read_text())
    for cond in stats["conditions"]:
        assert "syncretism_share" not in cond
        assert "final_secondary_holders" not in cond
