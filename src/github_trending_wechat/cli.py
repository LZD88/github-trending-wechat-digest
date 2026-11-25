from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from github_trending_wechat.config import ConfigError, Settings
from github_trending_wechat.logging_utils import configure_logging, redact_text
from github_trending_wechat.pipeline import build_application
from github_trending_wechat.scheduling import parse_target_date
from github_trending_wechat.sources import SourceError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="github-trending-wechat",
        description="Generate and deliver a daily GitHub Trending top 10 digest.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture", help="Archive the current Trending snapshot")
    capture_parser.add_argument("--scheduled", action="store_true", help="Use the nightly window")

    run_parser = subparsers.add_parser("run", help="Send an archived digest")
    run_parser.add_argument("--date", help="Target date (YYYY-MM-DD); defaults to yesterday")

    preview_parser = subparsers.add_parser("preview", help="Generate without sending")
    preview_parser.add_argument(
        "--date", help="Archived date (YYYY-MM-DD); defaults to live preview"
    )
    preview_parser.add_argument(
        "--save", action="store_true", help="Persist the generated snapshot"
    )

    resend_parser = subparsers.add_parser("resend", help="Manually resend a target date")
    resend_parser.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")

    binding_parser = subparsers.add_parser(
        "test-binding", help="Send a ServerChan binding verification message"
    )
    binding_parser.add_argument("--environment", default="default", help="Environment label")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    require_delivery = args.command in {"run", "resend", "test-binding"}
    settings: Settings | None = None
    try:
        settings = Settings.from_env(require_delivery=require_delivery)
        configure_logging(
            secrets=[
                settings.serverchan_sendkey,
                settings.github_token,
                settings.summary_api_key,
            ]
        )
        application = build_application(settings, require_delivery=require_delivery)
        target = parse_target_date(args.date) if getattr(args, "date", None) else None

        if args.command == "capture":
            snapshot = application.capture(scheduled=args.scheduled)
            print(
                f"capture=success target_date={snapshot.target_date} "
                f"fetched_at={snapshot.fetched_at.isoformat()} source={snapshot.source} "
                f"entries={len(snapshot.entries)}"
            )
            return 0
        if args.command == "preview":
            outcome = application.preview(target, save=args.save)
            print("\n\n".join(outcome.rendered.segments))
            return 0
        if args.command == "run":
            outcome = application.run(target)
            assert outcome.attempt is not None
            print(
                f"delivery={outcome.attempt.status} "
                f"target_date={outcome.snapshot.target_date.isoformat()}"
            )
            return 0 if outcome.attempt.status in {"success", "idempotent_skip"} else 1
        if args.command == "resend":
            assert target is not None
            outcome = application.resend(target)
            assert outcome.attempt is not None
            print(
                f"delivery={outcome.attempt.status} "
                f"target_date={outcome.snapshot.target_date.isoformat()} reason=manual_resend"
            )
            return 0 if outcome.attempt.status == "success" else 1
        if args.command == "test-binding":
            attempt = application.test_binding(args.environment)
            print(f"binding={attempt.status} messages={len(attempt.message_ids)}")
            return 0 if attempt.status == "binding_verified" else 1
    except (ConfigError, SourceError, RuntimeError, ValueError) as exc:
        secrets = []
        if settings:
            secrets = [
                settings.serverchan_sendkey,
                settings.github_token,
                settings.summary_api_key,
            ]
        print(f"ERROR: {redact_text(str(exc), secrets)}", file=sys.stderr)
        return 1
    parser.error(f"unknown command {args.command!r}")
    return 2
