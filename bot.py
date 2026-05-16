import os
import re
import logging
import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import anthropic

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

logging.basicConfig(level=logging.INFO)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

SYSTEM_PROMPT = """You are Bajrang, a personal life assistant.

You help manage:
- finances
- goals
- priorities
- tasks
- planning

Rules:
- Always prioritize user's personal data.
- Be direct and concise.
- Mention overspending if relevant.
- Use previous memory when possible.
- End with one short motivational line.
"""

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}


def save_to_supabase(user_message, assistant_response):
    url = f"{SUPABASE_URL}/rest/v1/events_log"

    data = {
        "user_message": user_message,
        "assistant_response": assistant_response,
        "source": "telegram"
    }

    requests.post(url, headers=headers, json=data)


def save_expense(amount, category, description):
    url = f"{SUPABASE_URL}/rest/v1/expenses"

    data = {
        "amount": amount,
        "category": category,
        "description": description,
        "currency": "EUR",
        "source": "telegram"
    }

    result = requests.post(url, headers=headers, json=data)

    print("Expense save status:", result.status_code)


def detect_expense(user_message):
    text = user_message.lower()

    if "spent" not in text:
        return None

    amount_match = re.search(r'(\d+)', text)

    if not amount_match:
        return None

    amount = float(amount_match.group(1))

    category = "general"

    categories = {
        "food": ["food", "restaurant", "burger", "pizza", "coffee"],
        "transport": ["uber", "taxi", "train", "fuel"],
        "shopping": ["shopping", "amazon", "clothes"],
        "bills": ["rent", "electricity", "internet"]
    }

    for cat, keywords in categories.items():
        for keyword in keywords:
            if keyword in text:
                category = cat

    return {
        "amount": amount,
        "category": category,
        "description": user_message
    }


def get_recent_memories():
    url = f"{SUPABASE_URL}/rest/v1/events_log?select=user_message,assistant_response&order=created_at.desc&limit=5"

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()

    return []


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    await update.message.chat.send_action("typing")

    expense = detect_expense(user_message)

    if expense:
        save_expense(
            expense["amount"],
            expense["category"],
            expense["description"]
        )

    recent_memories = get_recent_memories()

    conversation_history = []

    for memory in reversed(recent_memories):
        conversation_history.append({
            "role": "user",
            "content": memory["user_message"]
        })

        conversation_history.append({
            "role": "assistant",
            "content": memory["assistant_response"]
        })

    conversation_history.append({
        "role": "user",
        "content": user_message
    })

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=conversation_history
    )

    reply = response.content[0].text

    save_to_supabase(user_message, reply)

    await update.message.reply_text(reply)


def main():
    print("Bajrang is starting...")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("Bajrang is running!")

    app.run_polling()


if __name__ == "__main__":
    main()