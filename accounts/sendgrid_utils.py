import logging
from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .email_log import EmailLog

logger = logging.getLogger(__name__)


def send_email_via_sendgrid(to_email: str, subject: str, text: str) -> bool:
    api_key = (getattr(settings, "SENDGRID_API_KEY", "") or "").strip()
    from_email = (getattr(settings, "SENDGRID_FROM_EMAIL", "") or "").strip()
    key_fingerprint = f"len={len(api_key)} tail={api_key[-6:] if api_key else 'EMPTY'}"

    if not api_key or not from_email:
        EmailLog.objects.create(
            to_email=to_email,
            subject=subject,
            provider="sendgrid",
            success=False,
            status_code=None,
            response_body="",
            error=f"Missing SENDGRID_API_KEY or SENDGRID_FROM_EMAIL | {key_fingerprint} from={from_email}",
        )
        return False

    try:
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            plain_text_content=text,
        )
        sg = SendGridAPIClient(api_key)
        resp = sg.send(message)

        body = ""
        try:
            body = (resp.body or b"").decode("utf-8", errors="ignore")
        except Exception:
            body = str(resp.body)

        ok = (resp.status_code == 202)

        EmailLog.objects.create(
            to_email=to_email,
            subject=subject,
            provider="sendgrid",
            success=ok,
            status_code=resp.status_code,
            response_body=body,
            error=("" if ok else f"SendGrid non-202 | {key_fingerprint} from={from_email}"),
        )
        return ok

    except Exception as e:
        EmailLog.objects.create(
            to_email=to_email,
            subject=subject,
            provider="sendgrid",
            success=False,
            status_code=None,
            response_body="",
            error=f"{str(e)} | {key_fingerprint} from={from_email}",
        )
        logger.exception("SendGrid send failed")
        return False
