import os
import re
import json
import logging
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    filters,
    ContextTypes
)

import anthropic

load_dotenv()

# =========================
# ENV VARIABLES
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

ALLOWED_USER_ID = 8106199737

# =========================
# LOGGING
# =========================

logging.basicConfig(level=logging.INFO)

# =========================
# CLIENTS
# =========================

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

openai_client = OpenAI(
    api_key=OPENAI_API_KEY
)

# =========================
# SYSTEM PROMPT
# =========================

SYSTEM_PROMPT = """
You are Bajrang, a powerful personal AI assistant.

Rules:
- Maintain conversation continuity
- Use memory when relevant
- Be direct and intelligent
- Never invent financial information
- Help with planning, finance, productivity and life management
"""

# =========================
# SUPABASE
# =========================

supabase_headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

# =========================
# HELPERS
# =========================

def get_current_datetime():
    now = datetime.now(ZoneInfo("Europe/Berlin"))
    return now.strftime("%A, %d %B %Y, %H:%M")


# =========================
# CHAT MEMORY
# =========================

def save_to_supabase(user_message, assistant_response):

    url = f"{SUPABASE_URL}/rest/v1/events_log"

    data = {
        "user_message": user_message,
        "assistant_response": assistant_response,
        "source": "telegram"
    }

    requests.post(
        url,
        headers=supabase_headers,
        json=data
    )


def get_recent_memories():

    url = f"{SUPABASE_URL}/rest/v1/events_log?select=user_message,assistant_response&order=created_at.desc&limit=20"

    result = requests.get(
        url,
        headers=supabase_headers
    )

    if result.status_code == 200:
        return result.json()

    return []


# =========================
# PERSONAL MEMORY
# =========================

def save_personal_memory(memory_text):

    url = f"{SUPABASE_URL}/rest/v1/personal_memory"

    data = {
        "memory_text": memory_text,
        "memory_type": "general",
        "importance": "medium",
        "source": "telegram",
        "is_active": True
    }

    result = requests.post(
        url,
        headers=supabase_headers,
        json=data
    )

    return result.status_code in [200, 201, 204]


def get_personal_memories():

    url = f"{SUPABASE_URL}/rest/v1/personal_memory?select=memory_text&is_active=eq.true&order=created_at.desc&limit=50"

    result = requests.get(
        url,
        headers=supabase_headers
    )

    if result.status_code == 200:
        return result.json()

    return []


def detect_remember_command(message):

    lower = message.lower()

    remember_phrases = [
        "remember ",
        "remember that ",
        "please remember ",
        "save this ",
        "note that "
    ]

    for phrase in remember_phrases:

        if lower.startswith(phrase):

            memory_text = message[len(phrase):].strip()

            if memory_text:
                return memory_text

    return None


# =========================
# SEMANTIC MEMORY
# =========================

def generate_embedding(text):

    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )

    return response.data[0].embedding


def save_semantic_memory(content):

    if not OPENAI_API_KEY:
        return

    try:

        embedding = generate_embedding(content)

        url = f"{SUPABASE_URL}/rest/v1/semantic_memory"

        data = {
            "content": content,
            "source": "telegram",
            "embedding": embedding
        }

        requests.post(
            url,
            headers=supabase_headers,
            json=data
        )

    except Exception as e:
        print("Semantic save failed:", str(e))


def search_semantic_memory(query):

    if not OPENAI_API_KEY:
        return []

    try:

        embedding = generate_embedding(query)

        url = f"{SUPABASE_URL}/rest/v1/rpc/match_semantic_memory"

        data = {
            "query_embedding": embedding,
            "match_threshold": 0.70,
            "match_count": 5
        }

        result = requests.post(
            url,
            headers=supabase_headers,
            json=data
        )

        if result.status_code == 200:
            return result.json()

        return []

    except Exception as e:
        print("Semantic search failed:", str(e))
        return []


# =========================
# FINANCE
# =========================

def classify_finance_message(message):

    text = message.lower()

    amount_match = re.search(r"(\\d+(\\.\\d+)?)", text)

    if not amount_match:
        return None

    amount = float(amount_match.group(1))

    transaction_type = None

    if any(k in text for k in [
        "salary",
        "income",
        "received",
        "bonus"
    ]):
        transaction_type = "income"

    elif any(k in text for k in [
        "spent",
        "paid",
        "bought",
        "expense"
    ]):
        transaction_type = "expense"

    if not transaction_type:
        return None

    return {
        "amount": amount,
        "transaction_type": transaction_type,
        "description": message
    }


def save_finance_transaction(tx):

    url = f"{SUPABASE_URL}/rest/v1/finance_transactions"

    data = {
        "amount": tx["amount"],
        "currency": "EUR",
        "transaction_type": tx["transaction_type"],
        "description": tx["description"],
        "source": "telegram"
    }

    requests.post(
        url,
        headers=supabase_headers,
        json=data
    )


# =========================
# MAIN CHAT HANDLER
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ALLOWED_USER_ID:
        return

    user_message = update.message.text

    save_semantic_memory(user_message)

    remember_text = detect_remember_command(
        user_message
    )

    if remember_text:

        saved = save_personal_memory(
            remember_text
        )

        if saved:
            reply = f"Remembered: {remember_text}"
        else:
            reply = "Memory save failed."

        save_to_supabase(
            user_message,
            reply
        )

        await update.message.reply_text(reply)

        return

    finance_tx = classify_finance_message(
        user_message
    )

    if finance_tx:
        save_finance_transaction(finance_tx)

    semantic_results = search_semantic_memory(
        user_message
    )

    semantic_context = f"""
Relevant semantic memories:
{json.dumps(semantic_results, indent=2)}
"""

    personal_memory_context = f"""
Personal memories:
{json.dumps(get_personal_memories(), indent=2)}
"""

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
        model="claude-sonnet-4-20250514",
        max_tokens=1200,
        system=(
            SYSTEM_PROMPT
            + semantic_context
            + personal_memory_context
        ),
        messages=conversation_history
    )

    reply = response.content[0].text

    save_to_supabase(
        user_message,
        reply
    )

    await update.message.reply_text(reply)


# =========================
# MAIN
# =========================

def main():

    print("Bajrang is starting...")

    app = Application.builder().token(
        TELEGRAM_TOKEN
    ).build()

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("Bajrang is running!")

    app.run_polling()


if __name__ == "__main__":
    main()