#!/usr/bin/env python3
"""
Import articles from Intercom and convert to Mintlify MDX files.

Usage:
  python import.py                # import all articles
  python import.py --limit 5      # import only first 5 published articles (for testing)
"""

import os
import re
import sys
import json
import time
import hashlib
import requests
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote

INTERCOM_TOKEN = os.environ.get("INTERCOM_TOKEN")
DOCS_DIR = Path(__file__).parent.parent
IMAGES_DIR = DOCS_DIR / "images" / "imported"
HEADERS = {
    "Authorization": f"Bearer {INTERCOM_TOKEN}",
    "Accept": "application/json",
    "Intercom-Version": "2.11",
}

_image_cache: dict[str, str] = {}  # original URL → local path

# ── Global article link mapping ──────────────────────────────────────────────
# Populated in main() before any conversion happens.
# Maps Intercom article ID (str) → Mintlify relative path (e.g. "campaigns/my-article")
_article_link_map: dict[str, str] = {}


# ── Article → Collection mapping (scraped from help.maestra.io) ──────────────
# Maps article ID (str) → leaf collection ID (str)
# Built from the actual website structure at https://help.maestra.io/en/
ARTICLE_COLLECTION_MAP: dict[str, str] = {
    # Customers, orders and products > Customers (14162110)
    "11584375": "14162110", "11840644": "14162110", "11840796": "14162110",
    "11840886": "14162110", "11841410": "14162110", "12292528": "14162110",
    # Customers, orders and products > Actions (14164305)
    "11841652": "14164305",
    # Customers, orders and products > Orders (14166223)
    "11843001": "14166223",
    # Customers, orders and products > Products (14166379)
    "11843350": "14166379", "12359414": "14166379", "12510421": "14166379",
    "13016201": "14166379",
    # Customers, orders and products > Data Export (14166397)
    "11886904": "14166397",
    # Filters (3489400) — direct articles
    "6262584": "3489400", "6262582": "3489400",
    # Filters > Filtering by Campaign Engagement (17802447)
    "13153514": "17802447", "13154551": "17802447", "13154544": "17802447",
    "12822152": "17802447",
    # Filters > Filtering by Orders (18447532)
    "13667714": "18447532", "13667784": "18447532", "13666431": "18447532",
    "13666599": "18447532", "13666536": "18447532", "13666942": "18447532",
    "13667416": "18447532", "13667340": "18447532", "13667626": "18447532",
    "13667686": "18447532", "13667832": "18447532",
    # Segments (14300709)
    "11887488": "14300709", "11887995": "14300709", "11888563": "14300709",
    "11888976": "14300709", "11889655": "14300709", "11890112": "14300709",
    # Flows (14306688) — direct articles
    "11890158": "14306688", "11890212": "14306688", "11890368": "14306688",
    "12610982": "14306688",
    # Flows > Examples (14307925)
    "11890376": "14307925", "11890392": "14307925",
    # Campaigns (14324580) — direct articles
    "11897760": "14324580", "11898085": "14324580", "11898129": "14324580",
    "11898318": "14324580", "12062349": "14324580", "13901638": "14324580",
    # Campaigns > Email campaigns (14325818) — direct articles
    "11898514": "14325818", "12032930": "14325818",
    # Campaigns > Email campaigns > Get started (14352270)
    "11908974": "14352270", "11908956": "14352270",
    # Campaigns > Email campaigns > Email authentication methods (14352304)
    "11909019": "14352304",
    # Campaigns > Email campaigns > Email deliverability (14352309)
    "11909063": "14352309", "11909081": "14352309", "11909119": "14352309",
    "11909164": "14352309", "11909207": "14352309", "11909223": "14352309",
    "11909239": "14352309", "11909249": "14352309", "11909260": "14352309",
    "11909288": "14352309", "11909299": "14352309", "11909312": "14352309",
    "11909324": "14352309", "11909331": "14352309",
    # Campaigns > SMS campaigns (14326356)
    "11898684": "14326356", "13189084": "14326356",
    # Campaigns > Mobile Push Campaigns (14326815)
    "11898878": "14326815", "11898923": "14326815",
    # Campaigns > Common Settings (14327618)
    "11899072": "14327618", "11899127": "14327618", "11899160": "14327618",
    # Campaigns > A/B Tests (14328122)
    "11899222": "14328122",
    # Campaigns > Message template engine (14328275)
    "11899281": "14328275", "11899317": "14328275", "11899338": "14328275",
    "11909592": "14328275", "11909641": "14328275", "12533973": "14328275",
    # Campaigns > Webhooks (14328437)
    "11899352": "14328437", "11899415": "14328437", "11899437": "14328437",
    # Personalization > Pop-up forms and embedded blocks (14328859)
    "12441549": "14328859", "13520096": "14328859", "11899548": "14328859",
    # Personalization > Product recommendation (14329452)
    "11899614": "14329452",
    # Mobile app personalization (14329906)
    "11899783": "14329906", "11899700": "14329906",
    # Ad Optimization (14330415)
    "11899881": "14330415",
    # Loyalty (14330509)
    "11899917": "14330509", "11899942": "14330509", "11899955": "14330509",
    "13316509": "14330509",
    # Reports (14330727)
    "11899963": "14330727", "12089048": "14330727", "11963919": "14330727",
    "11900062": "14330727", "11900080": "14330727", "12610185": "14330727",
    "13908737": "14330727",
    # API integrations (14331018)
    "11900113": "14331018", "11900131": "14331018", "11900149": "14331018",
    "11900218": "14331018",
    # Administration (14331830)
    "11900237": "14331830", "12988784": "14331830", "13007364": "14331830",
    # Security (14331890)
    "11900245": "14331890", "12747464": "14331890", "12821109": "14331890",
    "12747519": "14331890", "13639572": "14331890", "13639576": "14331890",
    "13639601": "14331890",
}


def download_image(url: str) -> str:
    """Download image from URL, save locally, return relative path for MDX."""
    base_url = url.split("?")[0]
    raw_filename = base_url.rstrip("/").split("/")[-1]
    filename = unquote(raw_filename).replace("+", "-").replace(" ", "-")
    filename = re.sub(r"[^\x20-\x7E]", "", filename)
    if not filename or "." not in filename:
        short = hashlib.md5(base_url.encode()).hexdigest()[:8]
        filename = f"img-{short}.png"

    local_path = IMAGES_DIR / filename
    rel_path = f"/images/imported/{filename}"

    if url in _image_cache:
        return _image_cache[url]
    if local_path.exists():
        _image_cache[url] = rel_path
        return rel_path

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(resp.content)
        _image_cache[url] = rel_path
        return rel_path
    except Exception as e:
        print(f"  ! Failed to download image {url}: {e}")
        return url


def rewrite_intercom_link(href: str) -> str:
    """Convert Intercom article URLs to internal Mintlify paths."""
    m = re.search(r"/articles/(\d+)", href)
    if m:
        article_id = m.group(1)
        if article_id in _article_link_map:
            return f"/{_article_link_map[article_id]}"
    return href


# ── HTML → Markdown conversion ────────────────────────────────────────────────

# Intercom callout colors → Mintlify component name.
# Colors come from the inline style="background-color: #...;" attribute.
CALLOUT_COLOR_MAP = {
    "#e3e7fa80": "Note",     # blue
    "#d7efdc80": "Tip",      # green
    "#feedaf80": "Warning",  # yellow
    "#fed9db80": "Warning",  # red/pink (Mintlify has no Danger; map to Warning)
    "#e8e8e880": "Info",     # gray
}


class HtmlToMarkdown(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self._stack = []
        self._list_stack = []
        self._skip = False
        self._link_href = None
        self._list_item_index = []
        self._needs_space_after_marker = False
        self._just_opened_inline = False  # True right after emitting opening ** or *
        # Table state
        self._in_table = False
        self._table_rows: list[list[str]] = []  # [[cell, cell, ...], ...]
        self._table_is_header: list[bool] = []  # True if row came from <th>
        self._current_cell: list[str] | None = None
        self._current_row_is_header = False
        # Callout / accordion state
        # _div_stack: parallel to <div> opens — each entry is ("callout"|"acc-content"|"plain", component_name|None)
        self._div_stack: list[tuple[str, str | None]] = []
        self._in_summary = False
        self._saved_result_for_summary: list | None = None

    def _in_li(self):
        return "li" in self._stack

    def _append(self, text: str):
        """Append text to the current cell buffer if in a table, otherwise to main result."""
        if self._in_table and self._current_cell is not None:
            self._current_cell.append(text)
        else:
            self.result.append(text)

    def _ensure_inline_space(self):
        """Ensure a space before opening bold/italic marker if preceded by a word character.

        Prevents "text**bold**" — should be "text **bold**".
        """
        buf = self._current_cell if (self._in_table and self._current_cell is not None) else self.result
        if buf and buf[-1] and buf[-1][-1].isalnum():
            buf.append(" ")

    def _close_inline_marker(self, marker: str):
        """Close bold/italic marker, ensuring proper rendering.

        1. Move trailing whitespace outside: "**text **" → "**text** "
        2. Flag that next text may need a leading space so the marker
           is not glued to the following word:
           "**text.**For" → "**text.** For"
        """
        buf = self._current_cell if (self._in_table and self._current_cell is not None) else self.result
        # Check if last chunk ends with whitespace — move it outside
        if buf and buf[-1].endswith(" "):
            buf[-1] = buf[-1].rstrip(" ")
            buf.append(marker)
            buf.append(" ")
            self._needs_space_after_marker = False  # already have space
        else:
            buf.append(marker)
            self._needs_space_after_marker = True  # may need space before next word

    # Block-level tags that reset inline marker state
    _BLOCK_TAGS = frozenset((
        "p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
        "li", "ul", "ol", "br", "hr", "blockquote", "pre",
        "table", "tr", "td", "th", "thead", "tbody", "tfoot",
    ))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self._stack.append(tag)

        # Reset inline-marker flags at block boundaries so they
        # don't bleed from one paragraph / list-item / cell to the next.
        if tag in self._BLOCK_TAGS:
            self._needs_space_after_marker = False
            self._just_opened_inline = False

        if tag in ("script", "style"):
            self._skip = True
        elif tag == "table":
            self._in_table = True
            self._table_rows = []
            self._table_is_header = []
        elif tag == "tr":
            self._current_row_is_header = False
        elif tag in ("td", "th"):
            self._current_cell = []
            if tag == "th":
                self._current_row_is_header = True
        elif tag == "br" and self._in_table:
            if self._current_cell is not None:
                self._current_cell.append(" ")
        elif tag == "br":
            if self._in_li():
                self.result.append(" ")
            else:
                self.result.append("\n")
        elif tag == "p":
            if self._in_li():
                text = "".join(self.result)
                if text and not text.endswith(" ") and not text.endswith("\n- ") and not text.endswith(". "):
                    stripped = text.rstrip("\n")
                    if stripped.endswith("- ") or stripped.endswith(". "):
                        pass
                    elif text.endswith("\n"):
                        pass
            else:
                self._ensure_blank_line()
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._ensure_blank_line()
            level = int(tag[1])
            self.result.append("#" * level + " ")
        elif tag == "ul":
            self._list_stack.append("ul")
            self._list_item_index.append(0)
            if not self._in_li():
                self._ensure_blank_line()
        elif tag == "ol":
            self._list_stack.append("ol")
            self._list_item_index.append(0)
            if not self._in_li():
                self._ensure_blank_line()
        elif tag == "li":
            if self._list_stack:
                kind = self._list_stack[-1]
                indent = "  " * (len(self._list_stack) - 1)
                if kind == "ol":
                    self._list_item_index[-1] += 1
                    self.result.append(f"\n{indent}{self._list_item_index[-1]}. ")
                else:
                    self.result.append(f"\n{indent}- ")
        elif tag == "a":
            href = attrs.get("href", "")
            self._link_href = rewrite_intercom_link(href)
            self._append("[")
        elif tag == "strong" or tag == "b":
            self._ensure_inline_space()
            self._append("**")
            self._just_opened_inline = True
        elif tag == "em" or tag == "i":
            self._ensure_inline_space()
            self._append("*")
            self._just_opened_inline = True
        elif tag == "code":
            self._append("`")
        elif tag == "pre":
            self._ensure_blank_line()
            self.result.append("```\n")
        elif tag == "blockquote":
            self._ensure_blank_line()
        elif tag == "div":
            cls = (attrs.get("class") or "").lower()
            style = (attrs.get("style") or "").lower()
            if "intercom-interblocks-callout" in cls:
                m = re.search(r"background-color:\s*(#[0-9a-fA-F]+)", style)
                color = m.group(1).lower() if m else ""
                component = CALLOUT_COLOR_MAP.get(color, "Note")
                self._ensure_blank_line()
                self.result.append(f"<{component}>\n")
                self._div_stack.append(("callout", component))
            elif "collapsible-section-content" in cls:
                self._div_stack.append(("acc-content", None))
                self._ensure_blank_line()
            else:
                self._div_stack.append(("plain", None))
        elif tag == "details":
            self._ensure_blank_line()
        elif tag == "summary":
            self._in_summary = True
            self._saved_result_for_summary = self.result
            self.result = []
        elif tag == "img":
            src = attrs.get("src", "")
            alt = attrs.get("alt", "")
            if src and src.startswith(("http://", "https://")):
                src = download_image(src)
            elif src:
                self.result.append(f'`<img src="{src}">`')
                return
            if self._in_li():
                self.result.append(f"\n  ![{alt}]({src})")
            else:
                self._ensure_blank_line()
                self.result.append(f"![{alt}]({src})\n")
        elif tag == "hr":
            self._ensure_blank_line()
            self.result.append("---\n")

    def _flush_table(self):
        """Convert collected table rows into a Markdown table."""
        if not self._table_rows:
            return
        # Determine column count
        num_cols = max(len(row) for row in self._table_rows)
        # Normalize rows to same number of columns
        for row in self._table_rows:
            while len(row) < num_cols:
                row.append("")

        self._ensure_blank_line()

        # Check if first row is a header
        first_is_header = self._table_is_header[0] if self._table_is_header else False

        for i, row in enumerate(self._table_rows):
            cells = [c.replace("|", "\\|").strip() for c in row]
            self.result.append("| " + " | ".join(cells) + " |\n")
            # Add separator after header row
            if i == 0 and first_is_header:
                self.result.append("| " + " | ".join(["---"] * num_cols) + " |\n")
            elif i == 0 and not first_is_header:
                # No explicit header — treat first row as header anyway (common in Intercom)
                self.result.append("| " + " | ".join(["---"] * num_cols) + " |\n")

        self.result.append("\n")

    def handle_endtag(self, tag):
        if tag == "table":
            self._flush_table()
            self._in_table = False
            self._table_rows = []
            self._table_is_header = []
            self._current_cell = None
            if self._stack and self._stack[-1] == tag:
                self._stack.pop()
            return
        elif tag in ("td", "th"):
            if self._current_cell is not None:
                # Get the last row or create one
                if not self._table_rows or len(self._table_rows[-1]) != 0 and self._table_rows[-1] is not getattr(self, '_current_row_cells', None):
                    pass
                cell_text = "".join(self._current_cell).strip()
                # Clean up: remove excessive whitespace
                cell_text = re.sub(r"\s+", " ", cell_text)
                if not hasattr(self, '_current_row_cells') or self._current_row_cells is None:
                    self._current_row_cells = []
                self._current_row_cells.append(cell_text)
                self._current_cell = None
            if self._stack and self._stack[-1] == tag:
                self._stack.pop()
            return
        elif tag == "tr":
            row = getattr(self, '_current_row_cells', None) or []
            self._table_rows.append(row)
            self._table_is_header.append(self._current_row_is_header)
            self._current_row_cells = None
            if self._stack and self._stack[-1] == tag:
                self._stack.pop()
            return
        elif tag in ("tbody", "thead", "tfoot"):
            if self._stack and self._stack[-1] == tag:
                self._stack.pop()
            return

        if tag in ("script", "style"):
            self._skip = False
        elif tag == "p":
            if not self._in_li():
                self.result.append("\n")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.result.append("\n")
        elif tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
                self._list_item_index.pop()
            if not self._in_li():
                self.result.append("\n")
        elif tag == "li":
            while self.result and self.result[-1] in (" ", "\n"):
                self.result.pop()
        elif tag == "a":
            self._append(f"]({self._link_href})")
            self._link_href = None
        elif tag == "strong" or tag == "b":
            # Move trailing space outside the bold marker: "**text **" → "**text** "
            self._close_inline_marker("**")
        elif tag == "em" or tag == "i":
            self._close_inline_marker("*")
        elif tag == "code":
            self._append("`")
        elif tag == "pre":
            self.result.append("\n```\n")
        elif tag == "blockquote":
            self.result.append("\n")
        elif tag == "div":
            if self._div_stack:
                kind, comp = self._div_stack.pop()
                if kind == "callout" and comp:
                    if self.result and not "".join(self.result).endswith("\n"):
                        self.result.append("\n")
                    self.result.append(f"</{comp}>\n\n")
        elif tag == "summary":
            self._in_summary = False
            title_md = "".join(self.result).strip()
            self.result = self._saved_result_for_summary or []
            self._saved_result_for_summary = None
            # Strip markdown formatting and MDX escapes from the title.
            title = title_md.lstrip()
            title = re.sub(r"^#+\s*", "", title)  # strip leading heading markers
            title = re.sub(r"[*_`]", "", title)
            title = title.replace("\\{", "{").replace("\\}", "}")
            title = re.sub(r"\s+", " ", title).strip()
            title = title.replace('"', "'")
            self.result.append(f'<Accordion title="{title}">\n')
        elif tag == "details":
            if self.result and not "".join(self.result).endswith("\n"):
                self.result.append("\n")
            self.result.append("</Accordion>\n\n")

        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data):
        if self._skip:
            return
        # After opening bold/italic, if text starts with whitespace move it
        # before the marker so "** text**" becomes " **text**".
        if self._just_opened_inline:
            self._just_opened_inline = False
            if data and data[0] == " ":
                buf = self._current_cell if (self._in_table and self._current_cell is not None) else self.result
                marker = buf.pop()  # "**" or "*"
                buf.append(" ")
                buf.append(marker)
                data = data.lstrip(" ")
        # After closing bold/italic, if text starts with a letter/digit
        # insert a space so the marker renders correctly in MDX.
        # e.g. "**text.**For" → "**text.** For"
        if self._needs_space_after_marker:
            self._needs_space_after_marker = False
            if data and data[0].isalnum():
                if self._in_table and self._current_cell is not None:
                    self._current_cell.append(" ")
                else:
                    self.result.append(" ")
        # Inside table cell — collect into cell buffer
        if self._in_table and self._current_cell is not None:
            # Escape pipes for Markdown tables
            text = data.replace("{", "\\{").replace("}", "\\}")
            self._current_cell.append(text)
            return
        if "code" in self._stack or "pre" in self._stack:
            self.result.append(data)
            return
        data = data.replace("{", "\\{").replace("}", "\\}")
        # Any `<` reaching handle_data is literal text — real HTML tags route
        # through handle_starttag / handle_endtag and never appear here. Escape
        # all `<` so MDX doesn't try to parse `<img ...` and similar as JSX
        # (which fails on `.` and other non-attribute-name characters).
        data = re.sub(r"<>", "&lt;&gt;", data)
        data = data.replace("<", "&lt;")
        self.result.append(data)

    def _ensure_blank_line(self):
        text = "".join(self.result)
        if not text.endswith("\n\n") and text.strip():
            if text.endswith("\n"):
                self.result.append("\n")
            elif text:
                self.result.append("\n\n")

    def get_markdown(self):
        md = "".join(self.result)
        md = re.sub(r"\n{3,}", "\n\n", md)
        return md.strip()


def html_to_markdown(html: str) -> str:
    parser = HtmlToMarkdown()
    parser.feed(html or "")
    return parser.get_markdown()


# ── Slug helpers ──────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text


# ── Intercom API ──────────────────────────────────────────────────────────────

def fetch_all_articles():
    articles = []
    url = "https://api.intercom.io/articles"
    params = {"per_page": 50, "page": 1}

    while url:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        articles.extend(data.get("data", []))
        print(f"  Fetched page {params['page']} — {len(data.get('data', []))} articles")

        pages = data.get("pages", {})
        if pages.get("next"):
            params["page"] += 1
            time.sleep(0.2)
        else:
            break

    return articles


# ── Help center page scraping (for article display order) ────────────────────
# Intercom's articles API doesn't expose order. Order comes from scraping
# the public collection page on help.maestra.io.

_collection_order_cache: dict[str, list[tuple[str, str]]] = {}

def fetch_collection_order(col_id: str) -> list[tuple[str, str]]:
    """Scrape the public collection page; return [(kind, id), ...] in DOM order.

    kind ∈ {"article", "collection"}. Includes preview links for articles
    that live inside sub-collections — caller must filter by parent.
    """
    if col_id in _collection_order_cache:
        return _collection_order_cache[col_id]
    try:
        resp = requests.get(
            f"https://help.maestra.io/en/collections/{col_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        html = resp.text if resp.status_code == 200 else ""
    except Exception:
        html = ""
    items: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in re.finditer(r"/en/(articles|collections)/(\d+)", html):
        kind = "article" if m.group(1) == "articles" else "collection"
        eid = m.group(2)
        key = (kind, eid)
        if key in seen:
            continue
        if kind == "collection" and eid == col_id:
            continue
        seen.add(key)
        items.append(key)
    _collection_order_cache[col_id] = items
    return items


def fetch_all_collections() -> dict[str, dict]:
    """Fetch all collections (paginated) and return as {id: collection_dict}."""
    all_cols = []
    page = 1
    while True:
        resp = requests.get(
            "https://api.intercom.io/help_center/collections",
            headers=HEADERS,
            params={"per_page": 50, "page": page},
        )
        resp.raise_for_status()
        data = resp.json()
        all_cols.extend(data.get("data", []))
        if data.get("pages", {}).get("next"):
            page += 1
            time.sleep(0.2)
        else:
            break
    return {str(c["id"]): c for c in all_cols}


# ── Collection tree helpers ────────────────────────────────────────────────────

def build_collection_tree(collections: dict) -> list:
    """Return top-level collections sorted by order, each with .children list."""
    for c in collections.values():
        c["children"] = []
    roots = []
    for c in collections.values():
        parent_id = str(c.get("parent_id") or "")
        if parent_id and parent_id in collections:
            collections[parent_id]["children"].append(c)
        else:
            roots.append(c)
    roots.sort(key=lambda x: x.get("order", 999))
    for c in collections.values():
        c["children"].sort(key=lambda x: x.get("order", 999))
    return roots


def collection_path(col_id: str, collections: dict) -> str:
    """Build directory path for a collection by walking up parent chain.

    E.g. col "Get started" (parent=Email campaigns, grandparent=Campaigns)
    → "campaigns/email-campaigns/get-started"
    """
    if not col_id or col_id not in collections:
        return "general"
    parts = []
    current = col_id
    while current and current in collections:
        col = collections[current]
        parts.append(slugify(col["name"]))
        current = str(col.get("parent_id") or "")
    parts.reverse()
    return "/".join(parts)


# ── Article path computation ──────────────────────────────────────────────────

def resolve_leaf_collection(article: dict) -> str | None:
    """Return the leaf collection ID for an article, derived from Intercom's parent_ids."""
    pids = article.get("parent_ids") or []
    if pids:
        return str(pids[-1])
    # Legacy fallback: hand-scraped map (used only if the API didn't return parent_ids)
    return ARTICLE_COLLECTION_MAP.get(str(article.get("id", "")))


def compute_article_path(article: dict, collections: dict) -> str | None:
    """Compute the Mintlify relative path for an article (without .mdx)."""
    title = article.get("title", "Untitled")
    state = article.get("state", "")
    if state != "published":
        return None

    col_id = resolve_leaf_collection(article)
    dir_name = collection_path(col_id, collections) if col_id else "general"

    file_name = slugify(title)
    return f"{dir_name}/{file_name}"


# ── File writing ──────────────────────────────────────────────────────────────

def yaml_str(s: str) -> str:
    if '"' in s:
        s = s.replace("'", "\\'")
        return f"'{s}'"
    return f'"{s}"'


def write_article(article: dict, collections: dict) -> str | None:
    title = article.get("title", "Untitled")
    description = article.get("description", "")
    body_html = article.get("body", "") or ""
    state = article.get("state", "")

    if state != "published":
        return None

    col_id = resolve_leaf_collection(article)
    dir_name = collection_path(col_id, collections) if col_id else "general"

    file_name = slugify(title) + ".mdx"
    rel_path = f"{dir_name}/{file_name}"
    full_path = DOCS_DIR / dir_name / file_name

    full_path.parent.mkdir(parents=True, exist_ok=True)

    body_md = html_to_markdown(body_html)

    frontmatter_lines = [f"title: {yaml_str(title)}"]
    if description:
        frontmatter_lines.append(f"description: {yaml_str(description)}")

    frontmatter = "\n".join(frontmatter_lines)
    full_path.write_text(f"---\n{frontmatter}\n---\n\n{body_md}\n", encoding="utf-8")
    return rel_path


# ── docs.json rebuild ──────────────────────────────────────────────────────────

def build_nav_group(
    col: dict,
    aids_by_col: dict[str, list[str]],
    pages_by_aid: dict[str, str],
    collections: dict,
) -> dict | None:
    """Recursively build a Mintlify nav group, preserving Intercom display order.

    Article order and direct/sub-collection interleaving comes from scraping
    the public help center. Sub-collection order falls back to the API `order`
    field when not present on the page.
    """
    col_id = str(col["id"])
    child_ids = {str(c["id"]) for c in col.get("children", [])}
    direct_aids = set(aids_by_col.get(col_id, []))

    scraped = fetch_collection_order(col_id)
    pages: list = []
    seen_articles: set[str] = set()
    seen_subcols: set[str] = set()

    for kind, eid in scraped:
        if kind == "article" and eid in direct_aids and eid not in seen_articles:
            pages.append(pages_by_aid[eid])
            seen_articles.add(eid)
        elif kind == "collection" and eid in child_ids and eid not in seen_subcols:
            child = next(c for c in col["children"] if str(c["id"]) == eid)
            sub = build_nav_group(child, aids_by_col, pages_by_aid, collections)
            if sub:
                pages.append(sub)
            seen_subcols.add(eid)

    # Append anything the scrape missed (offline / scrape failure / new article).
    for aid in sorted(direct_aids - seen_articles, key=lambda a: pages_by_aid[a]):
        pages.append(pages_by_aid[aid])
    for child in col.get("children", []):
        if str(child["id"]) in seen_subcols:
            continue
        sub = build_nav_group(child, aids_by_col, pages_by_aid, collections)
        if sub:
            pages.append(sub)

    if not pages:
        return None
    return {"group": col["name"], "pages": pages}


def update_docs_json(
    pages_by_col: dict[str, list[str]],
    collection_tree: list,
    collections: dict,
    pages_by_aid: dict[str, str] | None = None,
    aids_by_col: dict[str, list[str]] | None = None,
):
    docs_json_path = DOCS_DIR / "docs.json"
    with open(docs_json_path, encoding="utf-8") as f:
        config = json.load(f)

    # Build imported groups from collection tree
    pages_by_aid = pages_by_aid or {}
    aids_by_col = aids_by_col or {}
    imported_groups = []
    for root in collection_tree:
        group = build_nav_group(root, aids_by_col, pages_by_aid, collections)
        if group:
            imported_groups.append(group)

    # Handle uncategorised articles
    general_pages = sorted(pages_by_col.get("general", []))
    if general_pages:
        imported_groups.append({"group": "General", "pages": general_pages})

    # Replace the Guides tab groups
    guides_tab = next(
        (t for t in config["navigation"]["tabs"] if t.get("tab") == "Guides"),
        None,
    )
    if guides_tab:
        guides_tab["groups"] = imported_groups
    else:
        config["navigation"]["tabs"].insert(0, {"tab": "Guides", "groups": imported_groups})

    with open(docs_json_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not INTERCOM_TOKEN:
        print("Error: INTERCOM_TOKEN not set")
        return

    # Parse --limit N flag
    limit = None
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])
            print(f"⚡ Incremental mode: processing only {limit} articles")

    # Parse --ids 1234,5678 flag (targeted re-import; skips cleanup and docs.json rebuild)
    target_ids: set[str] | None = None
    if "--ids" in sys.argv:
        idx = sys.argv.index("--ids")
        if idx + 1 < len(sys.argv):
            target_ids = {x.strip() for x in sys.argv[idx + 1].split(",") if x.strip()}
            print(f"🎯 Targeted mode: only article IDs {sorted(target_ids)}")

    print("Fetching collections...")
    collections = fetch_all_collections()
    collection_tree = build_collection_tree(collections)
    print(f"  Found {len(collections)} collections, {len(collection_tree)} top-level")

    print("Fetching articles...")
    all_articles = fetch_all_articles()
    print(f"  Total articles from API: {len(all_articles)}")

    published = [a for a in all_articles if a.get("state") == "published"]
    print(f"  Published articles: {len(published)}")

    # ── Pass 1: build article ID → Mintlify path mapping (ALL articles) ──
    print("\nPass 1: Building link mapping for all articles...")
    for article in published:
        article_id = str(article.get("id", ""))
        path = compute_article_path(article, collections)
        if article_id and path:
            _article_link_map[article_id] = path
    print(f"  Mapped {len(_article_link_map)} article links")

    # Show mapping stats
    mapped = sum(1 for a in published if (a.get("parent_ids") or []) or str(a.get("id", "")) in ARTICLE_COLLECTION_MAP)
    print(f"  With collection: {mapped}")
    print(f"  Fallback to 'general': {len(published) - mapped}")

    # Manually-maintained directories that the cleanup pass must not touch.
    PROTECTED_DIRS = ("for-developers",)

    # ── Clean up old imported MDX files (full mode only) ──
    if not limit and not target_ids:
        print("\nCleaning old imported .mdx files...")
        removed = 0
        for mdx in DOCS_DIR.rglob("*.mdx"):
            # Keep non-article files (like index pages in the repo root)
            rel = mdx.relative_to(DOCS_DIR)
            # Only remove files inside collection directories (not top-level docs)
            if len(rel.parts) >= 2 and rel.parts[0] not in PROTECTED_DIRS:
                mdx.unlink()
                removed += 1
        print(f"  Removed {removed} old files")
        # Remove empty directories
        for d in sorted(DOCS_DIR.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()

    # ── Pass 2: convert and write articles ──
    if target_ids:
        to_process = [a for a in published if str(a.get("id", "")) in target_ids]
        missing = target_ids - {str(a.get("id", "")) for a in to_process}
        if missing:
            print(f"  ! Missing IDs (not found in published): {sorted(missing)}")
    elif limit:
        to_process = published[:limit]
    else:
        to_process = published
    print(f"\nPass 2: Converting {len(to_process)} articles...")

    # Track pages by collection ID (for nav building)
    pages_by_col: dict[str, list[str]] = {}
    pages_by_aid: dict[str, str] = {}
    aids_by_col: dict[str, list[str]] = {}

    for article in to_process:
        rel_path = write_article(article, collections)
        if rel_path:
            article_id = str(article.get("id", ""))
            col_id = resolve_leaf_collection(article) or "general"
            page_path = rel_path.replace(".mdx", "")
            pages_by_col.setdefault(col_id, []).append(page_path)
            pages_by_aid[article_id] = page_path
            aids_by_col.setdefault(col_id, []).append(article_id)
            print(f"  ✓ {rel_path}")

    if target_ids:
        print("\nSkipping docs.json rebuild in targeted mode")
    else:
        print(f"\nUpdating docs.json...")
        update_docs_json(pages_by_col, collection_tree, collections, pages_by_aid, aids_by_col)

    written = sum(len(v) for v in pages_by_col.values())
    skipped = len(all_articles) - len(published)
    print(f"\nDone: {written} articles written, {skipped} skipped (drafts/unpublished)")
    if limit:
        print(f"  (incremental: processed {limit} of {len(published)} published)")

    # Report link migration stats
    link_count = 0
    unresolved = set()
    for article in to_process:
        body = article.get("body", "") or ""
        for m in re.finditer(r"/articles/(\d+)", body):
            aid = m.group(1)
            if aid in _article_link_map:
                link_count += 1
            else:
                unresolved.add(aid)
    print(f"\n  Internal links rewritten: {link_count}")
    if unresolved:
        print(f"  Unresolved article IDs: {unresolved}")


if __name__ == "__main__":
    main()
