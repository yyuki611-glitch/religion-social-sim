"""H3/H4 スイープ（v0.7.0、tasks/todo.md rev3）の完了基準4をテストとして固定する。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import run_sweep as sweep_mod  # noqa: E402


# --- local_retention（H3 指標）の単体テスト（合成データ） ---


def _agent(aid, belief):
    return {"id": aid, "current_belief": belief}


def _final(aid, belief):
    return {"id": aid, "belief": belief}


def test_local_retention_denominator_fixed_at_start():
    """分母は run 開始時の地域信仰保持者数で固定。途中改宗者も分母に残る。"""
    agents = [
        _agent("P001", "ujigami_shinto"),  # 保持
        _agent("P002", "ujigami_shinto"),  # 稲荷へ改宗（分母には残る）
        _agent("P003", "classical_shinto"),  # 保持
        _agent("P004", "inari_belief"),  # 地域信仰でない（分母外）
    ]
    finals = [
        _final("P001", "ujigami_shinto"),
        _final("P002", "inari_belief"),
        _final("P003", "classical_shinto"),
        _final("P004", "inari_belief"),
    ]
    m = sweep_mod.local_retention_metrics(agents, finals)
    assert m["local_retention"] == 2 / 3
    assert m["local_retention_ujigami"] == 1 / 2  # 診断キー
    assert m["local_retention_classical"] == 1.0


def test_local_retention_requires_same_belief_not_any_local():
    """氏神→古典神道への移動は「保持」ではない（同一信仰の保持のみカウント）。"""
    agents = [_agent("P001", "ujigami_shinto")]
    finals = [_final("P001", "classical_shinto")]
    m = sweep_mod.local_retention_metrics(agents, finals)
    assert m["local_retention"] == 0.0


def test_local_retention_na_when_no_initial_holders():
    agents = [_agent("P001", "inari_belief")]
    finals = [_final("P001", "inari_belief")]
    m = sweep_mod.local_retention_metrics(agents, finals)
    assert m["local_retention"] is None
    assert m["local_retention_classical"] is None


# --- post-patronage 窓（H4 指標）の単体テスト ---


def _conv(step, to, kind="conversion"):
    return {"step": str(step), "kind": kind, "to_belief": to}


def test_post_patronage_window_boundaries():
    conversions = [
        _conv(19, "classical_shinto"),  # 窓前 → 数えない
        _conv(20, "classical_shinto"),  # 窓内
        _conv(25, "classical_shinto"),  # 窓内（境界含む）
        _conv(26, "classical_shinto"),  # 窓後 → 数えない
        _conv(22, "inari_belief"),  # 窓内だが対象信念でない
        _conv(21, "classical_shinto", kind="syncretism"),  # 習合は数えない
    ]
    assert sweep_mod.post_patronage_conversions(conversions) == 2


# --- スキーマ防御（RESULT_FIELDS の固定） ---


def test_result_fields_unchanged():
    """F/G 追加で results.tsv の共通スキーマを変えないこと（byte 互換の前提）。"""
    assert sweep_mod.RESULT_FIELDS == [
        "sweep",
        "scenario",
        "trait",
        "delta",
        "seed",
        "steps",
        "conversions",
        "syncretisms",
        "retention_rate",
        "conv_to_salvation",
        "conv_to_practical",
        "conv_to_other",
        "early_conversions",
        "early_convert_retention",
    ]


# --- スイープ F/G の縮小版決定性と stats キー ---


def test_sweep_f_determinism_and_keys(tmp_path):
    sweep_mod.run_sweep("community", tmp_path / "r1", seeds=[1, 2])
    sweep_mod.run_sweep("community", tmp_path / "r2", seeds=[1, 2])
    for fname in ["results.tsv", "stats.json"]:
        assert (tmp_path / "r1" / "community" / fname).read_bytes() == (
            tmp_path / "r2" / "community" / fname
        ).read_bytes()
    stats = json.loads((tmp_path / "r1" / "community" / "stats.json").read_text())
    for cond in stats["conditions"]:
        assert "mean" in cond["local_retention"] and "n_na" in cond["local_retention"]
        assert "local_retention_ujigami" in cond and "local_retention_classical" in cond
        assert "conv_to_classical_post_patronage" not in cond  # G 専用キーは混入しない


def test_sweep_g_determinism_and_keys(tmp_path):
    sweep_mod.run_sweep("authority", tmp_path / "r1", seeds=[1, 2])
    sweep_mod.run_sweep("authority", tmp_path / "r2", seeds=[1, 2])
    assert (tmp_path / "r1" / "authority" / "results.tsv").read_bytes() == (
        tmp_path / "r2" / "authority" / "results.tsv"
    ).read_bytes()
    stats = json.loads((tmp_path / "r1" / "authority" / "stats.json").read_text())
    for cond in stats["conditions"]:
        assert "mean" in cond["conv_to_classical_post_patronage"]
        assert "local_retention" not in cond  # F 専用キーは混入しない


def test_existing_sweeps_have_no_h3_h4_keys(tmp_path):
    """A–E の stats.json に F/G のキーが混入しないこと（v0.6.0 byte 互換の前提）。"""
    sweep_mod.run_sweep("tolerance", tmp_path, seeds=[1])
    stats = json.loads((tmp_path / "tolerance" / "stats.json").read_text())
    for cond in stats["conditions"]:
        assert "local_retention" not in cond
        assert "conv_to_classical_post_patronage" not in cond
