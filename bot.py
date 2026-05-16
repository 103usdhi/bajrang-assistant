import os
import re
import logging
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import anthropic

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# YOUR TELEGRAM USER ID
ALLOWED_USER_ID = 8106199737

logging.basicConfig(level=logging.INFO)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

SYSTEM_PROMPT = """You are Bajrang, a personal life assistant.

You help manage:
- finances
- goals
- priorities
- tasks
- planning
- daily decisions

Rules:
- Always prioritize the user's personal data.
- Be direct and concise.
- Mention overspending if relevant.
- Use previous memory when possible.
- Use runtime date/time context if available.
- End every response with one short motivational line.
"""

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}


def get_current_datetime():
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    return now.strftime("%A, %d %B %Y, %H:%M")


def save_to_supabase(user_message, assistant_response):
    url = f"{SUPABASE_URL}/rest/v1/events_log"

    data = {
        "user_message": user_message,
        "assistant_response": assistant_response,
        "source": "telegram"
    }

    result = requests.post(url, headers=headers, json=data)

    if result.status_code not in [200, 201, 204]:
        print("Event save failed:", result.status_code, result.text)


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

    if result.status_code not in [200, 201, 204]:
        print("Expense save failed:", result.status_code, result.text)
    else:
        print("Expense save status:", result.status_code)


def detect_expense(user_message):
    text = user_message.lower()

    expense_keywords = ["spent", "paid", "bought", "expense"]

    if not any(keyword in text for keyword in expense_keywords):
        return None

    amount_match = re.search(r'(\d+(\.\d+)?)', text)

    if not amount_match:
        return None

    amount = float(amount_match.group(1))

    category = "general"

    categories = {
        "food": ["food", "pizza", "burger", "coffee", "restaurant", "groceries"],
        "transport": ["uber", "taxi", "fuel", "train", "bus"],
        "shopping": ["shopping", "amazon", "clothes", "shoes"],
        "bills": ["rent", "internet", "electricity", "insurance"],
        "health": ["doctor", "medicine", "hospital", "pharmacy"],
        "entertainment": ["movie", "netflix", "party", "cinema"]
    }

    for cat, keywords in categories.items():
        for keyword in keywords:
            if keyword in text:
                category = cat
                break

    return {
        "amount": amount,
        "category": category,
        "description": user_message
    }


def get_recent_memories():
    url = f"{SUPABASE_URL}/rest/v1/events_log?select=user_message,assistant_response&order=created_at.desc&limit=5"

    result = requests.get(url, headers=headers)

    if result.status_code == 200:
        return result.json()

    print("Memory fetch failed:", result.status_code, result.text)
    return []


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # SECURITY CHECK
    if update.effective_user.id != ALLOWED_USER_ID:
        print(f"Blocked unauthorized user: {update.effective_user.id}")
        return

    user_message = update.message.text

    await update.message.chat.send_action("typing")

    current_datetime = get_current_datetime()

    runtime_context = f"""

Runtime context:
- Current date and time: {current_datetime}
- Timezone: Europe/Berlin
- User location context: Germany
"""

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
        system=SYSTEM_PROMPT + runtime_context,
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