# AutoMail — Autonomous B2B Cold Outreach Studio

An open-source, deliverability-safe cold outreach engine crafted with **Apple HIG fluid design** and powered by **Groq LPU ultra-fast AI inference**. Specifically tailored for an **Automation Agency** pitching AI workflows, CRM automations, and operational streamlining to companies, HR, and executives.

---

## 🚀 Key Features

* **100% Free & Open Source**: Zero subscription fees ($0 vs $50–$100/mo for Lemlist/Instantly).
* **Apple Fluid Interface**: Built following Apple's WWDC Human Interface Guidelines — deep dark theme (`#000000`), frosted glass translucency (`backdrop-filter: blur(30px)`), tactile button feedback, and macOS segmented controls.
* **Dual Ingestion (CSV & Excel)**: Drag-and-drop CSV or Excel (`.xlsx`, `.xls`) with automatic column detection and interactive 5-row preview before importing.
* **Ultra-Fast Groq LPU Brain**: Free 1,000 AI requests/day powered by Groq's high-speed inference engine (`openai/gpt-oss-120b`). Analyzes role pain points (HR, Ops, Sales, Leadership) to generate crisp, tailored B2B emails (<100 words).
* **Live Rate Limit Monitor**: Real-time diagnostic bar tracking remaining Groq requests, tokens, and reset countdowns.
* **Smart Spintax Offline Fallback**: Works 100% offline with zero keys using pre-built agency templates with spintax `{Hi|Hello|Hey}` and dynamic variables.
* **Deliverability & Safety Engine**: RFC multipart MIME via Google SMTP, randomized human throttling (35s–75s), and daily caps (40/day) to prevent spam flagging.
* **Simulation & Inspection**: Dry-run simulation mode, "Send Test Copy to My Inbox" preview, and 1-click direct send.
* **1-Click Friend Onboarding**: Built-in "Account & Keys" setup modal with direct links to generate a Google App Password and get a free Groq key in seconds.

---

## ⚡ Quickstart (For You & Friends)

### 1. Launch the Application
Double-click `START_AUTOMAIL.bat` (or run in terminal):

```bash
python main.py
```

Your browser will automatically open to:
👉 **`http://localhost:8000`**

---

### 2. Connect Your Account (1-Click Setup)
Click **Account & Keys** in the top navigation bar:

1. **Gmail Setup**:
   * Visit [Google App Passwords](https://myaccount.google.com/apppasswords) (Make sure 2-Step Verification is ON).
   * Create an App Password named `AutoMail` and paste the 16 letters into the password field.
2. **Groq AI Setup (Free)**:
   * Get a free API key at [console.groq.com/keys](https://console.groq.com/keys) (No credit card needed, gives 1,000 requests/day).
   * Paste it into the Groq API key field.
3. Click **Save & Connect Account**. The app verifies both your SMTP login and Groq key with live green badges!

---

### 3. Import Leads & Launch
1. Drag and drop your **CSV or Excel (`.xlsx`)** lead list into the upload area.
2. Confirm column mappings in the interactive 5-row preview.
3. Click **Batch AI Personalize** to generate tailored copy for all leads.
4. Review drafts or click **Start Outreach** to begin sending safely.

---

## 🛡️ Deliverability & Cold Outreach Best Practices

1. **Warm-Up**: For new inboxes, start with 15–20 emails per day and gradually scale up to 40–50.
2. **Throttling**: Keep delays between 35 and 75 seconds (never blast 100 emails simultaneously).
3. **Personalization**: Role-specific pain point pitching yields 3x higher reply rates than generic templates.
