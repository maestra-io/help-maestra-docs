# Scripts

Tooling that generates and maintains the docs in this repo. Both scripts read articles from the Maestra Intercom workspace via the Intercom API.

## Setup

```bash
export INTERCOM_TOKEN=<your-intercom-token>
```

## `import.py`

Fetches articles from Intercom, converts the HTML to Mintlify MDX, downloads images, and rewrites navigation in `docs.json`.

```bash
python3 scripts/import.py                       # full sync (wipes generated MDX, rewrites docs.json)
python3 scripts/import.py --limit 5             # first 5 articles only (no cleanup, no docs.json rewrite)
python3 scripts/import.py --ids 6262584,12359414 # only these article IDs (no cleanup, no docs.json rewrite)
```

Targeted modes (`--limit`, `--ids`) leave manually-edited articles alone — use them when fixing specific articles.

What the converter handles:

- Headings, paragraphs, bold, italic, code, lists, blockquotes
- Tables → Markdown tables
- Images → downloaded to `images/imported/`
- Internal article links → rewritten to Mintlify paths
- Intercom callouts (`<div class="intercom-interblocks-callout">`) → `<Note>` / `<Tip>` / `<Warning>` / `<Info>` based on background color
- Intercom accordions (`<details>`+`<summary>`) → `<Accordion title="...">…</Accordion>`
- Bare `<` in body text escaped to `&lt;` so MDX doesn't try to JSX-parse HTML examples

## `generate_redirects.py`

Builds 301 redirect rules from the old Intercom URLs (`/en/articles/...`, `/en/collections/...`) to the new Mintlify paths and writes them into `docs.json`.

```bash
python3 scripts/generate_redirects.py            # update docs.json
python3 scripts/generate_redirects.py --dry-run  # print without writing
```
