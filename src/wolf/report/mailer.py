"""Email sender for the SysAdmin Daily/Weekly Report. SMTP credentials read
from environment variables only — populated from Vault by the Dagu job
runner, never hardcoded, never committed.
"""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class MissingCredentialError(RuntimeError):
    pass


def send_report(subject: str, plaintext_body: str, html_body: str | None = None) -> None:
    host = os.environ.get("WOLF_SMTP_HOST")
    port = int(os.environ.get("WOLF_SMTP_PORT", "587"))
    user = os.environ.get("WOLF_SMTP_USER")
    password = os.environ.get("WOLF_SMTP_PASSWORD")
    mailto = os.environ.get("WOLF_MAILTO", "anderson@42labs.io")

    if not host or not user or not password:
        raise MissingCredentialError(
            "WOLF_SMTP_HOST, WOLF_SMTP_USER and WOLF_SMTP_PASSWORD must be set "
            "(sourced from Vault by the Dagu job, never hardcoded)"
        )

    msg = MIMEMultipart("alternative")
    msg["From"] = f"SysAdmin <{user}>"
    msg["To"] = mailto
    msg["Subject"] = subject
    msg.attach(MIMEText(plaintext_body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [mailto], msg.as_string())
