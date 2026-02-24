import os
import re
import sqlite3
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TOKEN", "").strip()
if not TOKEN or ":" not in TOKEN:
    raise RuntimeError("TOKEN is missing/invalid. Set Railway Variable TOKEN from @BotFather.")

BASE_URL = "https://crewonboard.net/"
DB_PATH = "crewbot.sqlite"
CHECK_EVERY_SECONDS = 600  # 10 minutes

VAC_RE = re.compile(r"/vacancy/detail/(\d+)", re.IGNORECASE)


# ---------------- DB ----------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subscriptions (
            chat_id INTEGER PRIMARY KEY,
            rank_filter TEXT DEFAULT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_vacancies (
            vacancy_id INTEGER PRIMARY KEY,
            first_seen_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def sub_add(chat_id: int):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO subscriptions(chat_id, rank_filter, created_at) VALUES(?, NULL, ?)",
        (chat_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def sub_remove(chat_id: int):
    conn = db()
    conn.execute("DELETE FROM subscriptions WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()


def sub_set_rank(chat_id: int, rank: str | None):
    conn = db()
    conn.execute(
        "INSERT OR IGNORE INTO subscriptions(chat_id, rank_filter, created_at) VALUES(?, NULL, ?)",
        (chat_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.execute("UPDATE subscriptions SET rank_filter=? WHERE chat_id=?", (rank, chat_id))
    conn.commit()
    conn.close()


def sub_list():
    conn = db()
    rows = conn.execute("SELECT chat_id, rank_filter FROM subscriptions").fetchall()
    conn.close()
    return rows


def seen_add(vacancy_id: int) -> bool:
    """True if new, False if already seen."""
    conn = db()
    cur = conn.execute("SELECT 1 FROM seen_vacancies WHERE vacancy_id=?", (vacancy_id,))
    exists = cur.fetchone() is not None
    if not exists:
        conn.execute(
            "INSERT INTO seen_vacancies(vacancy_id, first_seen_at) VALUES(?, ?)",
            (vacancy_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    conn.close()
    return not exists


# ---------------- SCRAPE (Homepage IDs) ----------------
def fetch_latest_vacancy_ids(limit: int = 30) -> list[int]:
    """Strictly loads BASE_URL and extracts vacancy IDs from links like /vacancy/detail/12345"""
    r = requests.get(
        BASE_URL,
        timeout=25,
        headers={"User-Agent": "crewbot/1.0 (Telegram bot)"},
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    ids: list[int] = []

    for a in soup.select("a[href]"):
        href = a.get("href") or ""
        m = VAC_RE.search(href)
        if m:
            ids.append(int(m.group(1)))

    # unique keep order
    seen = set()
    uniq = []
    for vid in ids:
        if vid not in seen:
            seen.add(vid)
            uniq.append(vid)

    return uniq[:limit]


def vacancy_link(vacancy_id: int) -> str:
    return f"{BASE_URL}vacancy/detail/{vacancy_id}"


# ---------------- SCRAPE (Vacancy details) ----------------
def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _norm_key(s: str) -> str:
    s = _clean(s).lower()
    s = s.replace(":", "")
    return s


def parse_detail_pairs(soup: BeautifulSoup) -> dict[str, str]:
    """
    Tries to extract key/value pairs from common HTML patterns:
    - table rows (th/td)
    - dt/dd definition lists
    """
    pairs: dict[str, str] = {}

    # tables
    for tr in soup.select("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if th and td:
            k = _norm_key(th.get_text(" ", strip=True))
            v = _clean(td.get_text(" ", strip=True))
            if k and v:
                pairs[k] = v

    # dt/dd
    for dl in soup.select("dl"):
        dts = dl.find_all("dt")
        for dt in dts:
            dd = dt.find_next_sibling("dd")
            if dd:
                k = _norm_key(dt.get_text(" ", strip=True))
                v = _clean(dd.get_text(" ", strip=True))
                if k and v:
                    pairs[k] = v

    return pairs


def guess_details_from_text(text: str) -> dict[str, str]:
    """
    Fallback: regex search in full page text.
    """
    out: dict[str, str] = {}
    t = _clean(text)

    # Common labels
    patterns = {
        "rank": [
            r"(rank|position)\s*[:\-]\s*([A-Za-z0-9/ &\.\-]+)",
        ],
        "vessel": [
            r"(vessel|vessel type|ship type)\s*[:\-]\s*([A-Za-z0-9/ &\.\-]+)",
        ],
        "salary": [
            r"(salary|wage)\s*[:\-]\s*([A-Za-z0-9/ €$£\.\-,]+)",
        ],
        "contract": [
            r"(contract|contract duration)\s*[:\-]\s*([A-Za-z0-9/ &\.\-]+)",
        ],
    }

    for field, pats in patterns.items():
        for p in pats:
            m = re.search(p, t, flags=re.IGNORECASE)
            if m:
                out[field] = _clean(m.group(2))
                break

    return out


def fetch_vacancy_details(vacancy_id: int) -> dict[str, str]:
    """
    Loads vacancy detail page and tries to extract Rank/Vessel/Salary/Contract.
    """
    url = vacancy_link(vacancy_id)
    r = requests.get(url, timeout=25, headers={"User-Agent": "crewbot/1.0 (Telegram bot)"})
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    # 1) extract pairs from tables/dl
    pairs = parse_detail_pairs(soup)

    # map keys to our fields (different sites use different labels)
    def pick(*keys: str) -> str | None:
        for k in keys:
            nk = _norm_key(k)
            for kk, vv in pairs.items():
                if kk == nk:
                    return vv
        return None

    rank = pick("Rank", "Position", "Post", "Vacancy", "Job title")
    vessel = pick("Vessel", "Vessel type", "Ship type", "Type of vessel")
    salary = pick("Salary", "Wage", "Salary per month", "Monthly salary")
    contract = pick("Contract", "Contract duration", "Duration", "Period")

    # 2) fallback from full text if something missing
    text = soup.get_text(" ", strip=True)
    guessed = guess_details_from_text(text)

    rank = rank or guessed.get("rank")
    vessel = vessel or guessed.get("vessel")
    salary = salary or guessed.get("salary")
    contract = contract or guessed.get("contract")

    # final cleanup / defaults
    rank = rank or "Unknown"
    vessel = vessel or "Unknown"
    salary = salary or "Negotiable"
    contract = contract or "Unknown"

    return {
        "rank": _clean(rank),
        "vessel": _clean(vessel),
        "salary": _clean(salary),
        "contract": _clean(contract),
        "url": url,
    }


def format_vacancy_message(d: dict[str, str]) -> str:
    return (
        "🆕 NEW VACANCY\n\n"
        f"⚓ Rank: {d['rank']}\n"
        f"🚢 Vessel: {d['vessel']}\n"
        f"💰 Salary: {d['salary']}\n"
        f"📄 Contract: {d['contract']}\n\n"
        f"🔗 {d['url']}"
    )


# ---------------- BOT UI ----------------
RANKS = [
    "Any", "Master", "Chief Officer", "2nd Officer", "3rd Officer",
    "Chief Engineer", "2nd Engineer", "3rd Engineer", "4th Engineer",
    "AB", "OS", "Fitter", "Oiler", "Cook", "ETO"
]


def main_menu():
    keyboard = [
        ["⚓ Latest Jobs", "🌐 Website"],
        ["🔔 Subscribe", "🔕 Unsubscribe"],
        ["🎯 Set Rank Filter", "❌ Clear Filter"],
        ["📄 Apply Online", "📧 Contact"],
        ["ℹ️ About CrewOnBoard"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def rank_menu():
    rows = []
    row = []
    for i, r in enumerate(RANKS, 1):
        row.append(r)
        if i % 3 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(["⬅️ Back"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "⚓ Welcome to CrewOnBoard\n\n"
        "Global Maritime Job Platform 🌍\n\n"
        "Press 🔔 Subscribe to receive new vacancies.\n"
        "Press ⚓ Latest Jobs to see recent links from homepage."
    )
    await update.message.reply_text(text, reply_markup=main_menu())


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    conn = db()
    row = conn.execute("SELECT rank_filter FROM subscriptions WHERE chat_id=?", (chat_id,)).fetchone()
    conn.close()

    if row is None:
        await update.message.reply_text("Status: not subscribed.", reply_markup=main_menu())
    else:
        rf = row[0] or "Any"
        await update.message.reply_text(f"Status: subscribed ✅\nRank filter: {rf}", reply_markup=main_menu())


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    # rank selection flow
    if context.user_data.get("awaiting_rank"):
        if message == "⬅️ Back":
            context.user_data["awaiting_rank"] = False
            await update.message.reply_text("Back to menu.", reply_markup=main_menu())
            return

        if message not in RANKS:
            await update.message.reply_text("Choose rank using buttons.", reply_markup=rank_menu())
            return

        context.user_data["awaiting_rank"] = False
        if message == "Any":
            sub_set_rank(chat_id, None)
            await update.message.reply_text("✅ Rank filter set to: Any", reply_markup=main_menu())
        else:
            sub_set_rank(chat_id, message)
            await update.message.reply_text(f"✅ Rank filter set to: {message}", reply_markup=main_menu())
        return

    if message == "⚓ Latest Jobs":
        try:
            ids = fetch_latest_vacancy_ids(limit=10)
            if not ids:
                await update.message.reply_text("No jobs found on homepage right now.", reply_markup=main_menu())
                return

            lines = ["⚓ Latest Jobs (from homepage):\n"]
            for vid in ids:
                lines.append(vacancy_link(vid))
            await update.message.reply_text("\n".join(lines), reply_markup=main_menu())
        except Exception as e:
            await update.message.reply_text(f"Error loading jobs: {e}", reply_markup=main_menu())

    elif message == "🌐 Website":
        await update.message.reply_text("🌐 https://crewonboard.net", reply_markup=main_menu())

    elif message == "📄 Apply Online":
        await update.message.reply_text("📄 Apply here:\n\nhttps://crewonboard.net", reply_markup=main_menu())

    elif message == "📧 Contact":
        await update.message.reply_text("📧 crew@crewonboard.net", reply_markup=main_menu())

    elif message == "ℹ️ About CrewOnBoard":
        await update.message.reply_text("CrewOnBoard is a global maritime job platform.", reply_markup=main_menu())

    elif message == "🔔 Subscribe":
        sub_add(chat_id)
        await update.message.reply_text("✅ Subscribed! I will send new jobs (with details).", reply_markup=main_menu())

    elif message == "🔕 Unsubscribe":
        sub_remove(chat_id)
        await update.message.reply_text("✅ Unsubscribed.", reply_markup=main_menu())

    elif message == "🎯 Set Rank Filter":
        sub_add(chat_id)
        context.user_data["awaiting_rank"] = True
        await update.message.reply_text("Choose rank filter:", reply_markup=rank_menu())

    elif message == "❌ Clear Filter":
        sub_set_rank(chat_id, None)
        await update.message.reply_text("✅ Filter cleared (Any).", reply_markup=main_menu())

    else:
        await update.message.reply_text("Choose an option from the menu 👇", reply_markup=main_menu())


# ---------------- BACKGROUND CHECK ----------------
async def check_new_jobs(context: ContextTypes.DEFAULT_TYPE):
    try:
        ids = fetch_latest_vacancy_ids(limit=30)
        if not ids:
            return

        new_ids = []
        for vid in ids:
            if seen_add(vid):
                new_ids.append(vid)

        if not new_ids:
            return

        subs = sub_list()

        # For each new vacancy, load details once, then send to all subs
        for vid in new_ids[:10]:
            details = fetch_vacancy_details(vid)
            msg = format_vacancy_message(details)

            for chat_id, rank_filter in subs:
                # rank filter (simple contains match)
                if rank_filter:
                    if rank_filter.lower() not in details["rank"].lower():
                        continue
                await context.bot.send_message(chat_id=chat_id, text=msg)

    except Exception:
        return


# ---------------- RUN ----------------
def main():
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))
    application.add_handler(CommandHandler("testadmin", test_admin))

    application.job_queue.run_repeating(check_new_jobs, interval=CHECK_EVERY_SECONDS, first=10)

    application.run_polling()

import os
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

async def test_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_chat_id = int(os.getenv("ADMIN_CHAT_ID", "0"))
    
    if admin_chat_id == 0:
        await update.message.reply_text("ADMIN_CHAT_ID not found")
        return

    await context.bot.send_message(
        chat_id=admin_chat_id,
        text="Admin test message ✅"
    )

    await update.message.reply_text("Я отправил сообщение в админ-чат ✅")


if __name__ == "__main__":
    main()
    
