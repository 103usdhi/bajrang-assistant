import json
import re
from datetime import datetime

import requests


def get_finance_summary(get_monthly_spending_breakdown, get_overspending_insights, log_error):
    try:
        spending = get_monthly_spending_breakdown()
        insights = get_overspending_insights()
        return json.dumps({
            "monthly_breakdown": json.loads(spending) if "failed" not in spending else spending,
            "insights": json.loads(insights) if "failed" not in insights else insights
        }, indent=2)
    except Exception as e:
        log_error("get_finance_summary", e)
        return "Finance summary unavailable."


def classify_finance_message(message, finance_category_rules):
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

    for keyword, values in finance_category_rules.items():
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


def save_finance_transaction(tx, supabase_url, headers, log_error):
    try:
        url = f"{supabase_url}/rest/v1/finance_transactions"
        data = {
            "amount": tx["amount"],
            "currency": "EUR",
            "transaction_type": tx["transaction_type"],
            "category": tx["category"],
            "description": tx["description"],
            "is_essential": tx["is_essential"]
        }
        result = requests.post(url, headers=headers, json=data, timeout=10)
        if result.status_code in [200, 201, 204]:
            return True

        log_error(
            "save_finance_transaction",
            RuntimeError(f"Supabase returned {result.status_code}: {result.text}")
        )
        return False
    except Exception as e:
        log_error("save_finance_transaction", e)
        return False


def parse_finance_amount_legacy(text):
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
    def normalize_amount_token(token):
        candidate = token.strip().strip(".,")
        if not candidate:
            return None

        if "," in candidate and "." in candidate:
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
    cleaned = cleaned.replace("eur", "").replace("€", "").replace("â‚¬", "").replace("Ã¢â€šÂ¬", "")
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


def parse_plan_month(text, timezone):
    lowered = str(text or "").lower().strip()
    if not lowered:
        return None

    now = datetime.now(timezone)
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


def parse_future_plan_text(text, parse_finance_amount, parse_plan_month):
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
        "invest", "investment", "buy", "purchase", "refund",
        "expected income", "expected payment", "next month",
        "planned", "goal", "save for"
    )
    finance_context_markers = (
        "finance", "money", "income", "payment", "salary", "rent",
        "emi", "loan", "bill", "invest", "buy", "purchase", "refund", "goal", "save"
    )

    has_month_signal = "next month" in lowered or any(month in lowered for month in month_names)
    has_future_signal = any(marker in lowered for marker in future_plan_markers) or has_month_signal
    has_finance_context = any(marker in lowered for marker in finance_context_markers) or "€" in str(text or "") or "eur" in lowered

    return has_future_signal and has_finance_context


def is_finance_profile_line(text, is_critical_finance_capture_request):
    line = str(text or "").strip()
    if not line:
        return False
    lowered = line.lower()
    direct_keywords = ("salary", "rent", "emi", "loan", "savings goal", "future plan")
    if any(keyword in lowered for keyword in direct_keywords):
        return True
    return is_critical_finance_capture_request(line)


def extract_personal_fact(line):
    text = str(line or "").strip()
    lowered = text.lower()

    patterns = [
        (r"^(?:my name is|i am)\s+(.+)$", "Name"),
        (r"^(?:i live in|my location is)\s+(.+)$", "Location"),
        (r"^(?:i am|my role is|i work as)\s+(.+)$", "Job role"),
        (r"^(?:my dob is|my date of birth is|dob is)\s+(.+)$", "DOB")
    ]

    for pattern, label in patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            value = text[match.start(1):].strip(" .")
            if value:
                return {"label": label, "value": value, "line": text}
    return None


def split_personal_and_finance_lines(message, is_finance_profile_line, extract_personal_fact):
    lines = [line.strip() for line in str(message or "").splitlines() if line.strip()]
    finance_lines = []
    personal_facts = []

    for line in lines:
        if is_finance_profile_line(line):
            finance_lines.append(line)
            continue
        fact = extract_personal_fact(line)
        if fact:
            personal_facts.append(fact)

    return {"personal_facts": personal_facts, "finance_lines": finance_lines}


def save_personal_facts_with_finance_guard(
    message,
    split_personal_and_finance_lines,
    save_personal_memory,
    save_explicit_memory_content
):
    split = split_personal_and_finance_lines(message)
    personal_facts = split["personal_facts"]
    finance_lines = split["finance_lines"]

    saved_facts = []
    for fact in personal_facts:
        memory_text = f"{fact['label']}: {fact['value']}"
        saved_personal = save_personal_memory(memory_text)
        saved_semantic = save_explicit_memory_content(memory_text, "personal_memory")
        if saved_personal and saved_semantic:
            saved_facts.append(fact)

    if not finance_lines:
        return None

    lines = []
    if saved_facts:
        lines.extend(["Saved:"])
        for fact in saved_facts:
            lines.append(f"- {fact['label']}: {fact['value']}")
    else:
        lines.extend(["Saved:", "- No safe personal facts found to save."])

    lines.extend(["", "Not saved:"])
    for blocked in finance_lines:
        lines.append(f"- {blocked}")

    lines.extend(["", "For salary, use Finance Setup -> Set Monthly Salary."])
    return "\n".join(lines)


def is_finance_profile_question(text):
    lowered = str(text or "").lower().strip()
    if not lowered:
        return False
    if len(lowered) > 300:
        return False

    normalized = re.sub(r"\s+", " ", lowered)
    explicit_patterns = (
        r"^(show|view|list|summarize|summary of|what(?:'s| is)|how much(?: is| are)?)\s+(my\s+)?(finance profile|salary|rent|emi|loan|commitments?|fixed commitments?|savings goals?|future plans?|upcoming obligations)\b",
        r"^(finance profile|my finance profile|view finance profile|show finance profile)\b"
    )
    return any(re.search(pattern, normalized) for pattern in explicit_patterns)


def set_finance_pending_confirmation(context, pending_key, action, payload, summary, edit_state=None, edit_prompt=None):
    context.user_data[pending_key] = {
        "action": action,
        "payload": payload,
        "summary": summary,
        "edit_state": edit_state,
        "edit_prompt": edit_prompt or "Please update the value."
    }


def clear_finance_states(context, keys):
    for key in keys:
        context.user_data.pop(key, None)


def save_financial_profile_values(
    values,
    has_finance_write_access,
    log_error,
    get_finance_auth_error_message,
    allowed_user_id,
    timezone,
    get_finance_supabase_headers,
    supabase_url,
    log_finance_http_error
):
    try:
        if not has_finance_write_access():
            log_error("save_financial_profile_values", RuntimeError(get_finance_auth_error_message()))
            return False
        payload = {
            "user_id": allowed_user_id,
            "updated_at": datetime.now(timezone).isoformat()
        }
        payload.update(values)
        headers = dict(get_finance_supabase_headers())
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        result = requests.post(
            f"{supabase_url}/rest/v1/financial_profile",
            headers=headers,
            params={"on_conflict": "user_id"},
            json=payload,
            timeout=10
        )
        if result.status_code in [200, 201, 204]:
            return True
        log_finance_http_error("save_financial_profile_values", "financial_profile", "upsert", result)
        return False
    except Exception as e:
        log_error("save_financial_profile_values", e)
        return False


def insert_financial_commitment(
    payload,
    has_finance_write_access,
    log_error,
    get_finance_auth_error_message,
    allowed_user_id,
    timezone,
    get_finance_supabase_headers,
    supabase_url,
    log_finance_http_error
):
    try:
        if not has_finance_write_access():
            log_error("insert_financial_commitment", RuntimeError(get_finance_auth_error_message()))
            return False
        data = {
            "user_id": allowed_user_id,
            "created_at": datetime.now(timezone).isoformat(),
            "updated_at": datetime.now(timezone).isoformat(),
            "status": "active"
        }
        data.update(payload)
        result = requests.post(
            f"{supabase_url}/rest/v1/financial_commitments",
            headers=get_finance_supabase_headers(),
            json=data,
            timeout=10
        )
        if result.status_code in [200, 201, 204]:
            return True
        log_finance_http_error("insert_financial_commitment", "financial_commitments", "insert", result)
        return False
    except Exception as e:
        log_error("insert_financial_commitment", e)
        return False


def insert_financial_goal(
    payload,
    has_finance_write_access,
    log_error,
    get_finance_auth_error_message,
    allowed_user_id,
    timezone,
    get_finance_supabase_headers,
    supabase_url,
    log_finance_http_error
):
    try:
        if not has_finance_write_access():
            log_error("insert_financial_goal", RuntimeError(get_finance_auth_error_message()))
            return False
        data = {
            "user_id": allowed_user_id,
            "created_at": datetime.now(timezone).isoformat(),
            "updated_at": datetime.now(timezone).isoformat(),
            "status": "active"
        }
        data.update(payload)
        result = requests.post(
            f"{supabase_url}/rest/v1/financial_goals",
            headers=get_finance_supabase_headers(),
            json=data,
            timeout=10
        )
        if result.status_code in [200, 201, 204]:
            return True
        log_finance_http_error("insert_financial_goal", "financial_goals", "insert", result)
        return False
    except Exception as e:
        log_error("insert_financial_goal", e)
        return False


def insert_financial_plan(
    payload,
    has_finance_write_access,
    log_error,
    get_finance_auth_error_message,
    allowed_user_id,
    timezone,
    get_finance_supabase_headers,
    supabase_url,
    log_finance_http_error
):
    try:
        if not has_finance_write_access():
            log_error("insert_financial_plan", RuntimeError(get_finance_auth_error_message()))
            return False
        data = {
            "user_id": allowed_user_id,
            "created_at": datetime.now(timezone).isoformat(),
            "updated_at": datetime.now(timezone).isoformat(),
            "status": "planned"
        }
        data.update(payload)
        result = requests.post(
            f"{supabase_url}/rest/v1/financial_plans",
            headers=get_finance_supabase_headers(),
            json=data,
            timeout=10
        )
        if result.status_code in [200, 201, 204]:
            return True
        log_finance_http_error("insert_financial_plan", "financial_plans", "insert", result)
        return False
    except Exception as e:
        log_error("insert_financial_plan", e)
        return False


def fetch_finance_rows(table_name, select_columns, limit, allowed_user_id, get_finance_supabase_headers, supabase_url, log_error, log_finance_http_error):
    try:
        params = {
            "select": select_columns,
            "user_id": f"eq.{allowed_user_id}",
            "order": "created_at.desc",
            "limit": str(limit)
        }
        result = requests.get(
            f"{supabase_url}/rest/v1/{table_name}",
            headers=get_finance_supabase_headers(),
            params=params,
            timeout=10
        )
        if result.status_code == 200:
            return result.json()
        log_finance_http_error("fetch_finance_rows", table_name, "select", result)
        return []
    except Exception as e:
        log_error("fetch_finance_rows", e)
        return []


def get_financial_profile_row(fetch_finance_rows):
    rows = fetch_finance_rows("financial_profile", limit=1)
    return rows[0] if rows else {}


def format_finance_profile_summary(get_financial_profile_row, fetch_finance_rows, format_eur):
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


def build_finance_item_catalog(get_financial_profile_row, fetch_finance_rows, format_eur):
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


def update_finance_item_amount(
    item,
    amount,
    has_finance_write_access,
    log_error,
    get_finance_auth_error_message,
    save_financial_profile_values,
    timezone,
    supabase_url,
    get_finance_supabase_headers,
    log_finance_http_error
):
    try:
        if not has_finance_write_access():
            log_error("update_finance_item_amount", RuntimeError(get_finance_auth_error_message()))
            return False
        if item["table"] == "financial_profile":
            payload = {
                item["field"]: amount,
                "updated_at": datetime.now(timezone).isoformat()
            }
            return save_financial_profile_values(payload)

        params = {"id": f"eq.{item['id']}"}
        payload = {
            item["field"]: amount,
            "updated_at": datetime.now(timezone).isoformat()
        }
        result = requests.patch(
            f"{supabase_url}/rest/v1/{item['table']}",
            headers=get_finance_supabase_headers(),
            params=params,
            json=payload,
            timeout=10
        )
        if result.status_code in [200, 204]:
            return True
        log_finance_http_error("update_finance_item_amount", item["table"], "update", result)
        return False
    except Exception as e:
        log_error("update_finance_item_amount", e)
        return False


def delete_finance_item(
    item,
    has_finance_write_access,
    log_error,
    get_finance_auth_error_message,
    save_financial_profile_values,
    supabase_url,
    get_finance_supabase_headers,
    log_finance_http_error
):
    try:
        if not has_finance_write_access():
            log_error("delete_finance_item", RuntimeError(get_finance_auth_error_message()))
            return False
        if item["table"] == "financial_profile":
            return save_financial_profile_values({item["field"]: None})

        result = requests.delete(
            f"{supabase_url}/rest/v1/{item['table']}",
            headers=get_finance_supabase_headers(),
            params={"id": f"eq.{item['id']}"},
            timeout=10
        )
        if result.status_code in [200, 204]:
            return True
        log_finance_http_error("delete_finance_item", item["table"], "delete", result)
        return False
    except Exception as e:
        log_error("delete_finance_item", e)
        return False


def get_finance_transactions(select_columns, supabase_url, headers, log_error):
    try:
        url = f"{supabase_url}/rest/v1/finance_transactions?select={select_columns}"
        result = requests.get(url, headers=headers, timeout=10)
        if result.status_code != 200:
            return None
        return result.json()
    except Exception as e:
        log_error("get_finance_transactions", e)
        return None


def iter_expense_rows(rows):
    for row in rows:
        if row.get("transaction_type") != "expense":
            continue
        category = row.get("category") or "general"
        amount = float(row.get("amount") or 0)
        yield row, category, amount


def get_monthly_spending_breakdown(get_finance_transactions, iter_expense_rows, log_error):
    try:
        rows = get_finance_transactions("amount,category,transaction_type")
        if rows is None:
            return "Finance analytics failed."

        category_totals = {}
        total_spending = 0
        for _, category, amount in iter_expense_rows(rows):
            total_spending += amount
            category_totals[category] = category_totals.get(category, 0) + amount

        sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
        return json.dumps({
            "total_spending": round(total_spending, 2),
            "top_categories": sorted_categories[:10]
        }, indent=2)
    except Exception as e:
        log_error("get_monthly_spending_breakdown", e)
        return f"Finance analytics failed: {str(e)}"


def get_overspending_insights(get_finance_transactions, iter_expense_rows, log_error):
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

        biggest = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
        return json.dumps({
            "essential_spending": round(essential, 2),
            "non_essential_spending": round(non_essential, 2),
            "top_expense_categories": biggest,
            "warning": "High non-essential spending detected." if non_essential > essential else "Spending pattern looks balanced."
        }, indent=2)
    except Exception as e:
        log_error("get_overspending_insights", e)
        return f"Overspending analysis failed: {str(e)}"


def execute_finance_pending_action(
    pending,
    has_finance_write_access,
    get_finance_auth_error_message,
    save_financial_profile_values,
    insert_financial_commitment,
    insert_financial_goal,
    insert_financial_plan,
    update_finance_item_amount,
    delete_finance_item
):
    action = pending.get("action")
    payload = pending.get("payload", {})
    if action in {
        "save_profile_value",
        "save_commitment",
        "save_goal",
        "save_plan",
        "edit_item_amount",
        "delete_item"
    } and not has_finance_write_access():
        return False, get_finance_auth_error_message()

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


def parse_due_day_input(text):
    lowered = str(text or "").strip().lower()
    if lowered == "skip":
        return True, None
    match = re.search(r"\b([1-9]|[12][0-9]|3[01])\b", lowered)
    if not match:
        return False, None
    return True, int(match.group(1))

