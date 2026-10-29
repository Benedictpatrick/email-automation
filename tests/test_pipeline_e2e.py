from backend.database import init_db, clear_all_leads, get_leads, get_campaign_stats
from backend.ai_engine import generate_email_for_lead
from backend.dispatcher import dispatcher
import csv

def test_full_sample_pipeline():
    init_db()
    clear_all_leads()

    # 1. Test leads data
    test_leads = [
        {"email": "director@opslead.io", "first_name": "Marcus", "company": "Apex Freight", "job_title": "VP Operations", "website": "apex.io", "notes": "Logistics ops"},
        {"email": "sarah@lumina.io", "first_name": "Sarah", "company": "Lumina", "job_title": "Head of HR", "website": "lumina.io", "notes": "Recruiting 20 staff"},
        {"email": "elena@finovate.io", "first_name": "Elena", "company": "Finovate", "job_title": "Founder", "website": "finovate.io", "notes": "Reconciliation"}
    ]

    # 2. Upload via API / bulk insert
    from backend.database import bulk_insert_leads
    res = bulk_insert_leads(test_leads)
    assert res["inserted"] == len(test_leads)

    leads = get_leads()
    assert len(leads) == len(test_leads)

    # 3. Test AI / Spintax generation across roles
    from backend.database import update_lead
    for lead in leads:
        gen = generate_email_for_lead(lead, provider="spintax")
        assert gen["subject"]
        assert gen["body"]
        assert lead["company"] in gen["body"] or lead["company"] in gen["subject"]
        update_lead(lead["id"], email_subject=gen["subject"], email_body=gen["body"], status="generated")

    # 4. Test Dry-Run simulation dispatch
    success, msg = dispatcher.start_campaign(dry_run=True)
    assert success is True

    # Wait for dispatcher to finish dry-run (quick simulation)
    import time
    for _ in range(60):
        time.sleep(0.5)
        status = dispatcher.get_status()
        if not status["is_running"]:
            break

    final_stats = get_campaign_stats()
    assert final_stats["sent"] == len(test_leads)
    assert final_stats["failed"] == 0

