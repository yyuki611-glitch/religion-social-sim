from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sim_core.belief import conversion_pressure
from sim_core.domain_pack import load_domain_pack, read_tsv, read_yaml

# --- チューニング定数（信念スコアの重み） ---
W_APPEAL = 0.50  # 信念の訴求タグと本人特性の一致
W_COMMUNITY = 0.35  # 周囲の信者割合 × 共同体依存
W_INERTIA_STRENGTH = 0.25  # 現信仰の強度による慣性
W_INERTIA_TRADITION = 0.10  # 伝統志向による慣性
W_SECONDARY = 0.10  # 習合済みの信念への親和
EVENT_GAIN = 1.6  # イベント効果の全体係数
EVENT_DECAY = 0.92  # イベント効果の1ステップごとの減衰率
EVENT_MIN_WEIGHT = 0.05  # この重みを下回ったイベントは失効
STRENGTH_CAP = 0.90  # 通常成長での信仰強度の上限（鉄壁化を防ぐ）
PRESSURE_STEPS_TO_CONVERT = 3  # 改宗に必要な連続圧力ステップ数
SYNCRETISM_TOLERANCE = 0.65  # 習合が起きる寛容度の下限（syncretism_mode="threshold" のみ使用）

# --- graded 習合メカニズム（v0.6.0、設計: tasks/todo.md rev3）---
# 改宗トリガー時の「旧信仰を保持（習合的改宗）か完全改宗か」を競合スコアで決める。
# 重みは threshold 実験の改宗時 gap 分布（中央値0.18 / p90 0.29、v0.5.0 タグ時点の
# famine 20run・450件から較正）で固定済み。スイープE実行後の変更は禁止。
W_KEEP_TOLERANCE = 0.50  # 寛容: 併存への抵抗の低さ
W_KEEP_STRENGTH = 0.30  # 旧信仰への愛着（改宗時点の侵食後 strength）
W_KEEP_TRADITION = 0.20  # 伝統: 捨てることへの抵抗
GAP_REF = 0.30  # drop 項の正規化基準（観測 p90。これ以上で頭打ち）
W_DROP_NOVELTY = 0.35  # 新奇志向: 過去を引きずらない
# 副次取り込み（改宗なしの習合）の確率。最大0.50で意図的に頭打ち（改宗より稀な現象）
W_SYNC_OPEN_TOLERANCE = 0.25
W_SYNC_OPEN_NOVELTY = 0.15
W_SYNC_OPEN_ANXIETY = 0.10

# --- 郡モデル（v2.0、設計: tasks/todo.md rev3）---
# 橋渡し役（御師・講・旅僧・行商の史実に基づく。隣接村を知覚できる唯一の存在）
BRIDGE_ROLES = {"religious_specialist", "merchant"}
# 橋渡しの隣接村知覚の重み。0=村内のみ（非橋渡しと同一挙動）/ 0.5=半分よそ者 /
# 1.0=隣接村を自村と同格に知覚。較正データは存在しない設計上の仮定（README で開示）
BRIDGE_WEIGHT = 0.5
# local イベントが隣接村の橋渡しに届くときの減衰。発生村は 1.0、非隣接・非橋渡しは 0
BRIDGE_EVENT_WEIGHT = 0.5

# 信念の訴求タグ → エージェント特性のマッピング
APPEAL_TRAITS: dict[str, list[str]] = {
    "kinship": ["tradition_orientation"],
    "land": ["tradition_orientation"],
    "ritual_continuity": ["tradition_orientation"],
    "community": ["community_dependence"],
    "ancestor": ["tradition_orientation", "community_dependence"],
    "local_protection": ["community_dependence"],
    "practical_benefit": ["practical_benefit_need"],
    "commerce": ["practical_benefit_need", "novelty_openness"],
    "harvest": ["practical_benefit_need"],
    "water": ["practical_benefit_need"],
    "weather": ["practical_benefit_need"],
    "agriculture": ["practical_benefit_need"],
    "salvation": ["salvation_need"],
    "grief": ["salvation_need"],
    "afterlife": ["salvation_need"],
    "discipline": ["novelty_openness"],
    "elite_culture": ["novelty_openness", "authority_trust"],
    "self_cultivation": ["novelty_openness"],
    "nature": ["novelty_openness"],
    "awe": ["salvation_need", "novelty_openness"],
    "ascetic_power": ["salvation_need", "novelty_openness"],
}

TRAIT_KEYS = [
    "anxiety",
    "community_dependence",
    "authority_trust",
    "tradition_orientation",
    "novelty_openness",
    "salvation_need",
    "practical_benefit_need",
    "tolerance",
]


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def keep_decision(
    tolerance: float, old_strength: float, tradition: float, novelty: float, gap: float
) -> tuple[bool, float, float]:
    """graded 習合: 改宗トリガー時に旧信仰を副次として保持するか（習合的改宗）。

    (keep するか, keep_score, drop_score) を返す。同値は drop（完全改宗）。
    """
    keep_score = (
        W_KEEP_TOLERANCE * tolerance
        + W_KEEP_STRENGTH * old_strength
        + W_KEEP_TRADITION * tradition
    )
    drop_score = min(1.0, gap / GAP_REF) + W_DROP_NOVELTY * novelty
    return keep_score > drop_score, keep_score, drop_score


def syncretism_openness(tolerance: float, novelty: float, anxiety: float) -> float:
    """graded 習合: 改宗なしの副次取り込みが成立する確率（最大0.50）。"""
    return (
        W_SYNC_OPEN_TOLERANCE * tolerance
        + W_SYNC_OPEN_NOVELTY * novelty
        + W_SYNC_OPEN_ANXIETY * anxiety
    )


@dataclass
class AgentState:
    id: str
    label: str
    role: str
    traits: dict[str, float]
    belief: str
    strength: float
    initial_belief: str
    secondary_belief: str | None = None
    pressure: dict[str, int] = field(default_factory=dict)
    syncretism_pressure: dict[str, int] = field(default_factory=dict)
    village: str = ""  # 郡モードのみ使用（legacy では空のまま。挙動に影響しない）


@dataclass
class ActiveEvent:
    row: dict[str, str]
    start_step: int

    def weight(self, step: int) -> float:
        return EVENT_DECAY ** (step - self.start_step)

    def signal(self, key: str) -> float:
        return float(self.row.get(key) or 0.0)


def _load_agents(rows: list[dict[str, str]]) -> list[AgentState]:
    agents = []
    for row in rows:
        traits = {k: float(row[k]) for k in TRAIT_KEYS}
        agents.append(
            AgentState(
                id=row["id"],
                label=row["label"],
                role=row["role"],
                traits=traits,
                belief=row["current_belief"],
                strength=float(row["belief_strength"]),
                initial_belief=row["current_belief"],
            )
        )
    return agents


def _appeal_score(agent: AgentState, appeal: str) -> float:
    tags = [t for t in appeal.split(",") if t]
    if not tags:
        return 0.0
    total = 0.0
    for tag in tags:
        traits = APPEAL_TRAITS.get(tag, [])
        if traits:
            total += sum(agent.traits[t] for t in traits) / len(traits)
    return total / len(tags)


def _belief_score(
    agent: AgentState,
    belief_id: str,
    appeal: str,
    shares: dict[str, int],
    n_agents: int,
    active_events: list[ActiveEvent],
    step: int,
) -> tuple[float, str]:
    """そのステップでの、エージェントから見た信念の引力。(score, 主要因) を返す。"""
    parts: dict[str, float] = {}
    parts["appeal"] = _appeal_score(agent, appeal) * W_APPEAL

    others = shares.get(belief_id, 0) - (1 if agent.belief == belief_id else 0)
    parts["community"] = (others / max(1, n_agents - 1)) * agent.traits["community_dependence"] * W_COMMUNITY

    if agent.belief == belief_id:
        parts["inertia"] = agent.strength * W_INERTIA_STRENGTH + agent.traits["tradition_orientation"] * W_INERTIA_TRADITION
    if agent.secondary_belief == belief_id:
        parts["syncretism"] = W_SECONDARY

    event_total = 0.0
    event_names = []
    for ev in active_events:
        if ev.row.get("target_belief") != belief_id:
            continue
        w = ev.weight(step)
        # scandal は対象信念に向かう「悪い噂」なので、噂シグナルは反発に働く
        rumor_sign = -1.0 if ev.row.get("type") == "scandal" else 1.0
        contrib = EVENT_GAIN * w * (
            ev.signal("authority_signal") * agent.traits["authority_trust"]
            + rumor_sign * ev.signal("rumor_signal") * agent.traits["novelty_openness"]
            + ev.signal("community_signal") * agent.traits["community_dependence"]
            + max(ev.signal("anxiety_delta"), 0.0) * 0.3
        )
        event_total += contrib
        if abs(contrib) > 0.01:
            event_names.append(ev.row["id"])
    if event_total:
        parts[f"event:{'+'.join(event_names)}"] = event_total

    score = sum(parts.values())
    top = max(parts, key=lambda k: parts[k]) if parts else "none"
    return score, top


def _apply_generation_shift(agents: list[AgentState]) -> None:
    """世代交代：伝統志向と信仰強度が薄まり、新奇への開放度が上がる。"""
    for agent in agents:
        agent.traits["tradition_orientation"] = _clamp(agent.traits["tradition_orientation"] * 0.85)
        agent.traits["novelty_openness"] = _clamp(agent.traits["novelty_openness"] + 0.08)
        agent.strength = _clamp(agent.strength * 0.85, 0.05)


def run_scenario(
    domain_dir: str | Path,
    scenario_file: str,
    output_dir: str | Path,
    seed: int = 42,
    trait_adjustments: dict[str, float] | None = None,
    agents_rows: list[dict[str, str]] | None = None,
    syncretism_mode: str = "threshold",
    district_adjacency: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """シナリオを1回実行する。

    trait_adjustments: 特性名 → 加算デルタ。全エージェントの該当特性に
    加算して 0–1 にクランプする（スイープ実験用）。None なら既存挙動と完全に同一。
    乗算でなく加算なのは、上限クランプで条件間の差が潰れるのを避けるため。

    agents_rows: agents.tsv の代わりに使うエージェント行（母集団サンプリング用）。
    None なら従来どおり agents.tsv を読む（既存挙動と完全に同一）。

    syncretism_mode: "threshold"（既定）= tolerance >= 0.65 の二値ゲート（v0.5.0 までと
    byte 同一）。"graded" = keep/drop 競合スコア + 確率的副次取り込み（v0.6.0、H6 検証用）。
    """
    if syncretism_mode not in ("threshold", "graded"):
        raise ValueError(f"unknown syncretism_mode: {syncretism_mode}")
    pack = load_domain_pack(domain_dir)
    scenario = read_yaml(pack.scenario_path(scenario_file))
    agent_rows = agents_rows if agents_rows is not None else read_tsv(pack.data_path("agents.tsv"))
    belief_rows = read_tsv(pack.data_path("beliefs.tsv"))
    event_rows = read_tsv(pack.data_path("events.tsv"))

    rng = random.Random(seed)

    # 郡モード（v2.0）: agents_rows に village 列がある場合のみ。legacy パスは以降1行も変えない
    if agent_rows and "village" in agent_rows[0]:
        if district_adjacency is None:
            raise ValueError("district mode requires district_adjacency")
        return _run_district(
            pack,
            scenario,
            agent_rows,
            belief_rows,
            event_rows,
            rng,
            Path(output_dir),
            seed,
            trait_adjustments,
            syncretism_mode,
            district_adjacency,
        )

    agents = _load_agents(agent_rows)
    if trait_adjustments:
        unknown = set(trait_adjustments) - set(TRAIT_KEYS)
        if unknown:
            raise ValueError(f"unknown trait keys: {sorted(unknown)}")
        for agent in agents:
            for trait, delta in trait_adjustments.items():
                agent.traits[trait] = _clamp(agent.traits[trait] + delta)
    beliefs = {row["id"]: row for row in belief_rows}
    events_by_id = {row["id"]: row for row in event_rows}
    schedule: dict[int, list[str]] = {}
    for item in scenario.get("events", []):
        schedule.setdefault(int(item["step"]), []).append(item["id"])

    steps = int(scenario.get("steps", pack.domain.get("initial_steps", 50)))
    active_events: list[ActiveEvent] = []

    agent_turns: list[dict[str, Any]] = []
    share_turns: list[dict[str, Any]] = []
    conversions: list[dict[str, Any]] = []
    event_log: list[dict[str, Any]] = []

    for step in range(1, steps + 1):
        # 1. 予定イベントの発火
        for event_id in schedule.get(step, []):
            row = events_by_id[event_id]
            event_log.append({"step": step, "event_id": event_id, "type": row["type"]})
            if row["type"] == "generation":
                _apply_generation_shift(agents)
            else:
                active_events.append(ActiveEvent(row=row, start_step=step))
        active_events = [ev for ev in active_events if ev.weight(step) >= EVENT_MIN_WEIGHT]

        # 2. 現在の信者数（このステップ開始時点で固定）
        shares: dict[str, int] = {}
        for agent in agents:
            shares[agent.belief] = shares.get(agent.belief, 0) + 1

        # 3. 各エージェントの更新
        for agent in agents:
            anxiety = _clamp(
                agent.traits["anxiety"]
                + sum(ev.signal("anxiety_delta") * ev.weight(step) for ev in active_events)
            )
            scores: dict[str, tuple[float, str]] = {}
            for belief_id, row in beliefs.items():
                scores[belief_id] = _belief_score(
                    agent, belief_id, row["appeal"], shares, len(agents), active_events, step
                )

            current_score = scores[agent.belief][0]
            challengers = {b: s for b, (s, _) in scores.items() if b != agent.belief}
            best_other = max(challengers, key=lambda b: challengers[b])
            gap = challengers[best_other] - current_score

            openness = conversion_pressure(
                anxiety=anxiety,
                salvation_need=agent.traits["salvation_need"],
                practical_benefit_need=agent.traits["practical_benefit_need"],
                community_pressure=agent.traits["community_dependence"] * (1 - shares.get(agent.belief, 0) / len(agents)),
                authority_signal=max((ev.signal("authority_signal") * ev.weight(step) for ev in active_events), default=0.0),
                rumor_signal=max((ev.signal("rumor_signal") * ev.weight(step) for ev in active_events), default=0.0),
            )

            threshold = max(0.04, 0.06 + 0.12 * agent.traits["tradition_orientation"] - 0.06 * agent.traits["novelty_openness"])

            # 信仰強度の更新（通常成長は STRENGTH_CAP 止まり：鉄壁化を防ぐ）
            if gap <= 0:
                agent.strength = _clamp(agent.strength + 0.01, 0.05, STRENGTH_CAP)
            else:
                agent.strength = _clamp(agent.strength - (0.02 + 0.04 * gap), 0.05)

            # 改宗圧力の累積
            if gap > threshold:
                agent.pressure[best_other] = agent.pressure.get(best_other, 0) + 1
            else:
                agent.pressure = {b: c - 1 for b, c in agent.pressure.items() if c > 1}

            converted = False
            if agent.pressure.get(best_other, 0) >= PRESSURE_STEPS_TO_CONVERT and rng.random() < openness:
                reason = (
                    f"gap={gap:.2f} threshold={threshold:.2f} openness={openness:.2f} "
                    f"pull={scores[best_other][1]} anxiety={anxiety:.2f}"
                )
                old = agent.belief
                if syncretism_mode == "graded":
                    keep_old_as_secondary, keep_s, drop_s = keep_decision(
                        agent.traits["tolerance"],
                        agent.strength,
                        agent.traits["tradition_orientation"],
                        agent.traits["novelty_openness"],
                        gap,
                    )
                    reason += f" keep={keep_s:.2f} drop={drop_s:.2f}"
                else:
                    keep_old_as_secondary = agent.traits["tolerance"] >= SYNCRETISM_TOLERANCE
                agent.secondary_belief = old if keep_old_as_secondary else None
                agent.belief = best_other
                agent.strength = _clamp(0.35 + 0.3 * challengers[best_other], 0.05)
                agent.pressure = {}
                agent.syncretism_pressure = {}
                conversions.append(
                    {
                        "step": step,
                        "agent_id": agent.id,
                        "kind": "conversion",
                        "from_belief": old,
                        "to_belief": best_other,
                        "reason": reason,
                    }
                )
                converted = True

            # 習合（改宗には至らないが、副次信仰として取り込む）
            if syncretism_mode == "graded":
                # graded: tolerance の二値ゲートを外し、圧力到達時に確率判定。
                # rng 消費はこの分岐内でのみ発生（threshold パスの rng 消費列は不変）
                if (
                    not converted
                    and agent.secondary_belief != best_other
                    and threshold * 0.5 < gap <= threshold
                ):
                    agent.syncretism_pressure[best_other] = agent.syncretism_pressure.get(best_other, 0) + 1
                    if agent.syncretism_pressure[best_other] >= PRESSURE_STEPS_TO_CONVERT:
                        sync_p = syncretism_openness(
                            agent.traits["tolerance"],
                            agent.traits["novelty_openness"],
                            anxiety,
                        )
                        if rng.random() < sync_p:
                            agent.secondary_belief = best_other
                            agent.syncretism_pressure = {}
                            conversions.append(
                                {
                                    "step": step,
                                    "agent_id": agent.id,
                                    "kind": "syncretism",
                                    "from_belief": agent.belief,
                                    "to_belief": best_other,
                                    "reason": (
                                        f"sync_p={sync_p:.2f} tolerance={agent.traits['tolerance']:.2f} "
                                        f"gap={gap:.2f} pull={scores[best_other][1]}"
                                    ),
                                }
                            )
                        else:
                            agent.syncretism_pressure[best_other] = 0
            elif (
                not converted
                and agent.traits["tolerance"] >= SYNCRETISM_TOLERANCE
                and agent.secondary_belief != best_other
                and threshold * 0.5 < gap <= threshold
            ):
                agent.syncretism_pressure[best_other] = agent.syncretism_pressure.get(best_other, 0) + 1
                if agent.syncretism_pressure[best_other] >= PRESSURE_STEPS_TO_CONVERT:
                    agent.secondary_belief = best_other
                    agent.syncretism_pressure = {}
                    conversions.append(
                        {
                            "step": step,
                            "agent_id": agent.id,
                            "kind": "syncretism",
                            "from_belief": agent.belief,
                            "to_belief": best_other,
                            "reason": f"tolerance={agent.traits['tolerance']:.2f} gap={gap:.2f} pull={scores[best_other][1]}",
                        }
                    )

            agent_turns.append(
                {
                    "step": step,
                    "agent_id": agent.id,
                    "label": agent.label,
                    "belief": agent.belief,
                    "secondary_belief": agent.secondary_belief or "",
                    "strength": round(agent.strength, 3),
                    "anxiety": round(anxiety, 3),
                    "openness": round(openness, 3),
                    "top_pull": best_other,
                    "gap": round(gap, 3),
                }
            )

        # 4. ステップ末の信念分布を記録
        end_shares: dict[str, list[float]] = {}
        for agent in agents:
            end_shares.setdefault(agent.belief, []).append(agent.strength)
        for belief_id in beliefs:
            strengths = end_shares.get(belief_id, [])
            share_turns.append(
                {
                    "step": step,
                    "belief_id": belief_id,
                    "adherents": len(strengths),
                    "avg_strength": round(sum(strengths) / len(strengths), 3) if strengths else 0.0,
                }
            )

    # --- 出力 ---
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    def write_tsv(name: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
        with (out / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

    write_tsv(
        "agent_turns.tsv",
        agent_turns,
        ["step", "agent_id", "label", "belief", "secondary_belief", "strength", "anxiety", "openness", "top_pull", "gap"],
    )
    write_tsv("belief_shares.tsv", share_turns, ["step", "belief_id", "adherents", "avg_strength"])
    write_tsv("conversions.tsv", conversions, ["step", "agent_id", "kind", "from_belief", "to_belief", "reason"])
    write_tsv("events_log.tsv", event_log, ["step", "event_id", "type"])

    retention = sum(1 for a in agents if a.belief == a.initial_belief) / len(agents)
    final_shares = {b: 0 for b in beliefs}
    for agent in agents:
        final_shares[agent.belief] += 1

    summary = {
        "domain": pack.name,
        "scenario": scenario["id"],
        "seed": seed,
        "trait_adjustments": dict(trait_adjustments) if trait_adjustments else {},
        "steps": steps,
        "agents": len(agents),
        "beliefs": len(beliefs),
        "events": len(event_rows),
        "conversions": sum(1 for c in conversions if c["kind"] == "conversion"),
        "syncretisms": sum(1 for c in conversions if c["kind"] == "syncretism"),
        "retention_rate": round(retention, 3),
        "final_shares": final_shares,
        "final_agents": [
            {
                "id": a.id,
                "label": a.label,
                "belief": a.belief,
                "secondary_belief": a.secondary_belief,
                "strength": round(a.strength, 3),
            }
            for a in agents
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = out / "manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                f"domain={pack.name}",
                f"scenario={scenario['id']}",
                f"agents={len(agents)}",
                f"beliefs={len(beliefs)}",
                f"events={len(event_rows)}",
                f"steps={steps}",
                f"conversions={summary['conversions']}",
                f"syncretisms={summary['syncretisms']}",
                f"retention_rate={summary['retention_rate']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return summary


# =====================================================================
# 郡モード（v2.0）。legacy ループの複製 + 村内シェア + 橋渡し知覚 + local イベント。
# 設計判断（tasks/todo.md rev3）: legacy 分岐との helper 共通化は禁止——
# コード重複を許容して byte 互換を守る。
# =====================================================================


@dataclass
class _DistrictEvent:
    row: dict[str, str]
    start_step: int
    origin: str | None  # None = regional（全村フル）/ "V06" 等 = local

    def weight(self, step: int) -> float:
        return EVENT_DECAY ** (step - self.start_step)

    def signal(self, key: str) -> float:
        return float(self.row.get(key) or 0.0)


def _event_factor(ev: _DistrictEvent, agent: AgentState, adjacency: dict[str, list[str]]) -> float:
    """local イベントの到達係数。発生村=1.0 / 隣接村の橋渡し=BRIDGE_EVENT_WEIGHT / 他=0。"""
    if ev.origin is None:
        return 1.0
    if agent.village == ev.origin:
        return 1.0
    if agent.role in BRIDGE_ROLES and ev.origin in adjacency.get(agent.village, []):
        return BRIDGE_EVENT_WEIGHT
    return 0.0


def _belief_score_district(
    agent: AgentState,
    belief_id: str,
    appeal: str,
    perceived_counts: dict[str, float],
    perceived_n: float,
    active_events: list[_DistrictEvent],
    step: int,
    ev_factors: list[float],
) -> tuple[float, str]:
    """legacy _belief_score の郡版。シェアは知覚プロファイル、イベントは到達係数つき。"""
    parts: dict[str, float] = {}
    parts["appeal"] = _appeal_score(agent, appeal) * W_APPEAL

    others = perceived_counts.get(belief_id, 0.0) - (1.0 if agent.belief == belief_id else 0.0)
    parts["community"] = (
        (others / max(1.0, perceived_n - 1.0)) * agent.traits["community_dependence"] * W_COMMUNITY
    )

    if agent.belief == belief_id:
        parts["inertia"] = (
            agent.strength * W_INERTIA_STRENGTH
            + agent.traits["tradition_orientation"] * W_INERTIA_TRADITION
        )
    if agent.secondary_belief == belief_id:
        parts["syncretism"] = W_SECONDARY

    event_total = 0.0
    event_names = []
    for ev, factor in zip(active_events, ev_factors):
        if factor == 0.0 or ev.row.get("target_belief") != belief_id:
            continue
        w = ev.weight(step) * factor
        rumor_sign = -1.0 if ev.row.get("type") == "scandal" else 1.0
        contrib = EVENT_GAIN * w * (
            ev.signal("authority_signal") * agent.traits["authority_trust"]
            + rumor_sign * ev.signal("rumor_signal") * agent.traits["novelty_openness"]
            + ev.signal("community_signal") * agent.traits["community_dependence"]
            + max(ev.signal("anxiety_delta"), 0.0) * 0.3
        )
        event_total += contrib
        if abs(contrib) > 0.01:
            event_names.append(ev.row["id"])
    if event_total:
        parts[f"event:{'+'.join(event_names)}"] = event_total

    score = sum(parts.values())
    top = max(parts, key=lambda k: parts[k]) if parts else "none"
    return score, top


def district_perception(
    counts_by_v: dict[str, dict[str, float]],
    n_by_v: dict[str, float],
    adjacency: dict[str, list[str]],
    belief_ids: list[str],
) -> dict[str, dict[str, tuple[dict[str, float], float]]]:
    """村×{local, bridge} の知覚プロファイル (weighted_counts, weighted_denominator)。

    非橋渡し = (自村counts, 自村n)。橋渡し = (自村 + Σ隣接村×BRIDGE_WEIGHT, n も同様)。
    counts <= denominator が成分ごとに成立するため知覚シェアは常に <= 1.0。
    BRIDGE_WEIGHT=0 なら bridge プロファイルは local と一致する（非橋渡しと同一挙動）。
    """
    perceived: dict[str, dict[str, tuple[dict[str, float], float]]] = {}
    for v in counts_by_v:
        own_counts, own_n = counts_by_v[v], n_by_v[v]
        adj = adjacency.get(v, [])
        bridge_counts = {
            b: own_counts[b] + BRIDGE_WEIGHT * sum(counts_by_v[a][b] for a in adj)
            for b in belief_ids
        }
        bridge_n = own_n + BRIDGE_WEIGHT * sum(n_by_v[a] for a in adj)
        perceived[v] = {"local": (own_counts, own_n), "bridge": (bridge_counts, bridge_n)}
    return perceived


def _run_district(
    pack,
    scenario: dict[str, Any],
    agent_rows: list[dict[str, str]],
    belief_rows: list[dict[str, str]],
    event_rows: list[dict[str, str]],
    rng: random.Random,
    out: Path,
    seed: int,
    trait_adjustments: dict[str, float] | None,
    syncretism_mode: str,
    adjacency: dict[str, list[str]],
) -> dict[str, Any]:
    agents = _load_agents(agent_rows)
    for agent, row in zip(agents, agent_rows):
        agent.village = row["village"]
    if trait_adjustments:
        unknown = set(trait_adjustments) - set(TRAIT_KEYS)
        if unknown:
            raise ValueError(f"unknown trait keys: {sorted(unknown)}")
        for agent in agents:
            for trait, delta in trait_adjustments.items():
                agent.traits[trait] = _clamp(agent.traits[trait] + delta)

    beliefs = {row["id"]: row for row in belief_rows}
    events_by_id = {row["id"]: row for row in event_rows}
    schedule: dict[int, list[dict]] = {}
    for item in scenario.get("events", []):
        schedule.setdefault(int(item["step"]), []).append(item)

    steps = int(scenario.get("steps", pack.domain.get("initial_steps", 50)))
    villages = sorted({a.village for a in agents})
    members: dict[str, list[AgentState]] = {v: [] for v in villages}
    for a in agents:
        members[a.village].append(a)
    n_by_v = {v: float(len(members[v])) for v in villages}

    active_events: list[_DistrictEvent] = []
    agent_turns: list[dict[str, Any]] = []
    share_turns: list[dict[str, Any]] = []
    conversions: list[dict[str, Any]] = []
    event_log: list[dict[str, Any]] = []
    event_origins: dict[str, str] = {}

    for step in range(1, steps + 1):
        # 1. 予定イベントの発火（origin 付きは local イベント）
        for item in schedule.get(step, []):
            event_id = item["id"]
            row = events_by_id[event_id]
            origin = item.get("origin")
            event_log.append(
                {"step": step, "event_id": event_id, "type": row["type"], "origin": origin or ""}
            )
            if origin:
                event_origins[event_id] = origin
            if row["type"] == "generation":
                _apply_generation_shift(agents)  # 世代交代は郡全域
            else:
                active_events.append(_DistrictEvent(row=row, start_step=step, origin=origin))
        active_events = [ev for ev in active_events if ev.weight(step) >= EVENT_MIN_WEIGHT]

        # 2. 村別信者数（このステップ開始時点で固定）と知覚プロファイル
        counts_by_v: dict[str, dict[str, float]] = {
            v: {b: 0.0 for b in beliefs} for v in villages
        }
        for agent in agents:
            counts_by_v[agent.village][agent.belief] += 1.0
        perceived = district_perception(counts_by_v, n_by_v, adjacency, list(beliefs))

        # 3. 各エージェントの更新（legacy ループの複製 + 知覚/到達係数の差し替え）
        for agent in agents:
            p_counts, p_n = perceived[agent.village][
                "bridge" if agent.role in BRIDGE_ROLES else "local"
            ]
            ev_factors = [_event_factor(ev, agent, adjacency) for ev in active_events]
            anxiety = _clamp(
                agent.traits["anxiety"]
                + sum(
                    ev.signal("anxiety_delta") * ev.weight(step) * f
                    for ev, f in zip(active_events, ev_factors)
                )
            )
            scores: dict[str, tuple[float, str]] = {}
            for belief_id, row in beliefs.items():
                scores[belief_id] = _belief_score_district(
                    agent, belief_id, row["appeal"], p_counts, p_n, active_events, step, ev_factors
                )

            current_score = scores[agent.belief][0]
            challengers = {b: s for b, (s, _) in scores.items() if b != agent.belief}
            best_other = max(challengers, key=lambda b: challengers[b])
            gap = challengers[best_other] - current_score

            openness = conversion_pressure(
                anxiety=anxiety,
                salvation_need=agent.traits["salvation_need"],
                practical_benefit_need=agent.traits["practical_benefit_need"],
                community_pressure=agent.traits["community_dependence"]
                * (1 - p_counts.get(agent.belief, 0.0) / p_n),
                authority_signal=max(
                    (
                        ev.signal("authority_signal") * ev.weight(step) * f
                        for ev, f in zip(active_events, ev_factors)
                    ),
                    default=0.0,
                ),
                rumor_signal=max(
                    (
                        ev.signal("rumor_signal") * ev.weight(step) * f
                        for ev, f in zip(active_events, ev_factors)
                    ),
                    default=0.0,
                ),
            )

            threshold = max(
                0.04,
                0.06
                + 0.12 * agent.traits["tradition_orientation"]
                - 0.06 * agent.traits["novelty_openness"],
            )

            if gap <= 0:
                agent.strength = _clamp(agent.strength + 0.01, 0.05, STRENGTH_CAP)
            else:
                agent.strength = _clamp(agent.strength - (0.02 + 0.04 * gap), 0.05)

            if gap > threshold:
                agent.pressure[best_other] = agent.pressure.get(best_other, 0) + 1
            else:
                agent.pressure = {b: c - 1 for b, c in agent.pressure.items() if c > 1}

            converted = False
            if (
                agent.pressure.get(best_other, 0) >= PRESSURE_STEPS_TO_CONVERT
                and rng.random() < openness
            ):
                reason = (
                    f"gap={gap:.2f} threshold={threshold:.2f} openness={openness:.2f} "
                    f"pull={scores[best_other][1]} anxiety={anxiety:.2f}"
                )
                old = agent.belief
                if syncretism_mode == "graded":
                    keep_old_as_secondary, keep_s, drop_s = keep_decision(
                        agent.traits["tolerance"],
                        agent.strength,
                        agent.traits["tradition_orientation"],
                        agent.traits["novelty_openness"],
                        gap,
                    )
                    reason += f" keep={keep_s:.2f} drop={drop_s:.2f}"
                else:
                    keep_old_as_secondary = agent.traits["tolerance"] >= SYNCRETISM_TOLERANCE
                agent.secondary_belief = old if keep_old_as_secondary else None
                agent.belief = best_other
                agent.strength = _clamp(0.35 + 0.3 * challengers[best_other], 0.05)
                agent.pressure = {}
                agent.syncretism_pressure = {}
                conversions.append(
                    {
                        "step": step,
                        "agent_id": agent.id,
                        "village": agent.village,
                        "kind": "conversion",
                        "from_belief": old,
                        "to_belief": best_other,
                        "reason": reason,
                    }
                )
                converted = True

            if syncretism_mode == "graded":
                if (
                    not converted
                    and agent.secondary_belief != best_other
                    and threshold * 0.5 < gap <= threshold
                ):
                    agent.syncretism_pressure[best_other] = (
                        agent.syncretism_pressure.get(best_other, 0) + 1
                    )
                    if agent.syncretism_pressure[best_other] >= PRESSURE_STEPS_TO_CONVERT:
                        sync_p = syncretism_openness(
                            agent.traits["tolerance"], agent.traits["novelty_openness"], anxiety
                        )
                        if rng.random() < sync_p:
                            agent.secondary_belief = best_other
                            agent.syncretism_pressure = {}
                            conversions.append(
                                {
                                    "step": step,
                                    "agent_id": agent.id,
                                    "village": agent.village,
                                    "kind": "syncretism",
                                    "from_belief": agent.belief,
                                    "to_belief": best_other,
                                    "reason": (
                                        f"sync_p={sync_p:.2f} "
                                        f"tolerance={agent.traits['tolerance']:.2f} "
                                        f"gap={gap:.2f} pull={scores[best_other][1]}"
                                    ),
                                }
                            )
                        else:
                            agent.syncretism_pressure[best_other] = 0
            elif (
                not converted
                and agent.traits["tolerance"] >= SYNCRETISM_TOLERANCE
                and agent.secondary_belief != best_other
                and threshold * 0.5 < gap <= threshold
            ):
                agent.syncretism_pressure[best_other] = (
                    agent.syncretism_pressure.get(best_other, 0) + 1
                )
                if agent.syncretism_pressure[best_other] >= PRESSURE_STEPS_TO_CONVERT:
                    agent.secondary_belief = best_other
                    agent.syncretism_pressure = {}
                    conversions.append(
                        {
                            "step": step,
                            "agent_id": agent.id,
                            "village": agent.village,
                            "kind": "syncretism",
                            "from_belief": agent.belief,
                            "to_belief": best_other,
                            "reason": (
                                f"tolerance={agent.traits['tolerance']:.2f} "
                                f"gap={gap:.2f} pull={scores[best_other][1]}"
                            ),
                        }
                    )

            agent_turns.append(
                {
                    "step": step,
                    "agent_id": agent.id,
                    "village": agent.village,
                    "label": agent.label,
                    "belief": agent.belief,
                    "secondary_belief": agent.secondary_belief or "",
                    "strength": round(agent.strength, 3),
                    "anxiety": round(anxiety, 3),
                    "openness": round(openness, 3),
                    "top_pull": best_other,
                    "gap": round(gap, 3),
                }
            )

        # 4. ステップ末の村別信念分布
        for v in villages:
            end_shares: dict[str, list[float]] = {}
            for agent in members[v]:
                end_shares.setdefault(agent.belief, []).append(agent.strength)
            for belief_id in beliefs:
                strengths = end_shares.get(belief_id, [])
                share_turns.append(
                    {
                        "step": step,
                        "village": v,
                        "belief_id": belief_id,
                        "adherents": len(strengths),
                        "avg_strength": round(sum(strengths) / len(strengths), 3)
                        if strengths
                        else 0.0,
                    }
                )

    out.mkdir(parents=True, exist_ok=True)

    def write_tsv(name: str, rows: list[dict[str, Any]], fields: list[str]) -> None:
        with (out / name).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

    write_tsv(
        "agent_turns.tsv",
        agent_turns,
        [
            "step",
            "agent_id",
            "village",
            "label",
            "belief",
            "secondary_belief",
            "strength",
            "anxiety",
            "openness",
            "top_pull",
            "gap",
        ],
    )
    write_tsv(
        "belief_shares.tsv",
        share_turns,
        ["step", "village", "belief_id", "adherents", "avg_strength"],
    )
    write_tsv(
        "conversions.tsv",
        conversions,
        ["step", "agent_id", "village", "kind", "from_belief", "to_belief", "reason"],
    )
    write_tsv("events_log.tsv", event_log, ["step", "event_id", "type", "origin"])

    retention = sum(1 for a in agents if a.belief == a.initial_belief) / len(agents)
    final_shares = {b: 0 for b in beliefs}
    for agent in agents:
        final_shares[agent.belief] += 1

    summary = {
        "domain": pack.name,
        "scenario": scenario["id"],
        "seed": seed,
        "trait_adjustments": dict(trait_adjustments) if trait_adjustments else {},
        "district": {"villages": len(villages), "event_origins": event_origins},
        "steps": steps,
        "agents": len(agents),
        "beliefs": len(beliefs),
        "events": len(event_rows),
        "conversions": sum(1 for c in conversions if c["kind"] == "conversion"),
        "syncretisms": sum(1 for c in conversions if c["kind"] == "syncretism"),
        "retention_rate": round(retention, 3),
        "final_shares": final_shares,
        "final_agents": [
            {
                "id": a.id,
                "village": a.village,
                "label": a.label,
                "belief": a.belief,
                "secondary_belief": a.secondary_belief,
                "strength": round(a.strength, 3),
            }
            for a in agents
        ],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = out / "manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                f"domain={pack.name}",
                f"scenario={scenario['id']}",
                f"agents={len(agents)}",
                f"villages={len(villages)}",
                f"beliefs={len(beliefs)}",
                f"events={len(event_rows)}",
                f"steps={steps}",
                f"conversions={summary['conversions']}",
                f"syncretisms={summary['syncretisms']}",
                f"retention_rate={summary['retention_rate']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return summary
