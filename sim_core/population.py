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


def validate_district_spec(spec: dict[str, Any], belief_rows: list[dict[str, str]]) -> None:
    """district spec（v2.0 郡モデル）のバリデーション。違反は ValueError。

    村ごとのロール定義は validate_spec と同じ規則（特性網羅・center範囲・確率合計・
    信仰ID存在）に従い、さらに (1) ロール人数合計 = village_size、
    (2) 隣接リストが対称かつ全村を網羅、(3) bridge_roles が roles に存在、を要求する。
    """
    role_total = sum(int(r["count"]) for r in spec["roles"])
    if role_total != int(spec["village_size"]):
        raise ValueError(f"role counts sum to {role_total}, expected village_size {spec['village_size']}")
    # ロール定義の検証は既存 validate_spec を村サイズで再利用
    validate_spec(
        {"total": spec["village_size"], "spread": spec["spread"], "roles": spec["roles"]},
        belief_rows,
    )
    villages = [f"V{i:02d}" for i in range(1, int(spec["villages"]) + 1)]
    adj = spec["adjacency"]
    if set(adj.keys()) != set(villages):
        raise ValueError("adjacency must cover exactly all villages")
    for v, neighbors in adj.items():
        for n in neighbors:
            if n not in adj:
                raise ValueError(f"adjacency: unknown village {n}")
            if v not in adj[n]:
                raise ValueError(f"adjacency not symmetric: {v} -> {n}")
            if n == v:
                raise ValueError(f"adjacency: self-loop at {v}")
    role_ids = {r["id"] for r in spec["roles"]}
    unknown_bridges = set(spec["bridge_roles"]) - role_ids
    if unknown_bridges:
        raise ValueError(f"unknown bridge_roles: {sorted(unknown_bridges)}")


def generate_district(
    spec: dict[str, Any], rng: random.Random, belief_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    """district spec から agents.tsv 互換 + `village` 列の行リストを決定的に生成する。

    rng 消費順序（決定性規約・テストで固定）: 村順（V01..V16）→ 村内ロール順（spec 記載順）
    → エージェント順。各エージェントの内部順序は generate_agents と同一
    （(1) TRAIT_KEYS 順の8特性 → (2) 信仰強度 → (3) 初期信仰）。
    ID は `V{村:02d}-P{村内連番:03d}`。
    """
    validate_district_spec(spec, belief_rows)
    spread = float(spec["spread"])
    s_lo, s_hi = (float(x) for x in spec["strength_range"])

    rows: list[dict[str, str]] = []
    for vi in range(1, int(spec["villages"]) + 1):
        village = f"V{vi:02d}"
        idx = 0
        for role in spec["roles"]:
            belief_ids = list(role["beliefs"].keys())
            weights = [float(role["beliefs"][b]) for b in belief_ids]
            for n in range(int(role["count"])):
                idx += 1
                traits = {
                    key: rng.uniform(
                        float(role["traits"][key]) - spread, float(role["traits"][key]) + spread
                    )
                    for key in TRAIT_KEYS
                }
                strength = rng.uniform(s_lo, s_hi)
                belief = rng.choices(belief_ids, weights=weights)[0]
                rows.append(
                    {
                        "id": f"{village}-P{idx:03d}",
                        "label": f"{role['label']} {n + 1:02d}",
                        "role": role["id"],
                        "village": village,
                        **{key: f"{traits[key]:.4f}" for key in TRAIT_KEYS},
                        "current_belief": belief,
                        "belief_strength": f"{strength:.3f}",
                        "label_ja": f"{role['label_ja']}{n + 1:02d}",
                    }
                )
    return rows


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
