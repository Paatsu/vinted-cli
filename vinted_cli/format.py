"""Output formatting for Vinted CLI."""

from __future__ import annotations

import json
import sys
from typing import Any

MAX_DESCRIPTION_LENGTH = 200


def _json_compact(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _extract_price(item: dict) -> tuple[str, str]:
    """Return (amount, currency) handling both flat and nested price formats."""
    price = item.get("price")
    if isinstance(price, dict):
        return str(price.get("amount", "-")), price.get("currency_code", "")
    # Legacy flat format
    return str(price) if price else "-", item.get("currency", "")


def _extract_total_price(item: dict) -> tuple[str | None, str]:
    """Return total buyer price (including fee) when available."""
    total = item.get("total_item_price")
    if total is None:
        total = item.get("total_price")

    if isinstance(total, dict):
        amount = total.get("amount")
        if amount is None:
            return None, ""
        return str(amount), total.get("currency_code", "")

    if total in (None, ""):
        return None, ""

    return str(total), item.get("currency", "")


def _slim(item: dict) -> dict:
    """Strip an item to agent-essential fields."""
    amount, currency = _extract_price(item)
    total_amount, _ = _extract_total_price(item)
    out: dict[str, Any] = {
        "id": item.get("id"),
        "title": item.get("title"),
        "price": amount,
        "total_price": total_amount,
        "currency": currency,
        "brand": item.get("brand_title"),
        "size": item.get("size_title"),
        "condition": item.get("status"),
        "seller": item.get("user", {}).get("login"),
        "url": item.get("url"),
    }
    photo = item.get("photo")
    if isinstance(photo, dict):
        out["photo"] = photo.get("url") or photo.get("full_size_url")
    # Remove None values for cleaner output
    return {k: v for k, v in out.items() if v is not None}


def print_results(data: dict, *, output: str = "table", limit: int | None = None, raw: bool = False) -> None:
    """Print search results."""
    items = data.get("items", [])
    total = data.get("pagination", {}).get("total_count", len(items))

    if limit:
        items = items[:limit]

    if output == "json":
        results = items if raw else [_slim(i) for i in items]
        print(_json_compact({"total": total, "results": results}))
        return

    if output == "jsonl":
        for item in items:
            print(_json_compact(item if raw else _slim(item)))
        return

    if not items:
        print("No results found.", file=sys.stderr)
        return

    print(f"Found {total:,} listings (showing {len(items)}):\n")

    for item in items:
        title = item.get("title", "Untitled")
        price, currency = _extract_price(item)
        total_price, total_currency = _extract_total_price(item)
        brand = item.get("brand_title", "")
        size = item.get("size_title", "")
        condition = item.get("status", "")
        seller = item.get("user", {}).get("login", "")
        url = item.get("url", "")

        price_str = f"{price} {currency}".strip() if price else "-"
        meta_parts = [p for p in [brand, size, condition] if p]
        meta_str = " | ".join(meta_parts) if meta_parts else ""

        print(f"  {title}")
        print(f"  {price_str}" + (f" | {meta_str}" if meta_str else ""))
        if total_price:
            total_str = f"{total_price} {(total_currency or currency)}".strip()
            print(f"  Total (incl. fee): {total_str}")
        if seller:
            print(f"  Seller: {seller}")
        print(f"  {url}")
        print()


def print_item(data: dict, *, output: str = "table") -> None:
    """Print item details."""
    if output == "json":
        print(_json_compact(data))
        return

    item = data.get("item", data)

    if "error" in item:
        print(f"Error: {item['error']}", file=sys.stderr)
        return

    title = item.get("title", "Untitled")
    price, currency = _extract_price(item)
    total_price, total_currency = _extract_total_price(item)
    brand = item.get("brand_title", "")
    size = item.get("size_title", "")
    condition = item.get("status", "")
    description = item.get("description", "")
    shipping_text = item.get("shipping_text", "")
    seller = item.get("user", {}).get("login", "")
    url = item.get("url", "")

    price_str = f"{price} {currency}".strip()
    print(f"  {title}")
    print(f"  {price_str}")
    if total_price:
        total_str = f"{total_price} {(total_currency or currency)}".strip()
        print(f"  Total (incl. fee): {total_str}")
    if brand:
        print(f"  Brand: {brand}")
    if size:
        print(f"  Size: {size}")
    if condition:
        print(f"  Condition: {condition}")
    if seller:
        print(f"  Seller: {seller}")
    if description:
        print(f"  Description: {description[:MAX_DESCRIPTION_LENGTH]}")
    if shipping_text:
        print(f"  Shipping: {shipping_text}")
    if url:
        print(f"  {url}")
