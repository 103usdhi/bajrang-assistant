import os
import re
import json
import asyncio
import logging
import requests
import base64
import random
import html
from datetime import datetime, timedelta
import tempfile
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TimedOut
import pypdf
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

import anthropic

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASANA_TOKEN = os.getenv("ASANA_TOKEN")
GOOGLE_TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")
RENDER_API_KEY = os.getenv("RENDER_API_KEY")
RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

ALLOWED_USER_ID = 8106199737
TIMEZONE_NAME = "Europe/Berlin"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
RECENT_EXCHANGE_LIMIT = 6
PERSONAL_MEMORY_LIMIT = 15
SEMANTIC_MEMORY_MATCH_COUNT = 2
CLAUDE_MODEL = "claude-sonnet-4-6"

logging.basicConfig(level=logging.INFO)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

SYSTEM_PROMPT = """
You are Bajrang, a highly intelligent personal AI assistant.

BAJRANG IDENTITY:
- You are Bajrang, a personal AI assistant.
- You were designed, configured, and maintained by Dhiraj Damare.
- If asked who created/developed/built/owns/maintains you, answer consistently:
  "Bajrang was designed, configured, and maintained by Dhiraj Damare as a personal AI assistant project. AI coding assistants such as ChatGPT, Claude, Gemini, and Codex may have helped with code suggestions, but Dhiraj is the owner and maintainer."
- Do not invent developer names.
- Do not guess.
- Do not say Saurabh, Sachin, or any other person unless explicitly documented.

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
- Documents may be stored as searchable semantic chunks and document records. Use retrieved context when relevant, but avoid claiming perfect exact-document recall.
- When responding via voice, maintain a warm, conversational, and natural tone.
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
FINANCE_MENU_COMMANDS = {"finance setup", "finance foundation"}
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
ICON_ORANGE = "\U0001f7e0"
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

GMAIL_RECOVERY_MESSAGE = """Gmail authentication is unavailable.

Likely cause:
- Google refresh token expired or was revoked.

Recovery:
1. Run google_reauth.py locally.
2. Complete Google OAuth login.
3. Copy the generated token JSON.
4. Update GOOGLE_TOKEN_JSON in Render.
5. Redeploy Bajrang."""
GMAIL_NO_MATCH_MESSAGE = "📭 No matching Gmail messages found."
BAJRANG_IDENTITY_RESPONSE = (
    "Bajrang was designed, configured, and maintained by Dhiraj Damare as a personal AI assistant project. "
    "AI coding assistants such as ChatGPT, Claude, Gemini, and Codex may have helped with code suggestions, "
    "but Dhiraj is the owner and maintainer."
)
FINANCE_FLOW_STATE = "finance_flow_state"
FINANCE_PENDING_CONFIRM = "finance_pending_confirm"
FINANCE_EDIT_DELETE_STATE = "finance_edit_delete_state"

FINANCE_BTN_SETUP = "Finance Setup"
FINANCE_BTN_SET_SALARY = "Set Monthly Salary"
FINANCE_BTN_SET_RENT = "Set Rent"
FINANCE_BTN_ADD_EMI = "Add EMI / Loan"
FINANCE_BTN_ADD_BILL = "Add Recurring Bill"
FINANCE_BTN_ADD_GOAL = "Add Savings Goal"
FINANCE_BTN_ADD_PLAN = "Add Future Plan"
FINANCE_BTN_VIEW_PROFILE = "View Finance Profile"
FINANCE_BTN_EDIT_DELETE = "Edit/Delete Finance Item"

FINANCE_CONFIRM_SAVE = "✅ Save"
FINANCE_CONFIRM_EDIT = "✏️ Edit"
FINANCE_CONFIRM_CANCEL = "❌ Cancel"
FINANCE_ACTION_DELETE = "🗑 Delete"

supabase_headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}


def get_timezone():
    return ZoneInfo(TIMEZONE_NAME)


def is_identity_question(text):
    lowered = str(text or "").lower().strip()
    if not lowered:
        return False

    patterns = [
        r"\bwho\s+developed\s+you\b",
        r"\bwho\s+created\s+you\b",
        r"\bwho\s+built\s+you\b",
        r"\bwho\s+built\s+bajrang\b",
        r"\bwho\s+is\s+your\s+owner\b",
        r"\bwho\s+owns\s+you\b",
        r"\bwho\s+maintains\s+you\b",
        r"\bwhat\s+are\s+you\b"
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


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
            "created_at": datetime.now(get_timezone()).isoformat(),
            "module": module,
            "error_message": error_message
        }
        # Using a timeout to ensure the main thread isn't held up indefinitely
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
        res = requests.post(url, headers=supabase_headers, json=data, timeout=10)
        if res.status_code not in [200, 201, 204]:
            log_system_error("save_to_supabase", f"Supabase returned {res.status_code}: {res.text}")
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
        result = requests.get(url, headers=supabase_headers, timeout=10)
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
        result = requests.post(url, headers=supabase_headers, json=data, timeout=10)
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
        result = requests.get(url, headers=supabase_headers, timeout=10)
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


def get_finance_summary():
    """Aggregates balance and monthly spending for AI context."""
    try:
        # Using your existing breakdown/overspending logic to feed the AI context
        spending = get_monthly_spending_breakdown()
        insights = get_overspending_insights()
        return json.dumps({
            "monthly_breakdown": json.loads(spending) if "failed" not in spending else spending,
            "insights": json.loads(insights) if "failed" not in insights else insights
        }, indent=2)
    except Exception as e:
        log_system_error("get_finance_summary", e)
        return "Finance summary unavailable."


def save_semantic_memory(content, source="telegram"):
    if not openai_client:
        return

    try:
        embedding = generate_embedding(content)
        url = f"{SUPABASE_URL}/rest/v1/semantic_memory"
        data = {
            "content": content,
            "source": source,
            "embedding": embedding
        }
        requests.post(url, headers=supabase_headers, json=data, timeout=10)
    except Exception as e:
        log_system_error("save_semantic_memory", e)


def save_document_metadata(doc_data):
    try:
        url = f"{SUPABASE_URL}/rest/v1/uploaded_documents"
        result = requests.post(url, headers=supabase_headers, json=doc_data, timeout=10)
        if result.status_code in [200, 201, 204]:
            return True
        log_system_error("save_document_metadata", RuntimeError(f"Supabase returned {result.status_code}: {result.text}"))
        return False
    except Exception as e:
        log_system_error("save_document_metadata", e)
        return False


def get_uploaded_documents(limit=5):
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/uploaded_documents"
            f"?select=filename,document_type,created_at,semantic_chunk_count"
            f"&order=created_at.desc"
            f"&limit={limit}"
        )
        result = requests.get(url, headers=supabase_headers, timeout=10)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_system_error("get_uploaded_documents", e)
        return []


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
        result = requests.post(url, headers=supabase_headers, json=data, timeout=10)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_system_error("search_semantic_memory", e)
        return []


def classify_finance_message(message):
    text = message.lower()
    intent_keywords = [
        "spent", "paid", "bought", "salary", "income", "saved", 
        "invested", "rent", "bill", "cost", "expense", "refund", 
        "loan", "emi", "received", "bonus", "got paid"
    ]

    if not any(kw in text for kw in intent_keywords):
        return None

    amount_match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)

    if not amount_match:
        return None

    amount = float(amount_match.group(1))
    transaction_type = None

    if any(k in text for k in ["salary", "income", "received", "bonus", "got paid"]):
        transaction_type = "income"
    elif any(k in text for k in ["spent", "paid", "bought", "expense", "cost", "rent", "bill"]):
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
            "description": tx["description"],
            "is_essential": tx["is_essential"]
        }
        result = requests.post(url, headers=supabase_headers, json=data, timeout=10)
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


def _parse_finance_amount_legacy(text):
    cleaned = str(text or "").strip().lower()
    cleaned = cleaned.replace("eur", "").replace("€", "")
    cleaned = cleaned.replace(",", ".")
    match = re.search(r"(-?\d+(?:\.\d{1,2})?)", cleaned)
    if not match:
        return None
    try:
        value = float(match.group(1))
        if value <= 0:
            return None
        return round(value, 2)
    except Exception:
        return None


def parse_finance_amount(text):
    """
    Locale-safe parsing examples:
    - 1,200 -> 1200.00
    - 1.200 -> 1200.00
    - 1,200.50 -> 1200.50
    - 1.200,50 -> 1200.50
    """

    def normalize_amount_token(token):
        candidate = token.strip().strip(".,")
        if not candidate:
            return None

        if "," in candidate and "." in candidate:
            # Last separator is treated as decimal separator.
            if candidate.rfind(",") > candidate.rfind("."):
                return candidate.replace(".", "").replace(",", ".")
            return candidate.replace(",", "")

        if "," in candidate:
            parts = candidate.split(",")
            if len(parts) == 2:
                left, right = parts
                if len(right) == 3 and left:
                    return left + right
                if 1 <= len(right) <= 2:
                    return left + "." + right
            return "".join(parts)

        if "." in candidate:
            parts = candidate.split(".")
            if len(parts) == 2:
                left, right = parts
                if len(right) == 3 and left:
                    return left + right
                if 1 <= len(right) <= 2:
                    return left + "." + right
            return "".join(parts)

        return candidate

    cleaned = str(text or "").strip().lower()
    cleaned = cleaned.replace("eur", "").replace("€", "").replace("â‚¬", "")
    cleaned = cleaned.replace(" ", "").replace("\u00a0", "")

    match = re.search(r"-?\d[\d.,]*", cleaned)
    if not match:
        return None

    normalized = normalize_amount_token(match.group(0))
    if not normalized:
        return None

    try:
        value = float(normalized)
        if value <= 0:
            return None
        return round(value, 2)
    except Exception:
        return None


def format_eur(amount):
    try:
        value = float(amount or 0)
    except Exception:
        value = 0.0
    return f"EUR {value:,.2f}".replace(",", " ")


def parse_plan_month(text):
    lowered = str(text or "").lower().strip()
    if not lowered:
        return None

    now = datetime.now(get_timezone())
    if "next month" in lowered:
        month = now.month + 1
        year = now.year
        if month > 12:
            month = 1
            year += 1
        return f"{year:04d}-{month:02d}"

    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }
    for month_name, month_number in month_map.items():
        if month_name in lowered:
            year_match = re.search(r"\b(20\d{2})\b", lowered)
            year = int(year_match.group(1)) if year_match else now.year
            if not year_match and month_number < now.month:
                year += 1
            return f"{year:04d}-{month_number:02d}"

    iso_match = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", lowered)
    if iso_match:
        return f"{iso_match.group(1)}-{iso_match.group(2)}"

    return None


def parse_future_plan_text(text):
    raw = str(text or "").strip()
    lowered = raw.lower()
    amount = parse_finance_amount(raw)
    planned_month = parse_plan_month(raw)

    plan_type = "planned_expense"
    if "refund" in lowered:
        plan_type = "expected_refund"
    elif "invest" in lowered:
        plan_type = "investment"
    elif "buy" in lowered or "purchase" in lowered:
        plan_type = "purchase"

    return {
        "title": raw,
        "plan_type": plan_type,
        "planned_amount": amount,
        "planned_month": planned_month
    }


def is_critical_finance_capture_request(text):
    lowered = str(text or "").lower()
    has_number = bool(re.search(r"\b\d[\d.,]*\b", lowered))
    if not has_number:
        return False

    critical_words = (
        "salary", "rent", "emi", "loan", "recurring bill",
        "savings goal", "financial goal", "future plan"
    )
    if any(word in lowered for word in critical_words):
        return True

    month_names = (
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december"
    )
    future_plan_markers = (
        "invest",
        "investment",
        "buy",
        "purchase",
        "refund",
        "expected income",
        "expected payment",
        "next month",
        "planned",
        "goal",
        "save for"
    )
    finance_context_markers = (
        "finance", "money", "income", "payment", "salary", "rent",
        "emi", "loan", "bill", "invest", "buy", "purchase", "refund", "goal", "save"
    )

    has_month_signal = "next month" in lowered or any(month in lowered for month in month_names)
    has_future_signal = any(marker in lowered for marker in future_plan_markers) or has_month_signal
    has_finance_context = any(marker in lowered for marker in finance_context_markers) or "€" in str(text or "") or "eur" in lowered

    return has_future_signal and has_finance_context


def is_finance_profile_question(text):
    lowered = str(text or "").lower().strip()
    if not lowered:
        return False
    finance_targets = (
        "finance profile", "my salary", "my rent", "emi", "loan", "commitment",
        "savings goal", "future plan", "upcoming obligations", "fixed commitments"
    )
    action_words = ("show", "view", "what", "how much", "list", "summary", "profile")
    return any(target in lowered for target in finance_targets) and any(word in lowered for word in action_words)


def set_finance_pending_confirmation(context, action, payload, summary, edit_state=None, edit_prompt=None):
    context.user_data[FINANCE_PENDING_CONFIRM] = {
        "action": action,
        "payload": payload,
        "summary": summary,
        "edit_state": edit_state,
        "edit_prompt": edit_prompt or "Please update the value."
    }


def clear_finance_states(context):
    context.user_data.pop(FINANCE_FLOW_STATE, None)
    context.user_data.pop(FINANCE_PENDING_CONFIRM, None)
    context.user_data.pop(FINANCE_EDIT_DELETE_STATE, None)


def save_financial_profile_values(values):
    try:
        payload = {
            "user_id": ALLOWED_USER_ID,
            "updated_at": datetime.now(get_timezone()).isoformat()
        }
        payload.update(values)
        headers = dict(supabase_headers)
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        result = requests.post(
            f"{SUPABASE_URL}/rest/v1/financial_profile",
            headers=headers,
            json=payload,
            timeout=10
        )
        if result.status_code in [200, 201, 204]:
            return True
        log_system_error("save_financial_profile_values", RuntimeError(f"Supabase returned {result.status_code}: {result.text}"))
        return False
    except Exception as e:
        log_system_error("save_financial_profile_values", e)
        return False


def insert_financial_commitment(payload):
    try:
        data = {
            "user_id": ALLOWED_USER_ID,
            "created_at": datetime.now(get_timezone()).isoformat(),
            "updated_at": datetime.now(get_timezone()).isoformat(),
            "status": "active"
        }
        data.update(payload)
        result = requests.post(
            f"{SUPABASE_URL}/rest/v1/financial_commitments",
            headers=supabase_headers,
            json=data,
            timeout=10
        )
        if result.status_code in [200, 201, 204]:
            return True
        log_system_error("insert_financial_commitment", RuntimeError(f"Supabase returned {result.status_code}: {result.text}"))
        return False
    except Exception as e:
        log_system_error("insert_financial_commitment", e)
        return False


def insert_financial_goal(payload):
    try:
        data = {
            "user_id": ALLOWED_USER_ID,
            "created_at": datetime.now(get_timezone()).isoformat(),
            "updated_at": datetime.now(get_timezone()).isoformat(),
            "status": "active"
        }
        data.update(payload)
        result = requests.post(
            f"{SUPABASE_URL}/rest/v1/financial_goals",
            headers=supabase_headers,
            json=data,
            timeout=10
        )
        if result.status_code in [200, 201, 204]:
            return True
        log_system_error("insert_financial_goal", RuntimeError(f"Supabase returned {result.status_code}: {result.text}"))
        return False
    except Exception as e:
        log_system_error("insert_financial_goal", e)
        return False


def insert_financial_plan(payload):
    try:
        data = {
            "user_id": ALLOWED_USER_ID,
            "created_at": datetime.now(get_timezone()).isoformat(),
            "updated_at": datetime.now(get_timezone()).isoformat(),
            "status": "planned"
        }
        data.update(payload)
        result = requests.post(
            f"{SUPABASE_URL}/rest/v1/financial_plans",
            headers=supabase_headers,
            json=data,
            timeout=10
        )
        if result.status_code in [200, 201, 204]:
            return True
        log_system_error("insert_financial_plan", RuntimeError(f"Supabase returned {result.status_code}: {result.text}"))
        return False
    except Exception as e:
        log_system_error("insert_financial_plan", e)
        return False


def fetch_finance_rows(table_name, select_columns="*", limit=50):
    try:
        params = {
            "select": select_columns,
            "user_id": f"eq.{ALLOWED_USER_ID}",
            "order": "created_at.desc",
            "limit": str(limit)
        }
        result = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table_name}",
            headers=supabase_headers,
            params=params,
            timeout=10
        )
        if result.status_code == 200:
            return result.json()
        log_system_error("fetch_finance_rows", RuntimeError(f"{table_name} returned {result.status_code}: {result.text}"))
        return []
    except Exception as e:
        log_system_error("fetch_finance_rows", e)
        return []


def get_financial_profile_row():
    rows = fetch_finance_rows("financial_profile", limit=1)
    return rows[0] if rows else {}


def format_finance_profile_summary():
    profile = get_financial_profile_row()
    commitments = fetch_finance_rows("financial_commitments", select_columns="id,commitment_type,name,amount,due_day,status")
    goals = fetch_finance_rows("financial_goals", select_columns="id,title,target_amount,target_date,status")
    plans = fetch_finance_rows("financial_plans", select_columns="id,plan_type,title,planned_amount,planned_month,status")

    lines = [
        "💼 Finance Profile",
        "",
        "Salary and Rent",
        f"- Monthly Salary: {format_eur(profile.get('monthly_salary')) if profile.get('monthly_salary') else 'Not set'}",
        f"- Monthly Rent: {format_eur(profile.get('monthly_rent')) if profile.get('monthly_rent') else 'Not set'}",
        "",
        "Fixed Commitments"
    ]

    if commitments:
        for row in commitments[:8]:
            due = row.get("due_day")
            due_text = f" | Due day: {due}" if due else ""
            lines.append(f"- {row.get('name', 'Commitment')} ({row.get('commitment_type', 'commitment')}): {format_eur(row.get('amount'))}{due_text}")
    else:
        lines.append("- None set")

    lines.append("")
    lines.append("Savings Goals")
    if goals:
        for row in goals[:8]:
            target_date = row.get("target_date") or "No target date"
            lines.append(f"- {row.get('title', 'Goal')}: {format_eur(row.get('target_amount'))} by {target_date}")
    else:
        lines.append("- None set")

    lines.append("")
    lines.append("Future Plans")
    if plans:
        for row in plans[:8]:
            month = row.get("planned_month") or "No month set"
            lines.append(f"- {row.get('title', 'Plan')} ({row.get('plan_type', 'plan')}): {format_eur(row.get('planned_amount'))} in {month}")
    else:
        lines.append("- None set")

    lines.append("")
    lines.append("Upcoming Obligations")
    if commitments or plans:
        for row in commitments[:5]:
            due = row.get("due_day")
            due_text = f"day {due}" if due else "due day not set"
            lines.append(f"- {row.get('name', 'Commitment')}: {format_eur(row.get('amount'))} ({due_text})")
        for row in plans[:5]:
            month = row.get("planned_month") or "month not set"
            lines.append(f"- {row.get('title', 'Plan')}: {format_eur(row.get('planned_amount'))} ({month})")
    else:
        lines.append("- No upcoming obligations")

    return "\n".join(lines)


def build_finance_item_catalog():
    items = {}
    lines = ["Finance items (reply with code):", ""]

    profile = get_financial_profile_row()
    if profile.get("monthly_salary") is not None:
        items["SALARY"] = {"table": "financial_profile", "field": "monthly_salary", "id": profile.get("id")}
        lines.append(f"- SALARY: Monthly Salary ({format_eur(profile.get('monthly_salary'))})")
    if profile.get("monthly_rent") is not None:
        items["RENT"] = {"table": "financial_profile", "field": "monthly_rent", "id": profile.get("id")}
        lines.append(f"- RENT: Monthly Rent ({format_eur(profile.get('monthly_rent'))})")

    commitments = fetch_finance_rows("financial_commitments", select_columns="id,name,amount", limit=20)
    for index, row in enumerate(commitments, start=1):
        code = f"C{index}"
        items[code] = {"table": "financial_commitments", "field": "amount", "id": row.get("id"), "name": row.get("name") or "Commitment"}
        lines.append(f"- {code}: {row.get('name', 'Commitment')} ({format_eur(row.get('amount'))})")

    goals = fetch_finance_rows("financial_goals", select_columns="id,title,target_amount", limit=20)
    for index, row in enumerate(goals, start=1):
        code = f"G{index}"
        items[code] = {"table": "financial_goals", "field": "target_amount", "id": row.get("id"), "name": row.get("title") or "Goal"}
        lines.append(f"- {code}: {row.get('title', 'Goal')} ({format_eur(row.get('target_amount'))})")

    plans = fetch_finance_rows("financial_plans", select_columns="id,title,planned_amount", limit=20)
    for index, row in enumerate(plans, start=1):
        code = f"P{index}"
        items[code] = {"table": "financial_plans", "field": "planned_amount", "id": row.get("id"), "name": row.get("title") or "Plan"}
        lines.append(f"- {code}: {row.get('title', 'Plan')} ({format_eur(row.get('planned_amount'))})")

    if not items:
        lines.append("- No editable finance items found.")

    return items, "\n".join(lines)


def update_finance_item_amount(item, amount):
    try:
        if item["table"] == "financial_profile":
            payload = {
                item["field"]: amount,
                "updated_at": datetime.now(get_timezone()).isoformat()
            }
            return save_financial_profile_values(payload)

        params = {"id": f"eq.{item['id']}"}
        payload = {
            item["field"]: amount,
            "updated_at": datetime.now(get_timezone()).isoformat()
        }
        result = requests.patch(
            f"{SUPABASE_URL}/rest/v1/{item['table']}",
            headers=supabase_headers,
            params=params,
            json=payload,
            timeout=10
        )
        if result.status_code in [200, 204]:
            return True
        log_system_error("update_finance_item_amount", RuntimeError(f"Supabase returned {result.status_code}: {result.text}"))
        return False
    except Exception as e:
        log_system_error("update_finance_item_amount", e)
        return False


def delete_finance_item(item):
    try:
        if item["table"] == "financial_profile":
            return save_financial_profile_values({item["field"]: None})

        result = requests.delete(
            f"{SUPABASE_URL}/rest/v1/{item['table']}",
            headers=supabase_headers,
            params={"id": f"eq.{item['id']}"},
            timeout=10
        )
        if result.status_code in [200, 204]:
            return True
        log_system_error("delete_finance_item", RuntimeError(f"Supabase returned {result.status_code}: {result.text}"))
        return False
    except Exception as e:
        log_system_error("delete_finance_item", e)
        return False


def save_german_word(word, meaning, example_sentence, article=None, plural=None):
    try:
        url = f"{SUPABASE_URL}/rest/v1/german_words"
        data = {
            "word": word,
            "meaning": meaning,
            "example_sentence": example_sentence,
            "article": article,
            "plural": plural,
            "source": "Netzwerk Neu",
            "created_at": datetime.now(get_timezone()).isoformat()
        }
        result = requests.post(url, headers=supabase_headers, json=data, timeout=10)

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
        result = requests.post(url, headers=supabase_headers, json=data, timeout=10)

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


def get_random_german_words(limit=5):
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/german_words"
            f"?select=word,meaning,example_sentence,article,plural"
            f"&order=random()"
            f"&limit={limit}"
        )
        result = requests.get(url, headers=supabase_headers, timeout=10)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_system_error("get_random_german_words", e)
        return []




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
        logging.warning("get_google_credentials: GOOGLE_TOKEN_JSON missing or empty.")
        if required_scopes:
            log_system_error(
                "get_google_credentials",
                RuntimeError("Google token missing for required scopes: " + ", ".join(required_scopes))
            )
        return None

    try:
        logging.info("get_google_credentials: attempting GOOGLE_TOKEN_JSON parse.")
        token_data = json.loads(GOOGLE_TOKEN_JSON)
        logging.info(
            "get_google_credentials: token parsed. keys=%s refresh_token_present=%s",
            ",".join(sorted(token_data.keys())),
            bool(token_data.get("refresh_token"))
        )

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

        creds = Credentials.from_authorized_user_info(token_data)
        logging.info(
            "get_google_credentials: creds state before refresh valid=%s expired=%s refresh_token_present=%s",
            getattr(creds, "valid", None),
            getattr(creds, "expired", None),
            bool(getattr(creds, "refresh_token", None))
        )

        # If credentials are expired but have a refresh token, try to refresh them.
        try:
            if getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
                logging.info("get_google_credentials: credentials expired, attempting refresh.")
                creds.refresh(Request())
                logging.info(
                    "get_google_credentials: refresh completed valid=%s expired=%s",
                    getattr(creds, "valid", None),
                    getattr(creds, "expired", None)
                )
            elif getattr(creds, "expired", False) and not getattr(creds, "refresh_token", None):
                logging.warning(
                    "get_google_credentials: credentials expired but refresh_token is missing."
                )
        except RefreshError as e:
            # Refresh failed - likely revoked or invalid refresh token
            logging.error("get_google_credentials: RefreshError during refresh: %s", str(e))
            log_system_error("get_google_credentials", e)
            return None
        except Exception as e:
            # Any other refresh-related error
            logging.error("get_google_credentials: non-RefreshError during refresh: %s", str(e))
            log_system_error("get_google_credentials", e)
            return None

        return creds
    except Exception as e:
        logging.error("get_google_credentials: parsing/build failed: %s", str(e))
        log_system_error("get_google_credentials", e)
        return None


def get_gmail_search_query(text):
    """Strips trigger words to isolate search terms for the Gmail API."""
    if not text:
        return ""
    query = text.lower().strip()
    # Remove specific command aliases
    for cmd in ["gmail summary", "search gmail", "find email", "search email", "find mail"]:
        query = query.replace(cmd, "")
    # Remove common action verbs
    for word in ["show", "get", "check", "read", "did i get", "is there", "any"]:
        query = re.sub(rf"\b{word}\b", "", query, flags=re.IGNORECASE)
    return query.strip()


def clean_gmail_snippet(snippet, max_length=150):
    text = html.unescape(str(snippet or ""))
    text = re.sub(r"[\u034f\u200b-\u200f\ufeff]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) <= max_length:
        return text

    truncated = text[:max_length].rsplit(" ", 1)[0].strip()
    return (truncated or text[:max_length]).rstrip() + "..."


def format_gmail_date(raw_date):
    value = str(raw_date or "").strip()
    if not value:
        return "Unknown"
    try:
        dt = parsedate_to_datetime(value)
        return dt.strftime("%a, %d %b %Y")
    except Exception:
        return value


def format_gmail_search_results(emails, requested_max_results, total_estimate=None):
    if not emails:
        return GMAIL_NO_MATCH_MESSAGE

    single_result = requested_max_results == 1 or len(emails) == 1
    if single_result:
        email_row = emails[0]
        return "\n".join([
            "📧 Latest matching email",
            "",
            f"From: {email_row.get('from') or 'Unknown'}",
            f"Subject: {email_row.get('subject') or 'No subject'}",
            f"Date: {format_gmail_date(email_row.get('date'))}",
            f"Snippet: {clean_gmail_snippet(email_row.get('snippet', '')) or 'No preview available.'}"
        ])

    shown = emails[:5]
    lines = [
        "📧 Gmail Search Results",
        "",
        f"Found {len(emails)} matching emails."
    ]

    if (total_estimate and total_estimate > len(shown)) or len(emails) > 5:
        lines.append("Showing top 5 results.")

    lines.append("")
    for idx, email_row in enumerate(shown, start=1):
        lines.extend([
            f"{idx}. From: {email_row.get('from') or 'Unknown'}",
            f"Subject: {email_row.get('subject') or 'No subject'}",
            f"Date: {format_gmail_date(email_row.get('date'))}",
            f"Snippet: {clean_gmail_snippet(email_row.get('snippet', '')) or 'No preview available.'}",
            ""
        ])

    return "\n".join(lines).strip()


def search_gmail_messages(query, max_results=10):
    """Helper to search Gmail and return metadata + snippets. Excludes spam/trash."""
    try:
        creds = get_google_credentials()
        if not creds:
            return GMAIL_RECOVERY_MESSAGE

        service = build("gmail", "v1", credentials=creds)

        # Exclude spam and trash by default (avoid duplicating flags if already present)
        final_query = query.strip()
        if "-in:spam" not in final_query:
            final_query = f"{final_query} -in:spam"
        if "-in:trash" not in final_query:
            final_query = f"{final_query} -in:trash"
        final_query = final_query.strip()

        results = service.users().messages().list(
            userId="me",
            maxResults=max_results,
            q=final_query
        ).execute()

        messages = results.get("messages", [])
        result_estimate = results.get("resultSizeEstimate")
        if not messages:
            return GMAIL_NO_MATCH_MESSAGE

        emails = []

        for msg in messages:
            message = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()

            snippet = message.get("snippet", "")
            headers = message.get("payload", {}).get("headers", [])
            email = {"from": "", "subject": "", "date": "", "snippet": snippet}

            for h in headers:
                if h["name"].lower() == "from":
                    email["from"] = h["value"]
                elif h["name"].lower() == "subject":
                    email["subject"] = h["value"]
                elif h["name"].lower() == "date":
                    email["date"] = h["value"]

            emails.append(email)

        return format_gmail_search_results(
            emails,
            requested_max_results=max_results,
            total_estimate=result_estimate
        )
    except Exception as e:
        log_system_error("search_gmail_messages", e)
        return f"Gmail search failed: {str(e)}"


def get_gmail_summary(text=None):
    """Fetches a summary of recent emails, or performs a specific search if text is provided."""
    search_terms = get_gmail_search_query(text)
    
    # Default to inbox if no specific search term, otherwise prioritize search
    if not search_terms or search_terms in ["summary", "inbox"]:
        query = "in:inbox"
    else:
        # If the user doesn't specify 'all mail', we still prefer inbox results
        query = f"in:inbox {search_terms}" if "all mail" not in text.lower() else search_terms

    try:
        return search_gmail_messages(query, max_results=7)
    except Exception as e:
        log_system_error("get_gmail_summary", e)
        return f"Gmail fetch failed: {str(e)}"


def quote_gmail_from_value(value):
    sender = value.strip().strip("?.!,;:")
    if not sender:
        return ""
    if " " in sender and not (sender.startswith('"') and sender.endswith('"')):
        sender = f'"{sender}"'
    return sender


def extract_gmail_result_count(text, default=7):
    match = re.search(r"\b(?:top|latest|first)\s+(\d{1,2})\b", text or "", flags=re.IGNORECASE)
    if not match:
        return default

    try:
        count = int(match.group(1))
    except Exception:
        return default

    return max(1, min(count, 20))


def normalize_gmail_search_term(value):
    term = str(value or "").strip().strip("?.!,;:")
    term = term.strip('"').strip("'").strip()
    term = re.sub(r"\s+", " ", term)
    return term


def build_gmail_subject_query(value):
    term = normalize_gmail_search_term(value)
    if not term:
        return ""
    if " " in term and not (term.startswith('"') and term.endswith('"')):
        term = f'"{term}"'
    return f"subject:{term}"


def parse_gmail_search_intent(text):
    if not text:
        return None

    lowered = text.lower().strip()
    if lowered == "gmail summary":
        return None

    from_patterns = [
        (r"most recent email from\s+(.+)$", "latest_from"),
        (r"latest email from\s+(.+)$", "latest_from"),
        (r"did i get an email from\s+(.+)$", "did_i_get_from"),
        (r"any email from\s+(.+)$", "did_i_get_from"),
        (r"email from\s+(.+)$", "from"),
        (r"mail from\s+(.+)$", "from"),
        (r"gmail from\s+(.+)$", "from")
    ]

    for pattern, intent in from_patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if not match:
            continue
        sender = quote_gmail_from_value(match.group(1))
        if not sender:
            return None
        if intent == "latest_from":
            return {"intent": intent, "query": f"from:{sender}", "max_results": 1, "fallback_query": None}
        if intent == "did_i_get_from":
            return {
                "intent": intent,
                "query": f"from:{sender}",
                "max_results": 5,
                "fallback_query": sender
            }
        return {"intent": intent, "query": f"from:{sender}", "max_results": 7, "fallback_query": None}

    search_patterns = [
        r"search gmail for\s+(.+)$",
        r"find email about\s+(.+)$"
    ]
    for pattern in search_patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            query = match.group(1).strip().strip("?.!,;:")
            if query:
                return {"intent": "search", "query": query, "max_results": 7, "fallback_query": None}

    # Advanced generic Gmail intent detection:
    # supports "top/latest/first N", subject filters, sender filters, and containing/mentioning terms.
    if not re.search(r"\b(email|emails|gmail|mail|inbox|subject|sender|from|containing|mentioning)\b", lowered):
        return None

    max_results = extract_gmail_result_count(lowered, default=7)

    subject_patterns = [
        r"subject\s+(?:is\s+like|like|contains?|containing)\s+['\"]?(.+?)['\"]?$",
        r"(?:emails?|mail|gmail)\s+with\s+subject\s+['\"]?(.+?)['\"]?$",
        r"with\s+subject\s+['\"]?(.+?)['\"]?$",
        r"subject\s+['\"]?(.+?)['\"]?$"
    ]
    for pattern in subject_patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            subject_query = build_gmail_subject_query(match.group(1))
            if subject_query:
                return {
                    "intent": "advanced_subject_search",
                    "query": subject_query,
                    "max_results": max_results,
                    "fallback_query": None
                }

    from_patterns = [
        r"(?:top|latest|first)?\s*\d*\s*(?:emails?|mail|gmail)\s+from\s+(.+)$",
        r"(?:emails?|mail|gmail)\s+from\s+(.+)$",
        r"sender\s+(?:is|from)\s+(.+)$"
    ]
    for pattern in from_patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            sender = quote_gmail_from_value(match.group(1))
            if sender:
                return {
                    "intent": "advanced_from_search",
                    "query": f"from:{sender}",
                    "max_results": max_results,
                    "fallback_query": None
                }

    term_patterns = [
        r"(?:emails?|mail|gmail)\s+(?:containing|mentioning)\s+['\"]?(.+?)['\"]?$",
        r"(?:containing|mentioning)\s+['\"]?(.+?)['\"]?$",
        r"(?:search gmail for|search email for|find emails? containing|find emails? about|find email about)\s+['\"]?(.+?)['\"]?$"
    ]
    for pattern in term_patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            term = normalize_gmail_search_term(match.group(1))
            if term:
                return {
                    "intent": "advanced_term_search",
                    "query": term,
                    "max_results": max_results,
                    "fallback_query": None
                }

    return None


def create_gmail_draft(to_email, subject, body):
    try:
        creds = get_google_credentials(required_scopes=[GMAIL_COMPOSE_SCOPE])

        if not creds:
            return GMAIL_RECOVERY_MESSAGE

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
            headers=get_asana_headers(),
            timeout=10
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
            params=params,
            timeout=10
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
            json=data,
            timeout=10
        )

        if response.status_code in [200, 201]:
            return f"Asana task created: {task_name}"

        return f"Asana task creation failed: {response.status_code} {response.text}"
    except Exception as e:
        log_system_error("create_asana_task", e)
        return f"Asana error: {str(e)}"


def get_health_indicator(value):
    if value == "operational":
        return f"{ICON_GREEN} Online"
    if value == "partial":
        return f"{ICON_ORANGE} Partial"
    if value == "degraded":
        return f"{ICON_ORANGE} Degraded"
    if value == "timeout":
        return f"{ICON_YELLOW} Timeout"
    if value == "disabled":
        return f"{ICON_WHITE} Disabled"
    if value == "failed":
        return f"{ICON_RED} Failed"
    if value in ["not_checked", "unavailable", "unknown"]:
        return f"{ICON_WHITE} Not Checked"
    return f"{ICON_WHITE} {str(value).capitalize()}"


def format_record_count(value):
    if isinstance(value, int):
        return f"{value:,} records"

    if value == "count_unavailable":
        return f"{ICON_GREEN} Reachable (count n/a)"
    if value == "failed":
        return f"{ICON_RED} Failed"
    if value == "timeout":
        return f"{ICON_YELLOW} Timeout"
    if value == "partial":
        return f"{ICON_ORANGE} Partial"
    if value in ["not_checked", "unavailable", "unknown"]:
        return f"{ICON_WHITE} Not Checked"

    return f"{ICON_WHITE} Unknown"


def get_overall_health(report):
    # Core Infrastructure
    sb_status = report.get("supabase")
    if sb_status == "failed":
        return f"{ICON_RED} CRITICAL - Database Offline"
    if sb_status == "timeout":
        return f"{ICON_YELLOW} TIMEOUT - Supabase Connectivity Degraded"
    if sb_status in ("degraded", "partial"):
        return f"{ICON_ORANGE} PARTIAL - Supabase Degraded"

    infra_keys = ["claude", "openai_embeddings"]
    infra_failed = [k.capitalize().replace("_embeddings", "") for k in infra_keys if report.get(k) == "failed"]
    if infra_failed:
        return f"{ICON_RED} DEGRADED - {', '.join(infra_failed)} Failed"
    infra_timeout = [k.capitalize().replace("_embeddings", "") for k in infra_keys if report.get(k) == "timeout"]
    if infra_timeout:
        return f"{ICON_YELLOW} TIMEOUT - {', '.join(infra_timeout)} Slow"

    # Application Layer / Data Stores
    data_store_keys = [
        "events_log_count", "personal_memory_count", "semantic_memory_count",
        "finance_transactions_count", "german_words_count", "german_grammar_count",
        "documents_count", "logs_count"
    ]

    if any(report.get(k) == "failed" for k in data_store_keys):
        return f"{ICON_ORANGE} PARTIAL - Data Stores Unavailable"
    if any(report.get(k) in ("timeout", "partial") for k in data_store_keys):
        return f"{ICON_ORANGE} PARTIAL - Data Stores Degraded"

    app_keys = ["gmail", "calendar", "asana"]
    failed_apps = [k.capitalize() for k in app_keys if report.get(k) == "failed"]
    if failed_apps:
        return f"{ICON_ORANGE} PARTIAL - {', '.join(failed_apps)} Offline"
    timeout_apps = [k.capitalize() for k in app_keys if report.get(k) == "timeout"]
    if timeout_apps:
        return f"{ICON_YELLOW} TIMEOUT - {', '.join(timeout_apps)} Slow"

    return f"{ICON_GREEN} OPERATIONAL - Core infrastructure healthy"


def format_system_status_dashboard(report):
    data_labels = {
        "events_log_count": "Conversation logs",
        "personal_memory_count": "Personal memory",
        "semantic_memory_count": "Semantic memory",
        "finance_transactions_count": "Finance transactions",
        "german_words_count": "German words",
        "german_grammar_count": "German grammar",
        "documents_count": "Uploaded documents",
        "logs_count": "System logs"
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

    problem_states = {"failed", "timeout", "degraded", "partial"}
    service_keys = [
        ("supabase", "Supabase"),
        ("gmail", "Gmail"),
        ("calendar", "Calendar"),
        ("asana", "Asana"),
        ("openai_embeddings", "OpenAI Embeddings"),
        ("claude", "Claude")
    ]
    attention = [
        f"{label} ({state})"
        for key, label in service_keys
        for state in [report.get(key)]
        if state in problem_states
    ]
    attention.extend(
        f"{data_labels[key]} ({report.get(key)})"
        for key in data_labels
        if report.get(key) in problem_states
    )

    if attention:
        lines.extend([
            "",
            f"{ICON_WARNING} Attention",
            "Check: " + ", ".join(attention)
        ])
    else:
        lines.extend([
            "",
            f"{ICON_CHECK} Summary",
            "No active failures detected."
        ])

    return "\n".join(lines)


def truncate_text(value, max_length=260, preserve_newlines=False):
    value = str(value or "").strip()
    if not preserve_newlines:
        value = value.replace("\n", " ")

    if len(value) <= max_length:
        return value

    return value[: max_length - 3].rstrip() + "..."


def clean_telegram_text(text):
    text = str(text or "")

    # Remove heavy markdown markers that render poorly in Telegram plain text.
    text = text.replace("**", "").replace("__", "")

    lines = text.splitlines()
    cleaned_lines = []
    in_table_block = False
    table_rows = []
    previous_was_rule = False

    for raw_line in lines:
        line = raw_line.strip()

        # Normalize markdown headings.
        if line.startswith("###"):
            line = line.lstrip("#").strip()
        elif line.startswith("##"):
            line = line.lstrip("#").strip()

        # Collapse repeated horizontal rules.
        is_rule = bool(re.fullmatch(r"[-=_]{3,}", line))
        if is_rule:
            if previous_was_rule:
                continue
            cleaned_lines.append("-")
            previous_was_rule = True
            continue
        previous_was_rule = False

        # Collect markdown table rows for conversion.
        if "|" in line and line.count("|") >= 2:
            in_table_block = True
            table_rows.append(line.strip("|").strip())
            continue

        if in_table_block:
            # Flush previous table block as bullets.
            for row in table_rows:
                if re.fullmatch(r"[:\-\s|]+", row):
                    continue
                cells = [c.strip() for c in row.split("|") if c.strip()]
                if cells:
                    cleaned_lines.append("- " + " | ".join(cells))
            in_table_block = False
            table_rows = []

        cleaned_lines.append(line)

    if in_table_block:
        for row in table_rows:
            if re.fullmatch(r"[:\-\s|]+", row):
                continue
            cells = [c.strip() for c in row.split("|") if c.strip()]
            if cells:
                cleaned_lines.append("- " + " | ".join(cells))

    # Keep readable bullets and section spacing, but prevent huge blank blocks.
    normalized = []
    blank_count = 0
    for line in cleaned_lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                normalized.append("")
            continue
        blank_count = 0
        normalized.append(line)

    return "\n".join(normalized).strip()


def split_telegram_chunks(text, max_length=3500):
    text = str(text or "")
    if len(text) <= max_length:
        return [text]

    words = text.split()
    chunks = []
    current = ""

    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_length:
            current = candidate
        else:
            if current:
                chunks.append(current)
                current = word
            else:
                # Very long single token fallback.
                chunks.append(word[:max_length])
                remainder = word[max_length:]
                current = remainder

    if current:
        chunks.append(current)

    return chunks


async def send_clean_reply(message, text, reply_markup=None):
    cleaned = clean_telegram_text(text)
    chunks = split_telegram_chunks(cleaned, max_length=3500)
    sent_message = None

    for index, chunk in enumerate(chunks):
        if index == len(chunks) - 1 and reply_markup is not None:
            sent_message = await message.reply_text(chunk, reply_markup=reply_markup)
        else:
            sent_message = await message.reply_text(chunk)

    return sent_message


def format_log_time(value):
    if not value:
        return "Unknown time"

    try:
        clean_value = value.replace("Z", "+00:00")
        logged_at = datetime.fromisoformat(clean_value)
        return logged_at.strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        logging.warning("Failed to format log time '%s': %s", value, e)
        return str(value)


def parse_log_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception as e:
        logging.warning("Failed to parse datetime '%s': %s", value, e)
        return None


def get_log_sort_timestamp(row):
    logged_at = parse_log_datetime(row.get("created_at"))

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
    timestamp = format_log_time(row.get("created_at"))
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
    latest_time = format_log_time(rows[0].get("created_at"))
    oldest_time = format_log_time(rows[-1].get("created_at"))

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
            f"?select=created_at,module,error_message"
            f"&order=created_at.desc"
            f"&limit={limit}"
        )
        result = requests.get(url, headers=supabase_headers, timeout=10)

        if result.status_code != 200:
            return (
                f"{ICON_CLIPBOARD} Recent System Errors\n\n"
                f"Could not fetch logs. Supabase returned {result.status_code}."
            )

        return format_system_errors(result.json())
    except Exception as e:
        log_system_error("get_recent_system_errors", e)
        return f"{ICON_CLIPBOARD} Recent System Errors\n\nCould not fetch logs: {str(e)}"


def get_render_deploy_status():
    """Fetches the latest deployment status from Render API."""
    if not RENDER_API_KEY or not RENDER_SERVICE_ID:
        return "Render API credentials missing."

    try:
        url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/deploys"
        headers = {
            "Authorization": f"Bearer {RENDER_API_KEY}",
            "Accept": "application/json"
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            log_system_error("render_status", f"Render API returned {response.status_code}")
            return f"{ICON_RED} Could not fetch Render status."

        deploys = response.json()
        if not deploys:
            return f"{ICON_WHITE} No deployments found."

        # Render returns a list of objects, each containing a 'deploy' key
        latest = deploys[0]["deploy"]
        raw_status = latest["status"]

        # Map to requested labels
        if raw_status == "live":
            status_label, icon = "live", ICON_GREEN
        elif raw_status in ["build_failed", "pre_deploy_failed", "canceled"]:
            status_label, icon = "failed", ICON_RED
        elif raw_status in ["build_in_progress", "pre_deploy_in_progress", "created"]:
            status_label, icon = "building", ICON_YELLOW
        elif raw_status == "update_in_progress":
            status_label, icon = "deploying", ICON_YELLOW
        else:
            status_label, icon = raw_status, ICON_WHITE

        def fmt_time(iso_str):
            if not iso_str: return "N/A"
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return dt.astimezone(get_timezone()).strftime("%Y-%m-%d %H:%M")

        commit_msg = latest.get("commit", {}).get("message", "No message")
        finished_at = latest.get("finishedAt") or latest.get("updatedAt")

        lines = [
            f"{ICON_COMPASS} Render Deployment Status",
            "",
            f"Deploy ID: `{latest['id']}`",
            f"Status: {icon} {status_label.capitalize()}",
            f"Created: {fmt_time(latest['createdAt'])}",
            f"Finished: {fmt_time(finished_at)}",
            f"Commit: {truncate_text(commit_msg, 60)}"
        ]
        return "\n".join(lines)
    except Exception as e:
        log_system_error("render_status", e)
        return f"{ICON_RED} Render status error: {str(e)}"


def get_github_latest_commit():
    """Fetches the latest commit details from the GitHub repository."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return "GitHub credentials missing."

    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits?sha=main&per_page=1"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            log_system_error("github_status", f"GitHub API returned {response.status_code}")
            return f"{ICON_RED} Could not fetch GitHub status."

        commits = response.json()
        if not commits:
            return f"{ICON_WHITE} No commits found."

        commit_obj = commits[0]
        sha_short = commit_obj["sha"][:7]
        commit_info = commit_obj["commit"]
        author_name = commit_info["author"]["name"]
        message = commit_info["message"]
        
        dt = datetime.strptime(commit_info["author"]["date"], "%Y-%m-%dT%H:%M:%SZ")
        dt = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(get_timezone())
        timestamp = dt.strftime("%Y-%m-%d %H:%M")

        lines = [
            f"{ICON_MAGNIFIER} GitHub Latest Push",
            "",
            f"Message: {truncate_text(message, 100)}",
            f"Author: {author_name}",
            f"SHA: `{sha_short}`",
            f"Time: {timestamp}"
        ]
        return "\n".join(lines)
    except Exception as e:
        log_system_error("github_status", e)
        return f"{ICON_RED} GitHub status error: {str(e)}"


def check_table_count(table_name):
    try:
        url = f"{SUPABASE_URL}/rest/v1/{table_name}?select=id"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Prefer": "count=exact",
            "Range": "0-0",
        }
        res = requests.get(url, headers=headers, timeout=5)

        if res.status_code not in (200, 206):
            log_system_error(
                f"health_check.{table_name}",
                f"{res.status_code}: {res.text}"
            )
            return "failed"

        # HTTP success = table is reachable. Count parsing is a best-effort extra.
        content_range = res.headers.get("content-range", "")
        if "/" in content_range:
            total = content_range.split("/")[-1]
            if total.isdigit():
                return int(total)
        return "count_unavailable"

    except requests.exceptions.Timeout:
        return "timeout"
    except Exception as e:
        log_system_error(f"health_check.{table_name}", e)
        return "failed"


def get_system_status():
    report = {}
    report["current_time"] = get_current_datetime()

    # Comprehensive table check matching schema.sql
    checks = {
        "events_log_count": "events_log",
        "personal_memory_count": "personal_memory",
        "semantic_memory_count": "semantic_memory",
        "finance_transactions_count": "finance_transactions",
        "german_words_count": "german_words",
        "german_grammar_count": "german_grammar",
        "documents_count": "uploaded_documents",
        "logs_count": "system_logs"
    }

    # 1. Supabase Connectivity and Table Health
    supabase_overall_status = "operational"
    try:
        # Test a core table (system_logs) for initial Supabase connectivity.
        # If this fails we skip per-table probes to avoid amplifying doomed
        # log writes during an outage.
        initial_db_check = check_table_count("system_logs")
        if initial_db_check in ("failed", "timeout"):
            report["supabase"] = initial_db_check
            for key in checks:
                report[key] = "not_checked"
        else:
            for key, table in checks.items():
                result = check_table_count(table)
                report[key] = result
                # A reachable table with an unparseable count must NOT poison
                # the rollup — count_unavailable and ints are both healthy.
                if result == "failed":
                    supabase_overall_status = "degraded"
                elif result == "timeout" and supabase_overall_status != "degraded":
                    supabase_overall_status = "degraded"
                elif result == "partial" and supabase_overall_status == "operational":
                    supabase_overall_status = "partial"
            report["supabase"] = supabase_overall_status
    except Exception as e:
        log_system_error("get_system_status.supabase_critical", e)
        report["supabase"] = "failed"
        for key in checks:
            report[key] = "not_checked"

    # 2. External Service Layer (Gmail, Calendar, Asana)
    # Use structured lightweight probes — never sniff formatted summary text.
    try:
        creds = get_google_credentials()
        if not creds:
            report["gmail"] = "disabled"
        else:
            build("gmail", "v1", credentials=creds).users().getProfile(userId="me").execute()
            report["gmail"] = "operational"
    except requests.exceptions.Timeout:
        report["gmail"] = "timeout"
    except Exception as e:
        log_system_error("get_system_status.gmail", e)
        report["gmail"] = "timeout" if "timeout" in str(e).lower() else "failed"

    try:
        creds = get_google_credentials()
        if not creds:
            report["calendar"] = "disabled"
        else:
            build("calendar", "v3", credentials=creds).calendarList().list(maxResults=1).execute()
            report["calendar"] = "operational"
    except requests.exceptions.Timeout:
        report["calendar"] = "timeout"
    except Exception as e:
        log_system_error("get_system_status.calendar", e)
        report["calendar"] = "timeout" if "timeout" in str(e).lower() else "failed"

    try:
        if not ASANA_TOKEN:
            report["asana"] = "disabled"
        else:
            report["asana"] = "operational" if get_asana_user() else "failed"
    except requests.exceptions.Timeout:
        report["asana"] = "timeout"
    except Exception as e:
        log_system_error("get_system_status.asana", e)
        report["asana"] = "failed"

    # 3. Intelligence Layer (OpenAI, Claude)
    try:
        if openai_client:
            openai_client.embeddings.create(model="text-embedding-3-small", input="health_check", timeout=5.0)
            report["openai_embeddings"] = "operational"
        else:
            report["openai_embeddings"] = "disabled"
    except Exception as e:
        log_system_error("get_system_status.openai", e)
        report["openai_embeddings"] = "timeout" if "timeout" in str(e).lower() else "failed"

    try:
        client.messages.create(model=CLAUDE_MODEL, max_tokens=10, messages=[{"role": "user", "content": "health_check"}], timeout=5.0)
        report["claude"] = "operational"
    except Exception as e:
        log_system_error("get_system_status.claude", e)
        report["claude"] = "timeout" if "timeout" in str(e).lower() else "failed"

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
            model=CLAUDE_MODEL,
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
        ["Deploy Status", "Last Push"],
        ["Daily Briefing"],
        [FINANCE_BTN_SETUP, "Finance Report"],
        ["Overspending"],
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


def get_finance_setup_menu():
    keyboard = [
        [FINANCE_BTN_SET_SALARY, FINANCE_BTN_SET_RENT],
        [FINANCE_BTN_ADD_EMI, FINANCE_BTN_ADD_BILL],
        [FINANCE_BTN_ADD_GOAL, FINANCE_BTN_ADD_PLAN],
        [FINANCE_BTN_VIEW_PROFILE],
        [FINANCE_BTN_EDIT_DELETE],
        ["Back"]
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
            model=CLAUDE_MODEL,
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

def is_explicit_document_context_request(text):
    doc_words = ("document", "documents", "pdf", "pdfs", "file", "files", "uploaded")
    return has_explicit_data_action(text) and any(word in text for word in doc_words)


def get_documents_summary():
    try:
        docs = get_uploaded_documents(limit=10)
        if not docs:
            return "No documents found."
        return json.dumps(docs, indent=2)
    except Exception as e:
        log_system_error("get_documents_summary", e)
        return "Failed to fetch document summary."


LIVE_CONTEXT_PROVIDERS = [
    (lambda text: any(k in text for k in FINANCE_CONTEXT_KEYWORDS), "Finance", get_finance_summary),
    (lambda text: is_explicit_gmail_context_request(text), "Gmail", get_gmail_summary),
    (lambda text: is_explicit_calendar_context_request(text), "Calendar", get_calendar_summary),
    (lambda text: is_explicit_asana_context_request(text), "Asana", get_asana_tasks),
    (lambda text: is_explicit_document_context_request(text), "Uploaded Documents", get_documents_summary)
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


def get_recent_failures(limit=3):
    """Fetches recent failed quiz attempts for spaced repetition logic."""
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/events_log"
            f"?select=assistant_response"
            f"&assistant_response=ilike.*Not%20quite.*"
            f"&order=created_at.desc"
            f"&limit={limit}"
        )
        result = requests.get(url, headers=supabase_headers, timeout=10)
        if result.status_code != 200:
            return []

        failures = []
        for row in result.json():
            resp = row.get("assistant_response", "")
            # Extracts word from "Not quite. <word> means: ..."
            match = re.search(r"Not quite\. (.*?) means:", resp)
            if match:
                failures.append(match.group(1))
        return failures
    except Exception as e:
        log_system_error("get_recent_failures", e)
        return []


def generate_a1_practice():
    """Generates a dynamic, adaptive Goethe A1 German practice session."""
    try:
        # Gather adaptive context
        recent_words = get_random_german_words(limit=5)
        weak_areas = search_semantic_memory("German grammar mistakes corrections")
        recent_failures = get_recent_failures(limit=3)

        # Randomize session structure
        all_components = [
            "vocabulary", "grammar", "speaking prompt", "listening simulation",
            "sentence building", "article practice (der/die/das)", "verb conjugation",
            "exam mini-dialogue", "schreiben practice", "hören-style multiple choice"
        ]
        selected_components = random.sample(all_components, 4)
        scenarios = ["restaurant", "train station", "doctor", "appointments", "shopping", "introducing yourself"]

        prompt = (
            f"Scenario Context: {random.choice(scenarios)}\n"
            f"User Context:\n- Recent vocab: {compact_json(recent_words)}\n"
            f"- Spaced Repetition (prioritize): {', '.join(recent_failures)}\n"
            f"- Recurring weak points: {compact_json(weak_areas)}\n\n"
            f"Tasks to include: {', '.join(selected_components)}\n\n"
            "Instructions: Act as an adaptive A1 German tutor. Create a high-quality, practical exercise. "
            "Include one 'Say this aloud' voice-friendly prompt. Use bold and fixed-width formatting. Under 500 tokens."
        )

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=550,
            system="You are an adaptive Goethe A1 German Tutor. Focus on short, high-quality, interactive sessions.",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        log_system_error("generate_a1_practice", e)
        return f"A1 practice failed: {str(e)}"


def correct_german_text(text):
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
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
    clear_finance_states(context)
    clear_german_word_state(context)
    clear_german_grammar_state(context)
    context.user_data.pop(WAITING_FOR_GERMAN_CORRECTION, None)
    clear_german_quiz_state(context)


async def handle_german_word_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
    try:
        if context.user_data.get(WAITING_FOR_GERMAN_WORD):
            context.user_data.pop(WAITING_FOR_GERMAN_WORD, None)
            context.user_data[WAITING_FOR_GERMAN_MEANING] = True
            context.user_data[GERMAN_WORD_STATE] = {"word": user_message.strip()}
            reply = "What does it mean in English?"
            await send_clean_reply(update.message,reply)
            if is_voice_input and voice_replies_enabled:
                await send_voice_reply(update, reply)
            return True

        if context.user_data.get(WAITING_FOR_GERMAN_MEANING):
            context.user_data.pop(WAITING_FOR_GERMAN_MEANING, None)
            context.user_data[WAITING_FOR_GERMAN_EXAMPLE] = True
            state = context.user_data.setdefault(GERMAN_WORD_STATE, {})
            state["meaning"] = user_message.strip()
            reply = "Add one example sentence."
            await send_clean_reply(update.message,reply)
            if is_voice_input and voice_replies_enabled:
                await send_voice_reply(update, reply)
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
            await send_clean_reply(update.message,reply, reply_markup=get_german_a1_menu())
            if is_voice_input and voice_replies_enabled:
                await send_voice_reply(update, reply)
            return True

        return False
    except Exception as e:
        log_system_error("handle_german_word_flow", e)
        clear_german_word_state(context)
        await send_clean_reply(update.message,"German word flow failed.", reply_markup=get_german_a1_menu())
        return True


async def handle_german_grammar_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
    try:
        if context.user_data.get(WAITING_FOR_GRAMMAR_TOPIC):
            context.user_data.pop(WAITING_FOR_GRAMMAR_TOPIC, None)
            context.user_data[WAITING_FOR_GRAMMAR_NOTE] = True
            context.user_data[GERMAN_GRAMMAR_STATE] = {"topic": user_message.strip()}
            reply = "What note or explanation should I save?"
            await send_clean_reply(update.message,reply)
            if is_voice_input and voice_replies_enabled:
                await send_voice_reply(update, reply)
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
            await send_clean_reply(update.message,reply, reply_markup=get_german_a1_menu())
            if is_voice_input and voice_replies_enabled:
                await send_voice_reply(update, reply)
            return True

        return False
    except Exception as e:
        log_system_error("handle_german_grammar_flow", e)
        clear_german_grammar_state(context)
        await send_clean_reply(update.message,"Grammar rule flow failed.", reply_markup=get_german_a1_menu())
        return True


async def handle_german_correction_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
    if not context.user_data.get(WAITING_FOR_GERMAN_CORRECTION):
        return False

    try:
        context.user_data.pop(WAITING_FOR_GERMAN_CORRECTION, None)
        reply = correct_german_text(user_message)
        save_to_supabase("Correct My German", reply)
        await send_clean_reply(update.message, reply, reply_markup=get_read_aloud_markup())
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return True
    except Exception as e:
        log_system_error("handle_german_correction_flow", e)
        context.user_data.pop(WAITING_FOR_GERMAN_CORRECTION, None)
        await send_clean_reply(update.message,"German correction failed.", reply_markup=get_german_a1_menu())
        return True


async def handle_german_quiz_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
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
        await send_clean_reply(update.message,reply, reply_markup=get_german_a1_menu())
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return True
    except Exception as e:
        log_system_error("handle_german_quiz_flow", e)
        clear_german_quiz_state(context)
        await send_clean_reply(update.message,"German quiz failed.", reply_markup=get_german_a1_menu())
        return True


def clear_email_draft_state(context):
    context.user_data.pop(WAITING_FOR_EMAIL_TO, None)
    context.user_data.pop(WAITING_FOR_EMAIL_SUBJECT, None)
    context.user_data.pop(WAITING_FOR_EMAIL_BODY, None)
    context.user_data.pop(EMAIL_DRAFT_STATE, None)


async def handle_email_draft_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
    if context.user_data.get(WAITING_FOR_EMAIL_TO):
        context.user_data.pop(WAITING_FOR_EMAIL_TO, None)
        context.user_data[WAITING_FOR_EMAIL_SUBJECT] = True
        context.user_data[EMAIL_DRAFT_STATE] = {"to": user_message.strip()}
        reply = "What subject should I use?"
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return True

    if context.user_data.get(WAITING_FOR_EMAIL_SUBJECT):
        context.user_data.pop(WAITING_FOR_EMAIL_SUBJECT, None)
        context.user_data[WAITING_FOR_EMAIL_BODY] = True
        draft = context.user_data.setdefault(EMAIL_DRAFT_STATE, {})
        draft["subject"] = user_message.strip()
        reply = "What should the email say?"
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
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
        await send_clean_reply(update.message,reply, reply_markup=get_main_menu())
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return True

    return False


def get_finance_confirmation_menu():
    return ReplyKeyboardMarkup(
        [[FINANCE_CONFIRM_SAVE, FINANCE_CONFIRM_EDIT, FINANCE_CONFIRM_CANCEL]],
        resize_keyboard=True,
        one_time_keyboard=False
    )


def execute_finance_pending_action(pending):
    action = pending.get("action")
    payload = pending.get("payload", {})

    if action == "save_profile_value":
        ok = save_financial_profile_values(payload)
        return ok, "Finance profile updated." if ok else "Failed to save finance profile value."

    if action == "save_commitment":
        ok = insert_financial_commitment(payload)
        return ok, "Commitment saved." if ok else "Failed to save commitment."

    if action == "save_goal":
        ok = insert_financial_goal(payload)
        return ok, "Savings goal saved." if ok else "Failed to save savings goal."

    if action == "save_plan":
        ok = insert_financial_plan(payload)
        return ok, "Future plan saved." if ok else "Failed to save future plan."

    if action == "edit_item_amount":
        ok = update_finance_item_amount(payload["item"], payload["amount"])
        return ok, "Finance item updated." if ok else "Failed to update finance item."

    if action == "delete_item":
        ok = delete_finance_item(payload["item"])
        return ok, "Finance item deleted." if ok else "Failed to delete finance item."

    return False, "Unsupported finance action."


async def handle_finance_foundation_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
    text = user_message.lower().strip()

    if text in FINANCE_MENU_COMMANDS or text == FINANCE_BTN_SETUP.lower():
        clear_finance_states(context)
        await send_clean_reply(
            update.message,
            "Finance Setup Menu",
            reply_markup=get_finance_setup_menu()
        )
        return True

    if text == FINANCE_BTN_VIEW_PROFILE.lower() or is_finance_profile_question(text):
        summary = format_finance_profile_summary()
        await send_clean_reply(update.message, summary, reply_markup=get_finance_setup_menu())
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, summary)
        return True

    pending = context.user_data.get(FINANCE_PENDING_CONFIRM)
    if pending:
        if text == FINANCE_CONFIRM_SAVE.lower():
            success, message = execute_finance_pending_action(pending)
            clear_finance_states(context)
            reply = f"Confirmed: {message}" if success else f"I could not confirm save.\n{message}"
            await send_clean_reply(update.message, reply, reply_markup=get_finance_setup_menu())
            if is_voice_input and voice_replies_enabled:
                await send_voice_reply(update, reply)
            return True

        if text == FINANCE_CONFIRM_EDIT.lower():
            edit_state = pending.get("edit_state")
            edit_prompt = pending.get("edit_prompt") or "Please edit and send again."
            context.user_data.pop(FINANCE_PENDING_CONFIRM, None)
            if edit_state:
                context.user_data[FINANCE_FLOW_STATE] = edit_state
                await send_clean_reply(update.message, edit_prompt)
                return True
            await send_clean_reply(update.message, "Edit cancelled. Start again from Finance Setup.", reply_markup=get_finance_setup_menu())
            return True

        if text == FINANCE_CONFIRM_CANCEL.lower():
            clear_finance_states(context)
            await send_clean_reply(update.message, "Cancelled. No finance data was changed.", reply_markup=get_finance_setup_menu())
            return True

        await send_clean_reply(
            update.message,
            "Please choose ✅ Save, ✏️ Edit, or ❌ Cancel.",
            reply_markup=get_finance_confirmation_menu()
        )
        return True

    edit_state = context.user_data.get(FINANCE_EDIT_DELETE_STATE)
    if text == FINANCE_BTN_EDIT_DELETE.lower() and not edit_state:
        items, listing = build_finance_item_catalog()
        context.user_data[FINANCE_EDIT_DELETE_STATE] = {"step": "select_item", "items": items}
        await send_clean_reply(update.message, listing + "\n\nReply with item code (example: SALARY, C1, G1, P1).", reply_markup=get_finance_setup_menu())
        return True

    if edit_state:
        if edit_state.get("step") == "select_item":
            code = user_message.strip().upper()
            item = edit_state.get("items", {}).get(code)
            if not item:
                await send_clean_reply(update.message, "Invalid code. Please choose from the list.", reply_markup=get_finance_setup_menu())
                return True
            edit_state["selected_item"] = item
            edit_state["selected_code"] = code
            edit_state["step"] = "choose_action"
            action_menu = ReplyKeyboardMarkup(
                [[FINANCE_CONFIRM_EDIT, FINANCE_ACTION_DELETE, FINANCE_CONFIRM_CANCEL]],
                resize_keyboard=True,
                one_time_keyboard=False
            )
            await send_clean_reply(update.message, f"Selected {code}. Choose Edit or Delete.", reply_markup=action_menu)
            return True

        if edit_state.get("step") == "choose_action":
            if text == FINANCE_CONFIRM_CANCEL.lower():
                clear_finance_states(context)
                await send_clean_reply(update.message, "Cancelled. No finance data was changed.", reply_markup=get_finance_setup_menu())
                return True
            if text == FINANCE_ACTION_DELETE.lower():
                selected = edit_state["selected_item"]
                summary = f"I understood: Delete finance item {edit_state.get('selected_code')}. Save?"
                set_finance_pending_confirmation(
                    context,
                    action="delete_item",
                    payload={"item": selected},
                    summary=summary
                )
                await send_clean_reply(update.message, summary, reply_markup=get_finance_confirmation_menu())
                return True
            if text == FINANCE_CONFIRM_EDIT.lower():
                edit_state["step"] = "new_amount"
                await send_clean_reply(update.message, "Send the new amount (EUR).")
                return True
            await send_clean_reply(update.message, "Please choose Edit, Delete, or Cancel.")
            return True

        if edit_state.get("step") == "new_amount":
            amount = parse_finance_amount(user_message)
            if amount is None:
                await send_clean_reply(update.message, "Please enter a valid positive amount, e.g. 1200.")
                return True
            selected = edit_state["selected_item"]
            summary = f"I understood: Update {edit_state.get('selected_code')} to {format_eur(amount)}. Save?"
            set_finance_pending_confirmation(
                context,
                action="edit_item_amount",
                payload={"item": selected, "amount": amount},
                summary=summary
            )
            await send_clean_reply(update.message, summary, reply_markup=get_finance_confirmation_menu())
            return True

    if text == FINANCE_BTN_SET_SALARY.lower():
        context.user_data[FINANCE_FLOW_STATE] = {"kind": "set_salary", "step": "amount"}
        await send_clean_reply(update.message, "Enter monthly salary amount in EUR.")
        return True

    if text == FINANCE_BTN_SET_RENT.lower():
        context.user_data[FINANCE_FLOW_STATE] = {"kind": "set_rent", "step": "amount"}
        await send_clean_reply(update.message, "Enter monthly rent amount in EUR.")
        return True

    if text == FINANCE_BTN_ADD_EMI.lower():
        context.user_data[FINANCE_FLOW_STATE] = {"kind": "add_emi", "step": "name", "data": {}}
        await send_clean_reply(update.message, "Enter EMI/loan name (example: Car loan).")
        return True

    if text == FINANCE_BTN_ADD_BILL.lower():
        context.user_data[FINANCE_FLOW_STATE] = {"kind": "add_bill", "step": "name", "data": {}}
        await send_clean_reply(update.message, "Enter recurring bill name (example: Internet).")
        return True

    if text == FINANCE_BTN_ADD_GOAL.lower():
        context.user_data[FINANCE_FLOW_STATE] = {"kind": "add_goal", "step": "title", "data": {}}
        await send_clean_reply(update.message, "Enter savings goal title (example: Emergency fund).")
        return True

    if text == FINANCE_BTN_ADD_PLAN.lower():
        context.user_data[FINANCE_FLOW_STATE] = {"kind": "add_plan", "step": "details", "data": {}}
        await send_clean_reply(update.message, "Describe the future plan (example: Buy laptop €1200 in August).")
        return True

    flow = context.user_data.get(FINANCE_FLOW_STATE)
    if not flow:
        return False

    kind = flow.get("kind")
    step = flow.get("step")
    data = flow.setdefault("data", {})

    if kind in {"set_salary", "set_rent"} and step == "amount":
        amount = parse_finance_amount(user_message)
        if amount is None:
            await send_clean_reply(update.message, "Please enter a valid positive amount, e.g. 1200.")
            return True
        field = "monthly_salary" if kind == "set_salary" else "monthly_rent"
        label = "Monthly Salary" if kind == "set_salary" else "Rent"
        summary = f"I understood: {label} = {format_eur(amount)} monthly. Save?"
        edit_state = {"kind": kind, "step": "amount"}
        set_finance_pending_confirmation(
            context,
            action="save_profile_value",
            payload={field: amount},
            summary=summary,
            edit_state=edit_state,
            edit_prompt=f"Please re-enter {label.lower()} amount."
        )
        await send_clean_reply(update.message, summary, reply_markup=get_finance_confirmation_menu())
        return True

    if kind in {"add_emi", "add_bill"}:
        if step == "name":
            data["name"] = user_message.strip()
            flow["step"] = "amount"
            await send_clean_reply(update.message, "Enter monthly amount in EUR.")
            return True
        if step == "amount":
            amount = parse_finance_amount(user_message)
            if amount is None:
                await send_clean_reply(update.message, "Please enter a valid amount, e.g. 350.")
                return True
            data["amount"] = amount
            flow["step"] = "due_day"
            await send_clean_reply(update.message, "Enter due day in month (1-31), or type skip.")
            return True
        if step == "due_day":
            due_day = None
            if text != "skip":
                match = re.search(r"\b([1-9]|[12][0-9]|3[01])\b", text)
                if not match:
                    await send_clean_reply(update.message, "Please enter a valid day 1-31, or type skip.")
                    return True
                due_day = int(match.group(1))
            commitment_type = "emi_loan" if kind == "add_emi" else "recurring_bill"
            summary = (
                f"I understood: {data.get('name')} = {format_eur(data.get('amount'))} monthly"
                + (f", due day {due_day}" if due_day else "")
                + ". Save?"
            )
            payload = {
                "commitment_type": commitment_type,
                "name": data.get("name"),
                "amount": data.get("amount"),
                "currency": "EUR",
                "frequency": "monthly",
                "due_day": due_day
            }
            set_finance_pending_confirmation(
                context,
                action="save_commitment",
                payload=payload,
                summary=summary,
                edit_state={"kind": kind, "step": "name", "data": {}},
                edit_prompt="Please re-enter the commitment details."
            )
            await send_clean_reply(update.message, summary, reply_markup=get_finance_confirmation_menu())
            return True

    if kind == "add_goal":
        if step == "title":
            data["title"] = user_message.strip()
            flow["step"] = "target_amount"
            await send_clean_reply(update.message, "Enter target amount in EUR.")
            return True
        if step == "target_amount":
            amount = parse_finance_amount(user_message)
            if amount is None:
                await send_clean_reply(update.message, "Please enter a valid amount, e.g. 5000.")
                return True
            data["target_amount"] = amount
            flow["step"] = "target_date"
            await send_clean_reply(update.message, "Enter target date (YYYY-MM-DD) or type skip.")
            return True
        if step == "target_date":
            target_date = None
            if text != "skip":
                target_date = user_message.strip()
            summary = f"I understood: Savings goal '{data.get('title')}' target {format_eur(data.get('target_amount'))}"
            if target_date:
                summary += f" by {target_date}"
            summary += ". Save?"
            payload = {
                "title": data.get("title"),
                "target_amount": data.get("target_amount"),
                "target_date": target_date,
                "currency": "EUR"
            }
            set_finance_pending_confirmation(
                context,
                action="save_goal",
                payload=payload,
                summary=summary,
                edit_state={"kind": kind, "step": "title", "data": {}},
                edit_prompt="Please re-enter savings goal details."
            )
            await send_clean_reply(update.message, summary, reply_markup=get_finance_confirmation_menu())
            return True

    if kind == "add_plan":
        if step == "details":
            parsed = parse_future_plan_text(user_message)
            data.update(parsed)
            if not data.get("planned_amount"):
                flow["step"] = "planned_amount"
                await send_clean_reply(update.message, "Enter planned amount in EUR.")
                return True
            if not data.get("planned_month"):
                flow["step"] = "planned_month"
                await send_clean_reply(update.message, "When is this planned? (example: June, next month, 2026-08)")
                return True
            summary = (
                f"I understood: Future plan '{data.get('title')}' "
                f"for {format_eur(data.get('planned_amount'))} in {data.get('planned_month')}. Save?"
            )
            payload = {
                "plan_type": data.get("plan_type"),
                "title": data.get("title"),
                "planned_amount": data.get("planned_amount"),
                "planned_month": data.get("planned_month"),
                "currency": "EUR"
            }
            set_finance_pending_confirmation(
                context,
                action="save_plan",
                payload=payload,
                summary=summary,
                edit_state={"kind": kind, "step": "details", "data": {}},
                edit_prompt="Please re-enter the future plan details."
            )
            await send_clean_reply(update.message, summary, reply_markup=get_finance_confirmation_menu())
            return True
        if step == "planned_amount":
            amount = parse_finance_amount(user_message)
            if amount is None:
                await send_clean_reply(update.message, "Please enter a valid amount, e.g. 1200.")
                return True
            data["planned_amount"] = amount
            flow["step"] = "planned_month"
            await send_clean_reply(update.message, "When is this planned? (example: June, next month, 2026-08)")
            return True
        if step == "planned_month":
            month_value = parse_plan_month(user_message)
            if not month_value:
                await send_clean_reply(update.message, "Please provide month like June, next month, or 2026-08.")
                return True
            data["planned_month"] = month_value
            summary = (
                f"I understood: Future plan '{data.get('title')}' "
                f"for {format_eur(data.get('planned_amount'))} in {data.get('planned_month')}. Save?"
            )
            payload = {
                "plan_type": data.get("plan_type", "planned_expense"),
                "title": data.get("title"),
                "planned_amount": data.get("planned_amount"),
                "planned_month": data.get("planned_month"),
                "currency": "EUR"
            }
            set_finance_pending_confirmation(
                context,
                action="save_plan",
                payload=payload,
                summary=summary,
                edit_state={"kind": kind, "step": "details", "data": {}},
                edit_prompt="Please re-enter the future plan details."
            )
            await send_clean_reply(update.message, summary, reply_markup=get_finance_confirmation_menu())
            return True

    return False


def get_finance_transactions(select_columns):
    try:
        url = f"{SUPABASE_URL}/rest/v1/finance_transactions?select={select_columns}"
        result = requests.get(url, headers=supabase_headers, timeout=10)
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




def get_unsupported_action_reply():
    """Returns a standard message when an unsupported external action is requested."""
    return (
        "I did not complete that external action.\n"
        "Only these write actions are currently connected to real APIs: "
        "create calendar events, create Gmail drafts, create Asana tasks, "
        "save memories, and log finance transactions."
    )
def build_live_context(text):
    context_parts = []

    for should_fetch, title, provider in LIVE_CONTEXT_PROVIDERS:
        if should_fetch(text):
            if provider == get_gmail_summary:
                context_parts.append(f"\n\n{title}:\n{provider(text)}")
            else:
                context_parts.append(f"\n\n{title}:\n{provider()}")

    return "".join(context_parts)


async def transcribe_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribes a Telegram voice message using OpenAI Whisper."""
    if not openai_client:
        log_system_error("voice_transcription", "OpenAI client not initialized")
        return None

    temp_path = None
    try:
        voice_file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tf:
            temp_path = tf.name
        await voice_file.download_to_drive(temp_path)

        with open(temp_path, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return transcript.text
    except Exception as e:
        log_system_error("voice_transcription", e)
        return None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


async def send_voice_reply(update: Update, text: str, max_length: int = 700):
    """Converts text to speech and sends it as a Telegram voice message if allowed."""
    if not openai_client:
        return

    # Cost safety: Do not use TTS for long replies
    if len(text) > max_length:
        return

    temp_path = None
    try:
        # Clean markdown/formatting lightly before speech
        clean_text = re.sub(r"[*_`#]", "", text)

        response = openai_client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=clean_text
        )

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
            temp_path = tf.name
        response.stream_to_file(temp_path)

        target_message = update.effective_message
        if target_message is None:
            return
        with open(temp_path, "rb") as voice_fh:
            try:
                await target_message.reply_voice(voice=voice_fh)
            except TimedOut as e:
                log_system_error("voice_tts_timeout", e)
    except Exception as e:
        log_system_error("voice_tts", e)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


READ_ALOUD_MAX_CHARS = 1200
READ_ALOUD_USAGE_HINT = "Reply to a text message with /read or 🔊 and I'll read it aloud."
READ_ALOUD_CALLBACK = "tts_read"


def get_read_aloud_markup():
    """Inline keyboard with a single 🔊 Read Aloud button for attaching to bot replies."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔊 Read Aloud", callback_data=READ_ALOUD_CALLBACK)
    ]])


async def handle_tts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler for the inline 🔊 Read Aloud button."""
    query = update.callback_query
    if not query:
        return
    if update.effective_user.id != ALLOWED_USER_ID:
        try:
            await query.answer()
        except TimedOut as e:
            log_system_error("handle_tts_callback", e)
        return

    source_text = ""
    if query.message:
        source_text = (query.message.text or query.message.caption or "").strip()

    if not source_text:
        try:
            await query.answer(text="No text to read aloud.", show_alert=True)
        except TimedOut as e:
            log_system_error("handle_tts_callback", e)
        return

    if len(source_text) > READ_ALOUD_MAX_CHARS:
        try:
            await query.answer(
                text=f"Too long to read aloud (limit {READ_ALOUD_MAX_CHARS} chars).",
                show_alert=True
            )
        except TimedOut as e:
            log_system_error("handle_tts_callback", e)
        return

    try:
        await query.answer()
    except TimedOut as e:
        log_system_error("handle_tts_callback", e)

    await send_voice_reply(update, source_text, max_length=READ_ALOUD_MAX_CHARS)


async def handle_read_aloud(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Read the replied-to message aloud via TTS. Manual, on-demand — bypasses the voice-replies toggle."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return
    if not update.message:
        return

    replied = update.message.reply_to_message
    source_text = ""
    if replied:
        source_text = (replied.text or replied.caption or "").strip()

    if not source_text:
        await send_clean_reply(update.message, READ_ALOUD_USAGE_HINT)
        return

    if len(source_text) > READ_ALOUD_MAX_CHARS:
        await send_clean_reply(
            update.message,
            f"That message is too long to read aloud ({len(source_text)} chars, limit {READ_ALOUD_MAX_CHARS})."
        )
        return

    await send_voice_reply(update, source_text, max_length=READ_ALOUD_MAX_CHARS)


def compact_json(data):
    return json.dumps(data, separators=(",", ":"))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, overridden_text=None, is_voice_input=False, is_internal=False):
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    user_message = overridden_text if overridden_text is not None else (update.message.text if update.message else None)
    voice_replies_enabled = context.user_data.get("voice_replies_enabled", False)

    # Requirement: Skip voice reply generation for internal messages
    if is_internal:
        voice_replies_enabled = False

    if not user_message:
        return

    text = user_message.lower().strip()

    if text == "🔊":
        await handle_read_aloud(update, context)
        return

    if text == "voice replies on":
        context.user_data["voice_replies_enabled"] = True
        await send_clean_reply(update.message,"Voice replies are now ON.")
        return
    if text == "voice replies off":
        context.user_data["voice_replies_enabled"] = False
        await send_clean_reply(update.message,"Voice replies are now OFF.")
        return

    if text in BACK_COMMANDS:
        clear_interaction_states(context)
        await send_clean_reply(update.message,"Back to main menu.", reply_markup=get_main_menu())
        return

    if context.user_data.get(WAITING_FOR_CALENDAR_EVENT):
        context.user_data.pop(WAITING_FOR_CALENDAR_EVENT, None)
        reply = create_calendar_event_reply(user_message)
        save_to_supabase(user_message, reply)
        await send_clean_reply(update.message,reply, reply_markup=get_main_menu())
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    if await handle_email_draft_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
        return

    if await handle_german_word_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
        return

    if await handle_german_grammar_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
        return

    if await handle_german_correction_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
        return

    if await handle_german_quiz_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
        return

    if await handle_finance_foundation_flow(update, context, user_message, is_voice_input, voice_replies_enabled):
        return

    # Simple menu/help
    if text in MENU_COMMANDS:
        await send_clean_reply(update.message,
            "Choose an action:",
            reply_markup=get_main_menu()
        )
        return

    if text in GERMAN_MENU_COMMANDS:
        await send_clean_reply(update.message,
            "German A1 practice:",
            reply_markup=get_german_a1_menu()
        )
        return

    # Daily briefing shortcut
    if text == "daily briefing":
        await send_daily_briefing(context.application)
        return

    if is_identity_question(user_message):
        await send_clean_reply(update.message, BAJRANG_IDENTITY_RESPONSE, reply_markup=get_main_menu())
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, BAJRANG_IDENTITY_RESPONSE)
        return

    gmail_intent = parse_gmail_search_intent(user_message)
    if gmail_intent:
        logging.info(
            "Gmail intent detected: type=%s query=%s max_results=%s",
            gmail_intent.get("intent"),
            gmail_intent.get("query"),
            gmail_intent.get("max_results"),
        )
        result = search_gmail_messages(
            gmail_intent["query"],
            max_results=gmail_intent["max_results"]
        )
        if (
            result == GMAIL_NO_MATCH_MESSAGE
            and gmail_intent.get("fallback_query")
        ):
            result = search_gmail_messages(gmail_intent["fallback_query"], max_results=7)

        await send_clean_reply(update.message, result, reply_markup=get_main_menu())
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, result)
        return

    if text == "documents":
        docs = get_uploaded_documents(limit=10)
        if not docs:
            await send_clean_reply(update.message,"No documents found.")
            return

        lines = [f"{ICON_CLIPBOARD} Recently Uploaded Documents", ""]
        for d in docs:
            dt_str = d.get("created_at", "")
            dt = parse_log_datetime(dt_str)
            date_fmt = dt.strftime("%Y-%m-%d") if dt else "Unknown"
            lines.append(f"• {d['filename']} ({d['document_type']})")
            lines.append(f"  Date: {date_fmt} | Chunks: {d['semantic_chunk_count']}")
            lines.append("")

        await send_clean_reply(update.message,"\n".join(lines).strip())
        return

    # Consolidated automated detection for user messages
    if not is_internal:
        if is_critical_finance_capture_request(user_message):
            reply = (
                "For safety, I do not save salary/rent/EMI/goals/future plans from casual text.\n"
                "Use Finance Setup and confirm with ✅ Save."
            )
            await send_clean_reply(update.message, reply, reply_markup=get_finance_setup_menu())
            return

        save_semantic_memory(user_message)

        remember_text = detect_remember_command(user_message)
        if remember_text:
            saved = save_personal_memory(remember_text)
            reply = (
                f"Confirmed: I saved this memory.\nMemory: {remember_text}"
                if saved
                else "I could not confirm that this memory was saved. Please try again or check system logs."
            )
            save_to_supabase(user_message, reply)
            await send_clean_reply(update.message,reply)
            if is_voice_input and voice_replies_enabled:
                await send_voice_reply(update, reply)
            return

        finance_tx = classify_finance_message(user_message)
        if finance_tx:
            saved = save_finance_transaction(finance_tx)
            reply = format_finance_confirmation(finance_tx, saved)
            save_to_supabase(user_message, reply)
            await send_clean_reply(update.message,reply)
            if is_voice_input and voice_replies_enabled:
                await send_voice_reply(update, reply)
            return

    command = get_formatted_command(text)
    if command:
        title, provider = command
        if provider == get_gmail_summary:
            raw = provider(text)
        else:
            raw = provider()
        formatted = format_with_claude(title, raw)
        await send_clean_reply(update.message,formatted, reply_markup=get_main_menu())
        return

    if text == "create calendar event":
        context.user_data[WAITING_FOR_CALENDAR_EVENT] = True
        reply = "What would you like to schedule?\nExample: Dentist tomorrow 15:00"
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    if is_draft_email_request(text):
        clear_email_draft_state(context)
        context.user_data[WAITING_FOR_EMAIL_TO] = True
        reply = "Who should the draft email be addressed to?"
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    if text in ADD_GERMAN_WORD_COMMANDS:
        clear_german_word_state(context)
        context.user_data[WAITING_FOR_GERMAN_WORD] = True
        reply = "What German word should I save?"
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    if text in ADD_GRAMMAR_RULE_COMMANDS:
        clear_german_grammar_state(context)
        context.user_data[WAITING_FOR_GRAMMAR_TOPIC] = True
        reply = "What grammar topic should I save?"
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    if text in CORRECT_GERMAN_COMMANDS:
        context.user_data[WAITING_FOR_GERMAN_CORRECTION] = True
        reply = "Send the German sentence or text you want corrected."
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    if text == "a1 practice":
        reply = generate_a1_practice()
        save_to_supabase(user_message, reply)
        await send_clean_reply(update.message, reply, reply_markup=get_read_aloud_markup())
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    if text == "quiz me":
        words = get_random_german_words(limit=1)

        if not words:
            reply = "No German words found yet. Add a word first."
            await send_clean_reply(update.message,reply, reply_markup=get_german_a1_menu())
            return

        quiz = words[0]
        context.user_data[GERMAN_QUIZ_STATE] = quiz
        context.user_data[WAITING_FOR_GERMAN_QUIZ_ANSWER] = True
        reply = f"Quiz: What does '{quiz.get('word')}' mean?"
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    # Create Asana task
    task_name = extract_task_name(user_message)
    if task_name is not None:
        if not task_name:
            await send_clean_reply(update.message,"Please provide a task name.")
            return
        result = create_asana_task(task_name)
        reply = get_safe_action_result(
            result,
            "Asana task created:",
            "I could not confirm that an Asana task was created."
        )
        save_to_supabase(user_message, reply)
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    # Create calendar event from full command
    if is_calendar_event_request(text):
        reply = create_calendar_event_reply(user_message)
        save_to_supabase(user_message, reply)
        await send_clean_reply(update.message,reply)
        if is_voice_input and voice_replies_enabled:
            await send_voice_reply(update, reply)
        return

    # System status
    if text == "system status":
        status = await asyncio.to_thread(get_system_status)
        await send_clean_reply(update.message,status)
        return

    if text == "show errors":
        errors = get_recent_system_errors()
        await send_clean_reply(update.message,errors, reply_markup=get_main_menu())
        return

    if text in ["deploy status", "render status"]:
        status = get_render_deploy_status()
        await send_clean_reply(update.message,status, reply_markup=get_main_menu())
        return

    if text in ["last push", "github status"]:
        status = get_github_latest_commit()
        await send_clean_reply(update.message,status, reply_markup=get_main_menu())
        return

    if is_email_action_request(text):
        reply = (
            "I did not send, reply to, or forward any email.\n"
            "Email sending is disabled. I can create Gmail drafts through the Draft Email button."
        )
        save_to_supabase(user_message, reply)
        await send_clean_reply(update.message,reply)
        return

    if is_unsupported_external_action_request(text):
        reply = get_unsupported_action_reply()
        save_to_supabase(user_message, reply)
        await send_clean_reply(update.message,reply)
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
        model=CLAUDE_MODEL,
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
    await send_clean_reply(update.message, reply, reply_markup=get_read_aloud_markup())
    if is_voice_input and voice_replies_enabled:
        await send_voice_reply(update, reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for Telegram voice messages."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    voice = update.message.voice
    if voice.duration > 90:
        await send_clean_reply(update.message,"Voice note is too long (limit 90s).")
        return

    transcription = await transcribe_voice(update, context)
    if not transcription:
        await send_clean_reply(update.message,"I couldn't hear that clearly. Could you try again?")
        return

    await handle_message(update, context, overridden_text=transcription, is_voice_input=True)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for PDF documents to extract text and process with Claude."""
    if update.effective_user.id != ALLOWED_USER_ID:
        return

    doc = update.message.document
    if not doc.file_name.lower().endswith('.pdf'):
        await send_clean_reply(update.message,"I currently only support reading PDF files.")
        return

    status_msg = await send_clean_reply(update.message,f"Reading {doc.file_name}... {ICON_MAGNIFIER}")
    
    temp_path = None
    try:
        file = await doc.get_file()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            temp_path = tf.name
        await file.download_to_drive(temp_path)

        # Extract full text from PDF
        text_content = ""
        page_count = 0
        with open(temp_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            page_count = len(reader.pages)
            for page in reader.pages:
                text_content += page.extract_text() or ""

        if not text_content.strip():
            await status_msg.edit_text(
                "I couldn't find any readable text in that PDF. "
                "It might be a scanned PDF or an image-based PDF."
            )
            return

        # Split text into chunks of 8,000 characters
        chunk_size = 8000
        chunks = [text_content[i:i + chunk_size] for i in range(0, len(text_content), chunk_size)]
        
        await status_msg.edit_text(f"Storing {len(chunks)} chunks in semantic memory...")

        # Store each chunk into semantic_memory
        for chunk in chunks:
            save_semantic_memory(chunk, source="pdf")

        # Save metadata
        doc_data = {
            "filename": doc.file_name,
            "telegram_file_id": doc.file_id,
            "document_type": "pdf",
            "source": "telegram",
            "page_count": page_count,
            "semantic_chunk_count": len(chunks),
            "storage_status": "processed",
            "extracted_text_summary": truncate_text(text_content, 1000)
        }
        save_document_metadata(doc_data)

        # Create a short summary from only the first 2 chunks
        summary_text = "\n".join(chunks[:2])
        processing_prompt = (
            "The uploaded document has been preserved as a document record and split into searchable semantic chunks for later retrieval. "
            "Based *only* on the following opening segments, provide a concise overview of what this document is about. "
            "If it is German A1 learning material, identify the main topics.\n\n"
            f"Segments:\n{truncate_text(summary_text, 16000, preserve_newlines=True)}"
        )

        await status_msg.edit_text("Generating summary...")
        await handle_message(update, context, overridden_text=processing_prompt, is_internal=True)

        await send_clean_reply(update.message,
            f"{ICON_CHECK} Document Processing Complete:\n"
            f"- Filename: {doc.file_name}\n"
            f"- Pages: {page_count}\n"
            f"- Semantic chunks saved: {len(chunks)}"
        )

    except Exception as e:
        log_system_error("handle_document", e)
        await status_msg.edit_text("Failed to process the PDF safely.")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log_system_error("telegram_error_handler", context.error)


def main():
    print("Bajrang is starting...")

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("read", handle_read_aloud))
    app.add_handler(CallbackQueryHandler(handle_tts_callback, pattern=f"^{READ_ALOUD_CALLBACK}$"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
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
