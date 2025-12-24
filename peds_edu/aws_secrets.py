from __future__ import annotations

import base64
from functools import lru_cache
from typing import Optional

try:
    import boto3
    from botocore.exceptions import (
        BotoCoreError,
        ClientError,
        EndpointConnectionError,
        NoCredentialsError,
        NoRegionError,
        PartialCredentialsError,
    )
except Exception:  # pragma: no cover
    boto3 = None  # type: ignore
    BotoCoreError = Exception  # type: ignore
    ClientError = Exception  # type: ignore
    EndpointConnectionError = Exception  # type: ignore
    NoCredentialsError = Exception  # type: ignore
    NoRegionError = Exception  # type: ignore
    PartialCredentialsError = Exception  # type: ignore


_LAST_ERROR: str = ""


def get_last_error() -> str:
    """Best-effort last error string from the most recent Secrets Manager call in this process."""
    return _LAST_ERROR


@lru_cache(maxsize=32)
def get_secret_string(secret_name: str, region_name: str = "ap-south-1") -> Optional[str]:
    """
    Fetch a secret string from AWS Secrets Manager.

    Returns None if:
      - boto3/botocore isn't available, OR
      - AWS credentials are not available to the running process (e.g., missing instance role), OR
      - the secret cannot be fetched for any reason (access denied, not found, network issues, etc).

    This function is intentionally "best effort" and MUST NOT raise, because it may be
    used at Django settings import time and in request/response paths.
    """
    global _LAST_ERROR
    _LAST_ERROR = ""

    if boto3 is None:
        _LAST_ERROR = "boto3_unavailable"
        return None

    try:
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=region_name)
        response = client.get_secret_value(SecretId=secret_name)
    except (
        ClientError,
        NoCredentialsError,
        PartialCredentialsError,
        NoRegionError,
        EndpointConnectionError,
        BotoCoreError,
    ) as e:
        _LAST_ERROR = f"{type(e).__name__}: {e}"
        return None
    except Exception as e:
        _LAST_ERROR = f"{type(e).__name__}: {e}"
        return None

    if isinstance(response, dict) and response.get("SecretString"):
        return str(response["SecretString"]).strip()

    if isinstance(response, dict) and response.get("SecretBinary"):
        try:
            return base64.b64decode(response["SecretBinary"]).decode("utf-8").strip()
        except Exception as e:
            _LAST_ERROR = f"decode_error:{type(e).__name__}: {e}"
            return None

    return None
