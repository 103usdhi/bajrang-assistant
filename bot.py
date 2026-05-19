import os
import re
import json
import logging
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

import anthropic

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASANA_TOKEN = os.getenv("ASANA_TOKEN")
GOOGLE_TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

ALLOWED_USER_ID = 8106199737

logging.basicConfig(level=logging.INFO)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT = """
You are Bajrang, a highly intelligent personal AI assistant.

CRITICAL RULES:
- Maintain strong conversational continuity.
- Always infer context from recent conversation history.
- Follow short follow-ups naturally: "why?", "how?", "what about that?"
- Never ask unnecessary clarification if context already exists.
- Prioritize recent conversation first.
- Use semantic memory, explicit memory, finance data, Gmail, Calendar, and Asana when available.
- Never invent financial information.
- Be direct, intelligent and helpful.
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
    requests.post(url, headers=supabase_headers, json=data)


def get_recent_memories():
    url = f"{SUPABASE_URL}/rest/v1/events_log?select=user_message,assistant_response&order=created_at.desc&limit=20"
    result = requests.get(url, headers=supabase_headers)
    return result.json() if result.status_code == 200 else []


def save_personal_memory(memory_text):
    url = f"{SUPABASE_URL}/rest/v1/personal_memory"
    data = {
        "memory_text": memory_text,
        "memory_type": "general",
        "importance": "medium",
        "source": "telegram",
        "is_active": True
    }
    result = requests.post(url, headers=supabase_headers, json=data)
    return result.status_code in [200, 201, 204]


def get_personal_memories():
    url = f"{SUPABASE_URL}/rest/v1/personal_memory?select=memory_text&is_active=eq.true&order=created_at.desc&limit=50"
    result = requests.get(url, headers=supabase_headers)
    return result.json() if result.status_code == 200 else []


def detect_remember_command(message):
    lower = message.lower()
    phrases = ["remember ", "remember that ", "please remember ", "save this ", "note that ", "keep in mind "]

    for phrase in phrases:
        if lower.startswith(phrase):
            memory_text = message[len(phrase):].strip()
            if memory_text:
                return memory_text

    return None


def generate_embedding(text):
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


def save_semantic_memory(content):
    if not openai_client:
        return

    try:
        embedding = generate_embedding(content)
        url = f"{SUPABASE_URL}/rest/v1/semantic_memory"
        data = {
            "content": content,
            "source": "telegram",
            "embedding": embedding
        }
        requests.post(url, headers=supabase_headers, json=data)
    except Exception as e:
        print("Semantic save failed:", str(e))


def search_semantic_memory(query):
    if not openai_client:
        return []

    try:
        embedding = generate_embedding(query)
        url = f"{SUPABASE_URL}/rest/v1/rpc/match_semantic_memory"
        data = {
            "query_embedding": embedding,
            "match_threshold": 0.70,
            "match_count": 5
        }
        result = requests.post(url, headers=supabase_headers, json=data)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        print("Semantic search failed:", str(e))
        return []


def classify_finance_message(message):
    text = message.lower()
    amount_match = re.search(r"(\d+(\.\d+)?)", text)

    if not amount_match:
        return None

    amount = float(amount_match.group(1))
    transaction_type = None

    if any(k in text for k in ["salary", "income", "received", "bonus", "got paid"]):
        transaction_type = "income"
    elif any(k in text for k in ["spent", "paid", "bought", "expense", "cost", "also"]):
        transaction_type = "expense"
    elif any(k in text for k in ["saved", "saving"]):
        transaction_type = "saving"
    elif any(k in text for k in ["invested", "investment", "etf", "stock"]):
        transaction_type = "investment"
    elif any(k in text for k in ["loan", "emi", "debt"]):
        transaction_type = "debt_payment"
    elif any(k in text for k in ["refund", "returned"]):
        transaction_type = "refund"

    if not transaction_type:
        return None

    category = "general"
    subcategory = None
    is_essential = False

    rules = {
        "salary": ("salary", None, True),
        "rent": ("rent", "housing", True),
        "rewe": ("groceries", "food", True),
        "aldi": ("groceries", "food", True),
        "lidl": ("groceries", "food", True),
        "edeka": ("groceries", "food", True),
        "pizza": ("restaurant", "food", False),
        "burger": ("restaurant", "food", False),
        "coffee": ("coffee", "food", False),
        "train": ("train", "transport", True),
        "taxi": ("taxi", "transport", False),
        "uber": ("uber", "transport", False),
        "amazon": ("shopping", "lifestyle", False),
        "netflix": ("subscriptions", "lifestyle", False),
        "internet": ("internet", "housing", True),
        "electricity": ("electricity", "housing", True),
        "insurance": ("insurance", "health", True),
        "medicine": ("medicine", "health", True)
    }

    for keyword, values in rules.items():
        if keyword in text:
            category, subcategory, is_essential = values
            break

    return {
        "amount": amount,
        "transaction_type": transaction_type,
        "category": category,
        "subcategory": subcategory,
        "description": message,
        "raw_user_message": message,
        "is_essential": is_essential
    }


def save_finance_transaction(tx):
    url = f"{SUPABASE_URL}/rest/v1/finance_transactions"
    data = {
        "amount": tx["amount"],
        "currency": "EUR",
        "transaction_type": tx["transaction_type"],
        "category": tx["category"],
        "subcategory": tx["subcategory"],
        "description": tx["description"],
        "raw_user_message": tx["raw_user_message"],
        "source": "telegram",
        "is_essential": tx["is_essential"],
        "confidence_score": 0.85
    }
    requests.post(url, headers=supabase_headers, json=data)


def get_finance_summary():
    try:
        balance_url = f"{SUPABASE_URL}/rest/v1/finance_balance_overview?select=*"
        monthly_url = f"{SUPABASE_URL}/rest/v1/finance_current_month_spending?select=*"

        balance = requests.get(balance_url, headers=supabase_headers)
        monthly = requests.get(monthly_url, headers=supabase_headers)

        return json.dumps({
            "balance_overview": balance.json() if balance.status_code == 200 else [],
            "current_month_spending": monthly.json() if monthly.status_code == 200 else []
        }, indent=2)
    except Exception as e:
        return f"Finance fetch failed: {str(e)}"


def get_google_credentials():
    if not GOOGLE_TOKEN_JSON:
        return None

    token_data = json.loads(GOOGLE_TOKEN_JSON)
    return Credentials.from_authorized_user_info(token_data)


def get_gmail_summary():
    try:
        creds = get_google_credentials()

        if not creds:
            return "Google token missing."

        service = build("gmail", "v1", credentials=creds)

        results = service.users().messages().list(
            userId="me",
            maxResults=5,
            q="in:inbox"
        ).execute()

        messages = results.get("messages", [])
        emails = []

        for msg in messages:
            message = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()

            headers = message.get("payload", {}).get("headers", [])
            email = {"from": "", "subject": "", "date": ""}

            for h in headers:
                if h["name"].lower() == "from":
                    email["from"] = h["value"]
                elif h["name"].lower() == "subject":
                    email["subject"] = h["value"]
                elif h["name"].lower() == "date":
                    email["date"] = h["value"]

            emails.append(email)

        return json.dumps(emails, indent=2)
    except Exception as e:
        return f"Gmail fetch failed: {str(e)}"


def get_calendar_summary():
    try:
        creds = get_google_credentials()

        if not creds:
            return "Google token missing."

        service = build("calendar", "v3", credentials=creds)

        now = datetime.now(ZoneInfo("Europe/Berlin"))
        end = now + timedelta(days=30)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=20,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        return json.dumps(events_result.get("items", []), indent=2)
    except Exception as e:
        return f"Calendar fetch failed: {str(e)}"


def get_asana_user():
    headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}

    response = requests.get(
        "https://app.asana.com/api/1.0/users/me",
        headers=headers
    )

    if response.status_code != 200:
        return None

    return response.json()["data"]


def get_asana_tasks():
    try:
        if not ASANA_TOKEN:
            return "Asana token missing."

        user = get_asana_user()

        if not user:
            return "Could not fetch Asana user."

        headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}
        workspace_gid = user["workspaces"][0]["gid"]

        params = {
            "assignee": user["gid"],
            "workspace": workspace_gid,
            "completed_since": "now",
            "limit": 20,
            "opt_fields": "name,due_on,completed,projects.name"
        }

        task_response = requests.get(
            "https://app.asana.com/api/1.0/tasks",
            headers=headers,
            params=params
        )

        return json.dumps(task_response.json().get("data", []), indent=2)
    except Exception as e:
        return f"Asana fetch failed: {str(e)}"


def create_asana_task(task_name):
    try:
        if not ASANA_TOKEN:
            return "Asana token missing."

        user = get_asana_user()

        if not user:
            return "Could not fetch Asana user."

        headers = {
            "Authorization": f"Bearer {ASANA_TOKEN}",
            "Content-Type": "application/json"
        }

        workspace_gid = user["workspaces"][0]["gid"]

        data = {
            "data": {
                "name": task_name,
                "workspace": workspace_gid,
                "assignee": user["gid"]
            }
        }

        response = requests.post(
            "https://app.asana.com/api/1.0/tasks",
            headers=headers,
            json=data
        )

        if response.status_code in [200, 201]:
            return f"Asana task created: {task_name}"

        return f"Asana task creation failed: {response.status_code} {response.text}"
    except Exception as e:
        return f"Asana error: {str(e)}"


async def send_daily_briefing(app):
    prompt = f"""
Create my daily AI briefing.

Current date/time:
{get_current_datetime()}

Personal memories:
{json.dumps(get_personal_memories(), indent=2)}

Finance:
{get_finance_summary()}

Gmail:
{get_gmail_summary()}

Calendar:
{get_calendar_summary()}

Asana:
{get_asana_tasks()}

Output:
- greeting
- finance warning if needed
- important emails
- calendar items
- Asana priorities
- top 3 actions
- concise
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    briefing = response.content[0].text

    await app.bot.send_message(
        chat_id=ALLOWED_USER_ID,
        text=briefing
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    user_message = update.message.text
    text = user_message.lower()

    await update.message.chat.send_action("typing")

    save_semantic_memory(user_message)

    remember_text = detect_remember_command(user_message)

    if remember_text:
        saved = save_personal_memory(remember_text)

        if saved:
            reply = f"Remembered: {remember_text}"
        else:
            reply = "Memory save failed."

        save_to_supabase(user_message, reply)
        await update.message.reply_text(reply)
        return

    if text.startswith("create task ") or text.startswith("add task "):
        task_name = user_message.replace("create task", "").replace("add task", "").strip()

        if not task_name:
            await update.message.reply_text("Please provide a task name.")
            return

        result = create_asana_task(task_name)
        save_to_supabase(user_message, result)
        await update.message.reply_text(result)
        return

    finance_tx = classify_finance_message(user_message)

    if finance_tx:
        save_finance_transaction(finance_tx)

    semantic_results = search_semantic_memory(user_message)

    semantic_context = f"""
Relevant semantic memories:
{json.dumps(semantic_results, indent=2)}
"""

    runtime_context = f"""
Current date/time:
{get_current_datetime()}
Timezone: Europe/Berlin
"""

    personal_memory_context = f"""
Personal memories:
{json.dumps(get_personal_memories(), indent=2)}
"""

    finance_context = ""
    gmail_context = ""
    calendar_context = ""
    asana_context = ""

    if any(k in text for k in ["finance", "money", "balance", "spend", "spent", "expense", "salary", "income", "budget"]):
        finance_context = f"\n\nFinance live data:\n{get_finance_summary()}"

    if "email" in text or "gmail" in text:
        gmail_context = f"\n\nGmail live data:\n{get_gmail_summary()}"

    if "calendar" in text or "meeting" in text or "schedule" in text:
        calendar_context = f"\n\nCalendar live data:\n{get_calendar_summary()}"

    if "asana" in text or "task" in text or "project" in text:
        asana_context = f"\n\nAsana live data:\n{get_asana_tasks()}"

    if "daily briefing" in text or "morning briefing" in text:
        await send_daily_briefing(context.application)
        return

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
        max_tokens=1200,
        system=(
            SYSTEM_PROMPT
            + runtime_context
            + semantic_context
            + personal_memory_context
            + finance_context
            + gmail_context
            + calendar_context
            + asana_context
        ),
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

    scheduler = BackgroundScheduler(timezone="Europe/Berlin")

    scheduler.add_job(
        lambda: app.create_task(send_daily_briefing(app)),
        "cron",
        hour=8,
        minute=0
    )

    scheduler.start()

    print("Bajrang is running!")

    app.run_polling()


if __name__ == "__main__":
    main()