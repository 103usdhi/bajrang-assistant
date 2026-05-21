import os
import re
import json
import logging
import requests
import base64
import random
from datetime import datetime, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup
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
TIMEZONE_NAME = "Europe/Berlin"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
RECENT_EXCHANGE_LIMIT = 6
PERSONAL_MEMORY_LIMIT = 15
SEMANTIC_MEMORY_MATCH_COUNT = 2

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
- Never claim that calendar events, Asana tasks, emails, or database writes were completed unless an actual API/database result confirms success.
- If the user asks for an external action that is unsupported or unconfirmed, say that it was not completed and explain what is available.
- Be direct, intelligent and helpful.
"""

FINANCE_CATEGORY_RULES = {
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

CALENDAR_EVENT_PREFIXES = [
    "create calendar event",
    "add calendar event",
    "schedule event",
    "create meeting",
    "add meeting",
    "schedule meeting",
    "book meeting",
    "create event",
    "add event",
    "schedule"
]

ASANA_TASK_PREFIXES = [
    "create task",
    "add task",
    "create asana task",
    "add asana task"
]

WAITING_FOR_CALENDAR_EVENT = "waiting_for_calendar_event"
WAITING_FOR_EMAIL_TO = "waiting_for_email_to"
WAITING_FOR_EMAIL_SUBJECT = "waiting_for_email_subject"
WAITING_FOR_EMAIL_BODY = "waiting_for_email_body"
EMAIL_DRAFT_STATE = "email_draft"
WAITING_FOR_GERMAN_WORD = "waiting_for_german_word"
WAITING_FOR_GERMAN_MEANING = "waiting_for_german_meaning"
WAITING_FOR_GERMAN_EXAMPLE = "waiting_for_german_example"
GERMAN_WORD_STATE = "german_word"
WAITING_FOR_GRAMMAR_TOPIC = "waiting_for_grammar_topic"
WAITING_FOR_GRAMMAR_NOTE = "waiting_for_grammar_note"
GERMAN_GRAMMAR_STATE = "german_grammar"
WAITING_FOR_GERMAN_CORRECTION = "waiting_for_german_correction"
WAITING_FOR_GERMAN_QUIZ_ANSWER = "waiting_for_german_quiz_answer"
GERMAN_QUIZ_STATE = "german_quiz"

MENU_COMMANDS = {"menu", "start", "help"}
BACK_COMMANDS = {"back", "main menu"}
GERMAN_MENU_COMMANDS = {"german a1", "german", "german learning"}
ADD_GERMAN_WORD_COMMANDS = {"add word", "add german word"}
ADD_GRAMMAR_RULE_COMMANDS = {"grammar", "add grammar rule"}
CORRECT_GERMAN_COMMANDS = {"correct german", "correct my german"}
FINANCE_CONTEXT_KEYWORDS = [
    "finance",
    "money",
    "balance",
    "spend",
    "spent",
    "expense",
    "salary",
    "income",
    "budget"
]

ICON_GREEN = "\U0001f7e2"
ICON_YELLOW = "\U0001f7e1"
ICON_RED = "\U0001f534"
ICON_WHITE = "\u26aa"
ICON_COMPASS = "\U0001f9ed"
ICON_DATABASE = "\U0001f5c4\ufe0f"
ICON_BRAIN = "\U0001f9e0"
ICON_PLUG = "\U0001f50c"
ICON_CHART = "\U0001f4ca"
ICON_WARNING = "\u26a0\ufe0f"
ICON_CHECK = "\u2705"
ICON_CLIPBOARD = "\U0001f4cb"
ICON_MAGNIFIER = "\U0001f50e"

supabase_headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}


def get_timezone():
    return ZoneInfo(TIMEZONE_NAME)


def get_asana_headers(content_type=False):
    headers = {"Authorization": f"Bearer {ASANA_TOKEN}"}

    if content_type:
        headers["Content-Type"] = "application/json"

    return headers


def get_current_datetime():
    now = datetime.now(get_timezone())
    return now.strftime("%A, %d %B %Y, %H:%M")


def log_system_error(module, error):
    if isinstance(error, BaseException):
        exc_info = (type(error), error, error.__traceback__)
        error_message = str(error)
    else:
        exc_info = None
        error_message = str(error)

    logging.error("%s failed: %s", module, error_message, exc_info=exc_info)

    try:
        url = f"{SUPABASE_URL}/rest/v1/system_logs"
        data = {
            "timestamp": datetime.now(get_timezone()).isoformat(),
            "module": module,
            "error_message": error_message
        }
        requests.post(url, headers=supabase_headers, json=data, timeout=10)
    except Exception as logging_error:
        logging.error("system_logs write failed: %s", logging_error)


def save_to_supabase(user_message, assistant_response):
    try:
        url = f"{SUPABASE_URL}/rest/v1/events_log"
        data = {
            "user_message": user_message,
            "assistant_response": assistant_response,
            "source": "telegram"
        }
        requests.post(url, headers=supabase_headers, json=data)
    except Exception as e:
        log_system_error("save_to_supabase", e)


def get_recent_memories():
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/events_log"
            f"?select=user_message,assistant_response"
            f"&order=created_at.desc"
            f"&limit={RECENT_EXCHANGE_LIMIT}"
        )
        result = requests.get(url, headers=supabase_headers)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_system_error("get_recent_memories", e)
        return []


def save_personal_memory(memory_text):
    try:
        url = f"{SUPABASE_URL}/rest/v1/personal_memory"
        data = {
            "memory_text": memory_text,
            "memory_type": "general",
            "importance": "medium",
            "source": "telegram",
            "is_active": True
        }
        result = requests.post(url, headers=supabase_headers, json=data)
        if result.status_code in [200, 201, 204]:
            return True

        log_system_error(
            "save_personal_memory",
            RuntimeError(f"Supabase returned {result.status_code}: {result.text}")
        )
        return False
    except Exception as e:
        log_system_error("save_personal_memory", e)
        return False


def get_personal_memories():
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/personal_memory"
            f"?select=memory_text"
            f"&is_active=eq.true"
            f"&order=created_at.desc"
            f"&limit={PERSONAL_MEMORY_LIMIT}"
        )
        result = requests.get(url, headers=supabase_headers)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_system_error("get_personal_memories", e)
        return []


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
        log_system_error("save_semantic_memory", e)


def search_semantic_memory(query):
    if not openai_client:
        return []

    try:
        embedding = generate_embedding(query)
        url = f"{SUPABASE_URL}/rest/v1/rpc/match_semantic_memory"
        data = {
            "query_embedding": embedding,
            "match_threshold": 0.70,
            "match_count": SEMANTIC_MEMORY_MATCH_COUNT
        }
        result = requests.post(url, headers=supabase_headers, json=data)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_system_error("search_semantic_memory", e)
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

    for keyword, values in FINANCE_CATEGORY_RULES.items():
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
    try:
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
        if result.status_code in [200, 201, 204]:
            return True

        log_system_error(
            "save_finance_transaction",
            RuntimeError(f"Supabase returned {result.status_code}: {result.text}")
        )
        return False
    except Exception as e:
        log_system_error("save_finance_transaction", e)
        return False


def save_german_word(word, meaning, example_sentence):
    try:
        url = f"{SUPABASE_URL}/rest/v1/german_words"
        data = {
            "word": word,
            "meaning": meaning,
            "example_sentence": example_sentence,
            "created_at": datetime.now(get_timezone()).isoformat()
        }
        result = requests.post(url, headers=supabase_headers, json=data)

        if result.status_code in [200, 201, 204]:
            return True

        log_system_error(
            "save_german_word",
            RuntimeError(f"Supabase returned {result.status_code}: {result.text}")
        )
        return False
    except Exception as e:
        log_system_error("save_german_word", e)
        return False


def save_grammar_rule(topic, note):
    try:
        url = f"{SUPABASE_URL}/rest/v1/german_grammar"
        data = {
            "topic": topic,
            "note": note,
            "created_at": datetime.now(get_timezone()).isoformat()
        }
        result = requests.post(url, headers=supabase_headers, json=data)

        if result.status_code in [200, 201, 204]:
            return True

        log_system_error(
            "save_grammar_rule",
            RuntimeError(f"Supabase returned {result.status_code}: {result.text}")
        )
        return False
    except Exception as e:
        log_system_error("save_grammar_rule", e)
        return False


def get_random_german_words(limit=3):
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/german_words"
            f"?select=word,meaning,example_sentence"
            f"&order=created_at.desc"
            f"&limit=50"
        )
        result = requests.get(url, headers=supabase_headers)

        if result.status_code != 200:
            log_system_error(
                "get_random_german_words",
                RuntimeError(f"Supabase returned {result.status_code}: {result.text}")
            )
            return []

        rows = result.json()
        if len(rows) <= limit:
            return rows

        return random.sample(rows, limit)
    except Exception as e:
        log_system_error("get_random_german_words", e)
        return []


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
        log_system_error("get_finance_summary", e)
        return f"Finance fetch failed: {str(e)}"


def get_finance_transactions(select_columns):
    try:
        url = f"{SUPABASE_URL}/rest/v1/finance_transactions?select={select_columns}"
        result = requests.get(url, headers=supabase_headers)

        if result.status_code != 200:
            return None

        return result.json()
    except Exception as e:
        log_system_error("get_finance_transactions", e)
        return None


def iter_expense_rows(rows):
    for row in rows:
        if row.get("transaction_type") != "expense":
            continue

        category = row.get("category") or "general"
        amount = float(row.get("amount") or 0)

        yield row, category, amount


def get_monthly_spending_breakdown():
    try:
        rows = get_finance_transactions("amount,category,transaction_type")

        if rows is None:
            return "Finance analytics failed."

        category_totals = {}
        total_spending = 0

        for _, category, amount in iter_expense_rows(rows):
            total_spending += amount
            category_totals[category] = category_totals.get(category, 0) + amount

        sorted_categories = sorted(
            category_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return json.dumps({
            "total_spending": round(total_spending, 2),
            "top_categories": sorted_categories[:10]
        }, indent=2)

    except Exception as e:
        log_system_error("get_monthly_spending_breakdown", e)
        return f"Finance analytics failed: {str(e)}"


def get_overspending_insights():
    try:
        rows = get_finance_transactions("amount,category,transaction_type,is_essential")

        if rows is None:
            return "Overspending analysis failed."

        essential = 0
        non_essential = 0
        categories = {}

        for row, category, amount in iter_expense_rows(rows):
            if row.get("is_essential"):
                essential += amount
            else:
                non_essential += amount

            categories[category] = categories.get(category, 0) + amount

        biggest = sorted(
            categories.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return json.dumps({
            "essential_spending": round(essential, 2),
            "non_essential_spending": round(non_essential, 2),
            "top_expense_categories": biggest,
            "warning": "High non-essential spending detected." if non_essential > essential else "Spending pattern looks balanced."
        }, indent=2)

    except Exception as e:
        log_system_error("get_overspending_insights", e)
        return f"Overspending analysis failed: {str(e)}"


def get_google_token_scopes(token_data):
    scopes = token_data.get("scopes") or token_data.get("scope") or []

    if isinstance(scopes, str):
        scopes = re.split(r"[\s,]+", scopes.strip())

    return {scope for scope in scopes if scope}


def get_google_credentials(required_scopes=None):
    required_scopes = required_scopes or []

    if not GOOGLE_TOKEN_JSON:
        if required_scopes:
            log_system_error(
                "get_google_credentials",
                RuntimeError("Google token missing for required scopes: " + ", ".join(required_scopes))
            )
        return None

    try:
        token_data = json.loads(GOOGLE_TOKEN_JSON)

        if required_scopes:
            available_scopes = get_google_token_scopes(token_data)
            missing_scopes = [
                scope
                for scope in required_scopes
                if scope not in available_scopes
            ]

            if missing_scopes:
                log_system_error(
                    "get_google_credentials",
                    RuntimeError("Missing Google scopes: " + ", ".join(missing_scopes))
                )
                return None

        return Credentials.from_authorized_user_info(token_data)
    except Exception as e:
        log_system_error("get_google_credentials", e)
        return None


def get_gmail_summary():
    try:
        creds = get_google_credentials()

        if not creds:
            return "Google token missing."

        service = build("gmail", "v1", credentials=creds)

        results = service.users().messages().list(
            userId="me",
            maxResults=3,
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
        log_system_error("get_gmail_summary", e)
        return f"Gmail fetch failed: {str(e)}"


def create_gmail_draft(to_email, subject, body):
    try:
        creds = get_google_credentials(required_scopes=[GMAIL_COMPOSE_SCOPE])

        if not creds:
            log_system_error(
                "create_gmail_draft",
                RuntimeError(f"Missing Google token or required scope {GMAIL_COMPOSE_SCOPE}.")
            )
            return (
                "Gmail draft creation failed: missing Google token or required "
                f"scope {GMAIL_COMPOSE_SCOPE}."
            )

        message = EmailMessage()
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft_body = {
            "message": {
                "raw": encoded_message
            }
        }

        service = build("gmail", "v1", credentials=creds)
        draft = service.users().drafts().create(
            userId="me",
            body=draft_body
        ).execute()

        draft_id = draft.get("id")

        if draft_id:
            return f"Gmail draft created: {subject} (draft id: {draft_id})"

        log_system_error(
            "create_gmail_draft",
            RuntimeError("Gmail drafts.create returned no draft id.")
        )
        return "Gmail draft creation failed: Gmail did not return a draft id."
    except Exception as e:
        log_system_error("create_gmail_draft", e)
        return f"Gmail draft creation failed: {str(e)}"


def get_calendar_summary():
    try:
        creds = get_google_credentials()

        if not creds:
            return "Google token missing."

        service = build("calendar", "v3", credentials=creds)

        now = datetime.now(get_timezone())
        end = now + timedelta(days=30)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=end.isoformat(),
            maxResults=10,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        return json.dumps(events_result.get("items", []), indent=2)
    except Exception as e:
        log_system_error("get_calendar_summary", e)
        return f"Calendar fetch failed: {str(e)}"


def parse_calendar_event_request(message):
    text = message.strip()

    clean = text

    for prefix in CALENDAR_EVENT_PREFIXES:
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):].strip()
            break

    timezone = get_timezone()
    now = datetime.now(timezone)

    event_date = now.date()

    if "tomorrow" in clean.lower():
        event_date = (now + timedelta(days=1)).date()
        clean = re.sub(r"\btomorrow\b", "", clean, flags=re.IGNORECASE)

    elif "today" in clean.lower():
        event_date = now.date()
        clean = re.sub(r"\btoday\b", "", clean, flags=re.IGNORECASE)

    date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", clean)

    if date_match:
        event_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").date()
        clean = clean.replace(date_match.group(1), "")

    time_match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", clean)

    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        clean = clean.replace(time_match.group(0), "")
    else:
        hour = 9
        minute = 0

    title = clean.strip()

    if not title:
        title = "Untitled event"

    start_dt = datetime(
        event_date.year,
        event_date.month,
        event_date.day,
        hour,
        minute,
        tzinfo=timezone
    )

    end_dt = start_dt + timedelta(hours=1)

    return title, start_dt, end_dt


def create_calendar_event_from_text(message):
    try:
        creds = get_google_credentials()

        if not creds:
            return "Google token missing."

        title, start_dt, end_dt = parse_calendar_event_request(message)

        service = build("calendar", "v3", credentials=creds)

        event_body = {
            "summary": title,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": TIMEZONE_NAME
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": TIMEZONE_NAME
            }
        }

        service.events().insert(
            calendarId="primary",
            body=event_body
        ).execute()

        return f"Calendar event created: {title} at {start_dt.strftime('%Y-%m-%d %H:%M')}"

    except Exception as e:
        log_system_error("create_calendar_event_from_text", e)
        return f"Calendar event creation failed: {str(e)}"


def get_asana_user():
    try:
        response = requests.get(
            "https://app.asana.com/api/1.0/users/me",
            headers=get_asana_headers()
        )

        if response.status_code != 200:
            return None

        return response.json()["data"]
    except Exception as e:
        log_system_error("get_asana_user", e)
        return None


def get_asana_tasks():
    try:
        if not ASANA_TOKEN:
            return "Asana token missing."

        user = get_asana_user()

        if not user:
            return "Could not fetch Asana user."

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
            headers=get_asana_headers(),
            params=params
        )

        return json.dumps(task_response.json().get("data", []), indent=2)
    except Exception as e:
        log_system_error("get_asana_tasks", e)
        return f"Asana fetch failed: {str(e)}"


def create_asana_task(task_name):
    try:
        if not ASANA_TOKEN:
            return "Asana token missing."

        user = get_asana_user()

        if not user:
            return "Could not fetch Asana user."

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
            headers=get_asana_headers(content_type=True),
            json=data
        )

        if response.status_code in [200, 201]:
            return f"Asana task created: {task_name}"

        return f"Asana task creation failed: {response.status_code} {response.text}"
    except Exception as e:
        log_system_error("create_asana_task", e)
        return f"Asana error: {str(e)}"


def get_health_indicator(value):
    if value == "connected":
        return f"{ICON_GREEN} Online"

    if value == "disabled":
        return f"{ICON_WHITE} Disabled"

    if value == "failed":
        return f"{ICON_RED} Failed"

    return f"{ICON_YELLOW} Unknown"


def format_record_count(value):
    if isinstance(value, int):
        return f"{value:,} records"

    if value == "failed":
        return f"{ICON_RED} Unavailable"

    return f"{ICON_YELLOW} Unknown"


def get_overall_health(report):
    service_keys = [
        "supabase",
        "gmail",
        "calendar",
        "asana",
        "openai_embeddings",
        "claude"
    ]
    services = [report.get(key) for key in service_keys]

    if any(status == "failed" for status in services):
        return f"{ICON_RED} Attention needed"

    if any(status == "disabled" for status in services):
        return f"{ICON_YELLOW} Partially operational"

    return f"{ICON_GREEN} All systems operational"


def format_system_status_dashboard(report):
    data_labels = {
        "events_log_count": "Conversation logs",
        "personal_memory_count": "Personal memories",
        "semantic_memory_count": "Semantic memories",
        "finance_transactions_count": "Finance transactions"
    }

    lines = [
        f"{ICON_COMPASS} Bajrang System Dashboard",
        "",
        f"Overall Health: {get_overall_health(report)}",
        f"Last Check: {report['current_time']}",
        "",
        f"{ICON_DATABASE} Core Infrastructure",
        f"Supabase: {get_health_indicator(report.get('supabase'))}",
        "",
        f"{ICON_BRAIN} Intelligence",
        f"Claude: {get_health_indicator(report.get('claude'))}",
        f"OpenAI Embeddings: {get_health_indicator(report.get('openai_embeddings'))}",
        "",
        f"{ICON_PLUG} Connected Apps",
        f"Gmail: {get_health_indicator(report.get('gmail'))}",
        f"Calendar: {get_health_indicator(report.get('calendar'))}",
        f"Asana: {get_health_indicator(report.get('asana'))}",
        "",
        f"{ICON_CHART} Data Stores"
    ]

    for key, label in data_labels.items():
        lines.append(f"{label}: {format_record_count(report.get(key))}")

    failed_services = [
        label
        for key, label in [
            ("supabase", "Supabase"),
            ("gmail", "Gmail"),
            ("calendar", "Calendar"),
            ("asana", "Asana"),
            ("openai_embeddings", "OpenAI Embeddings"),
            ("claude", "Claude")
        ]
        if report.get(key) == "failed"
    ]

    if failed_services:
        lines.extend([
            "",
            f"{ICON_WARNING} Attention",
            "Check: " + ", ".join(failed_services)
        ])
    else:
        lines.extend([
            "",
            f"{ICON_CHECK} Summary",
            "No active failures detected."
        ])

    return "\n".join(lines)


def truncate_text(value, max_length=260):
    value = str(value or "").replace("\n", " ").strip()

    if len(value) <= max_length:
        return value

    return value[: max_length - 3].rstrip() + "..."


def format_log_time(value):
    if not value:
        return "Unknown time"

    try:
        clean_value = value.replace("Z", "+00:00")
        logged_at = datetime.fromisoformat(clean_value)
        return logged_at.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(value)


def parse_log_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def get_log_sort_timestamp(row):
    logged_at = parse_log_datetime(row.get("timestamp"))

    if not logged_at:
        return 0

    return logged_at.timestamp()


def get_error_severity(row):
    module = (row.get("module") or "").lower()
    message = (row.get("error_message") or "").lower()
    text = f"{module} {message}"

    critical_keywords = [
        "telegram_error_handler",
        "permission denied",
        "unauthorized",
        "invalid token",
        "connection refused",
        "timeout",
        "database",
        "supabase"
    ]
    warning_keywords = [
        "missing",
        "disabled",
        "failed",
        "could not fetch",
        "not found",
        "rate limit"
    ]

    if any(keyword in text for keyword in critical_keywords):
        return "critical"

    if any(keyword in text for keyword in warning_keywords):
        return "warning"

    return "notice"


def get_severity_label(severity):
    labels = {
        "critical": f"{ICON_RED} Critical",
        "warning": f"{ICON_WARNING} Warning",
        "notice": f"{ICON_YELLOW} Notice"
    }
    return labels.get(severity, f"{ICON_YELLOW} Notice")


def group_errors_by_severity(rows):
    grouped = {
        "critical": [],
        "warning": [],
        "notice": []
    }

    for row in rows:
        grouped[get_error_severity(row)].append(row)

    return grouped


def get_module_counts(rows):
    counts = {}

    for row in rows:
        module = row.get("module") or "unknown"
        counts[module] = counts.get(module, 0) + 1

    return sorted(counts.items(), key=lambda item: item[1], reverse=True)


def get_incident_summary(rows, grouped):
    if not rows:
        return "No incidents found in the latest system_logs entries."

    critical_count = len(grouped["critical"])
    warning_count = len(grouped["warning"])

    if critical_count:
        return f"{critical_count} critical incident(s) need attention."

    if warning_count:
        return f"{warning_count} warning(s) found; the bot is mostly operational."

    return "Only low-priority notices found."


def format_module_summary(rows):
    module_counts = get_module_counts(rows)

    if not module_counts:
        return "Modules: none"

    summary = ", ".join(
        f"{module} ({count})"
        for module, count in module_counts[:4]
    )

    if len(module_counts) > 4:
        summary += f", +{len(module_counts) - 4} more"

    return f"Modules: {summary}"


def format_incident_entry(row):
    module = row.get("module") or "unknown"
    timestamp = format_log_time(row.get("timestamp"))
    error_message = truncate_text(row.get("error_message"), max_length=180)

    return [
        f"{ICON_MAGNIFIER} {module}",
        f"Time: {timestamp}",
        f"Message: {error_message}"
    ]


def format_system_errors(rows):
    if not rows:
        return (
            f"{ICON_CLIPBOARD} Incident Dashboard\n\n"
            f"{ICON_CHECK} Summary\n"
            "No errors logged yet."
        )

    rows = sorted(
        rows,
        key=get_log_sort_timestamp,
        reverse=True
    )
    grouped = group_errors_by_severity(rows)
    latest_time = format_log_time(rows[0].get("timestamp"))
    oldest_time = format_log_time(rows[-1].get("timestamp"))

    lines = [
        f"{ICON_CLIPBOARD} Incident Dashboard",
        "",
        f"Health Summary: {get_incident_summary(rows, grouped)}",
        f"Latest Incident: {latest_time}",
        f"Window Start: {oldest_time}",
        f"Entries Reviewed: {len(rows)}",
        format_module_summary(rows),
        ""
    ]

    for severity in ["critical", "warning", "notice"]:
        severity_rows = grouped[severity]

        if not severity_rows:
            continue

        lines.extend([
            f"{get_severity_label(severity)} ({len(severity_rows)})",
            ""
        ])

        for index, row in enumerate(severity_rows, start=1):
            entry_lines = format_incident_entry(row)
            entry_lines[0] = f"{index}. {entry_lines[0]}"
            lines.extend(entry_lines)
            lines.append("")

    return "\n".join(lines).strip()


def get_recent_system_errors(limit=10):
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/system_logs"
            f"?select=timestamp,module,error_message"
            f"&order=timestamp.desc"
            f"&limit={limit}"
        )
        result = requests.get(url, headers=supabase_headers)

        if result.status_code != 200:
            return (
                f"{ICON_CLIPBOARD} Recent System Errors\n\n"
                f"Could not fetch logs. Supabase returned {result.status_code}."
            )

        return format_system_errors(result.json())
    except Exception as e:
        log_system_error("get_recent_system_errors", e)
        return f"{ICON_CLIPBOARD} Recent System Errors\n\nCould not fetch logs: {str(e)}"


def get_system_status():
    report = {}
    report["current_time"] = get_current_datetime()

    checks = {
        "events_log_count": "events_log",
        "personal_memory_count": "personal_memory",
        "semantic_memory_count": "semantic_memory",
        "finance_transactions_count": "finance_transactions"
    }

    try:
        test_url = f"{SUPABASE_URL}/rest/v1/events_log?select=id&limit=1"
        result = requests.get(test_url, headers=supabase_headers)
        report["supabase"] = "connected" if result.status_code == 200 else "failed"
    except Exception as e:
        log_system_error("get_system_status.supabase", e)
        report["supabase"] = "failed"

    for key, table in checks.items():
        try:
            url = f"{SUPABASE_URL}/rest/v1/{table}?select=id"
            result = requests.get(url, headers=supabase_headers)
            report[key] = len(result.json()) if result.status_code == 200 else "failed"
        except Exception as e:
            log_system_error(f"get_system_status.{table}", e)
            report[key] = "failed"

    try:
        report["gmail"] = "connected" if "failed" not in get_gmail_summary().lower() else "failed"
    except Exception as e:
        log_system_error("get_system_status.gmail", e)
        report["gmail"] = "failed"

    try:
        report["calendar"] = "connected" if "failed" not in get_calendar_summary().lower() else "failed"
    except Exception as e:
        log_system_error("get_system_status.calendar", e)
        report["calendar"] = "failed"

    try:
        report["asana"] = "connected" if "failed" not in get_asana_tasks().lower() else "failed"
    except Exception as e:
        log_system_error("get_system_status.asana", e)
        report["asana"] = "failed"

    try:
        if openai_client:
            generate_embedding("test")
            report["openai_embeddings"] = "connected"
        else:
            report["openai_embeddings"] = "disabled"
    except Exception as e:
        log_system_error("get_system_status.openai_embeddings", e)
        report["openai_embeddings"] = "failed"

    try:
        client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=10,
            messages=[{"role": "user", "content": "hello"}]
        )
        report["claude"] = "connected"
    except Exception as e:
        log_system_error("get_system_status.claude", e)
        report["claude"] = "failed"

    return format_system_status_dashboard(report)


async def send_daily_briefing(app):
    try:
        prompt = f"""
Create my daily AI briefing.

Current date/time:
{get_current_datetime()}

Personal memories:
{compact_json(get_personal_memories())}

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
            max_tokens=650,
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
    except Exception as e:
        log_system_error("send_daily_briefing", e)


def get_main_menu():
    keyboard = [
        ["System Status", "Show Errors"],
        ["Daily Briefing"],
        ["Finance Report", "Overspending"],
        ["Gmail Summary", "Calendar Summary"],
        ["Asana Tasks", "Create Calendar Event"],
        ["Draft Email"],
        ["German A1"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def get_german_a1_menu():
    keyboard = [
        ["Add Word", "Grammar"],
        ["Quiz Me", "Correct German"],
        ["A1 Practice"],
        ["Back"]
    ]

    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


def format_with_claude(title, raw_data):
    try:
        raw_data = truncate_text(raw_data, max_length=3500)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=450,
            system="Format for Telegram. Be concise. Use short headings/bullets. Hide raw JSON.",
            messages=[
                {
                    "role": "user",
                    "content": f"{title}\n{raw_data}"
                }
            ]
        )

        return response.content[0].text

    except Exception as e:
        log_system_error("format_with_claude", e)
        return f"{title} failed to format: {str(e)}"


FORMATTED_COMMANDS = [
    (("where am i overspending", "overspending"), "Overspending Analysis", get_overspending_insights),
    (("gmail summary",), "Gmail Summary", get_gmail_summary),
    (("calendar summary",), "Calendar Summary", get_calendar_summary),
    (("asana tasks",), "Asana Tasks", get_asana_tasks),
    (("finance report",), "Finance Report", get_monthly_spending_breakdown)
]

EXPLICIT_DATA_ACTION_WORDS = (
    "show",
    "summarize",
    "summary",
    "check",
    "read",
    "list",
    "what",
    "which",
    "when",
    "where",
    "tell"
)

LIVE_CONTEXT_PROVIDERS = [
    (lambda text: any(k in text for k in FINANCE_CONTEXT_KEYWORDS), "Finance", get_finance_summary),
    (lambda text: is_explicit_gmail_context_request(text), "Gmail", get_gmail_summary),
    (lambda text: is_explicit_calendar_context_request(text), "Calendar", get_calendar_summary),
    (lambda text: is_explicit_asana_context_request(text), "Asana", get_asana_tasks)
]


def get_formatted_command(text):
    for aliases, title, provider in FORMATTED_COMMANDS:
        if text in aliases:
            return title, provider

    return None


def is_calendar_event_request(text):
    if any(text.startswith(f"{prefix} ") for prefix in CALENDAR_EVENT_PREFIXES):
        return True

    action_words = ("create", "add", "schedule", "book")
    calendar_words = ("calendar", "event", "meeting", "appointment")
    return text.startswith(action_words) and any(word in text for word in calendar_words)


def is_email_action_request(text):
    action_words = ("send", "reply", "forward")
    email_words = ("email", "gmail", "mail")
    return text.startswith(action_words) and any(word in text for word in email_words)


def is_draft_email_request(text):
    return text in {"draft email", "create email draft", "draft gmail", "create gmail draft"}


def has_explicit_data_action(text):
    return any(word in text for word in EXPLICIT_DATA_ACTION_WORDS)


def is_explicit_gmail_context_request(text):
    gmail_words = ("gmail", "email", "inbox", "mail")
    return has_explicit_data_action(text) and any(word in text for word in gmail_words)


def is_explicit_calendar_context_request(text):
    calendar_words = ("calendar", "meeting", "appointment", "agenda")
    return has_explicit_data_action(text) and any(word in text for word in calendar_words)


def is_explicit_asana_context_request(text):
    asana_words = ("asana", "task", "tasks", "project", "projects")
    return has_explicit_data_action(text) and any(word in text for word in asana_words)


def is_unsupported_external_action_request(text):
    unsupported_actions = (
        "delete",
        "remove",
        "cancel",
        "update",
        "edit",
        "reschedule",
        "complete",
        "mark",
        "write",
        "store"
    )
    external_targets = (
        "calendar",
        "event",
        "meeting",
        "asana",
        "task",
        "email",
        "gmail",
        "mail",
        "database",
        "supabase",
        "table",
        "record"
    )

    return text.startswith(unsupported_actions) and any(target in text for target in external_targets)


def extract_task_name(message):
    for prefix in ASANA_TASK_PREFIXES:
        pattern = rf"^{re.escape(prefix)}\s+"
        task_name = re.sub(pattern, "", message, flags=re.IGNORECASE).strip()

        if task_name != message.strip():
            return task_name

    return None


def format_finance_confirmation(tx, saved):
    amount = f"{tx['amount']:.2f}"
    category = tx["category"]
    transaction_type = tx["transaction_type"].replace("_", " ")

    if saved:
        return (
            "Confirmed: I logged this finance transaction.\n"
            f"Type: {transaction_type}\n"
            f"Amount: EUR {amount}\n"
            f"Category: {category}"
        )

    return (
        "I could not confirm that this finance transaction was saved.\n"
        "No completion has been recorded. Please try again or check Supabase/system logs."
    )


def get_safe_action_result(result, success_prefix, failure_prefix):
    if result.startswith(success_prefix):
        return f"Confirmed: {result}"

    return f"{failure_prefix}\n{result}"


def create_calendar_event_reply(message):
    result = create_calendar_event_from_text(message)
    return get_safe_action_result(
        result,
        "Calendar event created:",
        "I could not confirm that a calendar event was created."
    )


def create_gmail_draft_reply(to_email, subject, body):
    result = create_gmail_draft(to_email, subject, body)
    return get_safe_action_result(
        result,
        "Gmail draft created:",
        "I could not confirm that a Gmail draft was created."
    )


def generate_a1_practice():
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=450,
            system="Create compact Goethe A1 German practice. No long explanations.",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Return exactly: 5 vocab words with meanings, "
                        "3 grammar tips, 2 speaking questions, 1 writing task."
                    )
                }
            ]
        )
        return response.content[0].text
    except Exception as e:
        log_system_error("generate_a1_practice", e)
        return f"A1 practice failed: {str(e)}"


def correct_german_text(text):
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=550,
            system=(
                "Correct German for an A1 learner. Be concise. Sections: "
                "Corrected, Mistakes, Improved, Practice Note."
            ),
            messages=[
                {
                    "role": "user",
                    "content": text
                }
            ]
        )
        correction = response.content[0].text
        save_semantic_memory(
            "German recurring mistake candidate: "
            + truncate_text(f"Original: {text} Correction: {correction}", max_length=700)
        )
        return correction
    except Exception as e:
        log_system_error("correct_german_text", e)
        return f"German correction failed: {str(e)}"


def clear_german_word_state(context):
    context.user_data.pop(WAITING_FOR_GERMAN_WORD, None)
    context.user_data.pop(WAITING_FOR_GERMAN_MEANING, None)
    context.user_data.pop(WAITING_FOR_GERMAN_EXAMPLE, None)
    context.user_data.pop(GERMAN_WORD_STATE, None)


def clear_german_grammar_state(context):
    context.user_data.pop(WAITING_FOR_GRAMMAR_TOPIC, None)
    context.user_data.pop(WAITING_FOR_GRAMMAR_NOTE, None)
    context.user_data.pop(GERMAN_GRAMMAR_STATE, None)


def clear_german_quiz_state(context):
    context.user_data.pop(WAITING_FOR_GERMAN_QUIZ_ANSWER, None)
    context.user_data.pop(GERMAN_QUIZ_STATE, None)


def clear_interaction_states(context):
    context.user_data.pop(WAITING_FOR_CALENDAR_EVENT, None)
    clear_email_draft_state(context)
    clear_german_word_state(context)
    clear_german_grammar_state(context)
    context.user_data.pop(WAITING_FOR_GERMAN_CORRECTION, None)
    clear_german_quiz_state(context)


async def handle_german_word_flow(update, context, user_message):
    try:
        if context.user_data.get(WAITING_FOR_GERMAN_WORD):
            context.user_data.pop(WAITING_FOR_GERMAN_WORD, None)
            context.user_data[WAITING_FOR_GERMAN_MEANING] = True
            context.user_data[GERMAN_WORD_STATE] = {"word": user_message.strip()}
            await update.message.reply_text("What does it mean in English?")
            return True

        if context.user_data.get(WAITING_FOR_GERMAN_MEANING):
            context.user_data.pop(WAITING_FOR_GERMAN_MEANING, None)
            context.user_data[WAITING_FOR_GERMAN_EXAMPLE] = True
            state = context.user_data.setdefault(GERMAN_WORD_STATE, {})
            state["meaning"] = user_message.strip()
            await update.message.reply_text("Add one example sentence.")
            return True

        if context.user_data.get(WAITING_FOR_GERMAN_EXAMPLE):
            context.user_data.pop(WAITING_FOR_GERMAN_EXAMPLE, None)
            state = context.user_data.get(GERMAN_WORD_STATE, {})
            word = state.get("word", "")
            meaning = state.get("meaning", "")
            example = user_message.strip()
            clear_german_word_state(context)

            saved = bool(word and meaning and example and save_german_word(word, meaning, example))
            reply = (
                f"Confirmed: saved German word.\nWord: {word}\nMeaning: {meaning}"
                if saved
                else "I could not confirm that the German word was saved."
            )
            save_to_supabase("Add German Word", reply)
            await update.message.reply_text(reply, reply_markup=get_german_a1_menu())
            return True

        return False
    except Exception as e:
        log_system_error("handle_german_word_flow", e)
        clear_german_word_state(context)
        await update.message.reply_text("German word flow failed.", reply_markup=get_german_a1_menu())
        return True


async def handle_german_grammar_flow(update, context, user_message):
    try:
        if context.user_data.get(WAITING_FOR_GRAMMAR_TOPIC):
            context.user_data.pop(WAITING_FOR_GRAMMAR_TOPIC, None)
            context.user_data[WAITING_FOR_GRAMMAR_NOTE] = True
            context.user_data[GERMAN_GRAMMAR_STATE] = {"topic": user_message.strip()}
            await update.message.reply_text("What note or explanation should I save?")
            return True

        if context.user_data.get(WAITING_FOR_GRAMMAR_NOTE):
            context.user_data.pop(WAITING_FOR_GRAMMAR_NOTE, None)
            state = context.user_data.get(GERMAN_GRAMMAR_STATE, {})
            topic = state.get("topic", "")
            note = user_message.strip()
            clear_german_grammar_state(context)

            saved = bool(topic and note and save_grammar_rule(topic, note))
            reply = (
                f"Confirmed: saved grammar rule.\nTopic: {topic}"
                if saved
                else "I could not confirm that the grammar rule was saved."
            )
            save_to_supabase("Add Grammar Rule", reply)
            await update.message.reply_text(reply, reply_markup=get_german_a1_menu())
            return True

        return False
    except Exception as e:
        log_system_error("handle_german_grammar_flow", e)
        clear_german_grammar_state(context)
        await update.message.reply_text("Grammar rule flow failed.", reply_markup=get_german_a1_menu())
        return True


async def handle_german_correction_flow(update, context, user_message):
    if not context.user_data.get(WAITING_FOR_GERMAN_CORRECTION):
        return False

    try:
        context.user_data.pop(WAITING_FOR_GERMAN_CORRECTION, None)
        reply = correct_german_text(user_message)
        save_to_supabase("Correct My German", reply)
        await update.message.reply_text(reply, reply_markup=get_german_a1_menu())
        return True
    except Exception as e:
        log_system_error("handle_german_correction_flow", e)
        context.user_data.pop(WAITING_FOR_GERMAN_CORRECTION, None)
        await update.message.reply_text("German correction failed.", reply_markup=get_german_a1_menu())
        return True


async def handle_german_quiz_flow(update, context, user_message):
    if not context.user_data.get(WAITING_FOR_GERMAN_QUIZ_ANSWER):
        return False

    try:
        context.user_data.pop(WAITING_FOR_GERMAN_QUIZ_ANSWER, None)
        quiz = context.user_data.get(GERMAN_QUIZ_STATE, {})
        clear_german_quiz_state(context)

        expected = (quiz.get("meaning") or "").lower()
        answer = user_message.lower().strip()
        correct = expected and (answer in expected or expected in answer)
        reply = (
            f"Correct. {quiz.get('word')} = {quiz.get('meaning')}"
            if correct
            else f"Not quite. {quiz.get('word')} means: {quiz.get('meaning')}"
        )
        example = quiz.get("example_sentence")
        if example:
            reply += f"\nExample: {example}"

        save_to_supabase("Quiz Me", reply)
        await update.message.reply_text(reply, reply_markup=get_german_a1_menu())
        return True
    except Exception as e:
        log_system_error("handle_german_quiz_flow", e)
        clear_german_quiz_state(context)
        await update.message.reply_text("German quiz failed.", reply_markup=get_german_a1_menu())
        return True


def clear_email_draft_state(context):
    context.user_data.pop(WAITING_FOR_EMAIL_TO, None)
    context.user_data.pop(WAITING_FOR_EMAIL_SUBJECT, None)
    context.user_data.pop(WAITING_FOR_EMAIL_BODY, None)
    context.user_data.pop(EMAIL_DRAFT_STATE, None)


async def handle_email_draft_flow(update, context, user_message):
    if context.user_data.get(WAITING_FOR_EMAIL_TO):
        context.user_data.pop(WAITING_FOR_EMAIL_TO, None)
        context.user_data[WAITING_FOR_EMAIL_SUBJECT] = True
        context.user_data[EMAIL_DRAFT_STATE] = {"to": user_message.strip()}
        await update.message.reply_text("What subject should I use?")
        return True

    if context.user_data.get(WAITING_FOR_EMAIL_SUBJECT):
        context.user_data.pop(WAITING_FOR_EMAIL_SUBJECT, None)
        context.user_data[WAITING_FOR_EMAIL_BODY] = True
        draft = context.user_data.setdefault(EMAIL_DRAFT_STATE, {})
        draft["subject"] = user_message.strip()
        await update.message.reply_text("What should the email say?")
        return True

    if context.user_data.get(WAITING_FOR_EMAIL_BODY):
        context.user_data.pop(WAITING_FOR_EMAIL_BODY, None)
        draft = context.user_data.get(EMAIL_DRAFT_STATE, {})
        to_email = draft.get("to", "")
        subject = draft.get("subject", "")
        body = user_message.strip()
        clear_email_draft_state(context)

        if not to_email or not subject or not body:
            reply = (
                "I could not create the Gmail draft because recipient, subject, or body was missing.\n"
                "No draft was created."
            )
        else:
            reply = create_gmail_draft_reply(to_email, subject, body)

        save_to_supabase("Draft Email", reply)
        await update.message.reply_text(reply, reply_markup=get_main_menu())
        return True

    return False


def get_unsupported_action_reply():
    return (
        "I did not complete that external action.\n"
        "Only these write actions are currently connected to real APIs: create calendar events, create Gmail drafts, create Asana tasks, save memories, and log finance transactions."
    )


def build_live_context(text):
    context_parts = []

    for should_fetch, title, provider in LIVE_CONTEXT_PROVIDERS:
        if should_fetch(text):
            context_parts.append(f"\n\n{title}:\n{provider()}")

    return "".join(context_parts)


def compact_json(data):
    return json.dumps(data, separators=(",", ":"))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    if not update.message or not update.message.text:
        return

    user_message = update.message.text
    text = user_message.lower().strip()

    if text in BACK_COMMANDS:
        clear_interaction_states(context)
        await update.message.reply_text("Back to main menu.", reply_markup=get_main_menu())
        return

    if context.user_data.get(WAITING_FOR_CALENDAR_EVENT):
        context.user_data.pop(WAITING_FOR_CALENDAR_EVENT, None)
        reply = create_calendar_event_reply(user_message)
        save_to_supabase(user_message, reply)
        await update.message.reply_text(reply, reply_markup=get_main_menu())
        return

    if await handle_email_draft_flow(update, context, user_message):
        return

    if await handle_german_word_flow(update, context, user_message):
        return

    if await handle_german_grammar_flow(update, context, user_message):
        return

    if await handle_german_correction_flow(update, context, user_message):
        return

    if await handle_german_quiz_flow(update, context, user_message):
        return

    # Simple menu/help
    if text in MENU_COMMANDS:
        await update.message.reply_text(
            "Choose an action:",
            reply_markup=get_main_menu()
        )
        return

    if text in GERMAN_MENU_COMMANDS:
        await update.message.reply_text(
            "German A1 practice:",
            reply_markup=get_german_a1_menu()
        )
        return

    # Daily briefing shortcut
    if text == "daily briefing":
        await send_daily_briefing(context.application)
        return

    # Persist semantic memory for inputs
    save_semantic_memory(user_message)

    # "Remember ..." handling
    remember_text = detect_remember_command(user_message)
    if remember_text:
        saved = save_personal_memory(remember_text)
        reply = (
            f"Confirmed: I saved this memory.\nMemory: {remember_text}"
            if saved
            else "I could not confirm that this memory was saved. Please try again or check system logs."
        )
        save_to_supabase(user_message, reply)
        await update.message.reply_text(reply)
        return

    command = get_formatted_command(text)
    if command:
        title, provider = command
        raw = provider()
        formatted = format_with_claude(title, raw)
        await update.message.reply_text(formatted, reply_markup=get_main_menu())
        return

    if text == "create calendar event":
        context.user_data[WAITING_FOR_CALENDAR_EVENT] = True
        await update.message.reply_text(
            "What would you like to schedule?\nExample: Dentist tomorrow 15:00"
        )
        return

    if is_draft_email_request(text):
        clear_email_draft_state(context)
        context.user_data[WAITING_FOR_EMAIL_TO] = True
        await update.message.reply_text(
            "Who should the draft email be addressed to?"
        )
        return

    if text in ADD_GERMAN_WORD_COMMANDS:
        clear_german_word_state(context)
        context.user_data[WAITING_FOR_GERMAN_WORD] = True
        await update.message.reply_text("What German word should I save?")
        return

    if text in ADD_GRAMMAR_RULE_COMMANDS:
        clear_german_grammar_state(context)
        context.user_data[WAITING_FOR_GRAMMAR_TOPIC] = True
        await update.message.reply_text("What grammar topic should I save?")
        return

    if text in CORRECT_GERMAN_COMMANDS:
        context.user_data[WAITING_FOR_GERMAN_CORRECTION] = True
        await update.message.reply_text("Send the German sentence or text you want corrected.")
        return

    if text == "a1 practice":
        reply = generate_a1_practice()
        save_to_supabase(user_message, reply)
        await update.message.reply_text(reply, reply_markup=get_german_a1_menu())
        return

    if text == "quiz me":
        words = get_random_german_words(limit=1)

        if not words:
            reply = "No German words found yet. Add a word first."
            await update.message.reply_text(reply, reply_markup=get_german_a1_menu())
            return

        quiz = words[0]
        context.user_data[GERMAN_QUIZ_STATE] = quiz
        context.user_data[WAITING_FOR_GERMAN_QUIZ_ANSWER] = True
        await update.message.reply_text(f"Quiz: What does '{quiz.get('word')}' mean?")
        return

    # Create Asana task
    task_name = extract_task_name(user_message)
    if task_name is not None:
        if not task_name:
            await update.message.reply_text("Please provide a task name.")
            return
        result = create_asana_task(task_name)
        reply = get_safe_action_result(
            result,
            "Asana task created:",
            "I could not confirm that an Asana task was created."
        )
        save_to_supabase(user_message, reply)
        await update.message.reply_text(reply)
        return

    # Create calendar event from full command
    if is_calendar_event_request(text):
        reply = create_calendar_event_reply(user_message)
        save_to_supabase(user_message, reply)
        await update.message.reply_text(reply)
        return

    # System status
    if text == "system status":
        status = get_system_status()
        await update.message.reply_text(status)
        return

    if text == "show errors":
        errors = get_recent_system_errors()
        await update.message.reply_text(errors, reply_markup=get_main_menu())
        return

    if is_email_action_request(text):
        reply = (
            "I did not send, reply to, or forward any email.\n"
            "Email sending is disabled. I can create Gmail drafts through the Draft Email button."
        )
        save_to_supabase(user_message, reply)
        await update.message.reply_text(reply)
        return

    # Finance classification / save
    finance_tx = classify_finance_message(user_message)
    if finance_tx:
        saved = save_finance_transaction(finance_tx)
        reply = format_finance_confirmation(finance_tx, saved)
        save_to_supabase(user_message, reply)
        await update.message.reply_text(reply)
        return

    if is_unsupported_external_action_request(text):
        reply = get_unsupported_action_reply()
        save_to_supabase(user_message, reply)
        await update.message.reply_text(reply)
        return

    # Semantic search & contexts
    semantic_results = search_semantic_memory(user_message)
    semantic_context = ""

    if semantic_results:
        semantic_context = f"\nRelevant semantic memories: {compact_json(semantic_results)}"

    runtime_context = f"""
Current date/time:
{get_current_datetime()}
Timezone: {TIMEZONE_NAME}
"""

    personal_memories = get_personal_memories()
    personal_memory_context = ""

    if personal_memories:
        personal_memory_context = f"\nPersonal memories: {compact_json(personal_memories)}"

    live_context = build_live_context(text)

    # Recent conversation history
    recent_memories = get_recent_memories()
    conversation_history = []
    for memory in reversed(recent_memories):
        conversation_history.append({"role": "user", "content": memory["user_message"]})
        conversation_history.append({"role": "assistant", "content": memory["assistant_response"]})
    conversation_history.append({"role": "user", "content": user_message})

    # Query Claude
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=900,
        system=(
            SYSTEM_PROMPT
            + runtime_context
            + semantic_context
            + personal_memory_context
            + live_context
        ),
        messages=conversation_history
    )

    reply = response.content[0].text
    save_to_supabase(user_message, reply)
    await update.message.reply_text(reply)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log_system_error("telegram_error_handler", context.error)


def main():
    print("Bajrang is starting...")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    app.add_error_handler(handle_error)

    scheduler = BackgroundScheduler(timezone=TIMEZONE_NAME)

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
