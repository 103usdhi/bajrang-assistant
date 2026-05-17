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

import anthropic

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ASANA_TOKEN = os.getenv("ASANA_TOKEN")

GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
GOOGLE_TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

ALLOWED_USER_ID = 8106199737

logging.basicConfig(level=logging.INFO)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

SYSTEM_PROMPT = """
You are Bajrang, a highly intelligent personal AI assistant.

You have access to:
- user memory
- expenses
- Asana tasks
- Gmail
- Google Calendar

Rules:
- prioritize user's real personal data first
- answer naturally
- never pretend data exists if missing
- summarize intelligently
- keep responses concise and useful
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

    creds = Credentials.from_authorized_user_info(
        token_data
    )

    return creds


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

        email_data = []

        for msg in messages:
            message = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject"]
            ).execute()

            headers = message.get("payload", {}).get("headers", [])

            sender = ""
            subject = ""

            for header in headers:
                if header["name"].lower() == "from":
                    sender = header["value"]

                if header["name"].lower() == "subject":
                    subject = header["value"]

            email_data.append({
                "from": sender,
                "subject": subject
            })

        return json.dumps(email_data, indent=2)

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
            maxResults=10,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])

        clean_events = []

        for event in events:
            clean_events.append({
                "title": event.get("summary"),
                "start": event.get("start"),
                "location": event.get("location")
            })

        return json.dumps(clean_events, indent=2)

    except Exception as e:
        return f"Calendar fetch failed: {str(e)}"


def get_asana_tasks():
    try:
        headers = {
            "Authorization": f"Bearer {ASANA_TOKEN}"
        }

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
            "limit": 10,
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
            projects = []

            for p in task.get("projects", []):
                projects.append(p["name"])

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

    keywords = ["spent", "paid", "bought"]

    if not any(k in text for k in keywords):
        return None

    amount_match = re.search(r'(\d+(\.\d+)?)', text)

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


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ALLOWED_USER_ID:
        print(f"Blocked unauthorized user: {update.effective_user.id}")
        return

    user_message = update.message.text

    await update.message.chat.send_action("typing")

    runtime_context = f"""
Current datetime:
{get_current_datetime()}
"""

    gmail_context = ""
    calendar_context = ""
    asana_context = ""

    text = user_message.lower()

    if "email" in text or "gmail" in text:
        gmail_context = f"""

Gmail live data:
{get_gmail_summary()}
"""

    if "calendar" in text or "meeting" in text or "schedule" in text:
        calendar_context = f"""

Calendar live data:
{get_calendar_summary()}
"""

    if "asana" in text or "task" in text or "project" in text:
        asana_context = f"""

Asana live data:
{get_asana_tasks()}
"""

    expense = detect_expense(user_message)

    if expense:
        save_expense(
            expense["amount"],
            expense["description"]
        )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
        system=SYSTEM_PROMPT
        + runtime_context
        + gmail_context
        + calendar_context
        + asana_context,
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

    print("Bajrang is running!")

    app.run_polling()


if __name__ == "__main__":
    main()