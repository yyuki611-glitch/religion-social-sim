"""母集団生成（v0.5.0、設計: tasks/todo.md rev3）。

seed ごとに別の村人集団をロール原型からサンプリングする。

決定性の規約（テストで byte 固定）:
- spec 記載のロール順 → ロール内で count 人分のエージェントループ
- 各エージェントにつき rng 呼び出しは次の順序で固定する:
  (1) TRAIT_KEYS 順に8特性を rng.uniform(center - spread, center + spread)
  (2) 信仰強度を rng.uniform(*strength_range)
  (3) 初期信仰を rng.choices(belief_ids, weights)[0]
- 渡された rng のみ使用。グローバル random は使わない
- ID は P001〜P060 の連番
"""
from __future__ import annotations

import random
from typing import Any

from sim_core.engine import TRAIT_KEYS

# center ± spread が [0,1] に収まることの下限/上限（生成時クランプを構造的に排除する）
_PROB_TOLERANCE = 1e-9


def validate_spec(spec: dict[str, Any], belief_rows: list[dict[str, str]]) -> None:
    """population spec の silent failure を防ぐバリデーション。違反は ValueError。

    チェック項目（設計 rev3 で宣言した5点）:
    (1) 初期信仰 ID が beliefs.tsv に存在する
    (2) 各ロールの信仰確率の合計が 1.0（誤差 1e-9）
    (3) TRAIT_KEYS の全8特性が定義済み
    (4) ロール人数の合計が spec["total"] と一致
    (5) 全 center が [spread, 1 - spread] に収まる（= クランプ前の範囲が [0,1] 内）
    """
    spread = float(spec["spread"])
    known_beliefs = {row["id"] for row in belief_rows}
    roles = spec["roles"]

    total = sum(int(r["count"]) for r in roles)
    if total != int(spec["total"]):
        raise ValueError(f"role counts sum to {total}, expected {spec['total']}")

    for role in roles:
        rid = role["id"]
        missing = set(TRAIT_KEYS) - set(role["traits"])
        if missing:
            raise ValueError(f"role {rid}: missing traits {sorted(missing)}")
        for trait, center in role["traits"].items():
            if trait not in TRAIT_KEYS:
                raise ValueError(f"role {rid}: unknown trait {trait}")
            if not (spread <= float(center) <= 1.0 - spread):
                raise ValueError(
                    f"role {rid}: trait {trait} center {center} ± {spread} leaves [0,1]"
                )
        unknown = set(role["beliefs"]) - known_beliefs
        if unknown:
            raise ValueError(f"role {rid}: unknown beliefs {sorted(unknown)}")
        prob_sum = sum(float(p) for p in role["beliefs"].values())
        if abs(prob_sum - 1.0) > _PROB_TOLERANCE:
            raise ValueError(f"role {rid}: belief probabilities sum to {prob_sum}, expected 1.0")


def generate_agents(
    spec: dict[str, Any], rng: random.Random, belief_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """spec から agents.tsv 互換の行リストを決定的に生成する。"""
    validate_spec(spec, belief_rows)
    spread = float(spec["spread"])
    s_lo, s_hi = (float(x) for x in spec["strength_range"])

    rows: list[dict[str, str]] = []
    idx = 0
    for role in spec["roles"]:
        belief_ids = list(role["beliefs"].keys())
        weights = [float(role["beliefs"][b]) for b in belief_ids]
        for n in range(int(role["count"])):
            idx += 1
            traits = {
                key: rng.uniform(float(role["traits"][key]) - spread, float(role["traits"][key]) + spread)
                for key in TRAIT_KEYS
            }
            strength = rng.uniform(s_lo, s_hi)
            belief = rng.choices(belief_ids, weights=weights)[0]
            rows.append(
                {
                    "id": f"P{idx:03d}",
                    "label": f"{role['label']} {n + 1:02d}",
                    "role": role["id"],
                    **{key: f"{traits[key]:.4f}" for key in TRAIT_KEYS},
                    "current_belief": belief,
                    "belief_strength": f"{strength:.3f}",
                    "label_ja": f"{role['label_ja']}{n + 1:02d}",
                }
            )
    return rows
