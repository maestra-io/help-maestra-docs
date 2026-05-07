#!/usr/bin/env python3
"""
Generate Mintlify redirects from Intercom article URLs → new Mintlify paths.

Fetches all published articles from Intercom API, computes old /en/articles/{id}-{slug}
paths and new Mintlify paths, then writes the "redirects" array into docs.json.

Usage:
  INTERCOM_TOKEN=... python generate_redirects.py
  INTERCOM_TOKEN=... python generate_redirects.py --dry-run   # just print, don't write
"""

import os
import re
import sys
import json
import time
import requests
from pathlib import Path
from urllib.parse import urlparse

INTERCOM_TOKEN = os.environ.get("INTERCOM_TOKEN")
DOCS_DIR = Path(__file__).parent.parent
HEADERS = {
    "Authorization": f"Bearer {INTERCOM_TOKEN}",
    "Accept": "application/json",
    "Intercom-Version": "2.11",
}

# ── Same mappings as import.py ───────────────────────────────────────────────

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


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text


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


def fetch_all_collections() -> dict[str, dict]:
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


def collection_path(col_id: str, collections: dict) -> str:
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


def extract_intercom_path(article: dict) -> str | None:
    """Extract the /en/articles/... path from Intercom article URL."""
    url = article.get("url", "")
    if not url:
        return None
    parsed = urlparse(url)
    # Intercom URL: https://help.maestra.io/en/articles/12345-slug
    path = parsed.path
    if "/articles/" in path:
        return path
    return None


def compute_new_path(article: dict, collections: dict) -> str | None:
    """Compute new Mintlify path for an article."""
    title = article.get("title", "Untitled")
    if article.get("state") != "published":
        return None

    article_id = str(article.get("id", ""))
    col_id = ARTICLE_COLLECTION_MAP.get(article_id)
    if col_id:
        dir_name = collection_path(col_id, collections)
    else:
        return None  # skip articles not in our map (they weren't imported)

    file_name = slugify(title)
    return f"/{dir_name}/{file_name}"


def find_first_article_for_collection(
    col_id: str,
    collections: dict,
    published: list[dict],
) -> str | None:
    """Find the first published article in a collection (or its children) and return its new path.

    Searches direct articles first, then recurses into child collections.
    """
    # Direct articles in this collection
    direct = []
    for article in published:
        aid = str(article.get("id", ""))
        if ARTICLE_COLLECTION_MAP.get(aid) == col_id:
            path = compute_new_path(article, collections)
            if path:
                mdx_file = DOCS_DIR / (path.lstrip("/") + ".mdx")
                if mdx_file.exists():
                    direct.append(path)
    if direct:
        return sorted(direct)[0]

    # Try child collections
    children = [
        c for c in collections.values()
        if str(c.get("parent_id") or "") == col_id
    ]
    children.sort(key=lambda c: c.get("order", 999))
    for child in children:
        result = find_first_article_for_collection(str(child["id"]), collections, published)
        if result:
            return result

    return None


def generate_collection_redirects(
    collections: dict,
    published: list[dict],
) -> tuple[list[dict], list[tuple]]:
    """Generate redirects for /en/collections/{id}-{slug} URLs."""
    redirects = []
    skipped = []

    for col_id, col in collections.items():
        # Build old Intercom path: /en/collections/{id}-{slug}
        col_slug = slugify(col.get("name", ""))
        old_path = f"/en/collections/{col_id}-{col_slug}"

        # Find destination: first article in this collection
        dest = find_first_article_for_collection(col_id, collections, published)
        if not dest:
            skipped.append((col_id, col.get("name"), "no articles found"))
            continue

        redirects.append({
            "source": old_path,
            "destination": dest,
        })

    return redirects, skipped


def main():
    if not INTERCOM_TOKEN:
        print("Error: INTERCOM_TOKEN not set")
        return

    dry_run = "--dry-run" in sys.argv

    print("Fetching collections...")
    collections = fetch_all_collections()
    print(f"  Found {len(collections)} collections")

    print("Fetching articles...")
    all_articles = fetch_all_articles()
    published = [a for a in all_articles if a.get("state") == "published"]
    print(f"  Published articles: {len(published)}")

    # ── Article redirects ──
    redirects = []
    skipped = []

    for article in published:
        old_path = extract_intercom_path(article)
        new_path = compute_new_path(article, collections)

        if not old_path:
            skipped.append((article.get("id"), article.get("title"), "no Intercom URL"))
            continue
        if not new_path:
            skipped.append((article.get("id"), article.get("title"), "not in collection map"))
            continue

        # Verify destination file exists
        mdx_file = DOCS_DIR / (new_path.lstrip("/") + ".mdx")
        if not mdx_file.exists():
            skipped.append((article.get("id"), article.get("title"), f"MDX not found: {mdx_file.name}"))
            continue

        redirects.append({
            "source": old_path,
            "destination": new_path,
        })

    print(f"\n  Article redirects: {len(redirects)}")
    if skipped:
        print(f"  Articles skipped: {len(skipped)}")
        for aid, title, reason in skipped:
            print(f"    - [{aid}] {title}: {reason}")

    # ── Collection redirects ──
    col_redirects, col_skipped = generate_collection_redirects(collections, published)
    redirects.extend(col_redirects)

    print(f"\n  Collection redirects: {len(col_redirects)}")
    if col_skipped:
        print(f"  Collections skipped: {len(col_skipped)}")
        for cid, name, reason in col_skipped:
            print(f"    - [{cid}] {name}: {reason}")

    # Sort for readability
    redirects.sort(key=lambda r: r["source"])

    print(f"\n  Total redirects: {len(redirects)}")

    if dry_run:
        print("\n--- DRY RUN: redirects that would be written ---")
        print(json.dumps(redirects, indent=2, ensure_ascii=False))
        return

    # Write to docs.json
    docs_json_path = DOCS_DIR / "docs.json"
    with open(docs_json_path, encoding="utf-8") as f:
        config = json.load(f)

    config["redirects"] = redirects

    with open(docs_json_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\n✓ Written {len(redirects)} redirects to docs.json")


if __name__ == "__main__":
    main()
