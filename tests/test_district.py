"""郡モデル（v2.0、tasks/todo.md rev3）のテスト。

ミニ郡（16村×20人=320人）で高速に検証する。村数・隣接は本番 district.yaml と同一、
村サイズだけ縮小（ロール比は維持）。
"""
import copy
import random
import sys
from pathlib import Path

import pytest

from sim_core.domain_pack import read_tsv, read_yaml
from sim_core.engine import (
    BRIDGE_ROLES,
    district_perception,
    run_scenario,
)
import sim_core.engine as eng
from sim_core.population import generate_district, validate_district_spec

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domain_packs" / "japan_religion"
sys.path.insert(0, str(ROOT / "experiments"))

MINI_COUNTS = {
    "farmer": 13,
    "household": 2,
    "artisan": 1,
    "merchant": 1,
    "religious_specialist": 1,
    "elder": 1,
    "authority": 1,
}  # 計20人/村


def _spec(village_size=None, counts=None):
    spec = copy.deepcopy(read_yaml(DOMAIN / "data" / "district.yaml"))
    if village_size:
        spec["village_size"] = village_size
        for r in spec["roles"]:
            r["count"] = (counts or MINI_COUNTS)[r["id"]]
    return spec


def _beliefs():
    return read_tsv(DOMAIN / "data" / "beliefs.tsv")


# --- スペックと生成 ---


def test_full_spec_validates_and_generates_6400():
    spec = _spec()
    validate_district_spec(spec, _beliefs())
    rows = generate_district(spec, random.Random(1), _beliefs())
    assert len(rows) == 6400
    assert len({r["village"] for r in rows}) == 16
    assert rows[0]["id"] == "V01-P001" and rows[-1]["id"] == "V16-P400"
    assert all("village" in r for r in rows)


def test_generate_district_deterministic():
    spec = _spec(20)
    r1 = generate_district(spec, random.Random(7), _beliefs())
    r2 = generate_district(spec, random.Random(7), _beliefs())
    assert r1 == r2


def test_adjacency_validation():
    spec = _spec(20)
    spec["adjacency"]["V01"] = ["V02"]  # V02->V01 はあるが非対称にする
    spec["adjacency"]["V02"] = ["V03", "V06"]  # V01 を外す
    with pytest.raises(ValueError, match="symmetric"):
        validate_district_spec(spec, _beliefs())


def test_role_total_must_match_village_size():
    spec = _spec(20)
    spec["roles"][0]["count"] += 1
    with pytest.raises(ValueError, match="village_size"):
        validate_district_spec(spec, _beliefs())


# --- 知覚プロファイル（codex Q3 で宣言した境界） ---


def _toy_counts():
    counts = {
        "V01": {"a": 10.0, "b": 0.0},
        "V02": {"a": 0.0, "b": 20.0},
    }
    n = {"V01": 10.0, "V02": 20.0}
    adj = {"V01": ["V02"], "V02": ["V01"]}
    return counts, n, adj


def test_perceived_share_never_exceeds_one():
    counts, n, adj = _toy_counts()
    p = district_perception(counts, n, adj, ["a", "b"])
    for v in p:
        for prof in ["local", "bridge"]:
            c, denom = p[v][prof]
            for b, cnt in c.items():
                assert cnt / denom <= 1.0 + 1e-12


def test_bridge_perceives_adjacent_with_half_weight():
    counts, n, adj = _toy_counts()
    p = district_perception(counts, n, adj, ["a", "b"])
    c, denom = p["V01"]["bridge"]
    assert c["b"] == pytest.approx(10.0)  # 隣接村の20人 × 0.5
    assert denom == pytest.approx(20.0)  # 10 + 20×0.5
    lc, ln = p["V01"]["local"]
    assert lc["b"] == 0.0 and ln == 10.0  # 非橋渡しは自村のみ


def test_bridge_weight_zero_equals_local(monkeypatch):
    monkeypatch.setattr(eng, "BRIDGE_WEIGHT", 0.0)
    counts, n, adj = _toy_counts()
    p = district_perception(counts, n, adj, ["a", "b"])
    assert p["V01"]["bridge"] == p["V01"]["local"]


# --- エンジン郡モード ---


def test_district_requires_adjacency(tmp_path):
    spec = _spec(20)
    rows = generate_district(spec, random.Random(1), _beliefs())
    with pytest.raises(ValueError, match="adjacency"):
        run_scenario(DOMAIN, "baseline.yaml", tmp_path, seed=1, agents_rows=rows)


def test_district_deterministic_and_village_outputs(tmp_path):
    spec = _spec(20)
    rows = generate_district(spec, random.Random(1), _beliefs())
    s1 = run_scenario(
        DOMAIN, "famine.yaml", tmp_path / "a", seed=2, agents_rows=rows,
        district_adjacency=spec["adjacency"],
    )
    s2 = run_scenario(
        DOMAIN, "famine.yaml", tmp_path / "b", seed=2, agents_rows=rows,
        district_adjacency=spec["adjacency"],
    )
    assert s1 == s2
    assert (tmp_path / "a" / "agent_turns.tsv").read_bytes() == (
        tmp_path / "b" / "agent_turns.tsv"
    ).read_bytes()
    shares = read_tsv(tmp_path / "a" / "belief_shares.tsv")
    assert "village" in shares[0]
    step1_v01 = [r for r in shares if r["step"] == "1" and r["village"] == "V01"]
    assert sum(int(r["adherents"]) for r in step1_v01) == 20  # 村サイズと一致


def test_local_event_reaches_distance_one_only(tmp_path):
    """噂（origin=V06）の直接到達は発生村+隣接村の橋渡しまで（距離1の配線）。

    早期窓（step5-10）の稲荷改宗が V06 以外で起きる場合、それは隣接村
    （V02/V05/V07/V10）の橋渡し役に限られることを確認する。
    （距離2以遠は社会連鎖のみなので、5ステップの早期窓ではまず届かない）
    """
    spec = _spec(20)
    rows = generate_district(spec, random.Random(3), _beliefs())
    role_by_id = {r["id"]: r["role"] for r in rows}
    run_scenario(
        DOMAIN, "miracle_rumor.yaml", tmp_path, seed=3, agents_rows=rows,
        district_adjacency=spec["adjacency"],
    )
    conv = read_tsv(tmp_path / "conversions.tsv")
    early_inari = [
        c for c in conv
        if c["kind"] == "conversion" and c["to_belief"] == "inari_belief"
        and 5 <= int(c["step"]) <= 10
    ]
    assert early_inari, "発生村で早期改宗が起きるはず"
    adjacent = {"V02", "V05", "V07", "V10"}
    for c in early_inari:
        if c["village"] == "V06":
            continue
        assert c["village"] in adjacent, f"距離2以遠への直接到達: {c}"
        assert role_by_id[c["agent_id"]] in BRIDGE_ROLES, f"非橋渡しに直接到達: {c}"


def test_legacy_paths_unaffected(tmp_path):
    """village 列がない場合は既存挙動（v0.2.0 既知結果のピン留め）。"""
    result = run_scenario(DOMAIN, "famine.yaml", tmp_path, seed=42)
    assert result["conversions"] == 2 and result["retention_rate"] == 0.75
