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
You are Bajrang, a highly intelligent personal AI assistant.

You can use:
- personal memory
- expenses
- Gmail
- Google Calendar
- Asana

Rules:
- prioritize user's real personal data
- be direct and useful
- never invent data
- answer naturally
- keep replies concise
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
                name = h["name"].lower()
                if name == "from":
                    email["from"] = h["value"]
                elif name == "subject":
                    email["subject"] = h["value"]
                elif name == "date":
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

        events = events_result.get("items", [])
        clean_events = []

        for event in events:
            clean_events.append({
                "title": event.get("summary"),
                "start": event.get("start"),
                "end": event.get("end"),
                "location": event.get("location", "")
            })

        return json.dumps(clean_events, indent=2)

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

        tasks = task_response.json()["data"]
        clean_tasks = []

        for task in tasks:
            projects = [p["name"] for p in task.get("projects", [])]

            clean_tasks.append({
                "task": task.get("name"),
                "due": task.get("due_on"),
                "completed": task.get("completed"),
                "projects": projects
            })

        return json.dumps(clean_tasks, indent=2)

    except Exception as e:
        return f"Asana fetch failed: {str(e)}"


def save_to_supabase(user_message, assistant_response):
    url = f"{SUPABASE_URL}/rest/v1/events_log"

    data = {
        "user_message": user_message,
        "assistant_response": assistant_response,
        "source": "telegram"
    }

    requests.post(url, headers=supabase_headers, json=data)


def detect_expense(user_message):
    text = user_message.lower()

    if not any(k in text for k in ["spent", "paid", "bought"]):
        return None

    amount_match = re.search(r"(\d+(\.\d+)?)", text)

    if not amount_match:
        return None

    return {
        "amount": float(amount_match.group(1)),
        "description": user_message
    }


def save_expense(amount, description):
    url = f"{SUPABASE_URL}/rest/v1/expenses"

    data = {
        "amount": amount,
        "description": description,
        "currency": "EUR",
        "source": "telegram"
    }

    requests.post(url, headers=supabase_headers, json=data)


async def send_daily_briefing(app):
    print("Running daily briefing...")

    gmail_data = get_gmail_summary()
    calendar_data = get_calendar_summary()
    asana_data = get_asana_tasks()

    briefing_prompt = f"""
Create my daily AI briefing.

Current date/time:
{get_current_datetime()}

Gmail:
{gmail_data}

Calendar:
{calendar_data}

Asana:
{asana_data}

Output:
- greeting
- today's meetings
- important emails
- Asana priorities
- top 3 actions
- keep it concise
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        messages=[
            {
                "role": "user",
                "content": briefing_prompt
            }
        ]
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

    gmail_context = ""
    calendar_context = ""
    asana_context = ""

    if "email" in text or "gmail" in text:
        gmail_context = f"\n\nGmail live data:\n{get_gmail_summary()}"

    if "calendar" in text or "meeting" in text or "schedule" in text:
        calendar_context = f"\n\nCalendar live data:\n{get_calendar_summary()}"

    if "asana" in text or "task" in text or "project" in text:
        asana_context = f"\n\nAsana live data:\n{get_asana_tasks()}"

    if "daily briefing" in text or "morning briefing" in text:
        await send_daily_briefing(context.application)
        return

    expense = detect_expense(user_message)

    if expense:
        save_expense(expense["amount"], expense["description"])

    runtime_context = f"""
Current date/time:
{get_current_datetime()}
Timezone: Europe/Berlin
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=SYSTEM_PROMPT + runtime_context + gmail_context + calendar_context + asana_context,
        messages=[
            {
                "role": "user",
                "content": user_message
            }
        ]
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