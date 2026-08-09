from kickbase_api.league import get_league_players_on_market
from kickbase_api.user import get_players_in_squad
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import sqlite3

def live_data_predictions(today_df, model, features):
    """Make live data predictions for today_df using the trained model"""

    # Set features and copy df
    today_df_features = today_df[features]
    today_df_results = today_df.copy()

    # Predict mv_target
    today_df_results["predicted_mv_target"] = np.round(model.predict(today_df_features), 2)

    # Sort by predicted_mv_target descending
    today_df_results = today_df_results.sort_values("predicted_mv_target", ascending=False)

    # Filter date to today or yesterday if before 22:15, because mv is updated around 22:15
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    cutoff_time = now.replace(hour=22, minute=15, second=0, microsecond=0)
    date = (now - timedelta(days=1)) if now <= cutoff_time else now
    date = date.date()

    # Drop rows where NaN mv
    today_df_results = today_df_results.dropna(subset=["mv"])

    # Keep only relevant columns
    today_df_results = today_df_results[["player_id", "first_name", "last_name", "position", "team_name", "date", "mv_change_1d", "mv_trend_1d", "mv", "predicted_mv_target", "p"]]

    return today_df_results


def join_current_squad(token, league_id, today_df_results):
    squad_players = get_players_in_squad(token, league_id)

    squad_df = pd.DataFrame(squad_players["it"])

    # Join squad_df ("i") with today_df ("player_id")
    squad_df = (
        pd.merge(today_df_results, squad_df, left_on="player_id", right_on="i")
        .drop(columns=["i"])
    )

    # Rename prob to s_11_prob for better understanding
    if "prob" not in squad_df.columns:
        squad_df["prob"] = np.nan  # Placeholder for non-pro users
    squad_df = squad_df.rename(columns={"prob": "s_11_prob"})

    # Rename mv_change_1d to mv_change_yesterday for better understanding
    squad_df = squad_df.rename(columns={"mv_change_1d": "mv_change_yesterday"})

    # Rename "mv_x" to "mv" for better understanding
    squad_df = squad_df.rename(columns={"mv_x": "mv"})

    # Add season statistics from database
    squad_df = add_season_statistics(squad_df)

    # Calculate points per market value (if points column exists)
    if "p" in squad_df.columns:
        squad_df["points_per_mv"] = np.round((squad_df["p"] / squad_df["mv"]) * 1000, 2)

    # Keep only relevant columns
    columns_to_keep = ["last_name", "team_name", "mv", "mv_change_yesterday", "predicted_mv_target", "s_11_prob", "points_per_mv", "season_points_per_mv"]
    squad_df = squad_df[[col for col in columns_to_keep if col in squad_df.columns]]

    return squad_df 


# TODO Add fail-safe check before player expires if the prob (starting 11) is still high, so no injuries or anything. if it dropped. dont bid / reccommend
def join_current_market(token, league_id, today_df_results):
    """Join the live predictions with the current market data to get bid recommendations"""

    players_on_market = get_league_players_on_market(token, league_id)

    # players_on_market to DataFrame
    market_df = pd.DataFrame(players_on_market)

    # Join market_df ("id") with today_df ("player_id")
    bid_df = (
        pd.merge(today_df_results, market_df, left_on="player_id", right_on="id")
        .drop(columns=["id"])
    )

    # exp contains seconds until expiration
    bid_df["hours_to_exp"] = np.round((bid_df["exp"] / 3600), 2)

    # check if current sysdate + hours_to_exp is after the next 22:00
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    next_22 = now.replace(hour=22, minute=0, second=0, microsecond=0)
    diff = np.round((next_22 - now).total_seconds() / 3600, 2)

    # If hours_to_exp < diff then it expires today
    bid_df["expiring_today"] = bid_df["hours_to_exp"] < diff

    # Drop rows where predicted_mv_target is less than 5000
    bid_df = bid_df[bid_df["predicted_mv_target"] > 5000]

    # Sort by predicted_mv_target descending
    bid_df = bid_df.sort_values("predicted_mv_target", ascending=False)

    # Rename prob to s_11_prob for better understanding
    if "prob" not in bid_df.columns:
        bid_df["prob"] = np.nan  # Placeholder for non-pro users
    bid_df = bid_df.rename(columns={"prob": "s_11_prob"})

    # Rename mv_change_1d to mv_change_yesterday for better understanding
    bid_df = bid_df.rename(columns={"mv_change_1d": "mv_change_yesterday"})

    # Add season statistics from database
    bid_df = add_season_statistics(bid_df)

    # Calculate points per market value (if points column exists)
    if "p" in bid_df.columns:
        bid_df["points_per_mv"] = np.round((bid_df["p"] / bid_df["mv"]) * 1000, 2)
    
    # Keep only relevant columns
    columns_to_keep = ["last_name", "team_name", "mv", "mv_change_yesterday", "predicted_mv_target", "s_11_prob", "hours_to_exp", "expiring_today", "points_per_mv", "season_points_per_mv"]
    bid_df = bid_df[[col for col in columns_to_keep if col in bid_df.columns]]

    return bid_df


def add_season_statistics(df, season_start_date="2025-08-15"):
    """Add season-level statistics (season points and season points_per_mv) to the dataframe"""
    
    try:
        conn = sqlite3.connect("player_data_total.db")
        
        season_stats = []
        for player_id in df["player_id"]:
            # Query database for total points since season start and initial mv
            cursor = conn.cursor()
            
            # Get sum of points since season start
            cursor.execute("""
                SELECT COALESCE(SUM(p), 0) as total_points
                FROM player_data_1d
                WHERE player_id = ? AND date >= ?
            """, (player_id, season_start_date))
            total_points = cursor.fetchone()[0]
            
            # Get market value on season start date (or closest date after)
            cursor.execute("""
                SELECT mv
                FROM player_data_1d
                WHERE player_id = ? AND date >= ? AND mv IS NOT NULL
                ORDER BY date ASC
                LIMIT 1
            """, (player_id, season_start_date))
            result = cursor.fetchone()
            season_start_mv = result[0] if result else None
            
            season_stats.append({
                "player_id": player_id,
                "season_total_points": total_points,
                "season_start_mv": season_start_mv
            })
        
        conn.close()
        
        # Convert to dataframe and merge
        season_df = pd.DataFrame(season_stats)
        df = df.merge(season_df, on="player_id", how="left")
        
        # Calculate season points per mv
        df["season_points_per_mv"] = np.where(
            df["season_start_mv"].notna() & (df["season_start_mv"] > 0),
            np.round((df["season_total_points"] / df["season_start_mv"]) * 1000, 2),
            np.nan
        )
        
    except Exception as e:
        print(f"Warning: Could not calculate season statistics: {e}")
    
    return df