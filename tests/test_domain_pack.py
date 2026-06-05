from pathlib import Path

from sim_core.domain_pack import load_domain_pack, read_tsv
from sim_core.engine import run_scenario


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = ROOT / "domain_packs" / "japan_religion"


def test_load_japan_religion_domain_pack():
    pack = load_domain_pack(DOMAIN)
    assert pack.name == "japan_religion"
    assert pack.domain["default_scenario"] == "baseline.yaml"


def test_beliefs_include_inari_and_jodo():
    beliefs = read_tsv(DOMAIN / "data" / "beliefs.tsv")
    ids = {row["id"] for row in beliefs}
    assert "inari_belief" in ids
    assert "jodo_buddhism" in ids


def test_smoke_run_writes_manifest(tmp_path):
    result = run_scenario(DOMAIN, "baseline.yaml", tmp_path)
    assert result["domain"] == "japan_religion"
    assert (tmp_path / "manifest.txt").exists()

