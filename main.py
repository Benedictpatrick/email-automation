import io
import csv
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
from contextlib import asynccontextmanager

from backend.database import (
    init_db, get_all_settings, set_setting, get_campaign_stats,
    get_leads, get_lead_by_id, update_lead, delete_lead, clear_all_leads,
    bulk_insert_leads, reset_lead_statuses, log_activity, get_recent_logs,
    approve_lead, approve_all_generated
)
from backend.ai_engine import generate_email_for_lead, get_groq_limits
from backend.mailer import test_smtp_connection, send_single_email
from backend.dispatcher import dispatcher
from backend.config import BASE_DIR

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log_activity("AutoMail engine started and database initialized.", level="INFO")
    yield

app = FastAPI(title="AutoMail - B2B Outreach Engine", version="1.0.0", lifespan=lifespan)

# Mount static files
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/", response_class=HTMLResponse)
def index_page():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>AutoMail Engine Running</h1><p>Dashboard UI loading...</p>")

# ----------------- STATS & STATUS -----------------

@app.get("/api/stats")
def api_get_stats():
    stats = get_campaign_stats()
    dispatcher_status = dispatcher.get_status()
    return {
        "stats": stats,
        "dispatcher": dispatcher_status
    }

@app.get("/api/groq/limits")
def api_get_groq_limits(refresh: bool = False):
    settings = get_all_settings()
    key = settings.get("groq_api_key", "")
    return get_groq_limits(key, force_refresh=refresh)

# ----------------- LEADS MANAGEMENT -----------------

def parse_leads_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    ext = filename.lower().split(".")[-1]
    if ext == "csv":
        try:
            return pd.read_csv(io.BytesIO(content), encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(content), encoding="latin-1")
    elif ext in ["xlsx", "xls"]:
        return pd.read_excel(io.BytesIO(content))
    else:
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx / .xls files are supported.")

def auto_detect_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    mapping = {
        "email": None,
        "first_name": None,
        "company": None,
        "job_title": None,
        "website": None,
        "notes": None
    }
    for col in columns:
        norm = str(col).strip().lower().replace("_", " ")
        if norm in ["email", "e-mail", "mail", "email address", "work email", "contact email"]:
            mapping["email"] = col
        elif norm in ["first name", "firstname", "name", "contact name", "contact", "lead name"]:
            if not mapping["first_name"]: mapping["first_name"] = col
        elif norm in ["company", "company name", "organization", "account", "business", "business name"]:
            if not mapping["company"]: mapping["company"] = col
        elif norm in ["job title", "title", "role", "position", "designation"]:
            if not mapping["job_title"]: mapping["job_title"] = col
        elif norm in ["website", "domain", "url", "company url", "web", "site"]:
            if not mapping["website"]: mapping["website"] = col
        elif norm in ["notes", "context", "industry", "description", "summary", "pain point", "pain points"]:
            if not mapping["notes"]: mapping["notes"] = col
    return mapping

@app.get("/api/leads")
def api_get_leads(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200),
    offset: int = Query(0)
):
    leads = get_leads(status=status, search=search, limit=limit, offset=offset)
    return {"leads": leads}

@app.post("/api/leads/preview-file")
async def api_preview_file(file: UploadFile = File(...)):
    content = await file.read()
    try:
        df = parse_leads_dataframe(file.filename, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="The uploaded file contains no data.")

    # Fill NaN values with empty strings
    df = df.fillna("")
    columns = [str(c) for c in df.columns]
    mapping = auto_detect_columns(columns)

    preview_rows = df.head(5).to_dict(orient="records")

    return {
        "filename": file.filename,
        "total_rows": len(df),
        "columns": columns,
        "suggested_mapping": mapping,
        "preview_rows": preview_rows
    }

@app.post("/api/leads/upload")
async def api_upload_leads_file(
    file: UploadFile = File(...),
    email_col: Optional[str] = Form(None),
    first_name_col: Optional[str] = Form(None),
    company_col: Optional[str] = Form(None),
    job_title_col: Optional[str] = Form(None),
    website_col: Optional[str] = Form(None),
    notes_col: Optional[str] = Form(None)
):
    content = await file.read()
    try:
        df = parse_leads_dataframe(file.filename, content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="The uploaded file contains no data.")

    df = df.fillna("")
    columns = [str(c) for c in df.columns]
    auto_map = auto_detect_columns(columns)

    target_email_col = email_col or auto_map.get("email")
    if not target_email_col or target_email_col not in df.columns:
        raise HTTPException(status_code=400, detail=f"Could not locate an email column. Columns found: {', '.join(columns)}")

    target_name_col = first_name_col or auto_map.get("first_name")
    target_comp_col = company_col or auto_map.get("company")
    target_role_col = job_title_col or auto_map.get("job_title")
    target_web_col = website_col or auto_map.get("website")
    target_notes_col = notes_col or auto_map.get("notes")

    leads_to_insert = []
    for _, row in df.iterrows():
        email = str(row.get(target_email_col, "")).strip().lower()
        if not email or "@" not in email:
            continue
        leads_to_insert.append({
            "email": email,
            "first_name": str(row.get(target_name_col, "")).strip() if target_name_col else "",
            "company": str(row.get(target_comp_col, "")).strip() if target_comp_col else "",
            "job_title": str(row.get(target_role_col, "")).strip() if target_role_col else "",
            "website": str(row.get(target_web_col, "")).strip() if target_web_col else "",
            "notes": str(row.get(target_notes_col, "")).strip() if target_notes_col else "",
        })

    result = bulk_insert_leads(leads_to_insert)
    log_activity(f"Imported '{file.filename}': {result['inserted']} leads added, {result['duplicates']} duplicates skipped.", level="INFO")
    return {
        "success": True,
        "filename": file.filename,
        "imported": result["inserted"],
        "duplicates": result["duplicates"],
        "total_in_file": len(leads_to_insert)
    }

class UpdateLeadRequest(BaseModel):
    first_name: Optional[str] = None
    company: Optional[str] = None
    job_title: Optional[str] = None
    website: Optional[str] = None
    notes: Optional[str] = None
    email_subject: Optional[str] = None
    email_body: Optional[str] = None
    status: Optional[str] = None

@app.post("/api/leads/{lead_id}/update")
def api_update_lead(lead_id: int, payload: UpdateLeadRequest):
    lead = get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    data = {k: v for k, v in payload.dict().items() if v is not None}
    update_lead(lead_id, **data)
    return {"success": True, "lead": get_lead_by_id(lead_id)}

@app.delete("/api/leads/{lead_id}")
def api_delete_lead(lead_id: int):
    delete_lead(lead_id)
    return {"success": True}

@app.post("/api/leads/clear")
def api_clear_leads():
    clear_all_leads()
    log_activity("All leads and logs cleared from database.", level="WARNING")
    return {"success": True}

@app.post("/api/leads/reset-status")
def api_reset_status(target: str = Form("pending")):
    reset_lead_statuses(target)
    log_activity(f"Reset all lead statuses to '{target}'.", level="INFO")
    return {"success": True}

# ----------------- AI PERSONALIZATION -----------------

class GenerateLeadRequest(BaseModel):
    custom_prompt: Optional[str] = None

@app.post("/api/leads/{lead_id}/generate")
def api_generate_single_lead(lead_id: int, payload: Optional[GenerateLeadRequest] = None):
    lead = get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    settings = get_all_settings()
    custom_prompt = payload.custom_prompt if payload else None

    result = generate_email_for_lead(
        lead=lead,
        api_key=settings.get("gemini_api_key"),
        agency_name=settings.get("agency_name"),
        sender_name=settings.get("from_name"),
        custom_prompt=custom_prompt,
        provider=settings.get("ai_provider"),
        groq_api_key=settings.get("groq_api_key"),
        groq_model=settings.get("groq_model")
    )

    update_lead(
        lead_id,
        email_subject=result["subject"],
        email_body=result["body"],
        custom_hook=result.get("custom_hook", ""),
        status="generated"
    )
    log_activity(f"Generated personalized email for {lead['email']} via {result.get('source', 'engine')}", level="SUCCESS", lead_email=lead['email'])
    return {"success": True, "generated": result, "lead": get_lead_by_id(lead_id)}

@app.post("/api/leads/batch-generate")
def api_batch_generate(payload: Optional[GenerateLeadRequest] = None):
    leads = get_leads(status="pending", limit=100)
    if not leads:
        return {"success": True, "count": 0, "message": "No pending leads found to generate."}

    settings = get_all_settings()
    custom_prompt = payload.custom_prompt if payload else None
    count = 0

    for lead in leads:
        res = generate_email_for_lead(
            lead=lead,
            api_key=settings.get("gemini_api_key"),
            agency_name=settings.get("agency_name"),
            sender_name=settings.get("from_name"),
            custom_prompt=custom_prompt,
            provider=settings.get("ai_provider"),
            groq_api_key=settings.get("groq_api_key"),
            groq_model=settings.get("groq_model")
        )
        update_lead(
            lead["id"],
            email_subject=res["subject"],
            email_body=res["body"],
            custom_hook=res.get("custom_hook", ""),
            status="generated"
        )
        count += 1

    log_activity(f"Batch generation completed: {count} leads personalized.", level="SUCCESS")
    return {"success": True, "count": count}

# ----------------- APPROVAL & PREVIEW -----------------

@app.post("/api/leads/{lead_id}/approve")
def api_approve_lead(lead_id: int):
    lead = get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")
    approve_lead(lead_id)
    log_activity(f"Approved email draft for {lead['email']}.", level="SUCCESS", lead_email=lead['email'])
    return {"success": True, "lead": get_lead_by_id(lead_id)}

@app.post("/api/leads/approve-all")
def api_approve_all():
    approve_all_generated()
    log_activity("All generated leads have been approved.", level="SUCCESS")
    return {"success": True}

class SendPreviewRequest(BaseModel):
    recipient_email: Optional[str] = None

@app.post("/api/leads/{lead_id}/send-preview")
def api_send_lead_preview(lead_id: int, payload: Optional[SendPreviewRequest] = None):
    lead = get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    settings = get_all_settings()
    target_email = (payload.recipient_email if payload and payload.recipient_email else None) or settings.get("from_email") or settings.get("smtp_user")
    if not target_email or "@" not in target_email:
        raise HTTPException(status_code=400, detail="No destination email specified for preview.")

    subject = lead.get("email_subject") or f"Question for {lead.get('company')}"
    body = lead.get("email_body") or "No email body has been generated for this lead yet."

    preview_subject = f"[PREVIEW FOR: {lead.get('company') or lead['email']}] {subject}"
    preview_body = f"""==================================================
PREVIEW INSPECTION EMAIL: This is the exact email that would be delivered to {lead.get('first_name')} ({lead['email']}) at {lead.get('company')}.
==================================================

{body}

==================================================
Target Lead Details:
- Contact: {lead.get('first_name')} {lead.get('job_title')}
- Company: {lead.get('company')}
- Website: {lead.get('website')}
- AI Hook: {lead.get('custom_hook')}
=================================================="""

    success, msg = send_single_email(
        to_email=target_email,
        to_name="You (Preview)",
        subject=preview_subject,
        body=preview_body,
        settings=settings
    )
    if success:
        log_activity(f"Sent preview copy of lead {lead['email']} to {target_email}", level="SUCCESS")
        return {"success": True, "message": f"Preview email sent to {target_email}!"}
    else:
        log_activity(f"Failed to send preview for {lead['email']}: {msg}", level="ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to send preview: {msg}")

@app.post("/api/leads/{lead_id}/send-now")
def api_send_lead_now(lead_id: int):
    lead = get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    settings = get_all_settings()
    subject = lead.get("email_subject")
    body = lead.get("email_body")

    # If email hasn't been generated yet, auto-generate with Groq AI first
    if not subject or not body:
        gen_result = generate_email_for_lead(
            lead=lead,
            api_key=settings.get("gemini_api_key"),
            agency_name=settings.get("agency_name"),
            sender_name=settings.get("from_name"),
            provider=settings.get("ai_provider"),
            groq_api_key=settings.get("groq_api_key"),
            groq_model=settings.get("groq_model")
        )
        subject = gen_result["subject"]
        body = gen_result["body"]
        update_lead(
            lead_id,
            email_subject=subject,
            email_body=body,
            custom_hook=gen_result.get("custom_hook", ""),
            status="generated"
        )

    # Deliver via SMTP to the prospect
    success, msg = send_single_email(
        to_email=lead["email"],
        to_name=lead.get("first_name", ""),
        subject=subject,
        body=body,
        settings=settings
    )

    if success:
        update_lead(lead_id, status="sent", sent_at=datetime.now().isoformat(), error_message="")
        log_activity(f"Single send: Delivered cold outreach email to {lead['email']} ({lead.get('company')})", level="SUCCESS", lead_email=lead['email'])
        return {"success": True, "message": f"Outreach email delivered to {lead['email']}!"}
    else:
        update_lead(lead_id, status="failed", error_message=msg)
        log_activity(f"Single send failed to {lead['email']}: {msg}", level="ERROR", lead_email=lead['email'])
        raise HTTPException(status_code=500, detail=f"Failed to send email: {msg}")

# ----------------- QUICK ACCOUNT ONBOARDING (FOR YOU & FRIENDS) -----------------

class QuickSetupRequest(BaseModel):
    from_name: Optional[str] = None
    agency_name: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    groq_api_key: Optional[str] = None

@app.post("/api/account/quick-setup")
def api_account_quick_setup(payload: QuickSetupRequest):
    if payload.from_name:
        set_setting("from_name", payload.from_name.strip())
    if payload.agency_name:
        set_setting("agency_name", payload.agency_name.strip())
    if payload.smtp_user:
        user = payload.smtp_user.strip()
        set_setting("smtp_user", user)
        set_setting("from_email", user)
        set_setting("smtp_host", "smtp.gmail.com")
        set_setting("smtp_port", "587")
    if payload.smtp_password and payload.smtp_password.strip() != "••••••••••••":
        pwd = payload.smtp_password.strip().replace(" ", "")
        set_setting("smtp_password", pwd)
    if payload.groq_api_key:
        key = payload.groq_api_key.strip()
        set_setting("groq_api_key", key)
        set_setting("ai_provider", "groq")

    # Verify SMTP
    settings = get_all_settings()
    smtp_ok, smtp_msg = verify_smtp_credentials(settings)

    # Verify Groq
    groq_res = get_groq_limits(settings.get("groq_api_key"), force_refresh=True)
    groq_ok = groq_res.get("connected", False)

    log_activity(f"Quick Account Setup completed: SMTP={smtp_ok}, Groq={groq_ok}", level="SUCCESS" if (smtp_ok and groq_ok) else "WARNING")

    return {
        "success": True,
        "smtp_ok": smtp_ok,
        "smtp_message": smtp_msg,
        "groq_ok": groq_ok,
        "groq_message": groq_res.get("status") or groq_res.get("error", "Key verified"),
        "settings": {
            "from_name": settings.get("from_name"),
            "agency_name": settings.get("agency_name"),
            "smtp_user": settings.get("smtp_user"),
            "groq_connected": groq_ok
        }
    }

@app.post("/api/account/clear")
def api_account_clear():
    set_setting("smtp_user", "")
    set_setting("from_email", "")
    set_setting("smtp_password", "")
    set_setting("groq_api_key", "")
    set_setting("gemini_api_key", "")
    log_activity("Account credentials cleared for secure sharing.", level="WARNING")
    return {"success": True, "message": "Credentials cleared. Ready to share with your friend."}

# ----------------- SETTINGS & SMTP -----------------

@app.get("/api/settings")
def api_get_settings():
    settings = get_all_settings()
    # Mask password for security
    masked = dict(settings)
    if masked.get("smtp_password"):
        masked["smtp_password_masked"] = "••••••••••••"
    return {"settings": masked}

@app.post("/api/settings")
def api_update_settings(payload: Dict[str, str]):
    for k, v in payload.items():
        if k == "smtp_password" and v.strip() == "••••••••••••":
            continue
        set_setting(k, v)
    log_activity("Settings updated successfully.", level="INFO")
    return {"success": True, "settings": get_all_settings()}

@app.post("/api/smtp/test-connection")
def api_test_smtp():
    settings = get_all_settings()
    success, message = test_smtp_connection(settings)
    return {"success": success, "message": message}

class TestSendRequest(BaseModel):
    target_email: str

@app.post("/api/smtp/test-send")
def api_test_send(payload: TestSendRequest):
    settings = get_all_settings()
    target = payload.target_email.strip()
    if not target or "@" not in target:
        raise HTTPException(status_code=400, detail="Valid target email required.")

    subject = f"Test Email: AutoMail Automation Engine for {settings.get('agency_name', 'Agency')}"
    body = f"""Hi there,

This is a test verification email from your AutoMail Cold Outreach Engine.

If you received this in your primary inbox, your SMTP credentials and deliverability headers are working properly!

Settings verified:
- Sender Name: {settings.get('from_name')}
- Host: {settings.get('smtp_host')}
- Agency: {settings.get('agency_name')}

You are ready to launch your cold outreach campaign.

Best regards,
{settings.get('from_name', 'The Automation Team')}"""

    success, msg = send_single_email(
        to_email=target,
        to_name="Test Recipient",
        subject=subject,
        body=body,
        settings=settings
    )
    if success:
        log_activity(f"Test email successfully delivered to {target}", level="SUCCESS")
        return {"success": True, "message": f"Test email sent to {target}!"}
    else:
        log_activity(f"Test email failed: {msg}", level="ERROR")
        return {"success": False, "message": msg}

# ----------------- CAMPAIGN DISPATCHER -----------------

class StartCampaignRequest(BaseModel):
    dry_run: bool = False
    lead_ids: Optional[List[int]] = None
    only_approved: bool = False

@app.post("/api/campaign/start")
def api_start_campaign(payload: StartCampaignRequest):
    success, msg = dispatcher.start_campaign(
        dry_run=payload.dry_run, 
        lead_ids=payload.lead_ids,
        only_approved=payload.only_approved
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@app.post("/api/campaign/pause")
def api_pause_campaign():
    success, msg = dispatcher.pause_campaign()
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@app.post("/api/campaign/stop")
def api_stop_campaign():
    success, msg = dispatcher.stop_campaign()
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

# ----------------- LOGS & EXPORT -----------------

@app.get("/api/logs")
def api_get_logs(limit: int = 100):
    return {"logs": get_recent_logs(limit=limit)}

@app.get("/api/export")
def api_export_csv():
    leads = get_leads(limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "email", "first_name", "company", "job_title", 
        "website", "notes", "status", "email_subject", "email_body", "sent_at", "error_message"
    ])
    for l in leads:
        writer.writerow([
            l.get("id"), l.get("email"), l.get("first_name"), l.get("company"),
            l.get("job_title"), l.get("website"), l.get("notes"), l.get("status"),
            l.get("email_subject"), l.get("email_body"), l.get("sent_at"), l.get("error_message")
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=automail_leads_export.csv"}
    )

if __name__ == "__main__":
    import uvicorn
    # Stable execution without spurious reloads from temp/cache/db files
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
