"""
Turning "Koramangala" into a point on the map, and a point back into a name.

The seeker's search needs both directions:

  forward   they type an area and get PGs near it, even when no listing
            happens to have that word in its address
  reverse   the app found their GPS position and wants to say "near HSR Layout"
            instead of printing coordinates

Why the API does this instead of the app calling a geocoder directly
--------------------------------------------------------------------
OpenStreetMap's Nominatim is free and has no key, and its usage policy asks for
two things a phone cannot promise: an identifying User-Agent, and no more than
one request a second. A WebView sets its own User-Agent, and a thousand phones
each keeping to one a second is a thousand a second. Proxying here lets one
process identify itself honestly, queue requests, and cache - areas in a city
are searched over and over, so most lookups never leave this server.

Set GEOCODER_URL to point at a self-hosted Nominatim (or a paid one with the
same API) when traffic outgrows the public instance.

Nothing here is ever required. A geocoder that is down or slow degrades to the
ordinary text search, which still matches listings by name, city and address.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from urllib import error as urlerror, parse as urlparse, request as urlrequest

from app.core.config import settings

log = logging.getLogger("pgdesk.geocode")

#: Seconds to wait for the geocoder. Short: a seeker is watching a spinner.
TIMEOUT = 6
#: Nominatim's published limit for its public instance.
MIN_INTERVAL = 1.0

CACHE_TTL = 24 * 3600
CACHE_MAX = 800

_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()
_last_call = 0.0


class GeocodeUnavailable(Exception):
    """The geocoder could not answer. Callers fall back to text search."""


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key: str, value) -> None:
    if len(_cache) >= CACHE_MAX:
        # Drop the oldest tenth rather than one at a time on every insert.
        for stale in sorted(_cache, key=lambda k: _cache[k][0])[: CACHE_MAX // 10]:
            _cache.pop(stale, None)
    _cache[key] = (time.time(), value)


def _get(path: str, params: dict) -> object:
    """One polite GET to the geocoder. Serialised so the rate limit holds."""
    global _last_call
    base = (settings.geocoder_url or "").rstrip("/")
    if not base:
        raise GeocodeUnavailable("no geocoder configured")
    url = f"{base}{path}?{urlparse.urlencode(params)}"
    req = urlrequest.Request(url, headers={
        "User-Agent": settings.geocoder_user_agent,
        "Accept": "application/json",
        "Accept-Language": "en-IN,en",
    })
    with _lock:
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            with urlrequest.urlopen(req, timeout=TIMEOUT) as res:   # noqa: S310 - fixed host
                body = res.read().decode("utf-8")
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            log.warning("geocoder unreachable: %s", exc)
            raise GeocodeUnavailable(str(exc)) from None
        finally:
            _last_call = time.monotonic()
    try:
        return json.loads(body)
    except ValueError:
        raise GeocodeUnavailable("unreadable geocoder response") from None


def _short_label(item: dict) -> tuple[str, str]:
    """
    "HSR Layout, Bengaluru" rather than the full nine-part display name.

    Returns (label, detail): the short name for the list row, the long one as
    the grey line underneath so two places with the same name can be told apart.
    """
    addr = item.get("address") or {}
    primary = (item.get("name") or addr.get("suburb") or addr.get("neighbourhood")
               or addr.get("city_district") or addr.get("town") or addr.get("village")
               or addr.get("city") or "")
    city = (addr.get("city") or addr.get("town") or addr.get("state_district")
            or addr.get("county") or addr.get("state") or "")
    parts = [p for p in (primary, city if city != primary else "") if p]
    label = ", ".join(parts) or (item.get("display_name") or "").split(",")[0]
    return label, item.get("display_name") or label


def search_places(query: str, *, limit: int = 6) -> list[dict]:
    q = " ".join((query or "").split())[:120]
    if len(q) < 2:
        return []
    key = f"s:{q.lower()}:{limit}"
    cached = _cache_get(key)
    if cached is not None:
        return cached

    data = _get("/search", {
        "q": q, "format": "jsonv2", "addressdetails": 1,
        "limit": max(1, min(limit, 10)), "countrycodes": "in",
    })
    out = []
    for item in data if isinstance(data, list) else []:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        label, detail = _short_label(item)
        out.append({"label": label, "detail": detail, "latitude": lat, "longitude": lon})
    _cache_put(key, out)
    return out


def reverse(latitude: float, longitude: float) -> dict | None:
    """Rounded to about 100 m before caching: nearby phones share one lookup."""
    key = f"r:{latitude:.3f}:{longitude:.3f}"
    cached = _cache_get(key)
    if cached is not None:
        return cached or None

    data = _get("/reverse", {
        "lat": f"{latitude:.5f}", "lon": f"{longitude:.5f}",
        "format": "jsonv2", "zoom": 15, "addressdetails": 1,
    })
    if not isinstance(data, dict) or data.get("error"):
        _cache_put(key, {})
        return None
    addr = data.get("address") or {}
    area = (addr.get("suburb") or addr.get("neighbourhood") or addr.get("city_district")
            or addr.get("town") or addr.get("village") or "")
    city = addr.get("city") or addr.get("town") or addr.get("state_district") or ""
    label = ", ".join(p for p in (area, city if city != area else "") if p) \
        or (data.get("display_name") or "").split(",")[0]
    result = {"label": label, "area": area or None, "city": city or None}
    _cache_put(key, result)
    return result
