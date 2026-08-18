"""Static accessibility and offline-link checks for the Plan 009 HTML guide."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPOSITORY_ROOT = Path(__file__).parents[3]
GUIDE_PATH = REPOSITORY_ROOT / "docs" / "guides" / "009-facility-models-explained.html"
ROOT_BLOCK_PATTERN = re.compile(r":root\s*\{(?P<body>.*?)\}", re.DOTALL)
COLOR_VARIABLE_PATTERN = re.compile(
    r"--(?P<name>[a-z0-9-]+):\s*(?P<value>#[0-9a-fA-F]{3,6})(?:;|\s)"
)


class GuideParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.sources: list[str] = []
        self.meta_descriptions: list[str] = []
        self.h1_count = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        self.tags.append(tag)
        if identifier := attributes.get("id"):
            self.ids.add(identifier)
        if tag == "a" and (href := attributes.get("href")):
            self.links.append(href)
        if tag in {"img", "script", "iframe", "link", "audio", "video"} and (
            source := attributes.get("src") or attributes.get("href")
        ):
            self.sources.append(source)
        if (
            tag == "meta"
            and attributes.get("name") == "description"
            and (description := attributes.get("content"))
        ):
            self.meta_descriptions.append(description)
        if tag == "h1":
            self.h1_count += 1


def parsed_guide() -> tuple[str, GuideParser]:
    document = GUIDE_PATH.read_text(encoding="utf-8")
    parser = GuideParser()
    parser.feed(document)
    parser.close()
    return document, parser


def relative_luminance(hex_color: str) -> float:
    digits = hex_color.removeprefix("#")
    if len(digits) == 3:
        digits = "".join(character * 2 for character in digits)
    channels = [int(digits[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (relative_luminance(first), relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_guide_has_required_semantic_and_accessible_structure() -> None:
    document, parser = parsed_guide()

    assert parser.h1_count == 1
    assert parser.meta_descriptions
    assert {"header", "nav", "main", "section", "footer"}.issubset(parser.tags)
    assert "main-content" in parser.ids
    assert '<a class="skip-link" href="#main-content">' in document
    assert "aria-label=" in document
    assert 'scope="col"' in document
    assert ":focus-visible" in document
    assert "prefers-reduced-motion: reduce" in document
    assert "prefers-color-scheme: dark" in document
    assert "max-width: 38rem" in document
    assert "@media print" in document
    assert "color-scheme: light dark" in document


def test_guide_is_network_free_and_contains_required_plan_evidence() -> None:
    document, parser = parsed_guide()

    assert "<script" not in document.lower()
    assert not parser.sources
    assert not any(urlsplit(link).scheme in {"http", "https"} for link in parser.links)
    for required_text in (
        "Plan 009",
        "cms_dialysis_facility.raw.v1",
        "CMS Certification Number (CCN)",
        "CCN \u00d7 source-snapshot SHA-256",
        "7,490",
        "6,999",
        "T-012",
        "T-013",
        "not_attempted",
        "better_than_expected",
        "observed outpatient dialysis use among Original Medicare beneficiaries",
        "patient residence",
        "Census Geocoder",
    ):
        assert required_text in document


def test_light_and_dark_text_pairs_meet_wcag_aa_contrast() -> None:
    document, _parser = parsed_guide()
    palette_blocks = ROOT_BLOCK_PATTERN.findall(document)

    assert len(palette_blocks) >= 2
    for block in palette_blocks[:2]:
        palette = {
            match.group("name"): match.group("value")
            for match in COLOR_VARIABLE_PATTERN.finditer(block)
        }
        for foreground, background in (
            ("ink", "page"),
            ("ink", "surface"),
            ("muted", "page"),
            ("accent", "surface"),
            ("accent-ink", "accent"),
            ("ink", "warm"),
        ):
            assert contrast_ratio(palette[foreground], palette[background]) >= 4.5


def test_every_internal_fragment_and_file_link_resolves() -> None:
    _document, parser = parsed_guide()

    for href in parser.links:
        parsed = urlsplit(href)
        if parsed.fragment and not parsed.path:
            assert parsed.fragment in parser.ids, href
        if parsed.path:
            target = (GUIDE_PATH.parent / unquote(parsed.path)).resolve()
            assert target.is_relative_to(REPOSITORY_ROOT.resolve()), href
            assert target.exists(), href


def test_guide_is_registered_in_repository_indexes() -> None:
    root_readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    guide_readme = (GUIDE_PATH.parent / "README.md").read_text(encoding="utf-8")

    assert GUIDE_PATH.name in root_readme
    assert GUIDE_PATH.name in guide_readme
