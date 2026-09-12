#!/usr/bin/env python3
"""
Daily subscription sweep. Run from cron.

    0 2 * * *  cd /srv/pgguru/backend && python expire_subscriptions.py

Idempotent, so a double run or a retry after a failed deploy changes nothing the
second time. `--dry-run` reports what would happen without writing, which is the
only sane way to check the thresholds on a live database before letting it
suspend anybody.

Deliberately a script rather than a background thread inside the API. A thread
would run once per worker process - four workers, four sweeps, four notification
emails to every owner on the same morning.
"""
import argparse
import sys

from app.core.database import SessionLocal
from app.services.subscription_lifecycle import SubscriptionLifecycleService


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report without changing anything")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = SubscriptionLifecycleService(db).sweep(dry_run=args.dry_run)
        # Same daily run: one-day menu specials older than a week are deleted.
        # The weekly menu is never touched. See operations_service.prune_old_specials.
        from app.services.operations_service import prune_old_specials
        pruned = prune_old_specials(db)
        if pruned:
            print(f"deleted {pruned} menu special(s) older than a week")
        if args.dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception as exc:                                    # noqa: BLE001
        db.rollback()
        print(f"sweep failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    prefix = "would " if args.dry_run else ""
    print(f"{prefix}warn:      {len(result.warned)}  {', '.join(result.warned[:5])}")
    print(f"{prefix}expire:    {len(result.expired)}  {', '.join(result.expired[:5])}")
    print(f"{prefix}suspend:   {len(result.suspended)}  {', '.join(result.suspended[:5])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
