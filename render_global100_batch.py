from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import render_global50_batch as batch


ROOT = Path(__file__).resolve().parent
GLOBAL100_DIR = ROOT / "data" / "global100"


def configure_global100() -> None:
    batch.GLOBAL50_DIR = GLOBAL100_DIR
    batch.PLAN_PATH = GLOBAL100_DIR / "global100_plan.csv"
    batch.PROFILE_DIR = GLOBAL100_DIR / "profiles"
    batch.SCRIPT_VERSION = "global100_dry_run_v1"

    def read_plan(path: Path = GLOBAL100_DIR / "global100_plan.csv") -> list[dict[str, str]]:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]

    original_create = batch.create_run_dir

    def create_run_dir(prefix: str = "global100_dry_run") -> Path:
        return original_create(prefix)

    batch.read_plan = read_plan
    batch.create_run_dir = create_run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Global100 index video dry-run and guarded rendering workflow")
    parser.add_argument("--dry-run", action="store_true", help="Generate review materials only")
    parser.add_argument("--render-sample", type=int, help="Prepare sample review set from different regions/types")
    parser.add_argument("--render-ready", action="store_true", help="Guarded command for approved ready rendering")
    parser.add_argument("--index", help="Only process one index_id")
    parser.add_argument("--episode", type=int, choices=[1, 2, 3, 4, 5], help="Only process one episode")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main() -> None:
    configure_global100()
    parser = build_parser()
    args = parser.parse_args()
    if not (args.dry_run or args.render_sample or args.render_ready):
        args.dry_run = True

    if not batch.PLAN_PATH.exists():
        raise SystemExit("请先运行：python build_global100_plan.py --force")

    if args.render_ready:
        run_dir = batch.guarded_render_message(args, mode="global100_render_ready_guard")
    elif args.render_sample:
        run_dir = batch.guarded_render_message(args, mode=f"global100_render_sample_{args.render_sample}_guard")
    else:
        run_dir = batch.render_dry_run(args, mode="global100_dry_run")

    print(json.dumps({"output_dir": str(run_dir), "batch_review": str(run_dir / "batch_review.html")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
