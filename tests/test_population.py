"""母集団生成（v0.5.0、tasks/todo.md rev3）の完了基準3をテストとして固定する。"""
import copy
import csv
import random
import sys
from pathlib import Path

import pytest

from sim_core.domain_pack import read_tsv, read_yaml
from sim_core.engine import TRAIT_KEYS, run_scenario
from sim_core.population import generate_agents, validate_spec

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domain_packs" / "japan_religion"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT / "experiments"))

import run_sweep as sweep_mod  # noqa: E402


def _spec():
    return read_yaml(DOMAIN / "data" / "population.yaml")


def _beliefs():
    return read_tsv(DOMAIN / "data" / "beliefs.tsv")


# --- バリデーション（spec の silent failure 防止） ---


def test_declared_spec_passes_validation():
    validate_spec(_spec(), _beliefs())


def test_center_out_of_clamp_free_range_raises():
    """center ± spread が [0,1] を外れる spec は ValueError（生成時クランプの構造的排除）。"""
    spec = copy.deepcopy(_spec())
    spec["roles"][0]["traits"]["anxiety"] = 0.95  # 0.95 + 0.12 > 1.0
    with pytest.raises(ValueError, match="leaves"):
        validate_spec(spec, _beliefs())


def test_belief_probability_sum_must_be_one():
    spec = copy.deepcopy(_spec())
    spec["roles"][0]["beliefs"]["inari_belief"] = 0.5  # 合計が 1.0 を超える
    with pytest.raises(ValueError, match="sum"):
        validate_spec(spec, _beliefs())


def test_unknown_belief_id_raises():
    spec = copy.deepcopy(_spec())
    spec["roles"][0]["beliefs"] = {"bogus_belief": 1.0}
    with pytest.raises(ValueError, match="unknown beliefs"):
        validate_spec(spec, _beliefs())


def test_missing_trait_raises():
    spec = copy.deepcopy(_spec())
    del spec["roles"][0]["traits"]["tolerance"]
    with pytest.raises(ValueError, match="missing traits"):
        validate_spec(spec, _beliefs())


def test_wrong_total_raises():
    spec = copy.deepcopy(_spec())
    spec["total"] = 61
    with pytest.raises(ValueError, match="sum to"):
        validate_spec(spec, _beliefs())


# --- 生成の決定性とスキーマ ---


def test_generate_is_deterministic():
    r1 = generate_agents(_spec(), random.Random(7), _beliefs())
    r2 = generate_agents(_spec(), random.Random(7), _beliefs())
    assert r1 == r2


def test_generate_matches_golden_fixture():
    """seed=1 の生成結果を golden fixture で byte 固定（生成仕様そのものの検証）。"""
    rows = generate_agents(_spec(), random.Random(1), _beliefs())
    with (FIXTURES / "population_seed1.tsv").open(encoding="utf-8", newline="") as f:
        golden = list(csv.DictReader(f, delimiter="\t"))
    assert rows == golden


def test_generate_count_ids_and_schema():
    rows = generate_agents(_spec(), random.Random(3), _beliefs())
    assert len(rows) == 60
    ids = [r["id"] for r in rows]
    assert ids == [f"P{i:03d}" for i in range(1, 61)]  # 連番・一意
    agents_tsv_cols = set(read_tsv(DOMAIN / "data" / "agents.tsv")[0].keys())
    assert set(rows[0].keys()) == agents_tsv_cols  # agents.tsv 互換スキーマ
    for r in rows:
        for key in TRAIT_KEYS:
            assert 0.0 <= float(r[key]) <= 1.0
        assert 0.50 <= float(r["belief_strength"]) <= 0.80


def test_role_counts_match_spec():
    rows = generate_agents(_spec(), random.Random(5), _beliefs())
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["role"]] = counts.get(r["role"], 0) + 1
    expected = {role["id"]: role["count"] for role in _spec()["roles"]}
    assert counts == expected


# --- agents_rows 注入（エンジン） ---


def test_agents_rows_none_reads_agents_tsv_unchanged(tmp_path):
    """None なら従来どおり（v0.2.0 既知結果のピン留めは test_sweep 側にもあるが、明示注入と比較）。"""
    base = run_scenario(DOMAIN, "famine.yaml", tmp_path / "a", seed=42)
    tsv_rows = read_tsv(DOMAIN / "data" / "agents.tsv")
    injected = run_scenario(DOMAIN, "famine.yaml", tmp_path / "b", seed=42, agents_rows=tsv_rows)
    assert base["final_shares"] == injected["final_shares"]
    assert (tmp_path / "a" / "agent_turns.tsv").read_bytes() == (
        tmp_path / "b" / "agent_turns.tsv"
    ).read_bytes()


def test_sampled_population_runs_with_60_agents(tmp_path):
    rows = generate_agents(_spec(), random.Random(11), _beliefs())
    summary = run_scenario(DOMAIN, "famine.yaml", tmp_path, seed=11, agents_rows=rows)
    assert summary["agents"] == 60


# --- sampled60 スイープの決定性（縮小版） ---


def test_sampled60_sweep_determinism(tmp_path):
    sweep_mod.run_sweep("tolerance", tmp_path / "r1", seeds=[1, 2], population="sampled60")
    sweep_mod.run_sweep("tolerance", tmp_path / "r2", seeds=[1, 2], population="sampled60")
    assert (tmp_path / "r1" / "tolerance" / "results.tsv").read_bytes() == (
        tmp_path / "r2" / "tolerance" / "results.tsv"
    ).read_bytes()
    assert (tmp_path / "r1" / "tolerance" / "stats.json").read_bytes() == (
        tmp_path / "r2" / "tolerance" / "stats.json"
    ).read_bytes()
