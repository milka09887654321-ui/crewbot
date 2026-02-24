from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

import os
TOKEN = os.getenv("TOKEN")

def main_menu():
    keyboard = [
        ["⚓ Latest Jobs", "🌐 Website"],
        ["📄 Apply Online", "📧 Contact"],
        ["ℹ️ About CrewOnBoard"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
⚓ Welcome to CrewOnBoard

Global Maritime Job Platform 🌍

Find maritime jobs worldwide.
"""

    await update.message.reply_text(text, reply_markup=main_menu())


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.message.text

    if message == "⚓ Latest Jobs":

        await update.message.reply_text(
            "⚓ Latest Jobs:\n\nhttps://crewonboard.net/vacancies"
        )

    elif message == "🌐 Website":

        await update.message.reply_text(
            "🌐 https://crewonboard.net"
        )

    elif message == "📄 Apply Online":

        await update.message.reply_text(
            "📄 Apply here:\n\nhttps://crewonboard.net"
        )

    elif message == "📧 Contact":

        await update.message.reply_text(
            "📧 crew@crewonboard.net"
        )

    elif message == "ℹ️ About CrewOnBoard":

        await update.message.reply_text(
            "CrewOnBoard is a global maritime job platform."
        )


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

app.add_handler(MessageHandler(filters.TEXT, menu))

app.run_polling()
