import argparse
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).parent.resolve())
sys.path.insert(0, PROJECT_ROOT)

from src.pipeline import run_pipeline
from src.comparator import print_comparison

GEN_MODES = ["source_aware"]
CHUNK_MODES = [
    "function_only",
    "function_plus_deps",
    "class_context",
    "hierarchical_summary",
    "token_budget",
    "full_source",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="LLM-based unit test generation and evaluation framework",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Target selection  (--target supersedes --function)
    parser.add_argument(
        "--target",
        default=None,
        help=(
            "Function or method to test.\n"
            "  Plain function:  --target factorial\n"
            "  Class method:    --target UserService.save_user\n"
            "(Overrides --function when provided)"
        ),
    )
    parser.add_argument(
        "--function",
        default="classify_triangle",
        help="Legacy: plain function name (default: classify_triangle)",
    )
    parser.add_argument(
        "--file",
        default=None,
        help=(
            "Path to the Python source file to analyse.\n"
            "Defaults to dataset/sample_functions.py"
        ),
    )

    # Generation mode
    parser.add_argument(
        "--mode",
        choices=GEN_MODES,
        default="source_aware",
        help="Generation mode (default: source_aware — LLM sees full source context)",
    )

    # Chunking mode
    parser.add_argument(
        "--chunking-mode",
        dest="chunking_mode",
        choices=CHUNK_MODES,
        default=None,
        help=(
            "Context assembly strategy (optional):\n"
            "  function_only        – target function only\n"
            "  function_plus_deps   – target + transitive helpers\n"
            "  class_context        – condensed class shell + deps\n"
            "  hierarchical_summary – detailed relevant, stubs for rest\n"
            "  token_budget         – greedy fill up to token limit\n"
            "  full_source          – entire file (baseline)\n"
            "When omitted the legacy single-function path is used."
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    target = args.target or args.function
    source_file = args.file or str(Path(PROJECT_ROOT) / "dataset" / "sample_functions.py")

    gen_modes = [args.mode]
    all_results: dict = {}

    for gen_mode in gen_modes:
        metrics = run_pipeline(
            source_file=source_file,
            function_name=target,
            project_root=PROJECT_ROOT,
            mode=gen_mode,
            chunking_mode=args.chunking_mode,
        )
        key = f"{gen_mode}" + (f"/{args.chunking_mode}" if args.chunking_mode else "")
        all_results[key] = metrics

    if len(all_results) > 1:
        print_comparison(all_results)


if __name__ == "__main__":
    main()
