"""CLI entrypoint.

Examples:
    python main.py --product "algo trading signals" --niche "retail day traders"
    python main.py --stage ads
    python main.py --stage script
    python main.py --stage video
"""
import argparse
import config
from agents import ads_manager_agent, script_agent, video_agent


def main():
    parser = argparse.ArgumentParser(description="CrowdWisdomTrading video ads agent pipeline")
    parser.add_argument("--product", default=config.TARGET_PRODUCT)
    parser.add_argument("--niche", default=config.TARGET_NICHE)
    parser.add_argument("--stage", choices=["all", "ads", "script", "video"], default="all")
    parser.add_argument("--pain-input", help="ads.json path, for --stage script")
    parser.add_argument("--script", help="script_*.json path, for --stage video (single script)")
    args = parser.parse_args()

    if args.stage in ("all", "ads"):
        ads_manager_agent.run(product=args.product, niche=args.niche)
    if args.stage in ("all", "script"):
        script_agent.run(ads_json_path=args.pain_input)
    if args.stage in ("all", "video"):
        video_agent.run(script_path=args.script)


if __name__ == "__main__":
    main()
