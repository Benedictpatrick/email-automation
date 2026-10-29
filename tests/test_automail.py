import os
import pytest
from fastapi.testclient import TestClient
from backend.database import (
    init_db, get_connection, bulk_insert_leads, get_leads,
    update_lead, delete_lead, clear_all_leads, get_campaign_stats,
    get_all_settings, set_setting
)
from backend.spintax import parse_spintax, fill_variables, render_spintax_template
from backend.ai_engine import detect_department, generate_email_for_lead
from backend.mailer import format_html_email
from main import app

client = TestClient(app)

def setup_module(module):
    init_db()
    clear_all_leads()

def test_spintax_parser():
    text = "{Hello|Hi|Greetings} world!"
    results = set()
    for _ in range(25):
        parsed = parse_spintax(text)
        results.add(parsed)
        assert "world!" in parsed
        assert any(greet in parsed for greet in ["Hello", "Hi", "Greetings"])
    assert len(results) > 1

def test_department_detection():
    assert detect_department("Head of People & HR") == "hr"
    assert detect_department("Talent Acquisition Manager") == "hr"
    assert detect_department("VP of Operations") == "operations"
    assert detect_department("Chief Operating Officer") == "operations"
    assert detect_department("Director of Sales") == "sales"
    assert detect_department("Founder & CEO") == "general"

def test_groq_generation():
    if not os.path.exists("api.txt"):
        return
    with open("api.txt", "r", encoding="utf-8") as f:
        key = f.read().strip()
    if not key:
        return

    lead = {
        "first_name": "Marcus",
        "company": "Apex Logistics",
        "job_title": "VP of Operations",
        "website": "apexlogistics.co",
        "notes": "Freight forwarding 3PL"
    }
    res = generate_email_for_lead(
        lead=lead,
        provider="groq",
        groq_api_key=key,
        groq_model="openai/gpt-oss-120b"
    )
    assert res["subject"]
    assert "Apex Logistics" in res["body"] or "Marcus" in res["body"] or "Apex" in res["body"]
    assert "groq" in res["source"]

def test_spintax_template_fallback():
    lead = {
        "first_name": "Elena",
        "company": "Finovate",
        "job_title": "Head of Operations",
        "website": "finovate.io",
        "notes": "Fast growing fintech"
    }
    result = generate_email_for_lead(lead, provider="spintax")
    assert result["subject"]
    assert "Elena" in result["body"]
    assert "Finovate" in result["body"]
    assert result["source"] == "spintax_template"

def test_html_email_formatting():
    text = "Hello Sarah,\n\nHope you are well.\n\nBest,\nAlex"
    html = format_html_email(text)
    assert "<!DOCTYPE html>" in html
    assert "Hello Sarah" in html
    assert "<p style=" in html

def test_database_crud():
    sample_leads = [
        {
            "email": "test1@sample.com",
            "first_name": "Test1",
            "company": "SampleCorp",
            "job_title": "HR Manager",
            "website": "sample.com",
            "notes": "Testing notes"
        },
        {
            "email": "test2@sample.com",
            "first_name": "Test2",
            "company": "SecondCorp",
            "job_title": "COO",
            "website": "second.com",
            "notes": ""
        }
    ]
    res = bulk_insert_leads(sample_leads)
    assert res["inserted"] == 2
    assert res["duplicates"] == 0

    # Test duplicate prevention
    res_dup = bulk_insert_leads(sample_leads)
    assert res_dup["inserted"] == 0
    assert res_dup["duplicates"] == 2

    leads = get_leads()
    assert len(leads) >= 2

    lead_id = leads[0]["id"]
    update_lead(lead_id, status="generated", email_subject="Custom Subject")
    updated = [l for l in get_leads() if l["id"] == lead_id][0]
    assert updated["status"] == "generated"
    assert updated["email_subject"] == "Custom Subject"

    stats = get_campaign_stats()
    assert stats["total"] >= 2
    assert stats["generated"] >= 1

def test_api_endpoints():
    # Stats
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "stats" in data
    assert "dispatcher" in data

    # Leads list
    r = client.get("/api/leads")
    assert r.status_code == 200
    assert "leads" in r.json()

    # Settings
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert "smtp_host" in r.json()["settings"]

    # CSV Upload test
    csv_content = "email,first_name,company,job_title\nalex@auto.io,Alex,AutoCorp,Director\n"
    r = client.post(
        "/api/leads/upload",
        files={"file": ("test_upload.csv", csv_content.encode("utf-8"), "text/csv")}
    )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert r.json()["imported"] == 1

def test_excel_upload_and_limits():
    import pandas as pd
    import io

    # Test Groq limits API
    r = client.get("/api/groq/limits")
    assert r.status_code == 200
    data = r.json()
    assert data["connected"] is True
    assert "remaining_requests" in data

    # Test Excel file preview & upload
    df = pd.DataFrame([
        {"Work Email": "client@enterprise.com", "Contact": "Robert", "Company Name": "Enterprise Corp", "Role": "VP Ops"}
    ])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)

    # Preview
    r = client.post(
        "/api/leads/preview-file",
        files={"file": ("test_leads.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    )
    assert r.status_code == 200
    preview_data = r.json()
    assert preview_data["total_rows"] == 1
    assert preview_data["suggested_mapping"]["email"] == "Work Email"
    assert preview_data["suggested_mapping"]["company"] == "Company Name"

    # Upload
    buf.seek(0)
    r = client.post(
        "/api/leads/upload",
        files={"file": ("test_leads.xlsx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"email_col": "Work Email", "first_name_col": "Contact", "company_col": "Company Name", "job_title_col": "Role"}
    )
    assert r.status_code == 200
    assert r.json()["imported"] == 1

