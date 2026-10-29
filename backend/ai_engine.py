import os
import json
import logging
from typing import Dict, Any, Optional
from backend.spintax import render_spintax_template, DEFAULT_TEMPLATES
from backend.config import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

def detect_department(title: str) -> str:
    t = (title or "").lower()
    if any(k in t for k in ["hr", "human resource", "talent", "recruit", "people", "hiring"]):
        return "hr"
    if any(k in t for k in ["operat", "ops", "coo", "supply", "logistics", "workflow", "process"]):
        return "operations"
    if any(k in t for k in ["sales", "cro", "bd", "business dev", "account exec", "growth", "revenue"]):
        return "sales"
    return "general"

def generate_with_groq(
    lead: Dict[str, Any],
    api_key: str,
    agency_name: str,
    sender_name: str,
    model: str = "openai/gpt-oss-120b",
    custom_prompt: Optional[str] = None
) -> Dict[str, str]:
    from groq import Groq
    client = Groq(api_key=api_key.strip())

    first_name = (lead.get("first_name") or "there").strip()
    company = (lead.get("company") or "your company").strip()
    job_title = (lead.get("job_title") or "Team").strip()
    website = (lead.get("website") or "").strip()
    notes = (lead.get("notes") or "").strip()
    dept = detect_department(job_title)

    system_instruction = f"""You are an elite B2B cold email copywriter working for an Automation Agency named "{agency_name}".
Your task is to write a high-converting, crisp, human-sounding cold outreach email to a decision-maker.
Sender signature name: "{sender_name}". Never output placeholders like [Name] or [Your Name]; always sign with "{sender_name}".

CRITICAL RULES:
1. Length: Maximum 70 to 100 words. Extremely concise and scannable.
2. Tone: Casual, professional, peer-to-peer. NO hype words (never say 'revolutionary', 'game-changing', 'synergy').
3. Focus on their role: Address specific daily headaches of a {job_title} at {company} (e.g. HR candidate screening & scheduling, Ops spreadsheet reconciliation, Sales lead routing).
4. Low friction Call To Action: Ask if they are open to a 2-minute video overview or a brief exchange next week.
5. You MUST return ONLY valid JSON with keys:
   - "subject": Short, curiosity-piquing subject line (under 6 words).
   - "body": The email body with clean paragraphs and signed by "{sender_name}".
   - "custom_hook": 1 short sentence describing the specific automation angle used.
"""

    user_prompt = f"""Target Lead Information:
- Contact Name: {first_name}
- Job Title: {job_title}
- Company: {company}
- Website: {website}
- Context/Industry Notes: {notes}
- Department: {dept}

Additional Guidance: {custom_prompt or "Focus on eliminating manual repetitive tasks and saving 15+ hours a week via custom AI workflows."}

Return JSON with keys 'subject', 'body', 'custom_hook'."""

    models_to_try = [model, "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
    models_to_try = list(dict.fromkeys(models_to_try))

    last_error = None
    for m in models_to_try:
        try:
            completion = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            raw = completion.choices[0].message.content.strip()
            data = json.loads(raw)
            return {
                "subject": data.get("subject", f"Quick question for {company}"),
                "body": data.get("body", "").replace("[Your Name]", sender_name).replace("[Name]", sender_name),
                "custom_hook": data.get("custom_hook", f"AI automation tailored for {job_title}"),
                "source": f"groq ({m})"
            }
        except Exception as e:
            last_error = e
            logger.warning(f"Groq model {m} failed: {e}. Trying next...")

    raise last_error or Exception("All Groq models failed.")

def generate_with_gemini(
    lead: Dict[str, Any],
    api_key: str,
    agency_name: str,
    sender_name: str,
    custom_prompt: Optional[str] = None
) -> Dict[str, str]:
    from google import genai
    client = genai.Client(api_key=api_key.strip())

    first_name = (lead.get("first_name") or "there").strip()
    company = (lead.get("company") or "your company").strip()
    job_title = (lead.get("job_title") or "Team").strip()
    website = (lead.get("website") or "").strip()
    notes = (lead.get("notes") or "").strip()
    dept = detect_department(job_title)

    system_instruction = f"""You are an elite B2B cold email copywriter working for an Automation Agency named "{agency_name}".
Sender signature name: "{sender_name}". Never output placeholders like [Name]; sign with "{sender_name}".
Write a crisp cold outreach email (70-100 words) pitching custom AI workflow automation for {job_title}.
Return raw JSON with keys: 'subject', 'body', 'custom_hook'."""

    user_prompt = f"Lead: {first_name}, {job_title} at {company}. Web: {website}. Notes: {notes}. Department: {dept}. {custom_prompt or ''}"

    model_name = "gemini-2.5-flash"
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config={"system_instruction": system_instruction, "temperature": 0.7}
        )
    except Exception:
        model_name = "gemini-1.5-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config={"system_instruction": system_instruction, "temperature": 0.7}
        )

    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        if lines[0].startswith("```"): lines = lines[1:]
        if lines and lines[-1].startswith("```"): lines = lines[:-1]
        raw_text = "\n".join(lines).strip()

    data = json.loads(raw_text)
    return {
        "subject": data.get("subject", f"Quick question for {company}"),
        "body": data.get("body", "").replace("[Your Name]", sender_name).replace("[Name]", sender_name),
        "custom_hook": data.get("custom_hook", f"AI automation tailored for {job_title}"),
        "source": f"gemini ({model_name})"
    }

def generate_email_for_lead(
    lead: Dict[str, Any],
    api_key: Optional[str] = None,
    agency_name: Optional[str] = None,
    sender_name: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    provider: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    groq_model: Optional[str] = None
) -> Dict[str, str]:
    """
    Intelligent multi-provider generation:
    1. Groq (Ultra-fast, LPU inference, high rate limits)
    2. Google Gemini
    3. Smart Spintax templates (Offline fallback)
    """
    first_name = (lead.get("first_name") or "there").strip()
    company = (lead.get("company") or "your company").strip()
    job_title = (lead.get("job_title") or "Team").strip()
    website = (lead.get("website") or "").strip()
    dept = detect_department(job_title)

    agency = agency_name or DEFAULT_SETTINGS.get("agency_name", "AutomaFlow")
    sender = sender_name or DEFAULT_SETTINGS.get("from_name", "Automation Team")
    groq_key = groq_api_key or os.getenv("GROQ_API_KEY", "")
    gemini_key = api_key or os.getenv("GEMINI_API_KEY", "")
    chosen_provider = provider or DEFAULT_SETTINGS.get("ai_provider", "groq")

    # 1. If explicit spintax is selected, skip AI
    if chosen_provider != "spintax":
        # 2. Try Groq if chosen or if groq key exists
        if chosen_provider == "groq" or (chosen_provider != "gemini" and groq_key and len(groq_key.strip()) > 10):
            if groq_key and len(groq_key.strip()) > 10:
                try:
                    return generate_with_groq(
                        lead=lead,
                        api_key=groq_key,
                        agency_name=agency,
                        sender_name=sender,
                        model=groq_model or "openai/gpt-oss-120b",
                        custom_prompt=custom_prompt
                    )
                except Exception as e:
                    logger.warning(f"Groq generation failed: {e}. Checking secondary providers...")

        # 3. Try Gemini
        if gemini_key and len(gemini_key.strip()) > 10:
            try:
                return generate_with_gemini(
                    lead=lead,
                    api_key=gemini_key,
                    agency_name=agency,
                    sender_name=sender,
                    custom_prompt=custom_prompt
                )
            except Exception as e:
                logger.warning(f"Gemini generation failed: {e}. Falling back to Spintax...")

    # 3. Smart Spintax template fallback
    tmpl = DEFAULT_TEMPLATES.get(dept, DEFAULT_TEMPLATES["general"])
    lead_context = {
        "first_name": first_name,
        "company": company,
        "job_title": job_title,
        "website": website,
        "sender_name": sender,
        "agency_name": agency,
    }

    subject = render_spintax_template(tmpl["subject"], lead_context)
    body = render_spintax_template(tmpl["body"], lead_context)

    return {
        "subject": subject,
        "body": body,
        "custom_hook": f"Smart Spintax Automation Template ({dept.upper()})",
        "source": "spintax_template"
    }

_GROQ_LIMITS_CACHE = {"timestamp": 0, "data": None}

def get_groq_limits(api_key: Optional[str] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Checks live rate limits directly from Groq's API headers.
    Caches results for 60 seconds to protect your free Groq API quota.
    """
    import time
    global _GROQ_LIMITS_CACHE
    now = time.time()

    if not force_refresh and _GROQ_LIMITS_CACHE["data"] and (now - _GROQ_LIMITS_CACHE["timestamp"] < 60):
        return _GROQ_LIMITS_CACHE["data"]

    key = api_key or os.getenv("GROQ_API_KEY", "")
    if not key or len(key.strip()) < 10:
        return {"connected": False, "error": "No Groq API Key configured."}

    import httpx
    try:
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key.strip()}"},
            json={
                "model": "openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            },
            timeout=8.0
        )
        headers = r.headers
        limit_req = int(headers.get("x-ratelimit-limit-requests", 1000))
        rem_req = int(headers.get("x-ratelimit-remaining-requests", 1000))
        limit_tok = int(headers.get("x-ratelimit-limit-tokens", 8000))
        rem_tok = int(headers.get("x-ratelimit-remaining-tokens", 8000))
        reset_req = headers.get("x-ratelimit-reset-requests", "0s")
        reset_tok = headers.get("x-ratelimit-reset-tokens", "0s")

        req_pct = round((rem_req / limit_req) * 100) if limit_req > 0 else 100
        tok_pct = round((rem_tok / limit_tok) * 100) if limit_tok > 0 else 100

        result = {
            "connected": True,
            "model": "openai/gpt-oss-120b",
            "limit_requests": limit_req,
            "remaining_requests": rem_req,
            "request_pct": req_pct,
            "limit_tokens": limit_tok,
            "remaining_tokens": rem_tok,
            "token_pct": tok_pct,
            "reset_requests": reset_req,
            "reset_tokens": reset_tok,
            "status": "Healthy & Active"
        }
        _GROQ_LIMITS_CACHE["timestamp"] = now
        _GROQ_LIMITS_CACHE["data"] = result
        return result
    except Exception as e:
        return {"connected": False, "error": str(e)}

