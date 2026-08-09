from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import requests


def format_df_for_discord(df, max_rows=8, max_cols=6):
    if df is None or df.empty:
        return "No data available."

    df = df.copy()
    if len(df.columns) > max_cols:
        df = df.iloc[:, :max_cols]

    truncated = False
    if len(df) > max_rows:
        df = df.head(max_rows)
        truncated = True

    table = df.to_string(index=False, justify="left")
    if truncated:
        table += "\n... (truncated)"
    return table


def send_notification(budget_df, market_df, squad_df, webhook_url=None):
    """Send a Kickbase report using a Discord webhook."""

    webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("\nNo Discord webhook URL provided, skipping notification.")
        return

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    date_to_show = now + timedelta(days=1) if now.hour >= 22 else now
    today = date_to_show.strftime("%d-%m-%Y")

    message_parts = [f"**Kickbase Report for {today}**"]

    message_parts.append("**Manager Budgets**")
    message_parts.append(f"```\n{format_df_for_discord(budget_df)}\n```")

    message_parts.append("**Market Recommendations**")
    message_parts.append(f"```\n{format_df_for_discord(market_df)}\n```")

    message_parts.append("**Squad Recommendations**")
    message_parts.append(f"```\n{format_df_for_discord(squad_df)}\n```")

    content = "\n".join(message_parts)
    if len(content) > 1900:
        content = (
            f"**Kickbase Report for {today}**\n"
            f"Manager Budgets: {len(budget_df)} rows\n"
            f"Market Recommendations: {len(market_df)} rows\n"
            f"Squad Recommendations: {len(squad_df)} rows"
        )

    response = requests.post(webhook_url, json={"content": content})
    if response.ok:
        print("\nDiscord notification sent successfully!")
    else:
        print(f"\nFailed to send Discord notification: {response.status_code} {response.text}")


def send_mail(*args, **kwargs):
    """Legacy compatibility wrapper for email notifier."""
    print("\nThe email notifier is deprecated. Use DISCORD_WEBHOOK_URL for Discord notifications.")
    return send_notification(*args, **kwargs)
