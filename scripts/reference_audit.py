#!/usr/bin/env python3
"""Offline integrity and metadata-consistency checks for the bibliography ledger."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ENTRY_HEAD = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)
CITE_RE = re.compile(r"\\cite\w*\s*\{([^}]*)\}")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_bib(text: str) -> dict[str, dict[str, object]]:
    """Parse the braced/string fields used by this repository without network access."""
    entries: dict[str, dict[str, object]] = {}
    offset = 0
    while True:
        match = ENTRY_HEAD.search(text, offset)
        if not match:
            break
        entry_type, key = match.group(1).lower(), match.group(2)
        pos = match.end()
        depth, end = 1, pos
        while end < len(text) and depth:
            if text[end] == "{":
                depth += 1
            elif text[end] == "}":
                depth -= 1
            end += 1
        if depth:
            raise ValueError(f"unterminated BibTeX entry: {key}")
        body = text[pos : end - 1]
        fields: dict[str, str] = {}
        cursor = 0
        while cursor < len(body):
            field_match = re.search(r"([A-Za-z][A-Za-z0-9_-]*)\s*=\s*", body[cursor:])
            if not field_match:
                break
            name = field_match.group(1).lower()
            value_pos = cursor + field_match.end()
            if value_pos >= len(body):
                raise ValueError(f"missing field value: {key}.{name}")
            if body[value_pos] == "{":
                value_depth, value_end = 1, value_pos + 1
                while value_end < len(body) and value_depth:
                    if body[value_end] == "{":
                        value_depth += 1
                    elif body[value_end] == "}":
                        value_depth -= 1
                    value_end += 1
                if value_depth:
                    raise ValueError(f"unterminated field: {key}.{name}")
                value = body[value_pos + 1 : value_end - 1]
                cursor = value_end
            elif body[value_pos] == '"':
                value_end = value_pos + 1
                while value_end < len(body):
                    if body[value_end] == '"' and body[value_end - 1] != "\\":
                        break
                    value_end += 1
                value = body[value_pos + 1 : value_end]
                cursor = value_end + 1
            else:
                value_end = value_pos
                while value_end < len(body) and body[value_end] not in ",\n":
                    value_end += 1
                value = body[value_pos:value_end].strip()
                cursor = value_end
            fields[name] = value.strip()
        entries[key] = {"type": entry_type, "fields": fields}
        offset = end
    return entries


def normalize_title(value: str) -> str:
    value = value.replace("---", "-").replace("--", "-")
    value = re.sub(r"\\[`'\"^~=.uvHtcdb]\s*\{?([A-Za-z])\}?", r"\1", value)
    value = re.sub(r"\\[A-Za-z]+\*?", " ", value)
    value = value.replace("{", "").replace("}", "")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", type=Path, help="paper directory; otherwise use the retained citation snapshot")
    parser.add_argument("--expected-count", type=int, default=67)
    args = parser.parse_args()
    artifact = Path(__file__).resolve().parents[1]
    evidence = artifact / "evidence"
    paper = args.paper.resolve() if args.paper else None
    use_live_paper = paper is not None and (paper / "references.bib").exists()
    errors: list[str] = []

    csv_path = evidence / "REFERENCE-AUDIT.csv"
    md_path = evidence / "REFERENCE-AUDIT.md"
    if use_live_paper:
        bib_path = paper / "references.bib"
        tex_paths = [paper / "main.tex", *sorted((paper / "sections").glob("*.tex"))]
        tex = "\n".join(path.read_text(encoding="utf-8") for path in tex_paths)
        cited = [key.strip() for match in CITE_RE.finditer(tex) for key in match.group(1).split(",") if key.strip()]
        source_mode = "live-paper"
        paper_bib_sha = sha256(bib_path)
    else:
        bib_path = evidence / "references.bib"
        snapshot_path = evidence / "paper-citation-snapshot.json"
        if not bib_path.exists() or not snapshot_path.exists():
            raise SystemExit("standalone verification requires evidence/references.bib and paper-citation-snapshot.json")
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        cited = list(snapshot["cited_keys"])
        if snapshot["bibliography_sha256"] != sha256(bib_path):
            errors.append("citation snapshot bibliography hash differs from evidence/references.bib")
        source_mode = "retained-paper-snapshot"
        paper_bib_sha = snapshot["bibliography_sha256"]

    bib_text = bib_path.read_text(encoding="utf-8")
    try:
        entries = parse_bib(bib_text)
    except ValueError as exc:
        errors.append(str(exc))
        entries = {}
    bib_keys = list(entries)
    bib_set, cited_set = set(bib_keys), set(cited)
    if len(bib_keys) != len(bib_set):
        errors.append("duplicate bibliography keys")
    if cited_set - bib_set:
        errors.append(f"cited keys missing from bibliography: {sorted(cited_set - bib_set)}")
    if bib_set - cited_set:
        errors.append(f"uncited bibliography keys: {sorted(bib_set - cited_set)}")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    row_by_key = {row["key"].strip(): row for row in rows}
    csv_keys = list(row_by_key)
    if len(rows) != len(csv_keys):
        errors.append("duplicate keys in REFERENCE-AUDIT.csv")
    if set(csv_keys) != bib_set:
        errors.append(f"audit/bibliography key mismatch: missing_in_audit={sorted(bib_set-set(csv_keys))}, extra_in_audit={sorted(set(csv_keys)-bib_set)}")

    archival_exceptions = ("usenix.org", "programming-journal.org", "vmssoftware.com")
    doi_owners: defaultdict[str, list[str]] = defaultdict(list)
    title_owners: defaultdict[str, list[str]] = defaultdict(list)
    for key, entry in entries.items():
        fields = entry["fields"]
        row = row_by_key.get(key)
        title = str(fields.get("title", "")).strip()
        year = str(fields.get("year", "")).strip()
        doi = str(fields.get("doi", "")).strip()
        if not title:
            errors.append(f"{key}: missing BibTeX title")
        if entry["type"] != "misc" and not year:
            errors.append(f"{key}: non-misc entry lacks year")
        if entry["type"] != "misc" and not (fields.get("author") or fields.get("editor")):
            errors.append(f"{key}: non-misc entry lacks author/editor")
        if title:
            title_owners[normalize_title(title)].append(key)
        if doi:
            if not DOI_RE.match(doi):
                errors.append(f"{key}: malformed DOI {doi!r}")
            doi_owners[doi.lower()].append(key)
        if row is None:
            continue
        if row["type"].strip().lower() != entry["type"]:
            errors.append(f"{key}: ledger type differs from BibTeX")
        if normalize_title(row["title"]) != normalize_title(title):
            errors.append(f"{key}: ledger title differs from BibTeX")
        if row["year"].strip() != year:
            errors.append(f"{key}: ledger year differs from BibTeX")
        if row["doi"].strip().lower() != doi.lower():
            errors.append(f"{key}: ledger DOI differs from BibTeX")
        url = row["verification_url"].strip()
        source_type = row["source_type"].strip()
        if not url.startswith("https://"):
            errors.append(f"{key}: verification URL is not HTTPS")
        if not source_type:
            errors.append(f"{key}: missing source_type")
        if source_type == "peer-reviewed" and not (doi or any(domain in url for domain in archival_exceptions)):
            errors.append(f"{key}: peer-reviewed entry lacks DOI/archival locator")
        if not row["supports_in_paper"].strip():
            errors.append(f"{key}: missing intended-use statement")

    for doi, keys in doi_owners.items():
        if len(keys) > 1:
            errors.append(f"duplicate DOI {doi}: {keys}")
    for title, keys in title_owners.items():
        if title and len(keys) > 1:
            errors.append(f"duplicate normalized title: {keys}")

    if len(bib_keys) != args.expected_count:
        errors.append(f"expected {args.expected_count} bibliography entries, found {len(bib_keys)}")
    if len(rows) != args.expected_count:
        errors.append(f"expected {args.expected_count} audit rows, found {len(rows)}")

    mirrors_match = None
    if use_live_paper:
        paper_csv, paper_md = paper / "REFERENCE-AUDIT.csv", paper / "REFERENCE-AUDIT.md"
        mirrors_match = paper_csv.read_bytes() == csv_path.read_bytes() and paper_md.read_bytes() == md_path.read_bytes()
        if not mirrors_match:
            errors.append("paper and artifact audit mirrors differ")
        if bib_path.read_bytes() != (evidence / "references.bib").read_bytes():
            errors.append("paper and artifact bibliography mirrors differ")

    result = {
        "source_mode": source_mode,
        "paper": str(paper) if paper else None,
        "bibliography_entries": len(bib_keys),
        "unique_cited_keys": len(cited_set),
        "audit_rows": len(rows),
        "bibliography_sha256": sha256(bib_path),
        "paper_bibliography_sha256": paper_bib_sha,
        "audit_csv_sha256": sha256(csv_path),
        "audit_md_sha256": sha256(md_path),
        "all_entries_cited": not (bib_set - cited_set),
        "all_citations_resolved": not (cited_set - bib_set),
        "audit_key_set_matches": set(csv_keys) == bib_set,
        "metadata_fields_match_ledger": not any("ledger" in error for error in errors),
        "duplicate_dois": {doi: keys for doi, keys in doi_owners.items() if len(keys) > 1},
        "duplicate_titles": {title: keys for title, keys in title_owners.items() if title and len(keys) > 1},
        "paper_artifact_mirrors_match": mirrors_match,
        "errors": errors,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
