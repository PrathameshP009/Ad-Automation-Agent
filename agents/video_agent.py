"""Agent 3 — Video Agent.

Takes a storyboard JSON from the Script Agent and renders it into a 30-60s .mp4,
via OpenMontage (preferred) or the ffmpeg fallback renderer. Also picks the
best-scoring storyboard when multiple are available, using a lightweight LLM judge
scoring on hook strength / pacing / proof / CTA clarity — since "wow" is ultimately
a creative call, this score is a *filter*, not a guarantee.
"""
import json
from pathlib import Path
from hermes.core import Agent

import config
from tools import video_gen_tool, llm_client

JUDGE_PROMPT = """You are a ruthless performance-marketing creative director grading a video
ad storyboard. Score 1-10 on each: hook_strength (does shot 1 stop the scroll in <3s with
NO branding), pacing, proof_credibility, cta_clarity, overall_wow. Return STRICT JSON:
{"hook_strength": 0, "pacing": 0, "proof_credibility": 0, "cta_clarity": 0, "overall_wow": 0, "verdict": "one sentence"}"""


def build_agent() -> Agent:
    return Agent(
        provider="openai",
        model=config.LLM_MODEL_FAST,
        name="VideoAgent",
        description="Renders a storyboard into a final cinematic video ad, picking the strongest of several scripts.",
        prompt="You render approved ad storyboards into final video output.",
    )


def score_storyboard(storyboard: dict) -> dict:
    return llm_client.chat_json(
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": json.dumps({k: v for k, v in storyboard.items() if k != "_research"})},
        ],
        model=config.LLM_MODEL_FAST,
        temperature=0.2,
    )


def pick_best(storyboards: list[dict]) -> dict:
    scored = []
    for sb in storyboards:
        judged = score_storyboard(sb)
        total = sum(v for k, v in judged.items() if isinstance(v, (int, float)))
        scored.append((total, sb, judged))
    scored.sort(key=lambda t: t[0], reverse=True)
    best_score, best_sb, best_judged = scored[0]
    print(f"[VideoAgent] Picked '{best_sb.get('title')}' (score {best_score}): {best_judged.get('verdict')}")
    return best_sb


def run(script_path: str = None, script_dir: str = None) -> Path:
    if script_path:
        storyboard = json.loads(Path(script_path).read_text())
    else:
        script_dir = Path(script_dir or config.OUTPUT_DIR)
        candidates = sorted(script_dir.glob("script_*.json"))
        if not candidates:
            raise FileNotFoundError(f"No script_*.json files found in {script_dir}. Run the Script Agent first.")
        storyboards = [json.loads(p.read_text()) for p in candidates]
        storyboard = pick_best(storyboards) if len(storyboards) > 1 else storyboards[0]

    out_path = video_gen_tool.render(storyboard, output_name="final_ad.mp4")
    print(f"[VideoAgent] Rendered final ad -> {out_path}")
    return out_path


if __name__ == "__main__":
    run()
