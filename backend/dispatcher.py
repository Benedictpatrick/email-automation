import time
import random
import threading
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.database import (
    get_leads, update_lead, log_activity, get_all_settings
)
from backend.ai_engine import generate_email_for_lead
from backend.mailer import send_single_email

logger = logging.getLogger(__name__)

class CampaignDispatcher:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.is_running = False
        self.is_paused = False
        self.should_stop = False
        self.dry_run = False

        self.total_leads = 0
        self.current_index = 0
        self.sent_count = 0
        self.failed_count = 0
        self.current_lead_email = ""
        self.status_message = "Idle"
        self.countdown_seconds = 0

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "dry_run": self.dry_run,
                "total_leads": self.total_leads,
                "current_index": self.current_index,
                "sent_count": self.sent_count,
                "failed_count": self.failed_count,
                "current_lead_email": self.current_lead_email,
                "status_message": self.status_message,
                "countdown_seconds": self.countdown_seconds,
            }

    def start_campaign(self, dry_run: bool = False, lead_ids: Optional[List[int]] = None, only_approved: bool = False):
        with self.lock:
            if self.is_running:
                return False, "Campaign is already running."

        # Verify eligible leads before starting
        if lead_ids:
            matching = [lead for lead in get_leads(limit=1000) if lead["id"] in lead_ids]
        elif only_approved:
            matching = get_leads(status="approved", limit=1000)
        else:
            all_l = get_leads(limit=1000)
            matching = [l for l in all_l if l["status"] in ["pending", "generated", "approved"]]

        if not matching:
            if only_approved:
                return False, "No approved leads found to send. Please approve your drafts first or uncheck 'Only Send Approved'."
            return False, "No pending leads found to send. (Existing leads are already marked 'sent'). Click 'Reset' to re-send or upload a new spreadsheet."

        with self.lock:
            self.is_running = True
            self.is_paused = False
            self.should_stop = False
            self.dry_run = dry_run
            self.sent_count = 0
            self.failed_count = 0
            self.current_index = 0
            self.total_leads = len(matching)
            self.status_message = "Starting..."

        self.thread = threading.Thread(target=self._run_loop, args=(lead_ids, only_approved), daemon=True)
        self.thread.start()
        return True, "Campaign started."

    def pause_campaign(self):
        with self.lock:
            if not self.is_running:
                return False, "No campaign is running."
            self.is_paused = not self.is_paused
            msg = "Campaign paused." if self.is_paused else "Campaign resumed."
            self.status_message = msg
            log_activity(msg, level="WARNING")
            return True, msg

    def stop_campaign(self):
        with self.lock:
            if not self.is_running:
                return False, "No campaign is running."
            self.should_stop = True
            self.status_message = "Stopping..."
            log_activity("Campaign stop requested by user.", level="WARNING")
            return True, "Campaign stopping."

    def _run_loop(self, lead_ids: Optional[List[int]] = None, only_approved: bool = False):
        try:
            settings = get_all_settings()
            min_delay = int(settings.get("delay_min_seconds", 35) or 35)
            max_delay = int(settings.get("delay_max_seconds", 75) or 75)
            daily_limit = int(settings.get("daily_send_limit", 40) or 40)

            # Fetch targeted leads
            if lead_ids:
                all_leads = [lead for lead in get_leads(limit=1000) if lead["id"] in lead_ids]
            elif only_approved:
                all_leads = get_leads(status="approved", limit=1000)
            else:
                all_leads = get_leads(limit=1000)
                # Only take leads that have not been sent yet
                all_leads = [l for l in all_leads if l["status"] in ["pending", "generated", "approved"]]

            with self.lock:
                self.total_leads = len(all_leads)

            if not all_leads:
                with self.lock:
                    self.status_message = "No pending leads found to send."
                    self.is_running = False
                log_activity("Campaign completed: No pending leads found.", level="INFO")
                return

            mode_str = "[DRY-RUN SIMULATION]" if self.dry_run else "[LIVE SEND]"
            log_activity(f"{mode_str} Starting campaign batch of {len(all_leads)} leads. Daily cap: {daily_limit}.", level="INFO")

            for idx, lead in enumerate(all_leads, start=1):
                # Check stop flag
                if self.should_stop:
                    break

                # Handle pause
                while self.is_paused and not self.should_stop:
                    time.sleep(1)

                if self.should_stop:
                    break

                # Enforce daily limit
                if self.sent_count >= daily_limit:
                    log_activity(f"Safety limit reached: daily cap of {daily_limit} emails reached. Halting campaign.", level="WARNING")
                    break

                with self.lock:
                    self.current_index = idx
                    self.current_lead_email = lead["email"]
                    self.status_message = f"Processing lead {idx}/{len(all_leads)}: {lead['email']}"

                # Ensure lead has an email subject and body
                subject = lead.get("email_subject")
                body = lead.get("email_body")
                if not subject or not body:
                    with self.lock:
                        self.status_message = f"Generating AI personalization for {lead['email']}..."
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
                        lead["id"],
                        email_subject=subject,
                        email_body=body,
                        custom_hook=gen_result.get("custom_hook", ""),
                        status="generated"
                    )

                # Send or simulate
                if self.dry_run:
                    time.sleep(1.5)  # Quick simulation
                    update_lead(lead["id"], status="sent", sent_at=datetime.now().isoformat(), error_message="Dry run simulation")
                    with self.lock:
                        self.sent_count += 1
                    log_activity(f"[DRY-RUN] Simulated send to {lead['email']} ({lead.get('company')}). Subject: {subject}", level="SUCCESS", lead_email=lead['email'])
                else:
                    success, msg = send_single_email(
                        to_email=lead["email"],
                        to_name=lead.get("first_name", ""),
                        subject=subject,
                        body=body,
                        settings=settings
                    )
                    if success:
                        update_lead(lead["id"], status="sent", sent_at=datetime.now().isoformat(), error_message="")
                        with self.lock:
                            self.sent_count += 1
                        log_activity(f"Successfully sent email to {lead['email']} ({lead.get('company')})", level="SUCCESS", lead_email=lead['email'])
                    else:
                        update_lead(lead["id"], status="failed", error_message=msg)
                        with self.lock:
                            self.failed_count += 1
                        log_activity(f"Failed to send to {lead['email']}: {msg}", level="ERROR", lead_email=lead['email'])

                # If this was not the last lead, apply randomized human delay (or 1s quick pause in dry-run)
                if idx < len(all_leads) and not self.should_stop:
                    delay = 1 if self.dry_run else random.randint(min_delay, max_delay)
                    if not self.dry_run:
                        log_activity(f"Waiting {delay} seconds before next send to protect domain reputation...", level="INFO")
                    
                    for remaining in range(delay, 0, -1):
                        if self.should_stop:
                            break
                        while self.is_paused and not self.should_stop:
                            time.sleep(1)
                        with self.lock:
                            self.countdown_seconds = remaining
                            self.status_message = f"Throttling: next send in {remaining}s (Anti-Spam Delay)"
                        time.sleep(1)

                    with self.lock:
                        self.countdown_seconds = 0

            with self.lock:
                self.status_message = "Campaign finished."
                self.is_running = False
                self.current_lead_email = ""

            log_activity(f"Campaign finished! Total Sent: {self.sent_count}, Failed: {self.failed_count}.", level="INFO")

        except Exception as e:
            logger.error(f"Campaign dispatcher crashed: {e}", exc_info=True)
            with self.lock:
                self.status_message = f"Error: {str(e)}"
                self.is_running = False
            log_activity(f"Campaign error: {str(e)}", level="ERROR")

# Global singleton dispatcher instance
dispatcher = CampaignDispatcher()
