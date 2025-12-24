from __future__ import annotations

import hashlib
import html as html_lib
import json
import os
import smtplib
import socket
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Iterable, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.apps import apps
from django.conf import settings

from peds_edu.aws_secrets import get_last_error, get_secret_string

SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"


def _truncate(s: str, limit: int = 12000) -> str:
    s = s or ""
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n... (truncated; len={len(s)})"


def _sanitize_secret(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s.strip()


def _extract_sendgrid_key(raw: str) -> str:
    """
    Supports secrets stored as:
      - Plain string: "SG...."
      - JSON: {"SendGrid_email":"SG...."}  <-- YOUR CURRENT SECRET FORMAT
      - JSON: {"SENDGRID_API_KEY":"SG...."} or {"api_key":"SG...."} etc.
    """
    raw = (raw or "").strip()
    if not raw:
        return ""

    if raw.startswith("{") and raw.endswith("}"):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                for k in (
                    # Your sample output key
                    "SendGrid_email",
                    "sendgrid_email",
                    # Other common variants
                    "SENDGRID_API_KEY",
                    "sendgrid_api_key",
                    "api_key",
                    "apikey",
                    "key",
                    "SENDGRID_KEY",
                    "sendgrid_key",
                ):
                    v = obj.get(k)
                    if isinstance(v, str) and v.strip():
                        return _sanitize_secret(v)
        except Exception:
            pass

    return _sanitize_secret(raw)


def _fingerprint(secret: str) -> str:
    secret = secret or ""
    if not secret:
        return "missing"
    h = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]
    return f"len={len(secret)} sha256_12={h}"


def _redacted_tail(secret: str, n: int = 4) -> str:
    secret = secret or ""
    if len(secret) < max(1, n):
        return "<short>"
    return secret[-n:]


def _aws_region() -> str:
    return (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or getattr(settings, "AWS_REGION", None)
        or "ap-south-1"
    )


def _aws_secret_name() -> str:
    return (
        os.getenv("SENDGRID_SECRET_NAME")
        or getattr(settings, "SENDGRID_SECRET_NAME", None)
        or "SendGrid_API"
    )


def _get_secret_string_uncached(secret_name: str, region_name: str) -> Tuple[str, Optional[str]]:
    try:
        wrapped = getattr(get_secret_string, "__wrapped__", None)
        if wrapped is not None:
            val = wrapped(secret_name, region_name=region_name)  # type: ignore[misc]
        else:
            val = get_secret_string(secret_name, region_name=region_name)

        err = (get_last_error() or "").strip()
        return (val or "").strip(), (err or None)
    except Exception as e:
        return "", f"{type(e).__name__}: {e}"


@dataclass(frozen=True)
class _KeyCandidate:
    source: str
    key: str

    @property
    def fp(self) -> str:
        return _fingerprint(self.key)

    @property
    def tail(self) -> str:
        try:
            n = int(os.getenv("SENDGRID_KEY_TAIL_CHARS", "4"))
        except Exception:
            n = 4
        n = max(2, min(12, n))
        return _redacted_tail(self.key, n=n)


def _iter_sendgrid_api_key_candidates() -> Tuple[list[_KeyCandidate], dict]:
    region = _aws_region()
    secret_name = _aws_secret_name()

    diag = {
        "secret_name": secret_name,
        "region": region,
        "aws_secret_attempted": True,
        "aws_secret_error": "",
        "aws_secret_value_present": False,
    }

    candidates_raw: list[tuple[str, str]] = []

    # AWS Secrets first
    secret_raw, secret_err = _get_secret_string_uncached(secret_name, region)
    if secret_err:
        diag["aws_secret_error"] = secret_err
    if secret_raw:
        diag["aws_secret_value_present"] = True

    secret_key = _extract_sendgrid_key(secret_raw)
    if secret_key:
        candidates_raw.append((f"aws_secrets:{secret_name}@{region}", secret_key))

    # Settings/env fallbacks
    candidates_raw.append(("settings.SENDGRID_API_KEY", str(getattr(settings, "SENDGRID_API_KEY", "") or "")))
    candidates_raw.append(("settings.EMAIL_HOST_PASSWORD", str(getattr(settings, "EMAIL_HOST_PASSWORD", "") or "")))
    candidates_raw.append(("env:SENDGRID_API_KEY", os.getenv("SENDGRID_API_KEY", "") or ""))
    candidates_raw.append(("env:EMAIL_HOST_PASSWORD", os.getenv("EMAIL_HOST_PASSWORD", "") or ""))

    out: list[_KeyCandidate] = []
    seen_fp: set[str] = set()
    for src, raw in candidates_raw:
        key = _extract_sendgrid_key(raw)
        if not key:
            continue
        fp = _fingerprint(key)
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        out.append(_KeyCandidate(source=src, key=key))

    return out, diag


def _resolve_from_email(from_email: Optional[str] = None) -> str:
    if from_email and str(from_email).strip():
        return str(from_email).strip()
    v = getattr(settings, "SENDGRID_FROM_EMAIL", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if v and str(v).strip():
        return str(v).strip()
    return "no-reply@example.com"


def _get_backend_mode() -> str:
    v = str(getattr(settings, "EMAIL_BACKEND_MODE", "") or "").strip().lower()
    if v in ("sendgrid", "smtp", "console"):
        return v
    # Default: if we have any key candidate, prefer sendgrid API
    cands, _ = _iter_sendgrid_api_key_candidates()
    return "sendgrid" if cands else "smtp"


def _probe_tcp(host: str, port: int, timeout: float = 3.0) -> str:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return "tcp_ok"
    except Exception as e:
        return f"tcp_fail:{type(e).__name__}"


def _log_email_attempt(
    *,
    to_email: str,
    subject: str,
    provider: str,
    success: bool,
    status_code: Optional[int] = None,
    response_body: str = "",
    error: str = "",
) -> None:
    try:
        EmailLog = apps.get_model("accounts", "EmailLog")
    except Exception:
        EmailLog = None

    if EmailLog is None:
        return

    try:
        EmailLog.objects.create(
            to_email=to_email,
            subject=subject,
            provider=provider,
            success=bool(success),
            status_code=status_code,
            response_body=_truncate(response_body or ""),
            error=_truncate(error or "", limit=8000),
        )
    except Exception:
        return


def _send_via_sendgrid_api(
    *,
    subject: str,
    to_emails: list[str],
    plain_text: str,
    from_email: str,
) -> Tuple[bool, Optional[int], str, str]:
    candidates, aws_diag = _iter_sendgrid_api_key_candidates()

    diag_base = {
        "provider": "sendgrid",
        "from_email": from_email,
        "to_count": len(to_emails),
        "aws_secrets": aws_diag,
        "candidates": [{"source": c.source, "fp": c.fp} for c in candidates],
        "sendgrid_api_url": SENDGRID_API_URL,
        "authorization_header_set": True,
    }

    if not candidates:
        return False, None, json.dumps(diag_base), "No SendGrid API key candidates found"

    safe_html = "<pre>" + html_lib.escape(plain_text or "") + "</pre>"

    payload = {
        "personalizations": [{"to": [{"email": e} for e in to_emails]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [
            {"type": "text/plain", "value": plain_text or ""},
            {"type": "text/html", "value": safe_html},
        ],
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    last_status: Optional[int] = None
    last_err_text: str = ""
    last_err_body: str = ""

    for cand in candidates:
        api_key = cand.key
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            req = Request(SENDGRID_API_URL, data=payload_bytes, headers=headers, method="POST")
            with urlopen(req, timeout=25) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                body = resp.read().decode("utf-8", errors="ignore") if resp else ""

            ok = isinstance(status, int) and 200 <= status < 300

            diag = dict(diag_base)
            diag.update(
                {
                    "selected_source": cand.source,
                    "sendgrid_api_key_fp": cand.fp,
                    "sendgrid_api_key_tail": cand.tail,
                    "status_code": status,
                }
            )

            combined = json.dumps(diag)
            if body:
                combined += "\n" + _truncate(body, 12000)

            if ok:
                return True, int(status), combined, ""

            last_status = int(status) if isinstance(status, int) else None
            last_err_text = f"HTTP {status}"
            last_err_body = body

            if status in (401, 403):
                continue

            break

        except HTTPError as e:
            status = getattr(e, "code", None)
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")  # type: ignore[attr-defined]
            except Exception:
                pass
            last_status = int(status) if isinstance(status, int) else None
            last_err_text = f"HTTPError {status}"
            last_err_body = body
            if status in (401, 403):
                continue
            break
        except URLError as e:
            last_status = None
            last_err_text = f"URLError: {e}"
            break
        except Exception as e:
            last_status = None
            last_err_text = f"{type(e).__name__}: {e}"
            break

    diag = dict(diag_base)
    diag.update({"selected_source": None, "last_status": last_status, "last_error": _truncate(last_err_text, 2000)})
    combined = json.dumps(diag)
    if last_err_body:
        combined += "\n" + _truncate(last_err_body, 12000)
    return False, last_status, combined, last_err_text or "SendGrid API send failed"


def _send_via_smtp(
    *,
    subject: str,
    to_emails: list[str],
    plain_text: str,
    from_email: str,
) -> Tuple[bool, Optional[int], str, str]:
    host = str(getattr(settings, "EMAIL_HOST", "") or "smtp.sendgrid.net").strip()
    port = int(getattr(settings, "EMAIL_PORT", 587) or 587)
    use_tls = bool(getattr(settings, "EMAIL_USE_TLS", True))
    use_ssl = bool(getattr(settings, "EMAIL_USE_SSL", False))
    user = str(getattr(settings, "EMAIL_HOST_USER", "apikey") or "apikey").strip()

    candidates, aws_diag = _iter_sendgrid_api_key_candidates()
    probe = _probe_tcp(host, port)

    # Prefer EMAIL_HOST_PASSWORD, but allow SendGrid candidates as SMTP password
    pw = _sanitize_secret(str(getattr(settings, "EMAIL_HOST_PASSWORD", "") or ""))
    pw_src = "settings.EMAIL_HOST_PASSWORD"
    if not pw and candidates:
        pw = candidates[0].key
        pw_src = candidates[0].source

    if not pw:
        diag = {
            "provider": "smtp",
            "host": host,
            "port": port,
            "use_tls": use_tls,
            "use_ssl": use_ssl,
            "probe": probe,
            "aws_secrets": aws_diag,
        }
        return False, None, json.dumps(diag), "No SMTP password available"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_emails)
    msg.set_content(plain_text or "")

    try:
        if use_ssl:
            server: smtplib.SMTP = smtplib.SMTP_SSL(host=host, port=port, timeout=20)
        else:
            server = smtplib.SMTP(host=host, port=port, timeout=20)

        try:
            server.ehlo()
            if use_tls and not use_ssl:
                ctx = ssl.create_default_context()
                server.starttls(context=ctx)
                server.ehlo()
            server.login(user, pw)
            server.send_message(msg)
            try:
                server.quit()
            except Exception:
                pass
        finally:
            try:
                server.close()
            except Exception:
                pass

        diag = {
            "provider": "smtp",
            "host": host,
            "port": port,
            "use_tls": use_tls,
            "use_ssl": use_ssl,
            "probe": probe,
            "smtp_user": user,
            "smtp_password_source": pw_src,
            "smtp_password_tail": _redacted_tail(pw, 4),
            "aws_secrets": aws_diag,
        }
        return True, 250, json.dumps(diag), ""
    except Exception as e:
        diag = {
            "provider": "smtp",
            "host": host,
            "port": port,
            "use_tls": use_tls,
            "use_ssl": use_ssl,
            "probe": probe,
            "smtp_user": user,
            "smtp_password_source": pw_src,
            "aws_secrets": aws_diag,
        }
        return False, None, json.dumps(diag), str(e)


def send_email_via_sendgrid(
    subject: str,
    to_emails: Iterable[str],
    plain_text_content: str,
    from_email: Optional[str] = None,
) -> bool:
    subject = (subject or "").strip()
    recipients = [str(e).strip() for e in (to_emails or []) if e and str(e).strip()]
    recipients = list(dict.fromkeys(recipients))

    if not subject or not recipients:
        for r in recipients or [""]:
            _log_email_attempt(
                to_email=r or "(missing)",
                subject=subject or "(missing)",
                provider="internal",
                success=False,
                status_code=None,
                response_body="",
                error="Missing subject and/or recipients",
            )
        return False

    mode = _get_backend_mode()
    from_addr = _resolve_from_email(from_email)

    providers = ["smtp", "sendgrid"] if mode == "smtp" else ["sendgrid", "smtp"]

    for provider in providers:
        if provider == "sendgrid":
            ok, status, resp_body, err = _send_via_sendgrid_api(
                subject=subject,
                to_emails=recipients,
                plain_text=plain_text_content or "",
                from_email=from_addr,
            )
        else:
            ok, status, resp_body, err = _send_via_smtp(
                subject=subject,
                to_emails=recipients,
                plain_text=plain_text_content or "",
                from_email=from_addr,
            )

        for r in recipients:
            _log_email_attempt(
                to_email=r,
                subject=subject,
                provider=provider,
                success=ok,
                status_code=status,
                response_body=resp_body,
                error=err,
            )

        if ok:
            return True

    return False
