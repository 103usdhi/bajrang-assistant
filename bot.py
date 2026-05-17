import os
import re
import json
import logging
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
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
ASANA_TOKEN = os.getenv("ASANA_TOKEN")
GOOGLE_TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

ALLOWED_USER_ID = 8106199737

logging.basicConfig(level=logging.INFO)
client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

SYSTEM_PROMPT = """
You are Bajrang, a personal AI assistant.

You can use:
- personal memory
- finance database
- Gmail
- Google Calendar
- Asana

Rules:
- Maintain conversation flow.
- Understand follow-up messages using recent chat history.
- Prioritize user's personal data.
- Never invent financial numbers.
- Be direct and useful.
- If user says "also", "that", "same", "continue", use recent context.
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

    if result.status_code == 200:
        return result.json()

    print("Memory fetch failed:", result.status_code, result.text)
    return []


def classify_finance_message(message):
    text = message.lower()

    amount_match = re.search(r"(\d+(\.\d+)?)", text)
    if not amount_match:
        return None

    amount = float(amount_match.group(1))
    transaction_type = None

    if any(k in text for k in ["salary", "income", "received", "got paid", "bonus"]):
        transaction_type = "income"
    elif any(k in text for k in ["spent", "paid", "bought", "cost", "expense", "also"]):
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

    result = requests.post(url, headers=supabase_headers, json=data)

    if result.status_code not in [200, 201, 204]:
        print("Finance save failed:", result.status_code, result.text)
    else:
        print("Finance transaction saved:", result.status_code)


def get_finance_summary():
    try:
        balance_url = f"{SUPABASE_URL}/rest/v1/finance_balance_overview?select=*"
        balance = requests.get(balance_url, headers=supabase_headers)

        monthly_url = f"{SUPABASE_URL}/rest/v1/finance_current_month_spending?select=*"
        monthly = requests.get(monthly_url, headers=supabase_headers)

        return json.dumps({
            "balance_overview": balance.json() if balance.status_code == 200 else [],
            "current_month_spending": monthly.json() if monthly.status_code == 200 else []
        }, indent=2)

    except Exception as e:
        return f"Finance fetch failed: {str(e)}"


def get_google_credentials():
    token_data = json.loads(GOOGLE_TOKEN_JSON)
    return Credentials.from_authorized_user_info(token_data)


def get_gmail_summary():
    try:
        creds = get_google_credentials()
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


def get_asana_tasks():
    try:
        headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}

        user_response = requests.get(
            "https://app.asana.com/api/1.0/users/me",
            headers=headers
        )

        user = user_response.json()["data"]
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


async def send_daily_briefing(app):
    print("Running daily briefing...")

    prompt = f"""
Create my daily AI briefing.

Current date/time:
{get_current_datetime()}

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
        messages=[{"role": "user", "content": prompt}]
    )

    briefing = response.content[0].text

    await app.bot.send_message(
        chat_id=ALLOWED_USER_ID,
        text=briefing
    )

    print("Daily briefing sent.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ALLOWED_USER_ID:
        print(f"Blocked unauthorized user: {update.effective_user.id}")
        return

    user_message = update.message.text
    text = user_message.lower()

    await update.message.chat.send_action("typing")

    finance_tx = classify_finance_message(user_message)

    if finance_tx:
        save_finance_transaction(finance_tx)

    runtime_context = f"""
Current date/time:
{get_current_datetime()}
Timezone: Europe/Berlin
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
        system=SYSTEM_PROMPT + runtime_context + finance_context + gmail_context + calendar_context + asana_context,
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