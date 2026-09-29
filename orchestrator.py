"""Wires the three agents into a Hermes multi-agent Team with a visible kanban board,
for the screen-recorded submission requirement ("a video output of the hermes kanban").

Hermes (hermes-ai) exposes multi-agent orchestration primitives; this module keeps the
board/task-state logic isolated from the actual agent logic in agents/, so the pipeline
in main.py can run headless (no UI) while this module runs it with the board attached.
"""
import argparse
import json
from hermes.core import Team, Task  # multi-agent orchestration primitives

import config
from agents import ads_manager_agent, script_agent, video_agent


BOARD_COLUMNS = ["Backlog", "Researching Ads", "Scripting", "Rendering", "Done"]


def build_team() -> Team:
    team = Team(
        name="CWT Video Ads Team",
        agents=[
            ads_manager_agent.build_agent(),
            script_agent.build_agent(),
            video_agent.build_agent(),
        ],
        board_columns=BOARD_COLUMNS,
    )
    return team


def run_pipeline_on_board(team: Team, product: str, niche: str) -> None:
    task1 = team.add_task(Task(
        title="Source & analyze winning ads",
        column="Researching Ads",
        assignee="AdsManagerAgent",
    ))
    ads = ads_manager_agent.run(product=product, niche=niche)
    team.move_task(task1, to_column="Done")

    task2 = team.add_task(Task(
        title="Write 3 cinematic storyboards",
        column="Scripting",
        assignee="ScriptAgent",
    ))
    storyboards = script_agent.run()
    team.move_task(task2, to_column="Done")

    task3 = team.add_task(Task(
        title="Judge scripts & render final ad",
        column="Rendering",
        assignee="VideoAgent",
    ))
    final_path = video_agent.run()
    team.move_task(task3, to_column="Done")

    print(f"\nPipeline complete. Final ad: {final_path}")
    print(f"Sourced {len(ads)} ads, wrote {len(storyboards)} storyboards.")


def main():
    parser = argparse.ArgumentParser(description="Run the CWT video ads pipeline on a Hermes kanban board.")
    parser.add_argument("--product", default=config.TARGET_PRODUCT)
    parser.add_argument("--niche", default=config.TARGET_NICHE)
    parser.add_argument("--ui", action="store_true", help="Launch Hermes' visual board UI (for screen recording).")
    args = parser.parse_args()

    team = build_team()

    if args.ui:
        # Hermes exposes a local web UI for the board; consult `hermes-ai` docs/CLI for the
        # exact launch command for your installed version (e.g. `hermes ui` or team.serve_ui()).
        # Kept as a clearly-marked follow-up since UI launch commands are version-sensitive.
        print("Launch the Hermes board UI per your installed hermes-ai version, then run the "
              "pipeline in another terminal so the board updates live for your recording.")

    run_pipeline_on_board(team, args.product, args.niche)


if __name__ == "__main__":
    main()
