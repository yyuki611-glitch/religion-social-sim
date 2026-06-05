"""validation/validation_plan.md の5項目をテストとして固定する。"""
from pathlib import Path

from sim_core.domain_pack import read_tsv
from sim_core.engine import run_scenario

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domain_packs" / "japan_religion"


def test_deterministic_same_seed(tmp_path):
    r1 = run_scenario(DOMAIN, "famine.yaml", tmp_path / "a", seed=42)
    r2 = run_scenario(DOMAIN, "famine.yaml", tmp_path / "b", seed=42)
    assert r1 == r2
    assert (tmp_path / "a" / "belief_shares.tsv").read_bytes() == (
        tmp_path / "b" / "belief_shares.tsv"
    ).read_bytes()


def test_baseline_keeps_local_belief_stable(tmp_path):
    result = run_scenario(DOMAIN, "baseline.yaml", tmp_path, seed=42)
    assert result["retention_rate"] >= 0.75


def test_famine_boosts_practical_and_salvation_beliefs(tmp_path):
    base = run_scenario(DOMAIN, "baseline.yaml", tmp_path / "base", seed=42)
    famine = run_scenario(DOMAIN, "famine.yaml", tmp_path / "famine", seed=42)
    coping_base = base["final_shares"]["inari_belief"] + base["final_shares"]["jodo_buddhism"]
    coping_famine = famine["final_shares"]["inari_belief"] + famine["final_shares"]["jodo_buddhism"]
    assert coping_famine > coping_base
    assert famine["retention_rate"] < 1.0


def test_miracle_rumor_creates_short_term_pressure(tmp_path):
    run_scenario(DOMAIN, "miracle_rumor.yaml", tmp_path, seed=42)
    conversions = read_tsv(tmp_path / "conversions.tsv")
    # 噂イベント（step 5）の直後〜15ステップ以内に対象信念への改宗が起きる
    early_to_inari = [
        c
        for c in conversions
        if c["to_belief"] == "inari_belief" and 5 <= int(c["step"]) <= 20
    ]
    assert early_to_inari


def test_every_conversion_has_reason_trace(tmp_path):
    for scenario in ["baseline.yaml", "famine.yaml", "miracle_rumor.yaml"]:
        out = tmp_path / scenario.replace(".yaml", "")
        run_scenario(DOMAIN, scenario, out, seed=42)
        for row in read_tsv(out / "conversions.tsv"):
            assert row["reason"].strip()


def test_outputs_separate_turns_and_aggregates(tmp_path):
    run_scenario(DOMAIN, "baseline.yaml", tmp_path, seed=42)
    for name in [
        "agent_turns.tsv",
        "belief_shares.tsv",
        "conversions.tsv",
        "events_log.tsv",
        "summary.json",
        "manifest.txt",
    ]:
        assert (tmp_path / name).exists(), name
    shares = read_tsv(tmp_path / "belief_shares.tsv")
    by_step: dict[str, int] = {}
    for row in shares:
        by_step[row["step"]] = by_step.get(row["step"], 0) + int(row["adherents"])
    assert set(by_step.values()) == {8}  # 各ステップの信者合計 = エージェント数
