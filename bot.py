import os
import re
import json
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
ASANA_TOKEN = os.getenv("ASANA_TOKEN")

ALLOWED_USER_ID = 8106199737

logging.basicConfig(level=logging.INFO)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

SYSTEM_PROMPT = """You are Bajrang, a highly intelligent personal AI assistant.

Your primary responsibility is to help the user using:
- personal memory
- saved data
- expenses
- goals
- priorities
- tasks
- decisions
- planning

However:
- you are NOT limited to those topics.
- you can answer general questions normally like a modern AI assistant.
- when personal context exists, prioritize it first.
- when personal context does not exist, answer using general intelligence.

Rules:
- Be direct and concise.
- Avoid unnecessary fluff.
- Use runtime context when available.
- Use memory when relevant.
- Never pretend data exists when it does not.
- Respond naturally like a premium AI assistant.
"""

supabase_headers = {
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

    result = requests.post(url, headers=supabase_headers, json=data)

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

    result = requests.post(url, headers=supabase_headers, json=data)

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

    result = requests.get(url, headers=supabase_headers)

    if result.status_code == 200:
        return result.json()

    print("Memory fetch failed:", result.status_code, result.text)
    return []


def test_asana_connection():
    if not ASANA_TOKEN:
        print("ASANA TEST: ASANA_TOKEN missing")
        return

    asana_headers = {
        "Authorization": f"Bearer {ASANA_TOKEN}"
    }

    url = "https://app.asana.com/api/1.0/users/me"

    response = requests.get(url, headers=asana_headers)

    print("ASANA STATUS:", response.status_code)

    try:
        print("ASANA RESPONSE:", json.dumps(response.json(), indent=2))
    except Exception:
        print("ASANA RAW RESPONSE:", response.text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ALLOWED_USER_ID:
        print(f"Blocked unauthorized user: {update.effective_user.id}")
        return

    user_message = update.message.text

    await update.message.chat.send_action("typing")

    # Temporary Asana API test
    if "test asana" in user_message.lower():
        test_asana_connection()
        await update.message.reply_text("Asana test executed. Check Render logs.")
        return

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