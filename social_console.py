from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from modules.social.publisher_manager import main
from modules.runtime_usage import observe_usage_best_effort


ROOT = Path(__file__).resolve().parent
HOT_NEWS_COMMANDS = {"prepare-hot-news-monitoring", "prepare-hot-news-auto"}


def observed_main(argv: list[str]) -> int:
    command = argv[0] if argv else "no_command"
    feature = "hot_news" if command in HOT_NEWS_COMMANDS else "social_workflow"
    started = time.perf_counter()
    try:
        result = main(argv)
    except Exception as exc:
        observe_usage_best_effort(
            ROOT,
            runtime_profile=os.environ.get("AFFILIATE_BOT_RUNTIME_PROFILE", "FULL_COMPATIBILITY"),
            entry_point="social_console.py",
            feature=feature,
            workflow="social",
            operation=command,
            success=False,
            output_generated=False,
            duration_ms=round((time.perf_counter() - started) * 1000),
            error_class=exc.__class__.__name__,
        )
        raise
    observe_usage_best_effort(
        ROOT,
        runtime_profile=os.environ.get("AFFILIATE_BOT_RUNTIME_PROFILE", "FULL_COMPATIBILITY"),
        entry_point="social_console.py",
        feature=feature,
        workflow="social",
        operation=command,
        success=result == 0,
        output_generated=command.startswith("prepare-"),
        duration_ms=round((time.perf_counter() - started) * 1000),
        error_class=None if result == 0 else "CommandFailed",
    )
    return result


if __name__ == "__main__":
    raise SystemExit(observed_main(sys.argv[1:]))
