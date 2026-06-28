import logging
import re
from datetime import datetime, time, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

load_dotenv()

import json
import os

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = -1004332813760
LOGS_TOPIC_ID = 64
REMINDER_TIME = time(20, 0)           # 8:00 PM daily reminder
DAY_RESET_HOUR = 6                    # Day resets at 6:00 AM Addis time
TIMEZONE = pytz.timezone("Africa/Addis_Ababa")
DATA_FILE = "streaks.json"

# Conversation states
WAITING_FOR_LOG = 1

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# ── Data helpers ──────────────────────────────────────────────────────────────

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_user(data: dict, user_id: str) -> dict:
    if user_id not in data:
        data[user_id] = {
            "name": "",
            "streak": 0,
            "last_log": None,
            "total_logs": 0,
        }
    return data[user_id]


def current_day_str() -> str:
    """
    Returns the current 'accountability day' as YYYY-MM-DD.
    Days before 6AM still count as the previous calendar day.
    """
    now = datetime.now(TIMEZONE)
    if now.hour < DAY_RESET_HOUR:
        now = now - timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def challenge_day_number() -> int:
    """Returns what day of the 90-day challenge we're on (starting from day 1)."""
    # Challenge start date — update this to your actual start date
    start_date = datetime(2026, 6, 29, tzinfo=TIMEZONE)
    today = datetime.now(TIMEZONE)
    delta = (today - start_date).days + 1
    return max(1, min(delta, 90))


# ── Commands ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)
    profile = get_user(data, uid)
    profile["name"] = user.first_name
    save_data(data)

    day = challenge_day_number()

    await update.message.reply_text(
        f"🌟 *Welcome to Summer LockIn 90, {user.first_name}!*\n\n"
        f"We're on *Day {day}/90* of the challenge.\n\n"
        "📋 *Commands:*\n"
        "/log — Submit your daily log\n"
        "/streak — See your current streak\n"
        "/leaderboard — See everyone's streaks\n\n"
        "Show up every day. Build the habit. 🔥",
        parse_mode="Markdown",
    )


async def log_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)
    profile = get_user(data, uid)

    if profile["last_log"] == current_day_str():
        await update.message.reply_text(
            f"✅ You already logged today, {user.first_name}!\n"
            f"🔥 Current streak: *{profile['streak']} days*\n\n"
            "Come back tomorrow and keep it going!",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    day = challenge_day_number()

    await update.message.reply_text(
        f"📋 *Daily Log — Day {day}/90*\n\n"
        "Send your log in this format:\n\n"
        "`ID: LU90-XXX`\n"
        "`Day: {day}/90`\n"
        "`Plan:`\n"
        "`- Task 1`\n"
        "`- Task 2`\n"
        "`Progress:`\n"
        "`- What you actually did`\n\n"
        "_Replace XXX with your member ID number._",
        parse_mode="Markdown",
    )
    return WAITING_FOR_LOG


async def log_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)
    profile = get_user(data, uid)
    log_text = update.message.text

    # Basic validation — must contain ID: and either Plan: or Progress:
    if "ID:" not in log_text or ("Plan:" not in log_text and "Progress:" not in log_text):
        await update.message.reply_text(
            "⚠️ Your log doesn't look quite right.\n\n"
            "Make sure it includes *ID:*, *Plan:*, and *Progress:* sections.\n"
            "Try again or send /cancel to stop.",
            parse_mode="Markdown",
        )
        return WAITING_FOR_LOG

    # Update streak
    profile["streak"] += 1
    profile["last_log"] = current_day_str()
    profile["total_logs"] = profile.get("total_logs", 0) + 1
    profile["name"] = user.first_name
    save_data(data)

    streak = profile["streak"]

    # Milestone check
    milestone = ""
    if streak == 7:
        milestone = "\n\n🏅 *One week streak! Incredible!*"
    elif streak == 30:
        milestone = "\n\n🏆 *30 days! You're unstoppable!*"
    elif streak == 90:
        milestone = "\n\n👑 *90 DAYS! YOU DID IT! LEGEND!*"

    # Confirm to user
    await update.message.reply_text(
        f"🔥 *Logged, {user.first_name}!*\n\n"
        f"⚡ Streak: *{streak} day{'s' if streak != 1 else ''}*{milestone}\n\n"
        "Your log has been posted to the group. Keep showing up! 💪",
        parse_mode="Markdown",
    )

    # Post to group logs topic
    group_message = (
        f"📋 *Daily Log from {user.first_name}*\n"
        f"🔥 Streak: {streak} day{'s' if streak != 1 else ''}\n\n"
        f"{log_text}"
    )

    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=LOGS_TOPIC_ID,
            text=group_message,
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(f"Failed to post to group: {e}")

    return ConversationHandler.END


async def log_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Log cancelled. Come back when you're ready! 💙")
    return ConversationHandler.END


async def streak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)
    profile = get_user(data, uid)

    current = profile["streak"]
    total = profile.get("total_logs", 0)
    last = profile["last_log"] or "Never"
    logged_today = profile["last_log"] == current_day_str()
    status = "✅ Logged today!" if logged_today else "⚠️ Not logged yet today"

    await update.message.reply_text(
        f"📊 *Your Stats, {user.first_name}*\n\n"
        f"🔥 Current streak: *{current} days*\n"
        f"📅 Total logs: *{total} days*\n"
        f"🗓 Last log: *{last}*\n"
        f"Today: {status}",
        parse_mode="Markdown",
    )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()

    if not data:
        await update.message.reply_text("No one has logged yet! Be the first with /log 🔥")
        return

    sorted_users = sorted(data.items(), key=lambda x: x[1].get("streak", 0), reverse=True)

    medals = ["🥇", "🥈", "🥉"]
    day = challenge_day_number()
    lines = [f"🏆 *LockIn 90 — Leaderboard*\n📅 Day {day}/90\n"]

    for i, (uid, profile) in enumerate(sorted_users):
        name = profile.get("name") or f"Member {i+1}"
        streak_count = profile.get("streak", 0)
        medal = medals[i] if i < 3 else f"{i+1}."
        logged_today = "✅" if profile.get("last_log") == current_day_str() else "💤"
        lines.append(f"{medal} {name} — *{streak_count} days* {logged_today}")

    lines.append("\n✅ = logged today  💤 = not yet")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Daily reminder ────────────────────────────────────────────────────────────

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    for uid, profile in data.items():
        if profile.get("last_log") != current_day_str():
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=(
                        "⏰ *Daily Reminder!*\n\n"
                        "You haven't logged today yet.\n"
                        "Don't break your streak! Send /log now 🔥\n\n"
                        f"🔥 Current streak: *{profile.get('streak', 0)} days*"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for /log
    log_handler = ConversationHandler(
        entry_points=[CommandHandler("log", log_start)],
        states={
            WAITING_FOR_LOG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_receive)
            ],
        },
        fallbacks=[CommandHandler("cancel", log_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(log_handler)
    app.add_handler(CommandHandler("streak", streak))
    app.add_handler(CommandHandler("leaderboard", leaderboard))

    # Daily reminder at 8PM Addis time
    app.job_queue.run_daily(
        send_reminder,
        time=time(20, 0, tzinfo=TIMEZONE),
        days=(0, 1, 2, 3, 4, 5, 6),
    )

    print("✅ LockIn90 bot is running...")
    app.run_polling()

from threading import Thread
from flask import Flask
health_app = Flask(__name__)

@health_app.route("/")
def health():
    return "Bot is running!"

def run_health():
    health_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    Thread(target=run_health).start()
    main()
