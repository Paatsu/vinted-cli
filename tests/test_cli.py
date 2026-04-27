"""Tests for Vinted CLI commands (mocked HTTP)."""

from __future__ import annotations

import json
from unittest.mock import patch

from click.testing import CliRunner

from vinted_cli.cli import main

SEARCH_RESPONSE = {
    "items": [
        {
            "id": 1234567890,
            "title": "Nike Air Max 90",
            "price": "499",
            "total_item_price": {"amount": "542.49", "currency_code": "SEK"},
            "currency": "SEK",
            "brand_title": "Nike",
            "size_title": "42",
            "status": "Very good",
            "url": "https://www.vinted.se/items/1234567890-nike-air-max-90",
            "user": {"login": "seller123"},
            "photo": {"url": "https://images.vinted.se/1.jpg", "full_size_url": "https://images.vinted.se/1_full.jpg"},
            "description": "Great condition Nike shoes",
        }
    ],
    "pagination": {
        "current_page": 1,
        "total_pages": 5,
        "total_count": 98,
        "per_page": 20,
    },
}

ITEM_RESPONSE = {
    "item": {
        "id": 1234567890,
        "title": "Nike Air Max 90",
        "price": "499",
        "total_item_price": {"amount": "542.49", "currency_code": "SEK"},
        "currency": "SEK",
        "brand_title": "Nike",
        "size_title": "42",
        "status": "Very good",
        "url": "https://www.vinted.se/items/1234567890-nike-air-max-90",
        "user": {"login": "seller123"},
        "description": "Great condition Nike shoes",
    }
}


def _mock_search(*args, **kwargs):
    return SEARCH_RESPONSE


def _mock_get_item(*args, **kwargs):
    return ITEM_RESPONSE


class TestSearchCommand:
    def test_table_output(self):
        with patch("vinted_cli.cli.api.search", _mock_search):
            result = CliRunner().invoke(main, ["search", "nike"])
        assert result.exit_code == 0
        assert "Nike Air Max 90" in result.output
        assert "499 SEK" in result.output
        assert "Total (incl. fee): 542.49 SEK" in result.output

    def test_json_output_is_slim(self):
        with patch("vinted_cli.cli.api.search", _mock_search):
            result = CliRunner().invoke(main, ["search", "nike", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 98
        listing = data["results"][0]
        assert listing["id"] == 1234567890
        assert listing["title"] == "Nike Air Max 90"
        assert listing["price"] == "499"
        assert listing["total_price"] == "542.49"
        # Slim output should not include raw photo object
        assert "photo" not in listing or isinstance(listing["photo"], str)
        # Slim output should not include description
        assert "description" not in listing

    def test_json_raw_output(self):
        with patch("vinted_cli.cli.api.search", _mock_search):
            result = CliRunner().invoke(main, ["search", "nike", "-o", "json", "--raw"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        listing = data["results"][0]
        assert "description" in listing
        assert isinstance(listing["photo"], dict)

    def test_jsonl_output(self):
        with patch("vinted_cli.cli.api.search", _mock_search):
            result = CliRunner().invoke(main, ["search", "nike", "-o", "jsonl"])
        assert result.exit_code == 0
        lines = [line for line in result.output.strip().splitlines() if line]
        assert len(lines) == 1
        item = json.loads(lines[0])
        assert item["id"] == 1234567890

    def test_limit(self):
        with patch("vinted_cli.cli.api.search", _mock_search):
            result = CliRunner().invoke(main, ["search", "nike", "-o", "json", "-n", "1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["results"]) == 1

    def test_invalid_country(self):
        result = CliRunner().invoke(main, ["search", "nike", "--country", "xx"])
        assert result.exit_code == 1
        assert "Unknown country" in result.output

    def test_invalid_condition(self):
        result = CliRunner().invoke(main, ["search", "nike", "--condition", "terrible"])
        assert result.exit_code != 0

    def test_table_output_shows_seller(self):
        with patch("vinted_cli.cli.api.search", _mock_search):
            result = CliRunner().invoke(main, ["search", "nike"])
        assert "seller123" in result.output

    def test_single_catalog_id_passed_to_api(self):
        captured = {}

        def capture_search(*args, **kwargs):
            captured.update(kwargs)
            return SEARCH_RESPONSE

        with patch("vinted_cli.cli.api.search", capture_search):
            result = CliRunner().invoke(main, ["search", "nike", "--catalog-id", "1231"])
        assert result.exit_code == 0
        assert captured.get("catalog_ids") == ["1231"]

    def test_multiple_catalog_ids_passed_to_api(self):
        captured = {}

        def capture_search(*args, **kwargs):
            captured.update(kwargs)
            return SEARCH_RESPONSE

        with patch("vinted_cli.cli.api.search", capture_search):
            result = CliRunner().invoke(main, ["search", "nike", "--catalog-id", "1231", "--catalog-id", "1232"])
        assert result.exit_code == 0
        assert captured.get("catalog_ids") == ["1231", "1232"]

    def test_search_without_query(self):
        captured = {}

        def capture_search(*args, **kwargs):
            captured["query"] = args[0] if args else kwargs.get("query", "")
            return SEARCH_RESPONSE

        with patch("vinted_cli.cli.api.search", capture_search):
            result = CliRunner().invoke(main, ["search", "--catalog-id", "1231"])
        assert result.exit_code == 0
        assert captured.get("query") == ""


class TestItemCommand:
    def test_table_output(self):
        with patch("vinted_cli.cli.api.get_item", _mock_get_item):
            result = CliRunner().invoke(main, ["item", "1234567890"])
        assert result.exit_code == 0
        assert "Nike Air Max 90" in result.output
        assert "499 SEK" in result.output
        assert "Total (incl. fee): 542.49 SEK" in result.output
        assert "Nike" in result.output

    def test_json_output(self):
        with patch("vinted_cli.cli.api.get_item", _mock_get_item):
            result = CliRunner().invoke(main, ["item", "1234567890", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["item"]["title"] == "Nike Air Max 90"


class TestInfoCommands:
    def test_countries(self):
        result = CliRunner().invoke(main, ["countries"])
        assert result.exit_code == 0
        assert "se" in result.output
        assert "vinted.se" in result.output

    def test_conditions(self):
        result = CliRunner().invoke(main, ["conditions"])
        assert result.exit_code == 0
        assert "very-good" in result.output
        assert "Very good" in result.output
