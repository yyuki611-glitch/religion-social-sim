"""スイープ機能（tasks/todo.md rev4）の完了基準2をテストとして固定する。"""
import sys
from pathlib import Path

import pytest

from sim_core.domain_pack import read_tsv
from sim_core.engine import run_scenario

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domain_packs" / "japan_religion"
sys.path.insert(0, str(ROOT / "experiments"))

import run_sweep as sweep_mod  # noqa: E402


# --- trait_adjustments（エンジン拡張） ---


def test_default_none_keeps_v020_behavior(tmp_path):
    """trait_adjustments なしの既存挙動が変わらないこと（v0.2.0 の既知結果で固定）。"""
    result = run_scenario(DOMAIN, "famine.yaml", tmp_path, seed=42)
    assert result["conversions"] == 2
    assert result["syncretisms"] == 0
    assert result["retention_rate"] == 0.75
    assert result["trait_adjustments"] == {}


def test_zero_delta_equals_no_adjustment(tmp_path):
    r1 = run_scenario(DOMAIN, "famine.yaml", tmp_path / "a", seed=42)
    r2 = run_scenario(
        DOMAIN, "famine.yaml", tmp_path / "b", seed=42, trait_adjustments={"anxiety": 0.0}
    )
    assert (tmp_path / "a" / "agent_turns.tsv").read_bytes() == (
        tmp_path / "b" / "agent_turns.tsv"
    ).read_bytes()
    assert r1["final_shares"] == r2["final_shares"]


def test_adjustment_applies_and_clamps(tmp_path):
    """+0.30 デルタで anxiety 最大エージェント（A03=0.75）が 1.0 にクランプされること。"""
    run_scenario(
        DOMAIN, "baseline.yaml", tmp_path, seed=1, trait_adjustments={"anxiety": 0.30}
    )
    turns = read_tsv(tmp_path / "agent_turns.tsv")
    a03_step1 = next(t for t in turns if t["agent_id"] == "A03" and t["step"] == "1")
    # baseline step1 はイベントなし → anxiety = clamp(0.75 + 0.30) = 1.0 がそのまま出る
    assert float(a03_step1["anxiety"]) == 1.0
    a05_step1 = next(t for t in turns if t["agent_id"] == "A05" and t["step"] == "1")
    assert float(a05_step1["anxiety"]) == pytest.approx(0.55)  # 0.25 + 0.30


def test_unknown_trait_key_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown trait"):
        run_scenario(
            DOMAIN, "baseline.yaml", tmp_path, seed=1, trait_adjustments={"bogus": 0.1}
        )


# --- early_convert_retention（H5 指標） ---


def _conv(step, agent, to, kind="conversion"):
    return {"step": str(step), "agent_id": agent, "kind": kind, "to_belief": to}


def test_early_convert_retention_calculation():
    conversions = [
        _conv(6, "A01", "inari_belief"),  # 窓内（5-10）→ 最終も inari = 保持
        _conv(7, "A02", "inari_belief"),  # 窓内 → 最終は classical_shinto = 喪失
        _conv(25, "A03", "jodo_buddhism"),  # 窓外 → 分母に入らない
    ]
    final_agents = [
        {"id": "A01", "belief": "inari_belief"},
        {"id": "A02", "belief": "classical_shinto"},
        {"id": "A03", "belief": "jodo_buddhism"},
    ]
    m = sweep_mod.compute_metrics(conversions, final_agents, "miracle_rumor")
    assert m["early_conversions"] == 2
    assert m["early_convert_retention"] == 0.5
    assert m["conversions"] == 3
    assert m["conv_to_practical"] == 2
    assert m["conv_to_salvation"] == 1


def test_early_retention_uses_last_in_window_target():
    """窓内で2回改宗したエージェントは最後の改宗先で判定する。"""
    conversions = [
        _conv(6, "A01", "inari_belief"),
        _conv(9, "A01", "jodo_buddhism"),
    ]
    final_agents = [{"id": "A01", "belief": "jodo_buddhism"}]
    m = sweep_mod.compute_metrics(conversions, final_agents, "miracle_rumor")
    assert m["early_convert_retention"] == 1.0


def test_no_early_conversions_is_na():
    m = sweep_mod.compute_metrics([], [{"id": "A01", "belief": "x"}], "baseline")
    assert m["early_convert_retention"] is None


# --- results.tsv スキーマと決定性 ---


def test_sweep_results_schema_and_determinism(tmp_path):
    """同じスイープを2回実行して results.tsv が byte 一致すること（縮小版: seed 2個）。
    fixed8（v0.4.0 互換パス）を明示指定。sampled60 の決定性は test_population 側。"""
    rows = sweep_mod.run_sweep("tolerance", tmp_path / "r1", seeds=[1, 2], population="fixed8")
    sweep_mod.run_sweep("tolerance", tmp_path / "r2", seeds=[1, 2], population="fixed8")
    f1 = (tmp_path / "r1" / "tolerance" / "results.tsv").read_bytes()
    f2 = (tmp_path / "r2" / "tolerance" / "results.tsv").read_bytes()
    assert f1 == f2
    # 残存ディレクトリがある状態での再実行でも一致（codex MEDIUM-9）
    sweep_mod.run_sweep("tolerance", tmp_path / "r1", seeds=[1, 2], population="fixed8")
    assert (tmp_path / "r1" / "tolerance" / "results.tsv").read_bytes() == f1

    header = f1.decode().splitlines()[0].split("\t")
    assert header == sweep_mod.RESULT_FIELDS
    # 行順: (scenario, trait, delta, seed) 昇順
    keys = [
        (r["scenario"], r["trait"], float(r["delta"]), r["seed"]) for r in rows
    ]
    assert keys == sorted(keys)
    # 2シナリオ × 5デルタ × 2seed
    assert len(rows) == 20


def test_sweep_a_schema_uses_none_trait(tmp_path):
    rows = sweep_mod.run_sweep("scenario_seeds", tmp_path, seeds=[1], population="fixed8")
    assert all(r["trait"] == "none" and r["delta"] == "+0.00" for r in rows)
    assert len(rows) == 3  # 3シナリオ × 1seed
