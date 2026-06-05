from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Belief:
    id: str
    label: str
    family: str
    appeal: str


def conversion_pressure(
    *,
    anxiety: float,
    salvation_need: float,
    practical_benefit_need: float,
    community_pressure: float,
    authority_signal: float,
    rumor_signal: float,
) -> float:
    """Simple deterministic score used before adding LLM interpretation."""
    return (
        anxiety * 0.25
        + salvation_need * 0.2
        + practical_benefit_need * 0.2
        + community_pressure * 0.15
        + authority_signal * 0.1
        + rumor_signal * 0.1
    )

