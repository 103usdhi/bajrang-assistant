import json
import re
from datetime import datetime
from datetime import date

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


def _legacy_is_critical_finance_capture_request(text):
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

    default_forces_credit_dependency = cushion_until_payday < 0 and expected_next_card_statement > 0
    health_rating, surplus_after_liabilities = get_financial_health_rating(
        monthly_left,
        expected_next_card_statement,
        forces_credit_dependency=default_forces_credit_dependency
    )

    if is_financial_understanding_prompt(text):
        pressure_points = collect_pressure_points(expense_items, baseline_pressure_items)

        positives = []
        if monthly_left > 0:
            positives.append("Income exceeds recurring obligations.")
        if monthly_left >= 0:
            positives.append("No monthly deficit detected.")
        if cushion_until_payday > 0:
            positives.append("There is still an estimated buffer before payday.")
        if expected_next_card_statement <= max(monthly_income * 0.35, 1):
            positives.append("Credit-card liability is currently manageable versus income.")

        risks = []
        if expected_next_card_statement > max(monthly_income * 0.35, 500):
            risks.append("Persistent high credit-card usage may tighten next month's flexibility.")
        if cushion_until_payday < 500:
            risks.append("Emergency buffer before payday is small.")
        if default_forces_credit_dependency:
            risks.append("You may depend on card/debt timing before salary arrives.")
        if any(name == "Loan commitments" for name, _ in pressure_points) and any(name == "Credit-card liabilities" for name, _ in pressure_points):
            risks.append("Multiple debt commitments reduce flexibility.")

        opportunities = []
        if any(name == "High recurring subscriptions" for name, _ in pressure_points):
            opportunities.append("Review recurring subscriptions and trim low-value ones.")
        if any(name == "Vehicle-related expenses" for name, _ in pressure_points):
            opportunities.append("Re-check vehicle costs (insurance/tax/registration) for possible reductions.")
        if expected_next_card_statement > 0:
            opportunities.append("Gradually reduce new card spending to lower next statement pressure.")
        if surplus_after_liabilities < 500:
            opportunities.append("Build an emergency buffer in small monthly steps until at least EUR 500.")
        if any(name == "Loan commitments" for name, _ in pressure_points):
            opportunities.append("If possible, evaluate partial early repayment on highest-cost debt.")

        lines.extend([
            "",
            "\U0001F9E0 Financial Understanding",
            f"- Overall situation: {health_rating.lower()}",
            f"- Financial health rating: {health_rating}",
            f"- Surplus after known liabilities: {format_eur(surplus_after_liabilities)}"
        ])

        lines.append("")
        lines.append("Key Pressure Points")
        if pressure_points:
            for name, amount in pressure_points[:4]:
                lines.append(f"- {name}: {format_eur(amount)}")
        else:
            lines.append("- No dominant pressure point detected from current data.")

        lines.append("")
        lines.append("Positive Observations")
        if positives:
            for item in positives[:4]:
                lines.append(f"- {item}")
        else:
            lines.append("- No strong positive signal yet from this snapshot.")

        lines.append("")
        lines.append("Risks and Warnings")
        if risks:
            for item in risks[:4]:
                lines.append(f"- {item}")
        else:
            lines.append("- No immediate structural warning detected.")

        lines.append("")
        lines.append("Improvement Opportunities")
        if opportunities:
            for item in opportunities[:4]:
                lines.append(f"- {item}")
        else:
            lines.append("- Keep monitoring and maintain current spending discipline.")

        lines.append("")
        lines.append(f"Comfort View: {build_comfort_view(health_rating)}")
        lines.append(f"- Suggested action style: {build_recommendation_from_health(health_rating)}")

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


def _is_income_heading(line):
    lowered = line.lower()
    return lowered in {"income", "income-", "income:"} or lowered.startswith("income")


def _is_expense_heading(line):
    lowered = line.lower()
    return lowered in {"expenses", "expense", "expenses-", "expense-", "expenses:", "expense:"} or lowered.startswith("expenses")


def _extract_label_amount(line, parse_finance_amount):
    patterns = [
        r"^(?:[-*•]\s*)?(.+?)\s*[:=\-]\s*(€?\s*\d[\d.,]*)\s*$"
    ]
    for pattern in patterns:
        match = re.match(pattern, line.strip(), flags=re.IGNORECASE)
        if not match:
            continue
        label = match.group(1).strip(" -:\t")
        amount = parse_finance_amount(match.group(2))
        if label and amount is not None:
            return label, amount
    return None, None


def parse_salary_credit_window(text):
    lowered = str(text or "").lower()
    between_match = re.search(
        r"salary.*between\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s*(?:and|to|-)\s*(\d{1,2})(?:st|nd|rd|th)?",
        lowered
    )
    if between_match:
        start = int(between_match.group(1))
        end = int(between_match.group(2))
        if start > end:
            start, end = end, start
        return max(1, min(start, 31)), max(1, min(end, 31))

    on_match = re.search(r"salary.*(?:on|by)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?", lowered)
    if on_match:
        day = max(1, min(int(on_match.group(1)), 31))
        return day, day

    return 12, 15


def extract_explicit_salary_day(text):
    lowered = str(text or "").lower()
    explicit_patterns = (
        r"salary\s+(?:is\s+)?credited\s+on\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?",
        r"salary\s+(?:came|comes)\s+on\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?",
        r"salary\s+(?:will\s+come|expected)\s+on\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?",
        r"salary\s+expected\s+on\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?"
    )
    for pattern in explicit_patterns:
        match = re.search(pattern, lowered)
        if match:
            day = int(match.group(1))
            return max(1, min(day, 31))
    return None


def parse_credit_card_snapshot(text, expense_items, parse_finance_amount):
    lowered = str(text or "").lower()

    statement_day = None
    payment_due_day = None
    current_statement_amount = None
    expected_next_statement_amount = None

    statement_match = re.search(
        r"statement(?:\s+generated)?(?:\s+on|\s+around)?\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?",
        lowered
    )
    if statement_match:
        statement_day = int(statement_match.group(1))

    due_match = re.search(
        r"(?:payment\s+due|due\s+date|bill\s+due)\s+(?:on\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?",
        lowered
    )
    if due_match:
        payment_due_day = int(due_match.group(1))

    current_match = re.search(
        r"(?:credit\s*card\s*(?:bill|statement)|current\s+statement(?:\s+amount)?)\D{0,20}(\d[\d.,]*)",
        lowered
    )
    if current_match:
        current_statement_amount = parse_finance_amount(current_match.group(1))

    expected_match = re.search(
        r"(?:expected|next)\s+(?:credit\s*card\s+)?statement(?:\s+amount)?\D{0,20}(\d[\d.,]*)",
        lowered
    )
    if expected_match:
        expected_next_statement_amount = parse_finance_amount(expected_match.group(1))

    if current_statement_amount is None:
        for item in expense_items:
            label = item["label"].lower()
            if "credit card" in label or "card bill" in label:
                current_statement_amount = item["amount"]
                break

    if expected_next_statement_amount is None and current_statement_amount is not None:
        expected_next_statement_amount = current_statement_amount

    has_card_context = (
        "credit card" in lowered
        or "statement" in lowered
        or any("credit card" in item["label"].lower() for item in expense_items)
    )
    if not has_card_context:
        return None

    return {
        "statement_day": statement_day,
        "payment_due_day": payment_due_day,
        "current_statement_amount": current_statement_amount,
        "expected_next_statement_amount": expected_next_statement_amount
    }


def parse_finance_snapshot_text(text, parse_finance_amount):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return {"income_items": [], "expense_items": [], "salary_window": (12, 15), "credit_card": None}

    section = None
    income_items = []
    expense_items = []

    income_hints = ("salary", "income", "allowance", "bonus", "refund", "credit", "pension")
    expense_hints = (
        "rent", "bill", "loan", "emi", "insurance", "tax", "expense",
        "registration", "fuel", "groceries", "payment", "debt", "card"
    )

    for raw in lines:
        line = raw.strip(" -*•\t")
        if not line:
            continue

        if _is_income_heading(line):
            section = "income"
            continue
        if _is_expense_heading(line):
            section = "expense"
            continue

        label, amount = _extract_label_amount(line, parse_finance_amount)
        if amount is None:
            continue

        lowered_label = label.lower()
        item = {"label": label, "amount": amount}

        if section == "income":
            income_items.append(item)
        elif section == "expense":
            expense_items.append(item)
        elif any(hint in lowered_label for hint in income_hints):
            income_items.append(item)
        elif any(hint in lowered_label for hint in expense_hints):
            expense_items.append(item)

    salary_window = parse_salary_credit_window(text)
    credit_card = parse_credit_card_snapshot(text, expense_items, parse_finance_amount)
    return {
        "income_items": income_items,
        "expense_items": expense_items,
        "salary_window": salary_window,
        "credit_card": credit_card
    }


def is_finance_advisory_request(text):
    lowered = str(text or "").lower().strip()
    if not lowered:
        return False

    advisory_phrases = (
        "what's your understanding", "whats your understanding", "understanding of this",
        "summarize this", "analyze my finances", "what do you think",
        "give me your assessment", "how healthy is my financial situation",
        "can i afford", "can i spend", "if i pay", "how much will i have left", "how much do i have left",
        "cash flow", "until payday", "before payday", "next salary", "payday",
        "credit card statement", "future liability", "projected balance", "surplus", "deficit",
        "buy this now", "should i wait until salary"
    )
    if any(phrase in lowered for phrase in advisory_phrases):
        return True

    has_income_expense_words = "income" in lowered and ("expenses" in lowered or "expense" in lowered)
    has_multiple_numbers = len(re.findall(r"\d[\d.,]*", lowered)) >= 3
    return has_income_expense_words and has_multiple_numbers


def parse_affordability_request(text, parse_finance_amount):
    lowered = str(text or "").lower()
    amount = None
    intent_amount_patterns = (
        r"(?:afford|spend|pay|buy|purchase|book|booking)\D{0,20}(€?\s*\d[\d.,]*)",
        r"(€\s*\d[\d.,]*)"
    )
    for pattern in intent_amount_patterns:
        matches = re.findall(pattern, lowered)
        if matches:
            candidate = parse_finance_amount(matches[-1])
            if candidate is not None:
                amount = candidate
                break
    if amount is None:
        numeric_tokens = re.findall(r"\d[\d.,]*", lowered)
        parsed_values = []
        for token in numeric_tokens:
            parsed = parse_finance_amount(token)
            if parsed is not None:
                parsed_values.append(parsed)
        if parsed_values:
            filtered = [v for v in parsed_values if v > 31]
            amount = max(filtered) if filtered else max(parsed_values)

    category_map = {
        "washing machine": "home appliance",
        "hotel": "travel",
        "booking": "travel",
        "advanzia": "credit card",
        "grocer": "groceries",
        "fuel": "transport",
        "car": "transport",
        "insurance": "insurance",
        "emi": "debt"
    }
    category = "general"
    for keyword, label in category_map.items():
        if keyword in lowered:
            category = label
            break
    essential_keywords = (
        "rent", "emi", "loan", "insurance", "electricity", "light bill",
        "mobile bill", "tax", "medicine", "groceries", "food", "school"
    )
    is_essential = any(token in lowered for token in essential_keywords) or category in {"insurance", "debt", "groceries"}

    timing = "this_month"
    if "before salary" in lowered or "until salary" in lowered or "before payday" in lowered:
        timing = "before_salary"
    elif "next month" in lowered:
        timing = "next_month"
    elif "now" in lowered:
        timing = "now"

    payment_method = "cash_or_bank"
    if any(word in lowered for word in ("card", "credit card", "advanzia")):
        payment_method = "credit_card"

    action_type = "purchase"
    if re.search(r"\bpay\b", lowered) and any(token in lowered for token in ("advanzia", "credit card", "card bill", "statement")):
        action_type = "card_bill_payment"
        payment_method = "cash_or_bank"

    return {
        "amount": amount,
        "category": category,
        "timing": timing,
        "payment_method": payment_method,
        "action_type": action_type,
        "is_essential": is_essential
    }


def classify_risk_level(value, forces_credit_dependency=False):
    if value < 0 or forces_credit_dependency:
        return "critical"
    if value < 200:
        return "risky"
    if value <= 500:
        return "tight"
    return "safe"


def is_financial_understanding_prompt(text):
    lowered = str(text or "").lower()
    phrases = (
        "what's your understanding", "whats your understanding", "understanding of this",
        "summarize this", "analyze my finances", "what do you think",
        "give me your assessment", "how healthy is my financial situation"
    )
    return any(phrase in lowered for phrase in phrases)


def infer_pressure_bucket(label):
    lowered = str(label or "").lower()
    if "rent" in lowered or "housing" in lowered:
        return "Housing costs"
    if any(token in lowered for token in ("car", "fuel", "registration", "plate", "insurance", "tax")):
        return "Vehicle-related expenses"
    if any(token in lowered for token in ("loan", "emi", "klarna", "debt")):
        return "Loan commitments"
    if any(token in lowered for token in ("credit card", "advanzia", "card bill", "statement")):
        return "Credit-card liabilities"
    if any(token in lowered for token in ("subscription", "netflix", "mobile", "internet")):
        return "High recurring subscriptions"
    return "Recurring commitments"


def collect_pressure_points(expense_items, baseline_pressure_items):
    totals = {}
    for item in expense_items or []:
        bucket = infer_pressure_bucket(item.get("label"))
        totals[bucket] = totals.get(bucket, 0.0) + float(item.get("amount") or 0)
    for item in baseline_pressure_items or []:
        bucket = infer_pressure_bucket(item.get("label"))
        totals[bucket] = totals.get(bucket, 0.0) + float(item.get("amount") or 0)
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    return ranked[:4]


def get_financial_health_rating(monthly_left, expected_next_card_statement, forces_credit_dependency=False):
    surplus_after_liabilities = round(float(monthly_left or 0) - float(expected_next_card_statement or 0), 2)
    if monthly_left < 0 or surplus_after_liabilities < 0 or forces_credit_dependency:
        return "Critical", surplus_after_liabilities
    if surplus_after_liabilities > 1000:
        return "Comfortable", surplus_after_liabilities
    if surplus_after_liabilities >= 500:
        return "Stable", surplus_after_liabilities
    if surplus_after_liabilities >= 200:
        return "Tight", surplus_after_liabilities
    return "Stressed", surplus_after_liabilities


def build_comfort_view(health_rating):
    if health_rating == "Comfortable":
        return "You appear financially comfortable with a healthy margin."
    if health_rating == "Stable":
        return "You appear financially stable with a reasonable buffer."
    if health_rating == "Tight":
        return "This is mathematically manageable, but not financially comfortable."
    if health_rating == "Stressed":
        return "Your obligations are manageable for now, but unexpected expenses could create pressure."
    return "Your current pattern suggests financial stress and dependency risk if spending continues."


def build_recommendation_from_health(health_rating):
    if health_rating == "Comfortable":
        return "buy now"
    if health_rating == "Stable":
        return "buy now"
    if health_rating == "Tight":
        return "wait until salary"
    if health_rating == "Stressed":
        return "pay partially"
    return "avoid this month"


def format_timeline_events(timeline_events, now, format_eur):
    if not timeline_events:
        return []

    month_label = now.strftime("%b")
    normalized = []
    for row in timeline_events:
        day = int(row.get("day") or 0)
        if day <= 0:
            continue
        normalized.append({
            "day": day,
            "title": str(row.get("title") or "Cash event"),
            "amount": float(row.get("amount") or 0)
        })

    normalized.sort(key=lambda x: x["day"])
    lines = ["📅 Upcoming Timeline", ""]
    for event in normalized[:6]:
        lines.append(f"{event['day']} {month_label}:")
        lines.append(f"- {event['title']} ({format_eur(event['amount'])})")
        lines.append("")
    return lines


def build_recommendation(risk_level, payment_method, action_type, timing, is_essential=False):
    if risk_level == "safe":
        if payment_method == "credit_card" and action_type == "purchase":
            return "buy now (card is fine, but next statement will be higher)"
        return "buy now"
    if risk_level == "tight":
        if is_essential and timing != "before_salary":
            return "pay partially"
        if is_essential and timing == "before_salary":
            return "wait until salary"
        if timing == "before_salary":
            return "wait until salary"
        return "wait until salary"
    if risk_level == "risky":
        if is_essential or action_type == "card_bill_payment":
            return "pay partially"
        return "avoid this month"
    if action_type == "card_bill_payment":
        return "pay partially"
    return "avoid this month (do not buy or pay full amount now)"


def _next_date_with_day(today, target_day):
    try:
        candidate = date(today.year, today.month, target_day)
    except ValueError:
        candidate = date(today.year, today.month, 28)
    if candidate >= today:
        return candidate
    next_month = today.month + 1
    next_year = today.year
    if next_month > 12:
        next_month = 1
        next_year += 1
    try:
        return date(next_year, next_month, target_day)
    except ValueError:
        return date(next_year, next_month, 28)


def build_finance_advisory_reply(text, timezone, parse_finance_amount, format_eur, baseline=None):
    snapshot = parse_finance_snapshot_text(text, parse_finance_amount)
    income_items = snapshot["income_items"]
    expense_items = snapshot["expense_items"]
    if not income_items and not expense_items and not snapshot.get("credit_card") and not baseline:
        return None

    baseline_income = float((baseline or {}).get("monthly_income") or 0)
    baseline_fixed_expenses = float((baseline or {}).get("fixed_expenses") or 0)
    baseline_salary_window = (baseline or {}).get("salary_window") or (12, 15)
    baseline_payday_day = int((baseline or {}).get("salary_payday_day") or 15)
    baseline_card_liability = float((baseline or {}).get("credit_card_liability") or 0)
    baseline_next_card = float((baseline or {}).get("expected_next_card_statement") or baseline_card_liability)
    baseline_pressure_items = (baseline or {}).get("pressure_items") or []
    baseline_timeline_events = (baseline or {}).get("timeline_events") or []
    baseline_trend_lines = (baseline or {}).get("trend_lines") or []
    repeated_value_suggestion = (baseline or {}).get("repeated_value_suggestion")

    monthly_income = round(sum(item["amount"] for item in income_items), 2) if income_items else round(baseline_income, 2)
    monthly_expenses = round(sum(item["amount"] for item in expense_items), 2) if expense_items else round(baseline_fixed_expenses, 2)
    monthly_left = round(monthly_income - monthly_expenses, 2)

    now = datetime.now(timezone).date()
    salary_start, salary_end = baseline_salary_window
    calculation_payday_day = baseline_payday_day
    salary_day_source = "default"

    explicit_from_text = extract_explicit_salary_day(text)
    if explicit_from_text is not None:
        calculation_payday_day = explicit_from_text
        salary_start, salary_end = explicit_from_text, explicit_from_text
        salary_day_source = "explicit_current_message"
    else:
        window_from_text = snapshot.get("salary_window")
        if window_from_text and tuple(window_from_text) != (12, 15):
            salary_start, salary_end = window_from_text
            calculation_payday_day = max(1, min(int(salary_end), 31))
            salary_day_source = "range_from_text"
        elif baseline_payday_day != 15:
            calculation_payday_day = baseline_payday_day
            salary_start, salary_end = baseline_salary_window
            salary_day_source = "explicit_recent_message"

    next_payday = _next_date_with_day(now, calculation_payday_day)
    days_until_payday = max((next_payday - now).days, 0)
    daily_burn = round(monthly_expenses / 30, 2) if monthly_expenses > 0 else 0.0
    needed_until_payday = round(daily_burn * days_until_payday, 2)
    cushion_until_payday = round(monthly_left - needed_until_payday, 2)

    lines = [
        "💼 Finance Advisory (Read-only)",
        "No values were saved. This is analysis only.",
        "",
        "📊 Monthly cash-flow",
        f"- Total income: {format_eur(monthly_income)}",
        f"- Total fixed expenses: {format_eur(monthly_expenses)}",
        f"- Expected monthly left: {format_eur(monthly_left)}"
    ]

    lines.extend([
        "",
        "⏳ Until payday view",
        f"- Salary usually expected between day {baseline_salary_window[0]} and day {baseline_salary_window[1]}",
        f"- Calculation payday used: day {calculation_payday_day}",
        f"- Days until payday: {days_until_payday}",
        f"- Estimated burn until payday: {format_eur(needed_until_payday)}",
        f"- Estimated cushion until payday: {format_eur(cushion_until_payday)}"
    ])
    if salary_day_source == "explicit_current_message":
        lines.append("- Salary date source: explicit date from your current message.")
    elif salary_day_source == "explicit_recent_message":
        lines.append("- Salary date source: latest explicit date from recent conversation.")
    elif salary_day_source == "range_from_text":
        lines.append("- Salary date source: range mentioned in your text; using conservative end of range.")
    else:
        lines.append("- Salary date source: default conservative day 15.")
    if cushion_until_payday < 0:
        lines.append("- Health: 🔴 Cash-pressure risk before payday.")
    elif cushion_until_payday < 250:
        lines.append("- Health: 🟠 Tight buffer before payday.")
    else:
        lines.append("- Health: 🟢 Buffer looks manageable.")

    credit_card = snapshot.get("credit_card")
    current_card_liability = baseline_card_liability
    expected_next_card_statement = baseline_next_card
    if credit_card:
        if credit_card.get("current_statement_amount") is not None:
            current_card_liability = float(credit_card.get("current_statement_amount") or 0)
        if credit_card.get("expected_next_statement_amount") is not None:
            expected_next_card_statement = float(credit_card.get("expected_next_statement_amount") or 0)
        lines.extend(["", "💳 Credit-card outlook"])
        statement_day = credit_card.get("statement_day")
        if statement_day:
            next_statement_date = _next_date_with_day(now, statement_day)
            lines.append(f"- Statement day: {statement_day} (next: {next_statement_date.isoformat()})")
        else:
            lines.append("- Statement day: not specified")

        due_day = credit_card.get("payment_due_day")
        if due_day:
            lines.append(f"- Payment due day: {due_day}")

        current_amount = current_card_liability
        expected_next = expected_next_card_statement
        if current_amount:
            lines.append(f"- Current statement amount: {format_eur(current_amount)}")
        if expected_next:
            lines.append(f"- Expected next statement: {format_eur(expected_next)}")
            future_left = round(monthly_left - float(expected_next), 2)
            lines.append(f"- Future liability impact: monthly left after statement ≈ {format_eur(future_left)}")

        lines.append("- Note: current spending typically appears on a future statement cycle.")
    elif current_card_liability or expected_next_card_statement:
        lines.extend([
            "",
            "💳 Credit-card outlook",
            f"- Current statement amount: {format_eur(current_card_liability)}",
            f"- Expected next statement: {format_eur(expected_next_card_statement)}",
            "- Note: current spending typically appears on a future statement cycle."
        ])

    default_forces_credit_dependency = cushion_until_payday < 0 and expected_next_card_statement > 0
    health_rating, surplus_after_liabilities = get_financial_health_rating(
        monthly_left,
        expected_next_card_statement,
        forces_credit_dependency=default_forces_credit_dependency
    )

    if is_financial_understanding_prompt(text):
        pressure_points = collect_pressure_points(expense_items, baseline_pressure_items)

        positives = []
        if monthly_left > 0:
            positives.append("Income exceeds recurring obligations.")
        if monthly_left >= 0:
            positives.append("No monthly deficit detected.")
        if cushion_until_payday > 0:
            positives.append("There is still an estimated buffer before payday.")
        if expected_next_card_statement <= max(monthly_income * 0.35, 1):
            positives.append("Credit-card liability is currently manageable versus income.")

        risks = []
        if expected_next_card_statement > max(monthly_income * 0.35, 500):
            risks.append("Persistent high credit-card usage may tighten next month's flexibility.")
        if cushion_until_payday < 500:
            risks.append("Emergency buffer before payday is small.")
        if default_forces_credit_dependency:
            risks.append("You may depend on card/debt timing before salary arrives.")
        if any(name == "Loan commitments" for name, _ in pressure_points) and any(name == "Credit-card liabilities" for name, _ in pressure_points):
            risks.append("Multiple debt commitments reduce flexibility.")

        opportunities = []
        if any(name == "High recurring subscriptions" for name, _ in pressure_points):
            opportunities.append("Review recurring subscriptions and trim low-value ones.")
        if any(name == "Vehicle-related expenses" for name, _ in pressure_points):
            opportunities.append("Re-check vehicle costs (insurance/tax/registration) for possible reductions.")
        if expected_next_card_statement > 0:
            opportunities.append("Gradually reduce new card spending to lower next statement pressure.")
        if surplus_after_liabilities < 500:
            opportunities.append("Build an emergency buffer in small monthly steps until at least EUR 500.")
        if any(name == "Loan commitments" for name, _ in pressure_points):
            opportunities.append("If possible, evaluate partial early repayment on highest-cost debt.")

        lines.extend([
            "",
            "\U0001F9E0 Financial Understanding",
            f"- Overall situation: {health_rating.lower()}",
            f"- Financial health rating: {health_rating}",
            f"- Surplus after known liabilities: {format_eur(surplus_after_liabilities)}"
        ])

        lines.append("")
        lines.append("Key Pressure Points")
        if pressure_points:
            for name, amount in pressure_points[:4]:
                lines.append(f"- {name}: {format_eur(amount)}")
        else:
            lines.append("- No dominant pressure point detected from current data.")

        lines.append("")
        lines.append("Positive Observations")
        if positives:
            for item in positives[:4]:
                lines.append(f"- {item}")
        else:
            lines.append("- No strong positive signal yet from this snapshot.")

        lines.append("")
        lines.append("Risks and Warnings")
        if risks:
            for item in risks[:4]:
                lines.append(f"- {item}")
        else:
            lines.append("- No immediate structural warning detected.")

        lines.append("")
        lines.append("Improvement Opportunities")
        if opportunities:
            for item in opportunities[:4]:
                lines.append(f"- {item}")
        else:
            lines.append("- Keep monitoring and maintain current spending discipline.")

        lines.append("")
        lines.append(f"Comfort View: {build_comfort_view(health_rating)}")
        lines.append(f"- Suggested action style: {build_recommendation_from_health(health_rating)}")

    timeline_lines = format_timeline_events(baseline_timeline_events, now, format_eur)
    if timeline_lines:
        lines.extend([""] + timeline_lines)

    if baseline_trend_lines:
        lines.append("")
        lines.append("📈 Trend Detection")
        for item in baseline_trend_lines[:3]:
            lines.append(item)

    if repeated_value_suggestion:
        lines.extend([
            "",
            "💡 Action Suggestion",
            f"- {repeated_value_suggestion}",
            "- I will not save anything unless you explicitly confirm."
        ])

    lowered = str(text or "").lower()
    if any(phrase in lowered for phrase in ("can i afford", "can i spend", "can i buy", "how much will i have left", "how much do i have left", "should i wait until salary", "if i pay")):
        intent = parse_affordability_request(text, parse_finance_amount)
        amount = intent.get("amount")
        if amount:
            action_type = intent["action_type"]
            payment_method = intent["payment_method"]

            immediate_before_salary_impact = amount
            next_statement_delta = 0.0

            if action_type == "purchase" and payment_method == "credit_card":
                immediate_before_salary_impact = 0.0
                next_statement_delta = amount
            elif action_type == "card_bill_payment":
                immediate_before_salary_impact = amount
                next_statement_delta = -min(amount, expected_next_card_statement or 0.0)

            available_balance_estimate = round(monthly_left - immediate_before_salary_impact, 2)
            before_payday_balance = round(cushion_until_payday - immediate_before_salary_impact, 2)
            projected_next_statement = max(round((expected_next_card_statement or 0.0) + next_statement_delta, 2), 0.0)
            after_salary_balance = round(before_payday_balance + monthly_income - projected_next_statement, 2)

            cash_if_immediate = round(cushion_until_payday - amount, 2)
            forces_credit_dependency = (
                payment_method == "credit_card"
                and action_type == "purchase"
                and cash_if_immediate < 0
            )

            risk_level = classify_risk_level(before_payday_balance, forces_credit_dependency=forces_credit_dependency)
            recommendation = build_recommendation(
                risk_level,
                payment_method,
                action_type,
                intent["timing"],
                is_essential=intent.get("is_essential", False)
            )

            lines.extend([
                "",
                "🛍️ Affordability check",
                f"- Purchase/Payment amount: {format_eur(amount)}",
                f"- Category: {intent['category']}",
                f"- Timing: {intent['timing'].replace('_', ' ')}",
                f"- Payment method: {payment_method.replace('_', ' ')}",
                f"- Available balance estimate: {format_eur(available_balance_estimate)}",
                f"- Before-salary view: {format_eur(before_payday_balance)} estimated cushion",
                f"- After-salary view: {format_eur(after_salary_balance)} estimated post-salary position",
                f"- Remaining buffer after this action: {format_eur(before_payday_balance)}",
                f"- Risk level: {risk_level}",
                f"- Impact on next card statement: {format_eur(projected_next_statement)} projected",
                f"- Recommendation: {recommendation}"
            ])
            if before_payday_balance < 500:
                lines.append("- Comfort view: This may be mathematically possible, but not comfortable.")
            if payment_method == "credit_card" and action_type == "purchase":
                lines.append("- Card note: this does not reduce cash immediately, but increases the next statement.")
            elif action_type == "card_bill_payment":
                lines.append("- Card note: paying Advanzia reduces cash now and can reduce upcoming card liability.")
        else:
            lines.extend([
                "",
                "🛍️ Affordability check",
                "- I can estimate this, but I need the amount (for example: can I afford €500?)."
            ])

    lines.extend([
        "",
        "To save salary/rent/EMI/goals/plans, use Finance Setup and confirm with ✅ Save."
    ])
    return "\n".join(lines)
