"""ビューワー生成の回帰テスト（v1.0.1）。

v1.0.0 で「母集団サンプリング run のビューワーが真っ暗」の実害が出た。
原因: agents 辞書が agents.tsv（8人）由来で、run の村人（P001〜）と不一致のまま
テンプレートの描画ループに渡っていた。agents 辞書は「run に登場する村人と
完全一致」でなければならない。
"""
import random
import sys
from pathlib import Path

from sim_core.domain_pack import read_tsv, read_yaml
from sim_core.engine import run_scenario
from sim_core.population import generate_agents

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domain_packs" / "japan_religion"
sys.path.insert(0, str(ROOT / "experiments"))

from render_viewer import build_data  # noqa: E402


def test_viewer_agents_match_run_for_sampled_population(tmp_path):
    """60人サンプリング村の run: agents 辞書が run の村人と完全一致し、日本語名が引ける。"""
    spec = read_yaml(DOMAIN / "data" / "population.yaml")
    beliefs = read_tsv(DOMAIN / "data" / "beliefs.tsv")
    rows = generate_agents(spec, random.Random(10**6 + 1), beliefs)
    run_scenario(DOMAIN, "famine.yaml", tmp_path, seed=1, agents_rows=rows)

    data = build_data(tmp_path, DOMAIN)
    turn_ids = {t["agent_id"] for t in data["agent_turns"]}
    assert set(data["agents"].keys()) == turn_ids  # 過不足なし（8人混入も欠落もなし）
    assert len(turn_ids) == 60
    # 日本語化の補完（Farmer 01 → 農民01）
    assert data["agents"]["P001"]["label_ja"].startswith("農民")


def test_viewer_agents_match_run_for_fixed8(tmp_path):
    """従来の8人村 run: agents.tsv の日本語名がそのまま使われる（後方互換）。"""
    run_scenario(DOMAIN, "famine.yaml", tmp_path, seed=42)
    data = build_data(tmp_path, DOMAIN)
    turn_ids = {t["agent_id"] for t in data["agent_turns"]}
    assert set(data["agents"].keys()) == turn_ids
    assert len(turn_ids) == 8
    assert data["agents"]["A01"]["label_ja"] == "米農家"
