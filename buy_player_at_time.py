import argparse
import os
import sqlite3
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
from kickbase_api.bids import place_bid
from kickbase_api.league import get_league_id
from kickbase_api.user import login

load_dotenv()

DB_PATH = "player_data_total.db"
MAX_SLEEP_SECONDS = 6 * 60 * 60  # 6 hours


def parse_args():
    parser = argparse.ArgumentParser(description="Lookup a player in the local database and place a timed bid.")
    parser.add_argument("--player-id", default="", help="Kickbase player id")
    parser.add_argument("--player-label", default="", help="Player name or slug")
    parser.add_argument("--search-only", action="store_true", help="Search the local database for matching players and print player_id(s) without placing a bid")
    parser.add_argument("--bid-time", help="ISO 8601 UTC bid time, e.g. 2026-08-10T03:00:00Z")
    parser.add_argument("--bid-amount", help="Bid amount")
    parser.add_argument("--competition-id", type=int, default=1, help="Competition id for the league")
    parser.add_argument("--league-name", default="", help="Optional league name to resolve league id")
    return parser.parse_args()


def parse_utc_iso(timestamp: str) -> datetime:
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp).astimezone(timezone.utc)


def wait_for_target_time(target_time: datetime):
    now = datetime.now(timezone.utc)
    delay = (target_time - now).total_seconds()
    if delay <= 0:
        print(f"Bid time {target_time.isoformat()} is now or already passed; executing immediately.")
        return

    if delay > MAX_SLEEP_SECONDS:
        raise RuntimeError(
            f"Target bid_time is too far in the future ({delay:.0f}s). "
            "GitHub Actions support up to 6 hours per job. "
            "Schedule the trigger closer to the bid time."
        )

    print(f"Waiting {delay:.0f} seconds until target bid time {target_time.isoformat()} UTC...")
    time.sleep(delay)
    print("Target bid time reached.")


def find_player_in_db(player_id: str, player_label: str, competition_id: int):
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database file not found: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        if player_id:
            cursor.execute(
                "SELECT player_id, first_name, last_name, team_name, competition_id FROM player_data_1d WHERE player_id = ? LIMIT 1",
                (player_id,),
            )
            row = cursor.fetchone()
            if row:
                return row
            raise ValueError(f"Player with id {player_id} not found in database.")

        label = player_label.strip().lower()
        cursor.execute(
            "SELECT player_id, first_name, last_name, team_name, competition_id FROM player_data_1d "
            "WHERE competition_id = ? AND (LOWER(first_name) LIKE ? OR LOWER(last_name) LIKE ? OR LOWER(first_name || ' ' || last_name) LIKE ? OR LOWER(team_name) LIKE ?) "
            "GROUP BY player_id LIMIT 1",
            (competition_id, f"%{label}%", f"%{label}%", f"%{label}%", f"%{label}%"),
        )
        row = cursor.fetchone()
        if row:
            return row

        raise ValueError(f"Player with label '{player_label}' not found in database for competition {competition_id}.")


def search_players_in_db(player_label: str, competition_id: int):
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Database file not found: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        label = player_label.strip().lower()
        params = [f"%{label}%", f"%{label}%", f"%{label}%", f"%{label}%"]
        query = (
            "SELECT player_id, first_name, last_name, team_name, competition_id "
            "FROM player_data_1d "
            "WHERE (LOWER(first_name) LIKE ? OR LOWER(last_name) LIKE ? OR LOWER(first_name || ' ' || last_name) LIKE ? OR LOWER(team_name) LIKE ?) "
        )

        if competition_id is not None:
            query += "AND competition_id = ? "
            params.append(competition_id)

        query += "GROUP BY player_id ORDER BY first_name, last_name LIMIT 50"
        cursor.execute(query, tuple(params))

        return cursor.fetchall()


def main():
    args = parse_args()

    if not args.player_id and not args.player_label:
        raise SystemExit("Either --player-id or --player-label must be provided.")

    if args.search_only:
        if not args.player_label:
            raise SystemExit("--search-only requires --player-label to be provided.")

        matches = search_players_in_db(args.player_label, args.competition_id)
        if not matches:
            print(f"No players found matching '{args.player_label}' in competition {args.competition_id}.")
            return

        print("Found matching players:")
        for player_id, first_name, last_name, team_name, db_competition_id in matches:
            print(f"- {player_id}: {first_name} {last_name} (team={team_name}, competition_id={db_competition_id})")
        return

    if not args.bid_time or not args.bid_amount:
        raise SystemExit("--bid-time and --bid-amount are required unless --search-only is used.")

    target_time = parse_utc_iso(args.bid_time)
    wait_for_target_time(target_time)

    player_row = find_player_in_db(args.player_id, args.player_label, args.competition_id)
    player_id, first_name, last_name, team_name, db_competition_id = player_row
    full_name = f"{first_name} {last_name}".strip()

    bid_amount = float(args.bid_amount)
    print(f"Found player in database: {full_name} (id={player_id}, team={team_name}, competition_id={db_competition_id})")
    print(f"Placing bid of {bid_amount} for player {player_id} at {target_time.isoformat()} UTC")

    username = os.getenv("KICK_USER")
    password = os.getenv("KICK_PASS")

    if not username or not password:
        raise SystemExit("KICK_USER and KICK_PASS must be set in environment variables.")

    token = login(username, password)

    league_name = args.league_name or os.getenv("LEAGUE_NAME", "")
    league_id = get_league_id(token, league_name) if league_name else None

    if not league_id:
        print("No league name provided or league lookup failed; using the first available league.")
        league_id = get_league_id(token, league_name)

    print(f"Using league_id={league_id}")

    response = place_bid(token, league_id, player_id, bid_amount)
    print("Bid response:", response)


if __name__ == "__main__":
    main()
