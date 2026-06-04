import base64
import html
import json
import logging
import re
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


def get_google_token_scopes(token_data):
    scopes = token_data.get("scopes") or token_data.get("scope") or []
    if isinstance(scopes, str):
        scopes = re.split(r"[\s,]+", scopes.strip())
    return {scope for scope in scopes if scope}


def get_google_credentials(google_token_json, required_scopes=None, log_error=None):
    required_scopes = required_scopes or []
    log_error = log_error or (lambda *args, **kwargs: None)

    if not google_token_json:
        logging.warning("get_google_credentials: GOOGLE_TOKEN_JSON missing or empty.")
        if required_scopes:
            log_error(
                "get_google_credentials",
                RuntimeError("Google token missing for required scopes: " + ", ".join(required_scopes))
            )
        return None

    try:
        logging.info("get_google_credentials: attempting GOOGLE_TOKEN_JSON parse.")
        token_data = json.loads(google_token_json)
        logging.info(
            "get_google_credentials: token parsed. keys=%s refresh_token_present=%s",
            ",".join(sorted(token_data.keys())),
            bool(token_data.get("refresh_token"))
        )

        if required_scopes:
            available_scopes = get_google_token_scopes(token_data)
            missing_scopes = [scope for scope in required_scopes if scope not in available_scopes]
            if missing_scopes:
                log_error(
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
                logging.warning("get_google_credentials: credentials expired but refresh_token is missing.")
        except RefreshError as e:
            logging.error("get_google_credentials: RefreshError during refresh: %s", str(e))
            log_error("get_google_credentials", e)
            return None
        except Exception as e:
            logging.error("get_google_credentials: non-RefreshError during refresh: %s", str(e))
            log_error("get_google_credentials", e)
            return None

        return creds
    except Exception as e:
        logging.error("get_google_credentials: parsing/build failed: %s", str(e))
        log_error("get_google_credentials", e)
        return None


def get_gmail_search_query(text):
    if not text:
        return ""
    query = text.lower().strip()
    for cmd in ["gmail summary", "search gmail", "find email", "search email", "find mail"]:
        query = query.replace(cmd, "")
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


def format_gmail_search_results(emails, requested_max_results, no_match_message, total_estimate=None):
    if not emails:
        return no_match_message

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


def search_gmail_messages(query, max_results, get_google_credentials, build, no_match_message, recovery_message, log_error):
    try:
        creds = get_google_credentials()
        if not creds:
            return recovery_message

        service = build("gmail", "v1", credentials=creds)

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
            return no_match_message

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
            total_estimate=result_estimate,
            no_match_message=no_match_message
        )
    except Exception as e:
        log_error("search_gmail_messages", e)
        return f"Gmail search failed: {str(e)}"


def get_gmail_summary(text, get_gmail_search_query, search_gmail_messages, log_error):
    search_terms = get_gmail_search_query(text)

    if not search_terms or search_terms in ["summary", "inbox"]:
        query = "in:inbox"
    else:
        query = f"in:inbox {search_terms}" if "all mail" not in text.lower() else search_terms

    try:
        return search_gmail_messages(query, max_results=7)
    except Exception as e:
        log_error("get_gmail_summary", e)
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

    sender_patterns = [
        r"(?:top|latest|first)?\s*\d*\s*(?:emails?|mail|gmail)\s+from\s+(.+)$",
        r"(?:emails?|mail|gmail)\s+from\s+(.+)$",
        r"sender\s+(?:is|from)\s+(.+)$"
    ]
    for pattern in sender_patterns:
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


def create_gmail_draft(
    to_email,
    subject,
    body,
    get_google_credentials,
    build,
    gmail_compose_scope,
    recovery_message,
    log_error
):
    try:
        creds = get_google_credentials(required_scopes=[gmail_compose_scope])
        if not creds:
            return recovery_message

        message = EmailMessage()
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        draft_body = {"message": {"raw": encoded_message}}

        service = build("gmail", "v1", credentials=creds)
        draft = service.users().drafts().create(userId="me", body=draft_body).execute()
        draft_id = draft.get("id")

        if draft_id:
            return f"Gmail draft created: {subject} (draft id: {draft_id})"

        log_error("create_gmail_draft", RuntimeError("Gmail drafts.create returned no draft id."))
        return "Gmail draft creation failed: Gmail did not return a draft id."
    except Exception as e:
        log_error("create_gmail_draft", e)
        return f"Gmail draft creation failed: {str(e)}"

