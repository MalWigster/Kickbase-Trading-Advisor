from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import requests


def format_df_for_discord(df, max_rows=20, max_cols=8):
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


def split_long_text(text, max_length=1900):
    if len(text) <= max_length:
        yield text
        return

    lines = text.splitlines(keepends=True)
    chunk = ""

    for line in lines:
        if len(chunk) + len(line) <= max_length:
            chunk += line
            continue

        if chunk:
            yield chunk
            chunk = ""

        if len(line) <= max_length:
            chunk = line
        else:
            for index in range(0, len(line), max_length):
                yield line[index:index + max_length]

    if chunk:
        yield chunk


def _send_webhook_message(webhook_url, content):
    response = requests.post(webhook_url, json={"content": content}, timeout=10)
    if not response.ok:
        print(f"\nFailed to send Discord notification: {response.status_code} {response.text}")
        return False
    return True


def send_notification(budget_df, market_df, squad_df, webhook_url=None):
    """Send a Kickbase report using a Discord webhook."""

    webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("\nNo Discord webhook URL provided, skipping notification.")
        return

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    date_to_show = now + timedelta(days=1) if now.hour >= 22 else now
    today = date_to_show.strftime("%d-%m-%Y")

    messages = [f"**Kickbase Report for {today}**"]
    for title, df in (
        ("Manager Budgets", budget_df),
        ("Market Recommendations", market_df),
        ("Squad Recommendations", squad_df),
    ):
        table_text = format_df_for_discord(df)
        chunks = list(split_long_text(table_text, max_length=1900 - 8))
        for index, chunk in enumerate(chunks):
            if index == 0:
                messages.append(f"**{title}**\n```\n{chunk}\n```")
            else:
                messages.append(f"```\n{chunk}\n```")

    for content in messages:
        if not _send_webhook_message(webhook_url, content):
            return

    print("\nDiscord notification sent successfully!")


def send_mail(*args, **kwargs):
    """Legacy compatibility wrapper for email notifier."""
    print("\nThe email notifier is deprecated. Use DISCORD_WEBHOOK_URL for Discord notifications.")
    return send_notification(*args, **kwargs)
