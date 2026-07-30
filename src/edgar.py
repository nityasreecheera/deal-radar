"""
SEC EDGAR ingestion for Form D filings.

Two endpoints are used. The full-text search API finds which filings exist for a
date range and industry, and the Archives serve each filing's XML. Neither
requires a key, but the SEC does require a User-Agent that identifies you, and
asks for no more than ten requests a second.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx

from src.models import SEC_HEALTHCARE_GROUPS, FormDFiling, RelatedPerson


SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

# The SEC blocks requests that do not identify a contact. Override via env so a
# deployment can declare its own operator.
DEFAULT_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "deal-radar nityasree.cheera24@gmail.com",
)

# The SEC asks for at most ten requests a second. This is deliberately well
# under that: a day's healthcare filings number in single digits, so there is
# nothing to gain by going faster and a block would cost a day of data.
REQUEST_DELAY_SECONDS = 0.2

SEARCH_PAGE_SIZE = 10

# A fetcher takes a URL and returns the response body. Injectable so that every
# test runs offline.
Fetcher = Callable[[str], str]


class EdgarError(RuntimeError):
    """Raised when EDGAR cannot be read."""


def create_fetcher(user_agent: str | None = None) -> Fetcher:
    """Build a fetcher that talks to the real EDGAR."""
    headers = {
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }

    client = httpx.Client(headers=headers, timeout=30.0, follow_redirects=True)

    def fetch(url: str) -> str:
        response = client.get(url)

        if response.status_code == 403:
            raise EdgarError(
                "EDGAR returned 403. Check that SEC_USER_AGENT identifies you "
                "with a contact address."
            )

        response.raise_for_status()

        return response.text

    return fetch


def build_search_url(
    industry_group: str,
    start_date: str,
    end_date: str,
    offset: int = 0,
) -> str:
    """
    Build a full-text search URL for Form D filings in one industry group.

    The industry group is matched as a quoted phrase because it appears verbatim
    inside each filing's XML. That is what makes filtering free — no filing has
    to be downloaded to discover whether it is relevant. The quotes must survive
    encoding, or the search matches each word separately and returns everything.
    """
    params: dict[str, str | int] = {
        "q": f'"{industry_group}"',
        "forms": "D",
        "startdt": start_date,
        "enddt": end_date,
    }

    if offset:
        params["from"] = offset

    return f"{SEARCH_URL}?{urlencode(params)}"


def filing_xml_url(cik: str, accession: str) -> str:
    """
    Build the URL of a filing's primary document.

    EDGAR wants the CIK without leading zeros and the accession without dashes,
    which is a small inconsistency worth handling in exactly one place.
    """
    numeric_cik = str(int(cik))
    flat_accession = accession.replace("-", "")

    return f"{ARCHIVES_URL}/{numeric_cik}/{flat_accession}/primary_doc.xml"


def parse_search_results(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Pull accession, CIK, and filing date out of a search response."""
    hits = payload.get("hits", {}).get("hits", [])

    results: list[dict[str, str]] = []

    for hit in hits:
        identifier = str(hit.get("_id") or "")
        source = hit.get("_source") or {}
        ciks = source.get("ciks") or []

        if ":" not in identifier or not ciks:
            continue

        results.append(
            {
                "accession": identifier.split(":", 1)[0],
                "cik": str(ciks[0]),
                "filed_date": str(source.get("file_date") or ""),
            }
        )

    return results


def total_hits(payload: dict[str, Any]) -> int:
    """How many filings matched, across all pages."""
    total = payload.get("hits", {}).get("total", {})

    return int(total.get("value") or 0)


def strip_namespace(tag: str) -> str:
    """Reduce '{urn:...}entityName' to 'entityName'."""
    return tag.split("}")[-1]


def find_text(element: ElementTree.Element, path: list[str]) -> str | None:
    """
    Walk a tag path ignoring namespaces and return the text found.

    Written by hand rather than with XPath because Form D declares a namespace
    that varies by schema version, and matching on local names is more durable
    than pinning the URI.
    """
    current: ElementTree.Element | None = element

    for name in path:
        if current is None:
            return None

        current = next(
            (
                child
                for child in current
                if strip_namespace(child.tag) == name
            ),
            None,
        )

    if current is None or current.text is None:
        return None

    text = current.text.strip()

    return text or None


def find_element(
    element: ElementTree.Element,
    path: list[str],
) -> ElementTree.Element | None:
    """Walk a tag path ignoring namespaces and return the element."""
    current: ElementTree.Element | None = element

    for name in path:
        if current is None:
            return None

        current = next(
            (child for child in current if strip_namespace(child.tag) == name),
            None,
        )

    return current


def to_int(value: str | None) -> int | None:
    """Parse an integer, treating anything unparseable as absent."""
    if value is None:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def child_or_self(
    element: ElementTree.Element,
    name: str,
) -> ElementTree.Element:
    """
    Return a named child, or the element itself when that child is absent.

    Written with an explicit None check rather than `or`, because an Element
    with no children is falsey — so `find_element(...) or element` silently
    falls back even when the child was found.
    """
    found = find_element(element, [name])

    return element if found is None else found


def parse_related_persons(root: ElementTree.Element) -> list[RelatedPerson]:
    """Read the officers, directors, and promoters named on the filing."""
    container = find_element(root, ["relatedPersonsList"])

    if container is None:
        return []

    people: list[RelatedPerson] = []

    for info in container:
        if strip_namespace(info.tag) != "relatedPersonInfo":
            continue

        name_block = child_or_self(info, "relatedPersonName")
        address = child_or_self(info, "relatedPersonAddress")
        relations = child_or_self(info, "relatedPersonRelationshipList")

        relationships = [
            child.text.strip()
            for child in relations
            if strip_namespace(child.tag) == "relationship"
            and child.text
            and child.text.strip()
        ]

        people.append(
            RelatedPerson(
                first_name=find_text(name_block, ["firstName"]) or "",
                last_name=find_text(name_block, ["lastName"]) or "",
                relationships=relationships,
                city=find_text(address, ["city"]),
                state=find_text(address, ["stateOrCountry"]),
            )
        )

    return people


def parse_form_d(
    xml_text: str,
    accession: str,
    filed_date: str,
) -> FormDFiling:
    """
    Parse a Form D primary document.

    The accession and filing date come from the search result rather than the
    document, because the document does not carry them.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise EdgarError(f"{accession}: could not parse XML ({exc})") from exc

    issuer = find_element(root, ["primaryIssuer"])

    if issuer is None:
        raise EdgarError(f"{accession}: no primaryIssuer in the filing")

    company_name = find_text(issuer, ["entityName"])
    cik = find_text(issuer, ["cik"])

    if not company_name or not cik:
        raise EdgarError(f"{accession}: filing has no issuer name or CIK")

    # Every one of these checks is `is not None` rather than truthiness: an
    # Element with no children is falsey, so `if offering` would treat an empty
    # <offeringData> as missing and silently drop every amount on the filing.
    address = find_element(issuer, ["issuerAddress"])
    offering = find_element(root, ["offeringData"])
    year_block = find_element(issuer, ["yearOfInc"])

    amounts = (
        find_element(offering, ["offeringSalesAmounts"])
        if offering is not None
        else None
    )

    industry_group = (
        find_text(offering, ["industryGroup", "industryGroupType"])
        if offering is not None
        else None
    )

    amendment = (
        find_text(offering, ["typeOfFiling", "isAmendment"])
        if offering is not None
        else None
    )

    investors = (
        find_text(offering, ["investors", "totalNumberAlreadyInvested"])
        if offering is not None
        else None
    )

    return FormDFiling(
        accession=accession,
        cik=cik,
        company_name=company_name,
        filed_date=filed_date,
        industry_group=industry_group or "Unknown",
        entity_type=find_text(issuer, ["entityType"]),
        jurisdiction=find_text(issuer, ["jurisdictionOfInc"]),
        year_of_incorporation=(
            to_int(find_text(year_block, ["value"]))
            if year_block is not None
            else None
        ),
        city=find_text(address, ["city"]) if address is not None else None,
        state=(
            find_text(address, ["stateOrCountry"])
            if address is not None
            else None
        ),
        total_offering_amount=(
            to_int(find_text(amounts, ["totalOfferingAmount"]))
            if amounts is not None
            else None
        ),
        total_amount_sold=(
            to_int(find_text(amounts, ["totalAmountSold"]))
            if amounts is not None
            else None
        ),
        investor_count=to_int(investors),
        is_amendment=(amendment or "").lower() == "true",
        related_persons=parse_related_persons(root),
    )


def search_industry(
    industry_group: str,
    start_date: str,
    end_date: str,
    fetch: Fetcher,
    max_results: int = 200,
) -> list[dict[str, str]]:
    """Page through search results for one industry group."""
    collected: list[dict[str, str]] = []
    offset = 0

    while offset < max_results:
        url = build_search_url(industry_group, start_date, end_date, offset)

        try:
            payload = json.loads(fetch(url))
        except json.JSONDecodeError as exc:
            raise EdgarError(f"search returned invalid JSON ({exc})") from exc

        page = parse_search_results(payload)
        collected.extend(page)

        total = total_hits(payload)
        offset += SEARCH_PAGE_SIZE

        if not page or offset >= total:
            break

        time.sleep(REQUEST_DELAY_SECONDS)

    return collected[:max_results]


def fetch_filings(
    start_date: str,
    end_date: str,
    industry_groups: list[str] | tuple[str, ...] = SEC_HEALTHCARE_GROUPS,
    fetch: Fetcher | None = None,
    max_per_group: int = 200,
) -> tuple[list[FormDFiling], list[str]]:
    """
    Fetch and parse every Form D filed in a date range for the given groups.

    Returns the filings alongside one message per filing that could not be read,
    so a single malformed document does not lose the whole day's data.

    Each industry group is searched separately rather than with one broad query,
    because a filing states exactly one group and precise matching avoids
    downloading filings that were never relevant.
    """
    fetcher = fetch or create_fetcher()

    problems: list[str] = []
    filings: list[FormDFiling] = []
    seen_accessions: set[str] = set()

    for group in industry_groups:
        try:
            results = search_industry(
                group,
                start_date,
                end_date,
                fetcher,
                max_results=max_per_group,
            )
        except EdgarError as exc:
            problems.append(f"search '{group}': {exc}")
            continue

        for result in results:
            accession = result["accession"]

            if accession in seen_accessions:
                continue

            seen_accessions.add(accession)

            url = filing_xml_url(result["cik"], accession)

            try:
                xml_text = fetcher(url)
                filing = parse_form_d(
                    xml_text,
                    accession,
                    result["filed_date"],
                )
            except (EdgarError, httpx.HTTPError) as exc:
                problems.append(f"{accession}: {exc}")
                continue

            # The search matched on a phrase inside the document, which can hit
            # a filing whose stated group is something else. Trust the parsed
            # field over the search match.
            if filing.in_groups(industry_groups):
                filings.append(filing)

            time.sleep(REQUEST_DELAY_SECONDS)

    filings.sort(key=lambda item: item.filed_date, reverse=True)

    return filings, problems
