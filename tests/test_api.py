"""Tests for API-level fallback behavior."""

from __future__ import annotations

from unittest.mock import patch

import httpx

from vinted_cli import api


def _response(url: str, status: int, body: str, *, content_type: str = "text/html; charset=utf-8") -> httpx.Response:
    return httpx.Response(
        status,
        text=body,
        headers={"content-type": content_type},
        request=httpx.Request("GET", url),
    )


def test_get_item_uses_primary_json_endpoint():
    responses = [
        _response(
            "https://www.vinted.se/api/v2/items/123",
            200,
            '{"item":{"id":123,"title":"Primary item"}}',
            content_type="application/json; charset=utf-8",
        )
    ]

    def fake_request(url: str, *, params=None, cookies):  # noqa: ANN001
        return responses.pop(0)

    with patch("vinted_cli.api._get_session", return_value=httpx.Cookies()):
        with patch("vinted_cli.api._request_with_retry", side_effect=fake_request):
            data = api.get_item("123", country="se")

    assert data["item"]["id"] == 123
    assert data["item"]["title"] == "Primary item"


def test_get_item_retries_once_after_403_with_refreshed_session():
    first_cookies = httpx.Cookies({"sid": "old"})
    second_cookies = httpx.Cookies({"sid": "new"})
    observed_cookie_sids: list[str] = []
    responses = [
        _response("https://www.vinted.se/api/v2/items/123", 403, "<html>Forbidden</html>"),
        _response(
            "https://www.vinted.se/api/v2/items/123",
            200,
            '{"item":{"id":123,"title":"Recovered item"}}',
            content_type="application/json; charset=utf-8",
        ),
    ]

    def fake_request(url: str, *, params=None, cookies):  # noqa: ANN001
        observed_cookie_sids.append(cookies.get("sid"))
        return responses.pop(0)

    with patch("vinted_cli.api._get_session", side_effect=[first_cookies, second_cookies]):
        with patch("vinted_cli.api._request_with_retry", side_effect=fake_request):
            data = api.get_item("123", country="se")

    assert data["item"]["title"] == "Recovered item"
    assert observed_cookie_sids == ["old", "new"]


def test_get_item_falls_back_to_item_page_on_404():
    page_html = (
        '<meta name="description" content="Thinkpad USB-C Dock Gen2 - Dock till dator"/>'
        '<h3 data-testid="item-shipping-banner-title">Leverans</h3>'
        '<h3 data-testid="item-shipping-banner-price">från 38,59&nbsp;kr</h3>'
        '<script>self.__next_f.push([1,"x",{"item":{'
        '"id":8260880672,"title":"Thinkpad USB-C Dock Gen2","currency":"SEK",'
        '"price":{"amount":"100.0","currency_code":"SEK"},'
        '"is_closed":true,"item_closing_action":"sold",'
        '"brand_dto":{"title":"Lenovo"},'
        '"photos":[{"url":"https://images.example/1.webp"}],'
        '"login":"hallbergsvintage"'
        "}}])</script>"
    )

    responses = [
        _response("https://www.vinted.se/api/v2/items/8260880672", 404, "<html>Not Found</html>"),
        _response("https://www.vinted.se/items/8260880672", 200, page_html),
    ]

    def fake_request(url: str, *, params=None, cookies):  # noqa: ANN001
        return responses.pop(0)

    with patch("vinted_cli.api._get_session", return_value=httpx.Cookies()):
        with patch("vinted_cli.api._request_with_retry", side_effect=fake_request):
            data = api.get_item("8260880672", country="se")

    item = data["item"]
    assert item["id"] == 8260880672
    assert item["title"] == "Thinkpad USB-C Dock Gen2"
    assert item["brand_title"] == "Lenovo"
    assert item["user"]["login"] == "hallbergsvintage"
    assert item["url"] == "https://www.vinted.se/items/8260880672"
    assert item["description"] == "Dock till dator"
    assert item["shipping_text"] == "Leverans från 38,59 kr"
    assert item["shipping_free"] is False
    assert item["shipping_price"]["amount"] == "38.59"
    assert item["shipping_price"]["currency_code"] == "SEK"


def test_get_item_fallback_extracts_free_shipping():
    page_html = (
        '<h3 data-testid="item-shipping-banner-title">Gratis frakt</h3>'
        '<script>self.__next_f.push([1,"x",{"item":{'
        '"id":111,"title":"Item with free shipping","currency":"SEK",'
        '"price":{"amount":"10.0","currency_code":"SEK"},'
        '"brand_dto":{"title":"Brand"},"login":"user1"'
        "}}])</script>"
    )
    responses = [
        _response("https://www.vinted.se/api/v2/items/111", 404, "<html>Not Found</html>"),
        _response("https://www.vinted.se/items/111", 200, page_html),
    ]

    def fake_request(url: str, *, params=None, cookies):  # noqa: ANN001
        return responses.pop(0)

    with patch("vinted_cli.api._get_session", return_value=httpx.Cookies()):
        with patch("vinted_cli.api._request_with_retry", side_effect=fake_request):
            data = api.get_item("111", country="se")

    item = data["item"]
    assert item["shipping_text"] == "Gratis frakt"
    assert item["shipping_free"] is True
    assert "shipping_price" not in item


def test_get_item_fallback_resolves_next_references():
    page_html = (
        '<script>self.__next_f.push([1,"3b:[\\"$\\",\\"$Ld3\\",null,{\\"value\\":{'
        '\\"price\\":{\\"amount\\":\\"50.0\\",\\"currency_code\\":\\"SEK\\"},'
        '\\"service_fee\\":{\\"amount\\":\\"10.0\\",\\"currency_code\\":\\"SEK\\"},'
        '\\"total_item_price\\":{\\"amount\\":\\"60.0\\",\\"currency_code\\":\\"SEK\\"},'
        '\\"photos\\":[{\\"url\\":\\"https://images.example/chromecast.webp\\"}]'
        "}}]\\n\"])</script>"
        '<script>self.__next_f.push([1,"x",{"item":{'
        '"id":8762725457,"title":"Chromecast","currency":"SEK",'
        '"price":"$3b:props:value:price",'
        '"service_fee":"$3b:props:value:service_fee",'
        '"total_item_price":"$3b:props:value:total_item_price",'
        '"photos":"$3b:props:value:photos",'
        '"brand_dto":{"title":"Google"},"login":"lisan12"'
        "}}])</script>"
    )
    responses = [
        _response("https://www.vinted.se/api/v2/items/8762725457", 404, "<html>Not Found</html>"),
        _response("https://www.vinted.se/items/8762725457", 200, page_html),
    ]

    def fake_request(url: str, *, params=None, cookies):  # noqa: ANN001
        return responses.pop(0)

    with patch("vinted_cli.api._get_session", return_value=httpx.Cookies()):
        with patch("vinted_cli.api._request_with_retry", side_effect=fake_request):
            data = api.get_item("8762725457", country="se")

    item = data["item"]
    assert item["price"] == {"amount": "50.0", "currency_code": "SEK"}
    assert item["service_fee"] == {"amount": "10.0", "currency_code": "SEK"}
    assert item["total_item_price"] == {"amount": "60.0", "currency_code": "SEK"}
    assert item["photo"]["url"] == "https://images.example/chromecast.webp"


def test_search_sends_multiple_catalog_ids():
    captured: dict = {}

    def fake_request_with_forbidden_recovery(url: str, *, domain: str, cookies, params=None):  # noqa: ANN001
        captured["url"] = url
        captured["domain"] = domain
        captured["params"] = params
        response = httpx.Response(
            200,
            json={"items": [], "pagination": {"total_count": 0}},
            request=httpx.Request("GET", url),
        )
        return response, cookies

    with patch("vinted_cli.api._get_session", return_value=httpx.Cookies()):
        with patch("vinted_cli.api._request_with_forbidden_recovery", side_effect=fake_request_with_forbidden_recovery):
            api.search("nike", country="se", catalog_ids=["1231", "1232"])

    assert captured["url"] == "https://www.vinted.se/api/v2/catalog/items"
    assert ("catalog_ids[]", "1231") in captured["params"]
    assert ("catalog_ids[]", "1232") in captured["params"]
