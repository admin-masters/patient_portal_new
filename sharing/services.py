from __future__ import annotations

import json
from typing import Any, Dict, List

from django.conf import settings
from django.core.cache import cache

from catalog.models import Video, VideoCluster


# Bump version to avoid stale caches from earlier code.
_CATALOG_CACHE_KEY = "clinic_catalog_json_v3"
_CATALOG_CACHE_SECONDS = int(getattr(settings, "CATALOG_CACHE_SECONDS", 3600) or 3600)


def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def build_whatsapp_message_prefixes(doctor_name: str | None = None) -> Dict[str, str]:
    """
    sharing/views.py calls build_whatsapp_message_prefixes(request.user.full_name)
    so we must accept 1 positional arg.
    """
    prefixes: Dict[str, str] = {"en": "Please see: "}
    langs = getattr(settings, "LANGUAGES", None)
    if isinstance(langs, (list, tuple)):
        for code, _name in langs:
            if code not in prefixes:
                prefixes[code] = prefixes["en"]
    return prefixes


def _build_catalog_payload() -> Dict[str, Any]:
    # 1) Bundles (clusters) = VideoCluster
    vc_qs = VideoCluster.objects.all()
    # these columns may/may not exist depending on your DB drift
    try:
        vc_qs = vc_qs.order_by("sort_order", "id")
    except Exception:
        vc_qs = vc_qs.order_by("id")

    clusters_payload: List[Dict[str, Any]] = []
    for vc in vc_qs:
        # Use pk string as the cluster id to ensure video.cluster_ids match exactly
        cid = str(vc.pk)
        display = _safe_str(getattr(vc, "display_name", "") or getattr(vc, "code", "") or f"Bundle {vc.pk}")
        clusters_payload.append({"id": cid, "display_name": display})

    # 2) Videos
    v_qs = Video.objects.all()
    try:
        v_qs = v_qs.order_by("sort_order", "id")
    except Exception:
        v_qs = v_qs.order_by("id")

    videos_payload: List[Dict[str, Any]] = []

    for v in v_qs:
        # Map video -> cluster_ids using M2M; fallback to empty if relation missing
        cluster_ids: List[str] = []
        try:
            cluster_ids = [str(vc.pk) for vc in v.clusters.all()]
        except Exception:
            cluster_ids = []

        titles: Dict[str, str] = {}
        urls: Dict[str, str] = {}

        # Preferred: per-language rows
        try:
            for lang in v.languages.all():
                lc = _safe_str(getattr(lang, "language_code", "")).strip() or "en"
                titles[lc] = _safe_str(getattr(lang, "title", "")).strip() or _safe_str(getattr(v, "code", "") or "Video")
                urls[lc] = _safe_str(getattr(lang, "youtube_url", "")).strip()
        except Exception:
            titles["en"] = _safe_str(getattr(v, "code", "") or "Video")
            urls["en"] = ""

        videos_payload.append(
            {
                "id": _safe_str(getattr(v, "code", None) or v.pk),
                "cluster_ids": cluster_ids,
                "titles": titles,
                "urls": urls,
                "trigger_names": [],
                "search_text": (_safe_str(getattr(v, "code", "")).lower()),
            }
        )

    return {
        "clusters": clusters_payload,
        "videos": videos_payload,
        "message_prefixes": build_whatsapp_message_prefixes(None),
    }


def get_catalog_json_cached(force_refresh: bool = False) -> str:
    if not force_refresh:
        cached = cache.get(_CATALOG_CACHE_KEY)
        if isinstance(cached, str) and cached.strip():
            return cached

    payload = _build_catalog_payload()
    data = json.dumps(payload, ensure_ascii=False)
    cache.set(_CATALOG_CACHE_KEY, data, timeout=_CATALOG_CACHE_SECONDS)
    return data
