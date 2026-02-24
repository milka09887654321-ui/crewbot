# profile_wizard.py
from __future__ import annotations

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler,
    ContextTypes, filters
)
from profile_store import upsert_profile, get_profile
from pdf_gen import generate_profile_pdf

# States
(
    S_FULLNAME, S_RANK, S_NATIONALITY, S_DOB,
    S_PHONE, S_WHATSAPP, S_EMAIL, S_ENGLISH,
    S_VESSEL_EXP, S_EXPERIENCE, S_CERTS, S_AVAIL,
    S_CONFIRM
) = range(13)

CB_PROFILE_START = "profile:start"
CB_PROFILE_CANCEL = "profile:cancel"
CB_PROFILE_CONFIRM = "profile:confirm"
CB_PROFILE_EDIT = "profile:edit"
CB_PROFILE_EXPORT = "profile:export"

def _kb_confirm():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Save", callback_data=CB_PROFILE_CONFIRM)],
        [InlineKeyboardButton("✏️ Edit again", callback_data=CB_PROFILE_EDIT)],
        [InlineKeyboardButton("📄 Export PDF", callback_data=CB_PROFILE_EXPORT)],
        [InlineKeyboardButton("❌ Cancel", callback_data=CB_PROFILE_CANCEL)],
    ])

def _fmt_preview(d: dict) -> str:
    def g(k): return (d.get(k) or "Unknown").strip() or "Unknown"
    return (
        "🧾 <b>Your Profile</b>\n\n"
        f"<b>Full name:</b> {g('full_name')}\n"
        f"<b>Rank:</b> {g('rank')}\n"
        f"<b>Nationality:</b> {g('nationality')}\n"
        f"<b>D.O.B:</b> {g('dob')}\n"
        f"<b>Phone:</b> {g('phone')}\n"
        f"<b>WhatsApp:</b> {g('whatsapp')}\n"
        f"<b>Email:</b> {g('email')}\n"
        f"<b>English:</b> {g('english')}\n"
        f"<b>Available from:</b> {g('available_from')}\n"
        f"<b>Vessel experience:</b> {g('vessel_exp')}\n"
        f"<b>Experience:</b> {g('experience')}\n"
        f"<b>Certificates:</b> {g('certificates')}\n"
    )

async def profile_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Call this from your /start menu button "🧾 My Profile".
    """
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Create / Edit Profile", callback_data=CB_PROFILE_START)],
        [InlineKeyboardButton("📄 Export PDF", callback_data=CB_PROFILE_EXPORT)],
        [InlineKeyboardButton("❌ Close", callback_data=CB_PROFILE_CANCEL)]
    ])
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Profile menu:", reply_markup=kb)
    else:
        await update.message.reply_text("Profile menu:", reply_markup=kb)

async def start_wizard_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["profile_draft"] = get_profile(q.from_user.id) or {}
    await q.edit_message_text("Enter Full name (as in passport):")
    return S_FULLNAME

async def _save_text(update: Update, context: ContextTypes.DEFAULT_TYPE, field: str) -> None:
    text = (update.message.text or "").strip()
    context.user_data.setdefault("profile_draft", {})[field] = text

async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "full_name")
    await update.message.reply_text("Enter Rank (e.g., AB / OS / 2/O / C/E):")
    return S_RANK

async def rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "rank")
    await update.message.reply_text("Enter Nationality (country):")
    return S_NATIONALITY

async def nationality(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "nationality")
    await update.message.reply_text("Enter Date of birth (YYYY-MM-DD) or text:")
    return S_DOB

async def dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "dob")
    await update.message.reply_text("Enter Phone (with country code):")
    return S_PHONE

async def phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "phone")
    await update.message.reply_text("Enter WhatsApp (or type 'same' if same as phone):")
    return S_WHATSAPP

async def whatsapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text.lower() == "same":
        text = context.user_data.get("profile_draft", {}).get("phone", "") or "Unknown"
    context.user_data.setdefault("profile_draft", {})["whatsapp"] = text
    await update.message.reply_text("Enter Email:")
    return S_EMAIL

async def email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "email")
    await update.message.reply_text("English level (e.g., Good / Fluent / Basic):")
    return S_ENGLISH

async def english(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "english")
    await update.message.reply_text("Vessel experience (types/years, short):")
    return S_VESSEL_EXP

async def vessel_exp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "vessel_exp")
    await update.message.reply_text("Experience / Sea service (free text):")
    return S_EXPERIENCE

async def experience(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "experience")
    await update.message.reply_text("Certificates (COC/endorsements/etc.):")
    return S_CERTS

async def certificates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "certificates")
    await update.message.reply_text("Available from (YYYY-MM-DD or text):")
    return S_AVAIL

async def available_from(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _save_text(update, context, "available_from")
    d = context.user_data.get("profile_draft", {})
    await update.message.reply_text(_fmt_preview(d), parse_mode=ParseMode.HTML, reply_markup=_kb_confirm())
    return S_CONFIRM

async def confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = context.user_data.get("profile_draft", {})
    upsert_profile(q.from_user.id, d)
    await q.edit_message_text("✅ Profile saved.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Export PDF", callback_data=CB_PROFILE_EXPORT)],
        [InlineKeyboardButton("✏️ Edit profile", callback_data=CB_PROFILE_START)],
    ]))
    return ConversationHandler.END

async def edit_again_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Enter Full name (as in passport):")
    return S_FULLNAME

async def export_pdf_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    prof = get_profile(user_id) or context.user_data.get("profile_draft") or {}
    if not prof:
        await q.edit_message_text("No profile yet. Create it first.", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧾 Create profile", callback_data=CB_PROFILE_START)]
        ]))
        return ConversationHandler.END

    pdf = generate_profile_pdf(prof)
    filename = f"profile_{user_id}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
    await q.message.reply_document(document=pdf, filename=filename, caption="📄 Your profile PDF")
    # keep menu open
    return S_CONFIRM if context.user_data.get("profile_draft") else ConversationHandler.END

async def cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Closed.")
    else:
        await update.message.reply_text("Cancelled.")
    context.user_data.pop("profile_draft", None)
    return ConversationHandler.END

def build_profile_wizard():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_wizard_cb, pattern=f"^{CB_PROFILE_START}$")],
        states={
            S_FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, full_name)],
            S_RANK: [MessageHandler(filters.TEXT & ~filters.COMMAND, rank)],
            S_NATIONALITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, nationality)],
            S_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, dob)],
            S_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone)],
            S_WHATSAPP: [MessageHandler(filters.TEXT & ~filters.COMMAND, whatsapp)],
            S_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, email)],
            S_ENGLISH: [MessageHandler(filters.TEXT & ~filters.COMMAND, english)],
            S_VESSEL_EXP: [MessageHandler(filters.TEXT & ~filters.COMMAND, vessel_exp)],
            S_EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, experience)],
            S_CERTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, certificates)],
            S_AVAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, available_from)],
            S_CONFIRM: [
                CallbackQueryHandler(confirm_cb, pattern=f"^{CB_PROFILE_CONFIRM}$"),
                CallbackQueryHandler(edit_again_cb, pattern=f"^{CB_PROFILE_EDIT}$"),
                CallbackQueryHandler(export_pdf_cb, pattern=f"^{CB_PROFILE_EXPORT}$"),
                CallbackQueryHandler(cancel_cb, pattern=f"^{CB_PROFILE_CANCEL}$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_cb, pattern=f"^{CB_PROFILE_CANCEL}$"), CommandHandler("cancel", cancel_cb)],
        allow_reentry=True,
    )
