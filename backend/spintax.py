import re
import random
from typing import Dict, Any

def parse_spintax(text: str) -> str:
    """
    Recursively resolves Spintax syntax like {Hi|Hello|Hey} into a single choice.
    Supports nested spintax.
    """
    pattern = re.compile(r"\{([^{}]+)\}")
    while True:
        match = pattern.search(text)
        if not match:
            break
        choices = match.group(1).split("|")
        selected = random.choice(choices)
        text = text[:match.start()] + selected + text[match.end():]
    return text

def fill_variables(template: str, lead: Dict[str, Any]) -> str:
    """
    Replaces variables like {{first_name}}, {{company}}, {{job_title}}, {{website}}
    with graceful fallbacks.
    """
    first_name = lead.get("first_name") or "there"
    company = lead.get("company") or "your company"
    job_title = lead.get("job_title") or "team"
    website = lead.get("website") or ""

    replacements = {
        "{{first_name}}": first_name,
        "{{firstName}}": first_name,
        "{{name}}": first_name,
        "{{company}}": company,
        "{{company_name}}": company,
        "{{job_title}}": job_title,
        "{{title}}": job_title,
        "{{website}}": website,
    }

    result = template
    for var, val in replacements.items():
        result = result.replace(var, val)
    return result

def render_spintax_template(template: str, lead: Dict[str, Any]) -> str:
    filled = fill_variables(template, lead)
    return parse_spintax(filled)

# Pre-packaged smart automation agency templates with spintax
DEFAULT_TEMPLATES = {
    "hr": {
        "subject": "{Quick question|Question regarding hiring ops|Automating candidate workflows} - {{company}}",
        "body": """{Hi|Hello|Hey} {{first_name}},

{Noticed|Saw} that {{company}} is actively hiring and scaling the team. 

{Usually|Often}, HR and talent teams get overwhelmed manually screening resumes, emailing applicants for scheduling, and updating candidate status across ATS and spreadsheets.

{We help talent teams automate|We build lightweight automations that}:
- Auto-screen and score inbound resumes based on your exact role criteria
- Trigger instant interview scheduling links without back-and-forth emails
- Auto-sync candidate profiles into your ATS/HRIS without manual data entry

{Would you be open to a 5-minute video showing how this works?|Open to seeing a quick 3-minute walkthrough on how we automated this for similar teams?}

{Best regards|Cheers|Warmly},
{{sender_name}}
{{agency_name}}"""
    },
    "operations": {
        "subject": "{Cutting manual tasks|Workflow automation question|Operations question} for {{company}}",
        "body": """{Hi|Hello|Hey} {{first_name}},

{Reaching out because|I noticed} you're leading operations at {{company}}. 

{Most ops leaders we speak with|A lot of growing companies} struggle with their team spending 10+ hours a week copying data between spreadsheets, ERPs, and internal tools, which creates costly bottlenecks.

{We build custom workflow automations and AI bots that|Our team helps companies}:
- Eliminate repetitive manual data entry between your business apps
- Automate daily/weekly cross-department reporting and reconciliation
- Connect your disconnected tools so data flows automatically with zero errors

{Could I share a 2-minute Loom showing how we eliminated this for another team?|Open to a brief exchange to see if this could save {{company}} 10+ hours a week?}

{Best|Regards|Thanks},
{{sender_name}}
{{agency_name}}"""
    },
    "sales": {
        "subject": "{Streamlining sales ops|Instant lead routing question|Lead automation} - {{company}}",
        "body": """{Hi|Hello|Hey} {{first_name}},

{Hope your week is going well.|Hope you're having a productive week.}

{I was looking into|I was reviewing} {{company}} and wanted to ask: how is your team currently handling inbound lead qualification and CRM updates?

{We help sales teams by deploying AI workflows that|We automate the repetitive sales grunt work}:
- Instant lead enrichment and routing to the right rep within 30 seconds
- Auto-logging meeting notes and next steps directly into your CRM
- Automating multi-channel follow-up sequences for cold or stalled leads

{Do you have 5 minutes this Thursday or Friday to compare notes?|Open to a quick chat to see if we can streamline {{company}}'s sales pipeline?}

{Best|Cheers},
{{sender_name}}
{{agency_name}}"""
    },
    "general": {
        "subject": "{Question regarding automation at|Streamlining workflows for|Quick idea for} {{company}}",
        "body": """{Hi|Hello|Hey} {{first_name}},

{I know you're busy, so I'll be brief.|Hope you're having a great week.}

{We run an automation studio that helps companies like {{company}} eliminate tedious manual work through AI workflows and smart integrations.|We specialize in building custom AI agents and workflow automations for growing companies.}

{Typically, we help teams save 15-20 hours a week by automating:|Our sweet spot is}:
- Repetitive data entry and cross-platform sync
- Automated reporting, invoicing, and document processing
- Custom AI assistants for customer support and internal workflows

{Would it make sense to connect for 10 minutes next week to see if there's a fit?|Could I send over a quick 2-minute overview of what we could automate for {{company}}?}

{Best|Warmly},
{{sender_name}}
{{agency_name}}"""
    }
}

