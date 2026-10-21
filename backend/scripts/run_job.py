"""Run one scheduled job and exit. This is what the GitHub Actions workflows call.

Usage (from backend/): uv run python -m scripts.run_job {cycle|trades|after-close}

  cycle        collect markets and news, tag them, refresh live recommendations
  trades       fill queued paper trades and check stop loss / take profit (only while open)
  after-close  grade today's daily recommendations and issue tomorrow's

Exits with code 1 if any step failed, so the workflow run shows up as failed.
"""

import argparse
import logging
import sys

from app import jobs
from app.analysis import market_hours
from app.trading import paper

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("run_job")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=["cycle", "trades", "after-close"])
    job = parser.parse_args().job

    if job == "cycle":
        failed = jobs.run_cycle()
    elif job == "trades":
        # The cron covers 11:00 to 17:00 ART on weekdays; this also skips the edges of that
        # window and catches a cron that fires late.
        if not market_hours.is_open():
            log.info("market closed, nothing to do")
            return 0
        changed = paper.check_open_trades()
        log.info("%d trades changed", len(changed))
        failed = []
    else:
        failed = jobs.after_close()

    if failed:
        log.error("failed steps: %s", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
