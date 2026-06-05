from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim_core.domain_pack import load_domain_pack
from sim_core.engine import run_scenario


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="domain_packs/japan_religion")
    parser.add_argument("--scenario", default="baseline.yaml")
    parser.add_argument("--output-dir", default="outputs/runs/baseline_smoke")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--narrate",
        choices=["claude", "ollama"],
        default=None,
        help="実行後に LLM で日本語ナラティブ（narrative.md）を生成する",
    )
    parser.add_argument("--narrate-model", default=None, help="--narrate で使うモデル名")
    args = parser.parse_args()

    result = run_scenario(Path(args.domain), args.scenario, Path(args.output_dir), seed=args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.narrate:
        from sim_core.llm_backend import narrate_run

        pack = load_domain_pack(args.domain)
        narrative = narrate_run(
            args.output_dir,
            system_context=pack.prompt_path("system_context.md").read_text(encoding="utf-8"),
            reflection_prompt=pack.prompt_path("belief_reflection.md").read_text(encoding="utf-8"),
            provider=args.narrate,
            model=args.narrate_model,
        )
        print(f"narrative: {narrative}")


if __name__ == "__main__":
    main()
