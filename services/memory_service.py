import re
import requests


def get_recent_memories(supabase_url, headers, recent_exchange_limit, log_error):
    try:
        url = (
            f"{supabase_url}/rest/v1/events_log"
            f"?select=user_message,assistant_response"
            f"&order=created_at.desc"
            f"&limit={recent_exchange_limit}"
        )
        result = requests.get(url, headers=headers, timeout=10)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_error("get_recent_memories", e)
        return []


def save_personal_memory(memory_text, supabase_url, headers, log_error):
    try:
        url = f"{supabase_url}/rest/v1/personal_memory"
        data = {
            "memory_text": memory_text,
            "memory_type": "general",
            "importance": "medium",
            "source": "telegram",
            "is_active": True
        }
        result = requests.post(url, headers=headers, json=data, timeout=10)
        if result.status_code in [200, 201, 204]:
            return True

        log_error(
            "save_personal_memory",
            RuntimeError(f"Supabase returned {result.status_code}: {result.text}")
        )
        return False
    except Exception as e:
        log_error("save_personal_memory", e)
        return False


def get_personal_memories(supabase_url, headers, personal_memory_limit, log_error):
    try:
        url = (
            f"{supabase_url}/rest/v1/personal_memory"
            f"?select=memory_text"
            f"&is_active=eq.true"
            f"&order=created_at.desc"
            f"&limit={personal_memory_limit}"
        )
        result = requests.get(url, headers=headers, timeout=10)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_error("get_personal_memories", e)
        return []


def looks_like_low_value_memory_text(content):
    text = str(content or "").strip()
    if not text:
        return True

    lowered = text.lower()
    compact = re.sub(r"\s+", " ", lowered)

    question_starts = (
        "do you", "did you", "can you", "could you", "will you", "would you",
        "what is", "what's", "where is", "when is", "why is", "how is",
        "who is", "which", "shall i", "should i", "is it", "are you"
    )
    transient_commands = (
        "system status", "show errors", "deploy status", "render status",
        "last push", "github status", "gmail summary", "calendar summary",
        "asana tasks", "finance report", "view finance profile", "show finance profile",
        "search gmail", "find email", "email from", "most recent email", "latest email",
        "read it", "draft email"
    )

    if compact.endswith("?") or compact.startswith(question_starts):
        return True
    if any(cmd in compact for cmd in transient_commands):
        return True
    if len(compact) < 12:
        return True
    return False


def should_store_semantic_memory(content, source):
    src = str(source or "telegram").strip().lower()
    text = str(content or "").strip()
    if not text:
        return False

    durable_sources = {"pdf", "personal_memory", "insurance", "document_note", "project_note"}
    if src in durable_sources:
        return True

    if src == "telegram" and looks_like_low_value_memory_text(text):
        return False

    return True


def filter_semantic_results(results, query_text):
    filtered = []
    query = str(query_text or "").strip().lower()

    for row in results or []:
        content = str(row.get("content", "")).strip()
        source = str(row.get("source", "")).strip().lower()
        if not content:
            continue

        if source == "telegram" and looks_like_low_value_memory_text(content):
            continue

        normalized = re.sub(r"\s+", " ", content.lower()).strip(" .!?")
        query_norm = re.sub(r"\s+", " ", query).strip(" .!?")
        if query_norm and normalized == query_norm:
            continue

        filtered.append(row)

    return filtered


def save_semantic_memory(
    content,
    source,
    openai_client,
    generate_embedding,
    supabase_url,
    headers,
    log_error
):
    if not openai_client:
        return

    try:
        if not should_store_semantic_memory(content, source):
            return
        embedding = generate_embedding(content)
        url = f"{supabase_url}/rest/v1/semantic_memory"
        data = {
            "content": content,
            "source": source,
            "embedding": embedding
        }
        requests.post(url, headers=headers, json=data, timeout=10)
    except Exception as e:
        log_error("save_semantic_memory", e)


def extract_prefixed_content(text, prefixes):
    original = str(text or "").strip()
    lowered = original.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            return original[len(prefix):].lstrip(" :-\n\t")
    return None


def detect_memory_save_command(text):
    original = str(text or "").strip()
    lowered = original.lower().strip()
    if not lowered:
        return None

    # Legacy exact-prefix support (kept for backward compatibility).
    command_map = [
        ("add this to insurance memory", "insurance"),
        ("add to insurance memory", "insurance"),
        ("remember this", "personal_memory"),
        ("save this", "personal_memory"),
        ("add this to document note", "document_note"),
        ("add this to project note", "project_note"),
        ("add to project note", "project_note"),
        ("add to finance memory", "finance_memory"),
        ("add this to finance memory", "finance_memory")
    ]
    for prefix, source in command_map:
        if lowered.startswith(prefix):
            content = original[len(prefix):].lstrip(" :=*-\n\t")
            return {"source": source, "content": content}

    # Extended phrase coverage with flexible separators.
    # Examples:
    # - remember in personal memory = test
    # - save to personal memory: test
    # - remember in insurance memory * note
    # - save to document note test
    # - add to project memory = note
    patterns = [
        (r"^(?:remember|save)\s+(?:in|to)\s+personal\s+memory(?:\s*[=:*]\s*|\s+)?(.*)$", "personal_memory"),
        (r"^(?:remember|save)\s+(?:in|to)\s+insurance\s+memory(?:\s*[=:*]\s*|\s+)?(.*)$", "insurance"),
        (r"^(?:remember|save)\s+(?:in|to)\s+document\s+note(?:\s*[=:*]\s*|\s+)?(.*)$", "document_note"),
        (r"^(?:remember|save)\s+(?:in|to)\s+project\s+memory(?:\s*[=:*]\s*|\s+)?(.*)$", "project_note"),
        (r"^(?:remember|save)\s+(?:in|to)\s+project\s+note(?:\s*[=:*]\s*|\s+)?(.*)$", "project_note"),
        (r"^(?:remember|save)\s+(?:in|to)\s+finance\s+memory(?:\s*[=:*]\s*|\s+)?(.*)$", "finance_memory"),
        (r"^add\s+to\s+project\s+memory(?:\s*[=:*]\s*|\s+)?(.*)$", "project_note"),
    ]

    for pattern, source in patterns:
        match = re.match(pattern, original, flags=re.IGNORECASE)
        if match:
            content = (match.group(1) or "").strip(" :=*-\n\t")
            return {"source": source, "content": content}

    return None


def detect_memory_recall_topic(text):
    lowered = str(text or "").strip().lower()
    patterns = [
        r"^what do you remember about\s+(.+)$",
        r"^what do you remember on\s+(.+)$",
        r"^remember anything about\s+(.+)$"
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1).strip(" ?.!,;:")
    return None


def is_read_it_request(text):
    lowered = str(text or "").strip().lower()
    return lowered.startswith("read it")


def summarize_read_request_content(content, truncate_text, client, claude_model, log_error):
    try:
        limited = truncate_text(content, max_length=6000, preserve_newlines=True)
        response = client.messages.create(
            model=claude_model,
            max_tokens=450,
            system=(
                "Summarize pasted text for Telegram. "
                "Use short sections: Summary, Key Points, Suggested Next Step. "
                "Do not claim data was saved."
            ),
            messages=[{"role": "user", "content": limited}]
        )
        return response.content[0].text
    except Exception as e:
        log_error("summarize_read_request_content", e)
        return "I could not summarize that text right now."


def clear_memory_intent_state(context, state_keys):
    for key in state_keys:
        context.user_data.pop(key, None)


def is_blocked_finance_memory_source(source):
    return str(source or "").strip().lower() in {"finance", "finance_memory"}


def is_source_allowed_for_finance_like_content(source):
    src = str(source or "").strip().lower()
    return src in {"document_note", "insurance", "project_note", "pdf"}


def should_block_memory_save_for_finance_profile(content, source, is_critical_finance_capture_request):
    if is_blocked_finance_memory_source(source):
        return True
    if is_source_allowed_for_finance_like_content(source):
        return False
    return is_critical_finance_capture_request(content)


def save_explicit_memory_content(
    content,
    source,
    should_block_memory_save_for_finance_profile,
    save_semantic_memory
):
    text = str(content or "").strip()
    if not text:
        return False
    if should_block_memory_save_for_finance_profile(text, source):
        return False
    save_semantic_memory(text, source=source)
    return True


def format_memory_recall_response(topic, results, truncate_text):
    if not results:
        return f"I do not have saved memory entries for '{topic}' yet."

    lines = [f"Memory recall for '{topic}':", ""]
    for idx, row in enumerate(results[:5], start=1):
        source = row.get("source") or "memory"
        content = truncate_text(row.get("content", ""), max_length=220, preserve_newlines=False)
        lines.append(f"{idx}. [{source}] {content}")
    return "\n".join(lines)


def search_semantic_memory(
    query,
    openai_client,
    generate_embedding,
    supabase_url,
    headers,
    semantic_memory_match_count,
    log_error
):
    if not openai_client:
        return []

    try:
        embedding = generate_embedding(query)
        url = f"{supabase_url}/rest/v1/rpc/match_semantic_memory"
        data = {
            "query_embedding": embedding,
            "match_threshold": 0.70,
            "match_count": semantic_memory_match_count
        }
        result = requests.post(url, headers=headers, json=data, timeout=10)
        return result.json() if result.status_code == 200 else []
    except Exception as e:
        log_error("search_semantic_memory", e)
        return []
