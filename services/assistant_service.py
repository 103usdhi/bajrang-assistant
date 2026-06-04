import json
from datetime import datetime


def is_identity_question(text, re_module):
    lowered = str(text or "").lower()
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
    return any(re_module.search(pattern, lowered) for pattern in patterns)


def get_current_datetime(timezone):
    now = datetime.now(timezone)
    return now.strftime("%A, %d %B %Y, %H:%M")


def compact_json(data):
    return json.dumps(data, separators=(",", ":"))


def format_with_claude(title, raw_data, truncate_text, client, model, log_error):
    try:
        raw_data = truncate_text(raw_data, max_length=3500)
        response = client.messages.create(
            model=model,
            max_tokens=450,
            system="Format for Telegram. Be concise. Use short headings/bullets. Hide raw JSON.",
            messages=[{"role": "user", "content": f"{title}\n{raw_data}"}]
        )
        return response.content[0].text
    except Exception as e:
        log_error("format_with_claude", e)
        return f"{title} failed to format: {str(e)}"


def get_formatted_command(text, formatted_commands):
    for aliases, title, provider in formatted_commands:
        if text in aliases:
            return title, provider
    return None


def has_explicit_data_action(text, explicit_words):
    return any(word in text for word in explicit_words)


def is_explicit_gmail_context_request(text, has_explicit_data_action):
    gmail_words = ("gmail", "email", "inbox", "mail")
    return has_explicit_data_action(text) and any(word in text for word in gmail_words)


def is_explicit_calendar_context_request(text, has_explicit_data_action):
    calendar_words = ("calendar", "meeting", "appointment", "agenda")
    return has_explicit_data_action(text) and any(word in text for word in calendar_words)


def is_explicit_asana_context_request(text, has_explicit_data_action):
    asana_words = ("asana", "task", "tasks", "project", "projects")
    return has_explicit_data_action(text) and any(word in text for word in asana_words)


def is_unsupported_external_action_request(text):
    unsupported_actions = (
        "delete", "remove", "cancel", "update", "edit",
        "reschedule", "complete", "mark", "write", "store"
    )
    external_targets = (
        "calendar", "event", "meeting", "asana", "task",
        "email", "gmail", "mail", "database", "supabase",
        "table", "record"
    )
    return text.startswith(unsupported_actions) and any(target in text for target in external_targets)


def build_live_context(text, providers):
    context_parts = []
    for should_fetch, title, provider in providers:
        if should_fetch(text):
            if provider.__name__ == "get_gmail_summary":
                context_parts.append(f"\n\n{title}:\n{provider(text)}")
            else:
                context_parts.append(f"\n\n{title}:\n{provider()}")
    return "".join(context_parts)


def build_runtime_context(current_datetime, timezone_name):
    return f"""
Current date/time:
{current_datetime}
Timezone: {timezone_name}
"""


def build_conversation_history(recent_memories, user_message):
    conversation_history = []
    for memory in reversed(recent_memories):
        conversation_history.append({"role": "user", "content": memory["user_message"]})
        conversation_history.append({"role": "assistant", "content": memory["assistant_response"]})
    conversation_history.append({"role": "user", "content": user_message})
    return conversation_history


def query_assistant_response(
    client,
    model,
    system_prompt,
    runtime_context,
    semantic_context,
    personal_memory_context,
    live_context,
    conversation_history
):
    response = client.messages.create(
        model=model,
        max_tokens=900,
        system=(
            system_prompt
            + runtime_context
            + semantic_context
            + personal_memory_context
            + live_context
        ),
        messages=conversation_history
    )
    return response.content[0].text

