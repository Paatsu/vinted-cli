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


def test_get_item_falls_back_to_item_page_on_404():
    page_html = (
        '<meta name="description" content="Thinkpad USB-C Dock Gen2 - Dock till dator"/>'
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
