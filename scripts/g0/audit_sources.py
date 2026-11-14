"""Offline metadata audit. Never opens URLs found in the input datasets.
Usage: python scripts/g0/audit_sources.py DATA_DIRECTORY OUTPUT_JSON
DATA_DIRECTORY contains phiusiil.csv, full_dataset.csv, train.csv, test.csv,
and sources.json (download URLs, hashes and byte counts).
No message/URL contents are printed or written to the report.
"""
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "ai"))
from url_analysis import URLInputError, inspect_url


def load(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def template(text):
    # Audit heuristic only; not a scam classifier or a finished anonymizer.
    text = normalized(text)
    text = re.sub(r"https?://\S+|www\.\S+", "[url]", text)
    return re.sub(r"\d+", "[number]", text)


def stats(rows, text_column, label_column):
    messages = [r[text_column] for r in rows]
    groups = collections.defaultdict(set)
    for r in rows:
        groups[normalized(r[text_column])].add(r[label_column])
    return {
        "rows": len(rows),
        "columns": list(rows[0]) if rows else [],
        "label_counts": dict(collections.Counter(r[label_column] for r in rows)),
        "blank_text_rows": sum(not s.strip() for s in messages),
        "exact_duplicate_rows": len(messages) - len(set(messages)),
        "normalized_duplicate_rows": len(messages) - len(groups),
        "normalized_conflicting_label_groups": sum(len(v) > 1 for v in groups.values()),
    }


def audit(directory):
    result = {"audit_date": "2026-11-14", "sources": json.loads((directory / "sources.json").read_text())}
    for name, source in result["sources"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == source["sha256"]
    sms = {name: load(directory / (name + ".csv")) for name in ("full_dataset", "train", "test")}
    result["sms"] = {name: stats(rows, "message", "label") for name, rows in sms.items()}
    train, test = sms["train"], sms["test"]
    result["sms"]["published_split_overlap"] = {
        "exact_messages": len({r["message"] for r in train} & {r["message"] for r in test}),
        "normalized_messages": len({normalized(r["message"]) for r in train} & {normalized(r["message"]) for r in test}),
        "heuristic_templates": len({template(r["message"]) for r in train} & {template(r["message"]) for r in test}),
    }
    # Flag for manual redaction, not a claim that the numbers are active secrets.
    pattern = re.compile(r"(?:otp|mã xác (?:thực|nhận)|ma xac (?:thuc|nhan))[^\n]{0,60}?\b\d{4,8}\b", re.I)
    result["sms"]["otp_like_unmasked_rows"] = {
        name: sum(bool(pattern.search(r["message"])) for r in rows) for name, rows in sms.items()
    }
    full = {(normalized(r["message"]), r["label"]) for r in sms["full_dataset"]}
    result["sms"]["split_rows_not_in_full_normalized"] = {
        name: sum((normalized(r["message"]), r["label"]) not in full for r in rows)
        for name, rows in (("train", train), ("test", test))
    }
    rows = load(directory / "phiusiil.csv")
    result["url"] = stats(rows, "URL", "label")
    accepted = collections.Counter()
    rejected = collections.Counter()
    groups = set()
    normalized_urls = collections.defaultdict(set)
    for row in rows:
        try:
            data = inspect_url(row["URL"])
        except URLInputError as exc:
            rejected[(exc.code, row["label"])] += 1
            continue
        accepted[row["label"]] += 1
        groups.add(data["url"]["registered_domain"] or data["url"]["hostname_ascii"])
        normalized_urls[data["url"]["normalized_url"]].add(row["label"])
    result["url"]["accepted_by_source_label"] = dict(accepted)
    result["url"]["rejected_by_code_and_source_label"] = {
        f"{code}:label={label}": count for (code, label), count in sorted(rejected.items())
    }
    result["url"]["accepted_domain_groups"] = len(groups)
    result["url"]["accepted_normalized_urls"] = len(normalized_urls)
    result["url"]["accepted_conflicting_normalized_urls"] = sum(len(labels) > 1 for labels in normalized_urls.values())
    return result


if __name__ == "__main__":
    directory, output = map(Path, sys.argv[1:])
    report = audit(directory)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Metadata audit complete; no raw input printed.")
