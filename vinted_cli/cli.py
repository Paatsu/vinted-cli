"""Vinted CLI — search Vinted from the terminal."""

from __future__ import annotations

import logging
import os
import sys

import click

from . import api, format

DEFAULT_COUNTRY = os.environ.get("VINTED_COUNTRY", "se")

SORT_CHOICES = ["relevance", "newest", "oldest", "price-asc", "price-desc"]


@click.group()
@click.version_option()
@click.option("--debug", is_flag=True, envvar="VINTED_DEBUG", help="Enable debug logging.")
@click.pass_context
def main(ctx: click.Context, debug: bool):
    """Search Vinted from the command line.

    Fast, minimal CLI for searching Vinted. Defaults to vinted.se.
    Designed for scripting, agents, and quick lookups.

    Set the VINTED_COUNTRY environment variable to change the default country.
    """
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)


@main.command()
@click.argument("query", default="", required=False)
@click.option("--country", default=DEFAULT_COUNTRY, show_default=True, help="Country code (se, fr, de, uk, pl, …)")
@click.option("--price-min", type=int, help="Minimum price")
@click.option("--price-max", type=int, help="Maximum price")
@click.option(
    "--condition",
    type=click.Choice(["new-with-tags", "new-without-tags", "very-good", "good", "satisfactory"], case_sensitive=False),
    help="Item condition",
)
@click.option("--brand-id", help="Numeric Vinted brand ID (e.g. 53 for Nike; include brand in query for free-text)")
@click.option("--size-id", help="Numeric Vinted size ID (include size in query for free-text, e.g. 'jeans XL')")
@click.option(
    "--catalog-id",
    multiple=True,
    help="Numeric Vinted catalog ID to filter by category. Repeat to include multiple categories (use `vinted catalogs` to list them)",
)
@click.option("--sort", type=click.Choice(SORT_CHOICES, case_sensitive=False), help="Sort order")
@click.option("-n", "--limit", type=int, help="Max results to show")
@click.option("-p", "--page", type=int, default=1, help="Page number")
@click.option("-o", "--output", type=click.Choice(["table", "json", "jsonl"]), default="table", help="Output format")
@click.option("--raw", is_flag=True, help="Full API response (default: slim agent-friendly fields)")
def search(
    query: str,
    country: str,
    price_min: int | None,
    price_max: int | None,
    condition: str | None,
    brand_id: str | None,
    size_id: str | None,
    catalog_id: tuple[str, ...],
    sort: str | None,
    limit: int | None,
    page: int,
    output: str,
    raw: bool,
):
    """Search listings on Vinted.

    QUERY is optional — omit it to browse without a text filter.

    \b
    Examples:
        vinted search "jeans"
        vinted search "iphone 15" --price-max 5000
        vinted search "nike" --condition very-good --sort price-asc
        vinted search "dress M" --sort newest -n 10
        vinted search "jacka" -o json | jq '.results[:3]'
        vinted search "jacka" --country se -o jsonl
        vinted search "sneakers" --catalog-id 1231
        vinted search "sneakers" --catalog-id 1231 --catalog-id 1232
        vinted search --catalog-id 1231 --sort newest
        vinted search --price-max 100
    """
    try:
        data = api.search(
            query,
            country=country,
            price_min=price_min,
            price_max=price_max,
            condition=condition,
            brand_id=brand_id,
            size_id=size_id,
            catalog_ids=list(catalog_id) if catalog_id else None,
            sort=sort,
            page=page,
        )
        format.print_results(data, output=output, limit=limit, raw=raw)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("item_id")
@click.option("--country", default=DEFAULT_COUNTRY, show_default=True, help="Country code (se, fr, de, uk, pl, …)")
@click.option("-o", "--output", type=click.Choice(["table", "json"]), default="table", help="Output format")
def item(item_id: str, country: str, output: str):
    """Get full details for a specific item.

    \b
    Examples:
        vinted item 1234567890
        vinted item 1234567890 -o json
        vinted item 1234567890 --country fr
    """
    try:
        data = api.get_item(item_id, country=country)
        format.print_item(data, output=output)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def countries():
    """List supported country codes.

    \b
    Examples:
        vinted countries
    """
    print("Supported country codes:\n")
    for code, domain in sorted(api.COUNTRIES.items()):
        print(f"  {code:<6}  {domain}")


@main.command()
def conditions():
    """List item condition filters.

    \b
    Examples:
        vinted conditions
    """
    print("Item conditions:\n")
    for key, label in api.CONDITION_LABELS.items():
        print(f"  {key:<20}  {label}")


@main.command()
@click.option("--country", default=DEFAULT_COUNTRY, show_default=True, help="Country code")
@click.option("--parent-id", type=int, default=None, help="Show only subcatalogs of this catalog ID")
@click.option("-o", "--output", type=click.Choice(["table", "json"]), default="table", help="Output format")
def catalogs(country: str, parent_id: int | None, output: str):
    """List Vinted catalog IDs and their names.

    \b
    Examples:
        vinted catalogs
        vinted catalogs --parent-id 2994
        vinted catalogs --parent-id 2994 -o json
        vinted catalogs --country fr --parent-id 2994
    """
    try:
        entries = api.list_catalogs(country=country, parent_id=parent_id)
        if output == "json":
            import json
            print(json.dumps(entries, ensure_ascii=False))
            return
        if not entries:
            click.echo("No catalogs found.", err=True)
            return
        for entry in entries:
            indent = "  " * entry["depth"]
            print(f"{indent}{entry['id']:<8}  {entry['title']}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
