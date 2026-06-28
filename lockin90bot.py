import logging
from datetime import datetime, time, timedelta
import pytz
import json
import os
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ── Config ────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = -1004332813760
LOGS_TOPIC_ID = 64
GENERAL_TOPIC_ID = 1
ADMIN_ID = 8103251058
DAY_RESET_HOUR = 6
TIMEZONE = pytz.timezone("Africa/Addis_Ababa")
DATA_FILE = "streaks.json"
CHALLENGE_START = datetime(2026, 6, 29, 6, 0, 0, tzinfo=pytz.timezone("Africa/Addis_Ababa"))

# Conversation states
WAITING_FOR_MEMBER_ID = 1
WAITING_FOR_LOG = 2

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
            "member_id": "",
            "streak": 0,
            "last_log": None,
            "total_logs": 0,
        }
    return data[user_id]


def current_day_str() -> str:
    now = datetime.now(TIMEZONE)
    if now.hour < DAY_RESET_HOUR:
        now = now - timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def challenge_day_number() -> int:
    now = datetime.now(TIMEZONE)
    if now < CHALLENGE_START:
        return 0
    delta = (now - CHALLENGE_START).days + 1
    return max(1, min(delta, 90))


def build_leaderboard_text() -> str:
    data = load_data()
    if not data:
        return "No logs yet! Be the first with /log 🔥"

    sorted_users = sorted(data.items(), key=lambda x: x[1].get("streak", 0), reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    day = challenge_day_number()
    day_text = f"Day {day}/90" if day > 0 else "Challenge starts June 29"
    lines = [f"🏆 *LockIn 90 — Leaderboard*\n📅 {day_text}\n"]

    for i, (uid, profile) in enumerate(sorted_users):
        name = profile.get("name") or f"Member {i+1}"
        member_id = profile.get("member_id") or "—"
        streak_count = profile.get("streak", 0)
        medal = medals[i] if i < 3 else f"{i+1}."
        logged_today = "✅" if profile.get("last_log") == current_day_str() else "💤"
        lines.append(f"{medal} {name} (`{member_id}`) — *{streak_count} days* {logged_today}")

    lines.append("\n✅ = logged today  💤 = not yet")
    return "\n".join(lines)


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)
    profile = get_user(data, uid)

    # Already registered
    if profile.get("member_id"):
        day = challenge_day_number()
        day_text = f"We're on *Day {day}/90*!" if day > 0 else "The challenge starts *June 29*! 🚀"
        await update.message.reply_text(
            f"👋 Welcome back, {user.first_name}!\n\n{day_text}\n\n"
            "📋 *Commands:*\n"
            "/log — Submit your daily log\n"
            "/streak — See your current streak\n"
            "/leaderboard — See everyone's streaks",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    # New user — save and ask for member ID
    profile["name"] = user.first_name
    save_data(data)

    await update.message.reply_text(
        f"🌟 *Welcome to Summer LockIn 90, {user.first_name}!*\n\n"
        "Before we begin, what is your *member ID*?\n\n"
        "_(It looks like_ `LU90-001` _— check with your group admin if unsure)_",
        parse_mode="Markdown",
    )
    return WAITING_FOR_MEMBER_ID


async def save_member_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    member_id = update.message.text.strip().upper()
    data = load_data()
    uid = str(user.id)
    profile = get_user(data, uid)

    if not member_id.startswith("LU90-"):
        await update.message.reply_text(
            "⚠️ That doesn't look right. Your ID should look like `LU90-001`.\n\nTry again:",
            parse_mode="Markdown",
        )
        return WAITING_FOR_MEMBER_ID

    profile["name"] = user.first_name
    profile["member_id"] = member_id
    save_data(data)

    day = challenge_day_number()
    day_text = f"We're on *Day {day}/90*!" if day > 0 else "The challenge starts *June 29*! 🚀"

    await update.message.reply_text(
        f"✅ *You're registered, {user.first_name}!*\n"
        f"🪪 Member ID: `{member_id}`\n\n{day_text}\n\n"
        "📋 *Commands:*\n"
        "/log — Submit your daily log\n"
        "/streak — See your current streak\n"
        "/leaderboard — See everyone's streaks\n\n"
        "Show up every day. Build the habit. 🔥",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def start_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Registration cancelled. Send /start to try again.")
    return ConversationHandler.END


# ── /log ─────────────────────────────────────────────────────────────────────

async def log_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)
    profile = get_user(data, uid)

    if not profile.get("member_id"):
        await update.message.reply_text(
            "⚠️ You need to register first! Send /start to set up your member ID."
        )
        return ConversationHandler.END

    day = challenge_day_number()
    if day == 0:
        await update.message.reply_text(
            "⏳ The challenge hasn't started yet!\n\nCome back on *June 29* to submit your first log. 🚀",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    if profile["last_log"] == current_day_str():
        await update.message.reply_text(
            f"✅ You already logged today, {user.first_name}!\n"
            f"🔥 Current streak: *{profile['streak']} days*\n\nCome back tomorrow!",
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    member_id = profile["member_id"]
    await update.message.reply_text(
        f"📋 *Daily Log — Day {day}/90*\n\n"
        f"Send your log below:\n\n"
        f"`ID: {member_id}`\n"
        f"`Day: {day}/90`\n"
        "`Plan:`\n`- Task 1`\n`- Task 2`\n"
        "`Progress:`\n`- What you actually did`\n\n"
        "_Send /cancel to stop._",
        parse_mode="Markdown",
    )
    return WAITING_FOR_LOG


async def log_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)
    profile = get_user(data, uid)
    log_text = update.message.text

    if "ID:" not in log_text or ("Plan:" not in log_text and "Progress:" not in log_text):
        await update.message.reply_text(
            "⚠️ Your log needs *ID:*, *Plan:*, and *Progress:* sections.\n\nTry again or send /cancel.",
            parse_mode="Markdown",
        )
        return WAITING_FOR_LOG

    profile["streak"] += 1
    profile["last_log"] = current_day_str()
    profile["total_logs"] = profile.get("total_logs", 0) + 1
    profile["name"] = user.first_name
    save_data(data)

    streak = profile["streak"]
    milestone = ""
    if streak == 7:
        milestone = "\n\n🏅 *One week streak! Incredible!*"
    elif streak == 30:
        milestone = "\n\n🏆 *30 days! You're unstoppable!*"
    elif streak == 90:
        milestone = "\n\n👑 *90 DAYS! YOU DID IT! LEGEND!*"

    await update.message.reply_text(
        f"🔥 *Logged, {user.first_name}!*\n\n"
        f"⚡ Streak: *{streak} day{'s' if streak != 1 else ''}*{milestone}\n\n"
        "Your log has been posted to the group. Keep showing up! 💪",
        parse_mode="Markdown",
    )

    day = challenge_day_number()
    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=LOGS_TOPIC_ID,
            text=(
                f"📋 *Daily Log — Day {day}/90*\n"
                f"👤 {user.first_name} (`{profile['member_id']}`)\n"
                f"🔥 Streak: {streak} day{'s' if streak != 1 else ''}\n\n{log_text}"
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(f"Failed to post log to group: {e}")

    return ConversationHandler.END


async def log_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Log cancelled. Come back when you're ready! 💙")
    return ConversationHandler.END


# ── /streak ───────────────────────────────────────────────────────────────────

async def streak_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    uid = str(user.id)
    profile = get_user(data, uid)

    logged_today = profile.get("last_log") == current_day_str()
    status = "✅ Logged today!" if logged_today else "⚠️ Not logged yet today"

    await update.message.reply_text(
        f"📊 *Your Stats, {user.first_name}*\n\n"
        f"🪪 Member ID: `{profile.get('member_id') or 'Not registered'}`\n"
        f"🔥 Current streak: *{profile.get('streak', 0)} days*\n"
        f"📅 Total logs: *{profile.get('total_logs', 0)} days*\n"
        f"🗓 Last log: *{profile.get('last_log') or 'Never'}*\n"
        f"Today: {status}",
        parse_mode="Markdown",
    )


# ── /leaderboard ──────────────────────────────────────────────────────────────

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_leaderboard_text(), parse_mode="Markdown")


# ── /testlog (admin only) ─────────────────────────────────────────────────────

async def testlog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Admin only.")
        return

    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            message_thread_id=LOGS_TOPIC_ID,
            text=(
                "📋 *Daily Log — Day 1/90* _(TEST)_\n"
                "👤 Ruhama (`LU90-001`)\n🔥 Streak: 1 day\n\n"
                "ID: LU90-001\nDay: 1/90\nPlan:\n- Read Quran\n- Study Python\n"
                "Progress:\n- Done all ✅"
            ),
            parse_mode="Markdown",
        )
        await update.message.reply_text("✅ Test log posted to Daily Logs!")
    except Exception as e:
        await update.message.reply_text(f"❌ Failed: {e}")

    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=build_leaderboard_text() + "\n\n_(TEST)_",
            parse_mode="Markdown",
        )
        await update.message.reply_text("✅ Test leaderboard posted to General!")
    except Exception as e:
        await update.message.reply_text(f"❌ Leaderboard failed: {e}")


# ── Scheduled jobs ────────────────────────────────────────────────────────────

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    day = challenge_day_number()
    if day == 0:
        return
    data = load_data()
    for uid, profile in data.items():
        if profile.get("last_log") != current_day_str():
            try:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=(
                        f"⏰ *Day {day}/90 — Daily Reminder!*\n\n"
                        f"You haven't logged today yet.\n"
                        f"🔥 Current streak: *{profile.get('streak', 0)} days*\n\n"
                        "Don't break it! Send /log now 💪"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass


async def post_daily_leaderboard(context: ContextTypes.DEFAULT_TYPE):
    day = challenge_day_number()
    if day == 0:
        return
    try:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=build_leaderboard_text(),
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(f"Failed to post leaderboard: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    start_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_MEMBER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_member_id)
            ],
        },
        fallbacks=[CommandHandler("cancel", start_cancel)],
    )

    log_handler = ConversationHandler(
        entry_points=[CommandHandler("log", log_start)],
        states={
            WAITING_FOR_LOG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_receive)
            ],
        },
        fallbacks=[CommandHandler("cancel", log_cancel)],
    )

    application.add_handler(start_handler)
    application.add_handler(log_handler)
    application.add_handler(CommandHandler("streak", streak_cmd))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("testlog", testlog))

    # 8PM reminder
    application.job_queue.run_daily(
        send_reminder,
        time=time(20, 0, tzinfo=TIMEZONE),
        days=(0, 1, 2, 3, 4, 5, 6),
    )

    # 6AM leaderboard post
    application.job_queue.run_daily(
        post_daily_leaderboard,
        time=time(6, 0, tzinfo=TIMEZONE),
        days=(0, 1, 2, 3, 4, 5, 6),
    )

    print("✅ LockIn90 bot is running...")
    application.run_polling()


# ── Health check for Render ───────────────────────────────────────────────────

health_app = Flask(__name__)

@health_app.route("/")
def health():
    return "LockIn90 bot is running!"

def run_health():
    health_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


if __name__ == "__main__":
    Thread(target=run_health).start()
    main()