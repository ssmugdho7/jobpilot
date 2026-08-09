import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from app.db import init_db
from app.pipeline import run_scan, run_scan_async


def main():
    parser = argparse.ArgumentParser(description="JobPilot - Google/LinkedIn job scanner + ATS CV generator")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit")
    parser.add_argument("--web", action="store_true", help="Start web dashboard")
    parser.add_argument("--port", type=int, default=5001, help="Web dashboard port")
    args = parser.parse_args()

    init_db()

    if args.web:
        from app.web.app import start_web

        if not args.once:
            run_scan_async()
        start_web(port=args.port)
    elif args.once:
        run_scan()
    else:
        from app.web.app import start_web
        run_scan_async()
        start_web(port=args.port)


if __name__ == "__main__":
    main()
