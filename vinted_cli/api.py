"""Vinted search API client."""

from __future__ import annotations

import html
import json
import logging
import re
import time

import httpx

log = logging.getLogger(__name__)

# Per-domain session cookie cache (lives for the duration of the process)
_session_cache: dict[str, httpx.Cookies] = {}

# Retry configuration
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = 1.0          # seconds; doubles each attempt
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

# Supported country code → domain mapping
COUNTRIES: dict[str, str] = {
    "se": "www.vinted.se",
    "fr": "www.vinted.fr",
    "de": "www.vinted.de",
    "uk": "www.vinted.co.uk",
    "pl": "www.vinted.pl",
    "be": "www.vinted.be",
    "nl": "www.vinted.nl",
    "it": "www.vinted.it",
    "es": "www.vinted.es",
    "at": "www.vinted.at",
    "lu": "www.vinted.lu",
    "pt": "www.vinted.pt",
    "cz": "www.vinted.cz",
    "hu": "www.vinted.hu",
    "ro": "www.vinted.ro",
    "sk": "www.vinted.sk",
    "lt": "www.vinted.lt",
    "lv": "www.vinted.lv",
    "ee": "www.vinted.ee",
}

# Vinted item condition status IDs
CONDITIONS: dict[str, str] = {
    "new-with-tags": "6",
    "new-without-tags": "1",
    "very-good": "2",
    "good": "3",
    "satisfactory": "4",
}

CONDITION_LABELS: dict[str, str] = {
    "new-with-tags": "New with tags",
    "new-without-tags": "New without tags",
    "very-good": "Very good",
    "good": "Good",
    "satisfactory": "Satisfactory",
}

# Sort order mapping
SORT_MAP: dict[str, str] = {
    "relevance": "relevance",
    "newest": "newest_first",
    "oldest": "oldest_first",
    "price-asc": "price_low_to_high",
    "price-desc": "price_high_to_low",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
}


def _base_url(domain: str) -> str:
    return f"https://{domain}"


def _get_session(domain: str) -> httpx.Cookies:
    """Return cached session cookies for *domain*, fetching them if not yet cached."""
    if domain in _session_cache:
        log.debug("Reusing cached session cookie for %s", domain)
        return _session_cache[domain]

    log.debug("Fetching session cookie from https://%s/", domain)
    r = httpx.get(
        f"https://{domain}/",
        headers=HEADERS,
        timeout=15,
        follow_redirects=True,
    )
    log.debug("Session response: %s, cookies: %s", r.status_code, dict(r.cookies))
    r.raise_for_status()
    _session_cache[domain] = r.cookies
    return r.cookies


def _refresh_session(domain: str) -> httpx.Cookies:
    """Force-refresh session cookies for *domain*."""
    _session_cache.pop(domain, None)
    return _get_session(domain)


def _request_with_retry(url: str, *, params=None, cookies: httpx.Cookies) -> httpx.Response:
    """GET *url* with exponential-backoff retries on transient errors (429, 5xx)."""
    delay = _RETRY_BACKOFF
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        r = httpx.get(url, params=params, headers=HEADERS, cookies=cookies, timeout=15, follow_redirects=True)
        if r.status_code not in _RETRY_STATUS_CODES:
            return r
        if attempt == _RETRY_ATTEMPTS:
            break
        # Respect Retry-After header if present (429 often sends it)
        retry_after = r.headers.get("Retry-After")
        wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
        log.debug("HTTP %s — retrying in %.1fs (attempt %d/%d)", r.status_code, wait, attempt, _RETRY_ATTEMPTS)
        time.sleep(wait)
        delay *= 2
    r.raise_for_status()
    return r  # unreachable after raise_for_status, satisfies type checkers


def _request_with_forbidden_recovery(
    url: str, *, domain: str, cookies: httpx.Cookies, params=None
) -> tuple[httpx.Response, httpx.Cookies]:
    """Request once, and if blocked (403), refresh session and retry once."""
    r = _request_with_retry(url, params=params, cookies=cookies)
    if r.status_code != 403:
        return r, cookies

    log.debug("HTTP 403 for %s, refreshing session and retrying once", url)
    refreshed = _refresh_session(domain)
    retried = _request_with_retry(url, params=params, cookies=refreshed)
    return retried, refreshed


def _extract_item_object_from_page(page_html: str) -> dict | None:
    """Extract embedded item JSON from a Vinted item page."""
    marker_idx = page_html.find(r"\"item\":{")
    escaped_quotes = True
    if marker_idx == -1:
        marker_idx = page_html.find('"item":{')
        escaped_quotes = False
    if marker_idx == -1:
        return None

    start = page_html.find("{", marker_idx)
    if start == -1:
        return None

    # The embedded object uses escaped quotes (e.g. {\"id\":...}).
    # Braces are still literal, so a simple depth scan is sufficient here.
    depth = 0
    end = -1
    for pos, ch in enumerate(page_html[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = pos
                break

    if end == -1:
        return None

    raw = page_html[start : end + 1]
    if escaped_quotes:
        normalized = raw.replace(r"\"", '"').replace(r"\/", "/").replace('"$undefined"', "null")
    else:
        normalized = raw.replace('"$undefined"', "null")
    try:
        return json.loads(normalized)
    except json.JSONDecodeError:
        return None


def _is_escaped_at(text: str, pos: int) -> bool:
    backslashes = 0
    i = pos - 1
    while i >= 0 and text[i] == "\\":
        backslashes += 1
        i -= 1
    return backslashes % 2 == 1


def _extract_next_row(page_html: str, row_id: str) -> object | None:
    marker = f'"{row_id}:'
    start = page_html.find(marker)
    if start == -1:
        return None

    end = -1
    for pos in range(start + 1, len(page_html)):
        if page_html[pos] == '"' and not _is_escaped_at(page_html, pos):
            end = pos
            break
    if end == -1:
        return None

    try:
        row = json.loads(page_html[start : end + 1])
        return json.loads(row.split(":", 1)[1].strip())
    except (IndexError, json.JSONDecodeError):
        return None


def _resolve_next_reference(page_html: str, reference: str) -> object | None:
    if not reference.startswith("$") or ":" not in reference:
        return None

    row_id, path = reference[1:].split(":", 1)
    value = _extract_next_row(page_html, row_id)
    if value is None:
        return None

    for part in path.split(":"):
        if part == "props" and isinstance(value, list) and len(value) > 3:
            value = value[3]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            return None
    return value


def _resolve_item_references_from_page(item: dict, page_html: str) -> None:
    for key in ("photos", "price", "service_fee", "total_item_price", "plugins"):
        value = item.get(key)
        if isinstance(value, str):
            resolved = _resolve_next_reference(page_html, value)
            if resolved is not None:
                item[key] = resolved


def _extract_meta_description(page_html: str) -> str | None:
    marker = '<meta name="description" content="'
    i = page_html.find(marker)
    if i == -1:
        return None
    start = i + len(marker)
    end = page_html.find('"/>', start)
    if end == -1:
        return None
    return html.unescape(page_html[start:end]).strip()


def _parse_shipping_amount(text: str) -> str | None:
    """Extract normalized decimal amount from shipping text like 'från 38,59 kr'."""
    match = re.search(r"([0-9]+(?:[ .][0-9]{3})*(?:[,.][0-9]{1,2})?)", text)
    if not match:
        return None
    value = match.group(1).replace(" ", "").replace("\xa0", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    return value


def _extract_shipping_from_page(page_html: str, item_currency: str | None) -> dict:
    """Extract shipping banner details from item page HTML."""
    out: dict = {}

    title_match = re.search(r'data-testid="item-shipping-banner-title">([^<]+)<', page_html)
    price_match = re.search(r'data-testid="item-shipping-banner-price">([^<]+)<', page_html)

    title = html.unescape(title_match.group(1)).replace("\xa0", " ").strip() if title_match else None
    price_text = html.unescape(price_match.group(1)).replace("\xa0", " ").strip() if price_match else None
    shipping_text = " ".join(p for p in [title, price_text] if p).replace("\xa0", " ").strip()
    if not shipping_text:
        return out

    out["shipping_text"] = shipping_text

    # Vinted shows this in localized text; keep broad matching for robustness.
    if title and "gratis frakt" in title.lower():
        out["shipping_free"] = True
        return out

    amount = _parse_shipping_amount(price_text or shipping_text)
    if amount is not None:
        out["shipping_free"] = False
        out["shipping_price"] = {"amount": amount, "currency_code": item_currency or ""}

    return out


def _page_fallback_item(item_id: int | str, domain: str, cookies: httpx.Cookies) -> dict:
    item_url = f"https://{domain}/items/{item_id}"
    log.debug("Fallback GET %s", item_url)
    page_resp, _ = _request_with_forbidden_recovery(item_url, domain=domain, cookies=cookies)
    page_resp.raise_for_status()

    item = _extract_item_object_from_page(page_resp.text)
    if not item:
        raise ValueError("Could not parse item data from item page fallback")

    _resolve_item_references_from_page(item, page_resp.text)

    # Keep output close to the old API shape expected by formatters and scripts.
    if "brand_title" not in item and isinstance(item.get("brand_dto"), dict):
        item["brand_title"] = item["brand_dto"].get("title")
    if "user" not in item and item.get("login"):
        item["user"] = {"login": item["login"]}
    if "photo" not in item and isinstance(item.get("photos"), list) and item["photos"]:
        item["photo"] = item["photos"][0]
    if "url" not in item:
        item["url"] = item_url
    if "description" not in item:
        description = _extract_meta_description(page_resp.text)
        if description:
            title = item.get("title", "")
            prefix = f"{title} - "
            item["description"] = description[len(prefix) :] if title and description.startswith(prefix) else description
    item.update(_extract_shipping_from_page(page_resp.text, item.get("currency")))

    return {"item": item}


def _resolve_country(country: str) -> str:
    domain = COUNTRIES.get(country.lower())
    if not domain:
        raise ValueError(f"Unknown country '{country}'. Valid: {', '.join(sorted(COUNTRIES))}")
    return domain


def _resolve_condition(name: str) -> str:
    code = CONDITIONS.get(name.lower())
    if not code:
        raise ValueError(f"Unknown condition '{name}'. Valid: {', '.join(sorted(CONDITIONS))}")
    return code


def search(
    query: str = "",
    *,
    country: str = "se",
    price_min: int | None = None,
    price_max: int | None = None,
    condition: str | None = None,
    brand_id: str | None = None,
    size_id: str | None = None,
    catalog_ids: list[str] | tuple[str, ...] | None = None,
    sort: str | None = None,
    per_page: int = 20,
    page: int = 1,
) -> dict:
    """Search listings on Vinted.

    brand_id, size_id, and catalog IDs are numeric Vinted API IDs (e.g. brand_id="53" for Nike).
    Include brand or size terms in the query text for free-text filtering instead.
    """
    domain = _resolve_country(country)
    cookies = _get_session(domain)

    params: list[tuple[str, str]] = [
        ("per_page", str(per_page)),
        ("page", str(page)),
    ]
    if query:
        params.append(("search_text", query))
    if price_min is not None:
        params.append(("price_from", str(price_min)))
    if price_max is not None:
        params.append(("price_to", str(price_max)))
    if condition:
        params.append(("status_ids[]", _resolve_condition(condition)))
    if brand_id:
        params.append(("brand_ids[]", brand_id))
    if size_id:
        params.append(("size_ids[]", size_id))
    if catalog_ids:
        for catalog_id in catalog_ids:
            params.append(("catalog_ids[]", catalog_id))
    if sort:
        params.append(("order", SORT_MAP.get(sort, sort)))

    log.debug("GET https://%s/api/v2/catalog/items params=%s", domain, params)
    r, _ = _request_with_forbidden_recovery(
        f"https://{domain}/api/v2/catalog/items",
        params=params,
        domain=domain,
        cookies=cookies,
    )
    log.debug("Search response: %s", r.status_code)
    log.debug("Response body: %s", r.text[:2000])
    r.raise_for_status()
    return r.json()


def get_item(item_id: int | str, *, country: str = "se") -> dict:
    """Fetch full details for a specific item."""
    domain = _resolve_country(country)
    cookies = _get_session(domain)

    log.debug("GET https://%s/api/v2/items/%s", domain, item_id)
    r, cookies = _request_with_forbidden_recovery(
        f"https://{domain}/api/v2/items/{item_id}",
        domain=domain,
        cookies=cookies,
    )
    log.debug("Item response: %s", r.status_code)
    log.debug("Response body: %s", r.text[:2000])
    if r.status_code == 404:
        log.debug("Primary item endpoint returned 404; falling back to item page parsing")
        return _page_fallback_item(item_id, domain, cookies)
    r.raise_for_status()
    return r.json()


def fetch_catalogs(*, country: str = "se") -> list[dict]:
    """Fetch the full catalog tree from the Vinted API."""
    domain = _resolve_country(country)
    cookies = _get_session(domain)

    params = [("page", "1"), ("time", str(int(time.time())))]
    log.debug("GET https://%s/api/v2/catalog/initializers", domain)
    r, _ = _request_with_forbidden_recovery(
        f"https://{domain}/api/v2/catalog/initializers",
        params=params,
        domain=domain,
        cookies=cookies,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("dtos", {}).get("catalogs", [])


def _walk_catalogs(catalogs: list[dict], parent_id: int | None, depth: int) -> list[dict]:
    """Recursively walk catalog tree, collecting all nodes under parent_id."""
    results = []
    for cat in catalogs:
        if parent_id is None or cat.get("id") == parent_id:
            # Found the root we care about — collect everything under it
            results.append({"id": cat["id"], "title": cat["title"], "depth": depth})
            for child in cat.get("catalogs") or []:
                results.extend(_walk_catalogs([child], None, depth + 1))
        else:
            # Keep searching deeper
            results.extend(_walk_catalogs(cat.get("catalogs") or [], parent_id, depth))
    return results


def list_catalogs(*, country: str = "se", parent_id: int | None = None) -> list[dict]:
    """Return a flat list of catalogs, optionally scoped to a parent catalog ID."""
    catalogs = fetch_catalogs(country=country)
    return _walk_catalogs(catalogs, parent_id, 0)
