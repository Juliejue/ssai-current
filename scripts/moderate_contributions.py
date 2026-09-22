#!/usr/bin/env python3
"""Review the anonymous co-creation queue without exposing it publicly."""

from __future__ import annotations

import argparse
import os
import sys

import psycopg


def parser() -> argparse.ArgumentParser:
    output = argparse.ArgumentParser(description="Review Current community contributions")
    action = output.add_mutually_exclusive_group(required=True)
    action.add_argument("--list", action="store_true", help="list pending submissions")
    action.add_argument("--approve", metavar="CONTRIBUTION_ID")
    action.add_argument("--reject", metavar="CONTRIBUTION_ID")
    return output


def main() -> int:
    args = parser().parse_args()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not configured", file=sys.stderr)
        return 2

    with psycopg.connect(database_url) as connection:
        if args.list:
            rows = connection.execute(
                """
                SELECT contribution_id, city, place_name, kind, reason, media_count, created_at
                FROM community_contributions
                WHERE moderation_status = 'pending'
                ORDER BY created_at ASC
                LIMIT 100
                """
            ).fetchall()
            if not rows:
                print("No pending contributions.")
                return 0
            for row in rows:
                print(f"{row[0]} | {row[1]} | {row[2]} | {row[3]} | media={row[5]}")
                print(f"  {row[4]}")
            return 0

        contribution_id = args.approve or args.reject
        if not contribution_id or not contribution_id.startswith("contrib_"):
            print("Invalid contribution id", file=sys.stderr)
            return 2
        status = "approved" if args.approve else "rejected"
        cursor = connection.execute(
            """
            UPDATE community_contributions
            SET moderation_status = %s, reviewed_at = now()
            WHERE contribution_id = %s AND moderation_status = 'pending'
            """,
            (status, contribution_id),
        )
        if cursor.rowcount != 1:
            print("No pending contribution matched that id", file=sys.stderr)
            return 1
        print(f"{contribution_id}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
