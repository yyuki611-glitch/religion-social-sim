from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


class LLMError(RuntimeError):
    pass


def generate(prompt: str, *, provider: str = "claude", model: str | None = None, timeout: int = 300) -> str:
    """CLI 経由で LLM にプロンプトを投げてテキストを返す。

    provider:
      - "claude": Claude Code CLI（`claude -p`）
      - "ollama": ローカル Ollama（`ollama run <model>`）
    """
    if provider == "claude":
        cmd = ["claude", "-p"]
        if model:
            cmd += ["--model", model]
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout
        )
    elif provider == "ollama":
        cmd = ["ollama", "run", model or "qwen2.5:7b"]
        result = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, timeout=timeout
        )
    else:
        raise LLMError(f"unknown provider: {provider}")

    if result.returncode != 0:
        raise LLMError(f"{provider} failed: {result.stderr.strip()[:500]}")
    return result.stdout.strip()


def narrate_run(
    output_dir: str | Path,
    *,
    system_context: str,
    reflection_prompt: str,
    provider: str = "claude",
    model: str | None = None,
) -> Path:
    """実行結果（summary.json + conversions.tsv）から日本語ナラティブを生成して narrative.md に保存する。"""
    out = Path(output_dir)
    summary: dict[str, Any] = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    conversions = (out / "conversions.tsv").read_text(encoding="utf-8")

    prompt = "\n\n".join(
        [
            system_context.strip(),
            reflection_prompt.strip(),
            "以下はシミュレーション1回分の実行結果です。日本語で、村で何が起きたかの物語的な観察記録（500字前後）と、"
            "どの信仰がなぜ伸び・衰えたかの分析（箇条書き）を書いてください。",
            "## summary.json\n" + json.dumps(summary, ensure_ascii=False, indent=2),
            "## conversions.tsv\n" + conversions,
        ]
    )
    text = generate(prompt, provider=provider, model=model)
    narrative = out / "narrative.md"
    narrative.write_text(text + "\n", encoding="utf-8")
    return narrative
