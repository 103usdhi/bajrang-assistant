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

You are connected to the user's personal memory, expenses database, and selected external APIs.

Primary behavior:
- Prioritize user's personal data first.
- If Asana data is provided in context, use it directly.
- Do not say you lack Asana access if Asana context is provided.
- You are not limited to finance/tasks; answer general questions too.
- Be direct, concise, and useful.
- Never invent data.
- End with one short motivational line.
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


def asana_headers():
    return {
        "Authorization": f"Bearer {ASANA_TOKEN}",
        "Accept": "application/json"
    }


def get_asana_user():
    url = "https://app.asana.com/api/1.0/users/me"
    response = requests.get(url, headers=asana_headers())

    print("ASANA USER STATUS:", response.status_code)

    if response.status_code != 200:
        print("ASANA USER ERROR:", response.text)
        return None

    return response.json().get("data")


def get_asana_tasks():
    if not ASANA_TOKEN:
        return "ASANA_TOKEN is missing."

    user = get_asana_user()

    if not user:
        return "Could not fetch Asana user."

    workspaces = user.get("workspaces", [])

    if not workspaces:
        return "No Asana workspaces found."

    workspace_gid = workspaces[0]["gid"]
    user_gid = user["gid"]

    url = "https://app.asana.com/api/1.0/tasks"

    params = {
        "assignee": user_gid,
        "workspace": workspace_gid,
        "completed_since": "now",
        "limit": 20,
        "opt_fields": "gid,name,completed,due_on,due_at,created_at,modified_at,projects.name,workspace.name,permalink_url"
    }

    response = requests.get(url, headers=asana_headers(), params=params)

    print("ASANA TASKS STATUS:", response.status_code)

    if response.status_code != 200:
        print("ASANA TASKS ERROR:", response.text)
        return f"Asana task fetch failed: {response.status_code} {response.text}"

    tasks = response.json().get("data", [])

    if not tasks:
        return "No open Asana tasks found for your user."

    clean_tasks = []

    for task in tasks:
        project_names = []

        for project in task.get("projects", []):
            project_names.append(project.get("name"))

        clean_tasks.append({
            "name": task.get("name"),
            "due_on": task.get("due_on"),
            "completed": task.get("completed"),
            "projects": project_names,
            "url": task.get("permalink_url")
        })

    return json.dumps(clean_tasks, indent=2)


def is_asana_request(message):
    text = message.lower()

    keywords = [
        "asana",
        "task",
        "tasks",
        "pending",
        "overdue",
        "project",
        "projects",
        "summarize my asana",
        "what did you read from asana"
    ]

    return any(keyword in text for keyword in keywords)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

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

    asana_context = ""

    if is_asana_request(user_message):
        asana_data = get_asana_tasks()
        asana_context = f"""

Asana live data:
{asana_data}
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
        max_tokens=1200,
        system=SYSTEM_PROMPT + runtime_context + asana_context,
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