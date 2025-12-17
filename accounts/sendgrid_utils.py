import logging
import os
import socket
import ssl as ssl_lib
import time
from email.message import EmailMessage
from pathlib import Path
import smtplib

from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from .email_log import EmailLog

logger = logging.getLogger(__name__)

ENV_PATH = Path("/home/ubuntu/peds_edu_app/.env")


def _read_env_var(name: str, default: str = "") -> str:
    val = (os.getenv(name) or "").strip()
    if val:
        return val

    if not ENV_PATH.exists():
        return default

    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k != name:
                continue
            v = v.strip().strip('"').strip("'")
            return v
    except Exception:
        logger.exception("Failed reading .env at %s", ENV_PATH)

    return default


def _smtp_enabled() -> bool:
    mode = (os.getenv("EMAIL_BACKEND") or "").strip().lower()
    if mode:
        return mode == "smtp"
    backend = getattr(settings, "EMAIL_BACKEND", "")
    return "smtp" in (backend or "").lower()


def _probe_outbound(host: str, port: int, use_ssl: bool) -> str:
    try:
        sock = socket.create_connection((host, port), timeout=10)
        if use_ssl:
            ctx = ssl_lib.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=host)
        sock.close()
        return "tcp_ok" + ("_ssl_ok" if use_ssl else "")
    except Exception as e:
        return f"{type(e).__name__}: {str(e)}"


class _CapturingSMTPMixin:
    """Mixin to capture smtplib debug output."""
    def __init__(self, *args, **kwargs):
        self._debug_lines: list[str] = []
        super().__init__(*args, **kwargs)

    def _print_debug(self, *args):
        try:
            self._debug_lines.append(" ".join(str(a) for a in args))
        except Exception:
            pass

    def get_transcript(self) -> str:
        return "\n".join(self._debug_lines)


class CapturingSMTP(_CapturingSMTPMixin, smtplib.SMTP):
    pass


class CapturingSMTP_SSL(_CapturingSMTPMixin, smtplib.SMTP_SSL):
    pass


def _smtp_send_raw(to_email: str, subject: str, text: str) -> tuple[bool, str, str]:
    """
    Returns: (success, transcript, error_message)
    """
    host = getattr(settings, "EMAIL_HOST", "") or "smtp.sendgrid.net"
    port = int(getattr(settings, "EMAIL_PORT", 587) or 587)
    use_tls = bool(getattr(settings, "EMAIL_USE_TLS", False))
    use_ssl = bool(getattr(settings, "EMAIL_USE_SSL", False))
    user = getattr(settings, "EMAIL_HOST_USER", "") or "apikey"
    password = getattr(settings, "EMAIL_HOST_PASSWORD", "") or ""
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or getattr(settings, "SENDGRID_FROM_EMAIL", "")

    # Build message
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content(text)

    transcript = []

    # Retry on intermittent disconnects
    for attempt in range(1, 4):
        smtp = None
        try:
            if use_ssl:
                ctx = ssl_lib.create_default_context()
                smtp = CapturingSMTP_SSL(host=host, port=port, timeout=15, context=ctx)
            else:
                smtp = CapturingSMTP(host=host, port=port, timeout=15)

            smtp.set_debuglevel(1)

            # Greet
            smtp.ehlo()

            # STARTTLS path (usually port 587)
            if use_tls and not use_ssl:
                ctx = ssl_lib.create_default_context()
                smtp.starttls(context=ctx)
                smtp.ehlo()

            # Auth
            if user and password:
                smtp.login(user, password)

            # Send
            smtp.send_message(msg)

            # Quit cleanly
            try:
                smtp.quit()
            except Exception:
                try:
                    smtp.close()
                except Exception:
                    pass

            t = smtp.get_transcript()
            return True, t, ""

        except smtplib.SMTPServerDisconnected as e:
            # Capture transcript so far and retry
            t = smtp.get_transcript() if smtp else ""
            transcript.append(f"--- attempt {attempt} disconnected ---\n{t}")
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            return False, "\n\n".join(transcript), f"SMTPServerDisconnected: {str(e)}"

        except Exception as e:
            t = smtp.get_transcript() if smtp else ""
            return False, t, f"{type(e).__name__}: {str(e)}"

        finally:
            try:
                if smtp:
                    smtp.close()
            except Exception:
                pass

    return False, "\n\n".join(transcript), "Unknown SMTP failure"


def send_email_via_sendgrid(to_email: str, subject: str, text: str) -> bool:
    """
    Sends email:
    - Prefer SMTP if EMAIL_BACKEND=smtp
    - Otherwise attempt SendGrid Web API

    Always logs to EmailLog.
    """
    # ---------- SMTP path ----------
    if _smtp_enabled():
        host = getattr(settings, "EMAIL_HOST", "smtp.sendgrid.net")
        port = int(getattr(settings, "EMAIL_PORT", 587) or 587)
        use_ssl = bool(getattr(settings, "EMAIL_USE_SSL", False))

        probe = _probe_outbound(host, port, use_ssl)

        ok, transcript, err = _smtp_send_raw(to_email, subject, text)

        EmailLog.objects.create(
            to_email=to_email,
            subject=subject,
            provider="smtp",
            success=ok,
            status_code=202 if ok else None,
            response_body=transcript or "",
            error=("" if ok else f"{err} | host={host} port={port} tls={getattr(settings,'EMAIL_USE_TLS','')} ssl={getattr(settings,'EMAIL_USE_SSL','')} user={getattr(settings,'EMAIL_HOST_USER','')} | probe={probe}"),
        )
        return ok

    # ---------- SendGrid Web API path ----------
    api_key = (getattr(settings, "SENDGRID_API_KEY", "") or "").strip()
    from_email = (getattr(settings, "SENDGRID_FROM_EMAIL", "") or "").strip()

    if not api_key:
        api_key = _read_env_var("SENDGRID_API_KEY", "")
    if not from_email:
        from_email = _read_env_var("SENDGRID_FROM_EMAIL", "")

    api_key = (api_key or "").strip()
    from_email = (from_email or "").strip()

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

        try:
            body = (resp.body or b"").decode("utf-8", errors="ignore")
        except Exception:
            body = str(resp.body)

        ok = resp.status_code == 202

        EmailLog.objects.create(
            to_email=to_email,
            subject=subject,
            provider="sendgrid",
            success=ok,
            status_code=resp.status_code,
            response_body=body,
            error="" if ok else f"SendGrid non-202 | {key_fingerprint} from={from_email}",
        )
        return ok

    except Exception as e:
        status_code = getattr(e, "status_code", None)

        body = ""
        try:
            raw_body = getattr(e, "body", None)
            if raw_body is not None:
                if isinstance(raw_body, (bytes, bytearray)):
                    body = raw_body.decode("utf-8", errors="ignore")
                else:
                    body = str(raw_body)
        except Exception:
            body = ""

        if not body:
            try:
                resp = getattr(e, "response", None)
                if resp is not None:
                    rb = getattr(resp, "body", None)
                    if isinstance(rb, (bytes, bytearray)):
                        body = rb.decode("utf-8", errors="ignore")
                    elif rb is not None:
                        body = str(rb)
            except Exception:
                pass

        EmailLog.objects.create(
            to_email=to_email,
            subject=subject,
            provider="sendgrid",
            success=False,
            status_code=status_code,
            response_body=body,
            error=f"{str(e)} | {key_fingerprint} from={from_email}",
        )
        logger.exception("SendGrid send failed")
        return False
