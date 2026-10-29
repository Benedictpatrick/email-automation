import smtplib
import ssl
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, Tuple
import html

def format_html_email(body_text: str) -> str:
    """
    Converts plain text email into clean, readable HTML email styling
    without looking like a promotional marketing blast (mimics standard Gmail/Outlook formatting).
    """
    escaped = html.escape(body_text)
    # Convert double line breaks into paragraphs
    paragraphs = escaped.split("\n\n")
    html_paragraphs = [f"<p style='margin: 0 0 14px 0;'>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip()]
    content = "".join(html_paragraphs)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.55;
    color: #222222;
}}
p {{
    margin: 0 0 14px 0;
}}
</style>
</head>
<body>
{content}
</body>
</html>"""

def test_smtp_connection(settings: Dict[str, str]) -> Tuple[bool, str]:
    """
    Validates SMTP credentials by attempting to authenticate.
    """
    host = settings.get("smtp_host", "").strip()
    port = int(settings.get("smtp_port", 587) or 587)
    user = settings.get("smtp_user", "").strip()
    password = settings.get("smtp_password", "").strip()

    if not host or not user or not password:
        return False, "Host, Username, and Password cannot be empty."

    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=12) as server:
                server.login(user, password)
        else:
            with smtplib.SMTP(host, port, timeout=12) as server:
                server.ehlo()
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
        return True, "SMTP connection and authentication successful!"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"

def send_single_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    settings: Dict[str, str]
) -> Tuple[bool, str]:
    """
    Sends an individual cold outreach email via SMTP.
    """
    host = settings.get("smtp_host", "").strip()
    port = int(settings.get("smtp_port", 587) or 587)
    user = settings.get("smtp_user", "").strip()
    password = settings.get("smtp_password", "").strip()
    from_name = settings.get("from_name", "").strip() or "Automation Team"
    from_email = settings.get("from_email", "").strip() or user
    reply_to = settings.get("reply_to", "").strip() or from_email

    if not host or not user or not password:
        return False, "SMTP configuration incomplete (missing host, user, or password)."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    if reply_to:
        msg["Reply-To"] = reply_to

    # Plain text version
    part_text = MIMEText(body, "plain", "utf-8")
    # HTML formatted version
    part_html = MIMEText(format_html_email(body), "html", "utf-8")

    msg.attach(part_text)
    msg.attach(part_html)

    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as server:
                server.login(user, password)
                server.sendmail(from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
                server.sendmail(from_email, [to_email], msg.as_string())
        return True, "Email sent successfully"
    except Exception as e:
        return False, str(e)

