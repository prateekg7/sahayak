"""Validation script for curated government schemes dataset (T12.4).

Verifies schema integrity, required metadata, source links, and dates.
Fails CI if any scheme entry lacks a valid official portal link or verification date.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from datetime import date
from pathlib import Path

SCHEMES_FILE = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "sahayak"
    / "modules"
    / "local_info"
    / "data"
    / "schemes.json"
)


def validate_schemes_dataset(path: Path = SCHEMES_FILE) -> list[str]:
    """Validate all schemes in dataset, returning list of validation errors."""
    errors: list[str] = []
    if not path.is_file():
        return [f"Schemes dataset file not found at: {path}"]

    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Failed to parse JSON in {path}: {exc}"]

    if not isinstance(content, list) or len(content) == 0:
        return [f"Schemes dataset must be a non-empty list, found {type(content)}"]

    ids_seen: set[str] = set()

    for idx, entry in enumerate(content):
        label = f"Scheme #{idx}"
        if not isinstance(entry, dict):
            errors.append(f"{label} is not a dictionary.")
            continue

        scheme_id = entry.get("id")
        if not scheme_id or not isinstance(scheme_id, str):
            errors.append(f"{label} missing valid 'id'.")
        elif scheme_id in ids_seen:
            errors.append(f"Duplicate scheme id: '{scheme_id}'.")
        else:
            ids_seen.add(scheme_id)
            label = f"Scheme '{scheme_id}'"

        name = entry.get("name")
        if not name or not isinstance(name, str):
            errors.append(f"{label} missing valid 'name'.")

        url = entry.get("official_portal_url")
        if not url or not isinstance(url, str):
            errors.append(f"{label} missing required 'official_portal_url'.")
        else:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"{label} has invalid official_portal_url '{url}'.")

        verified_date = entry.get("last_verified_date")
        if not verified_date or not isinstance(verified_date, str):
            errors.append(f"{label} missing required 'last_verified_date'.")
        else:
            try:
                date.fromisoformat(verified_date)
            except ValueError:
                errors.append(f"{label} invalid last_verified_date format '{verified_date}'.")

        criteria = entry.get("criteria")
        if not criteria or not isinstance(criteria, dict):
            errors.append(f"{label} missing valid 'criteria' object.")

    return errors


def main() -> None:
    errors = validate_schemes_dataset()
    if errors:
        print("ERROR: Schemes dataset validation failed:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    print("Schemes dataset validation passed successfully.")


if __name__ == "__main__":
    main()
