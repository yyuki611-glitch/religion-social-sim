from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import csv
import yaml


@dataclass(frozen=True)
class DomainPack:
    name: str
    root: Path
    domain: dict[str, Any]

    def data_path(self, filename: str) -> Path:
        return self.root / "data" / filename

    def prompt_path(self, filename: str) -> Path:
        return self.root / "prompts" / filename

    def scenario_path(self, filename: str) -> Path:
        return self.root / "scenarios" / filename


def load_domain_pack(path: str | Path) -> DomainPack:
    root = Path(path)
    with (root / "domain.yaml").open("r", encoding="utf-8") as f:
        domain = yaml.safe_load(f)
    return DomainPack(name=domain["name"], root=root, domain=domain)


def read_tsv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def read_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

