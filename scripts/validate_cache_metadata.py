"""Validate local historical-data cache metadata for Apex research."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.download_binance_klines import binance_monthly_kline_url, ensure_metadata

DEFAULT_CACHE_DIR = ROOT / "data" / "history" / "binance"
OUTPUT_JSON = ROOT / "runtime" / "cache_metadata_report.json"
OUTPUT_MD = ROOT / "docs" / "backtests" / "cache-metadata-report.md"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_row_count(path: Path) -> int:
    with path.open("r", newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def validate_file(path: Path, repair: bool = False, market: str = "spot") -> dict:
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    warnings = []
    metadata = {}
    row_count = csv_row_count(path)
    checksum = sha256_file(path)

    def repair_metadata() -> bool:
        inferred = infer_binance_file(path)
        if not inferred:
            return False
        url = binance_monthly_kline_url(inferred["symbol"], inferred["interval"], inferred["month"], market)
        ensure_metadata(path, inferred["symbol"], inferred["interval"], inferred["month"], market, url, "repair")
        return True

    if not meta_path.exists():
        if repair:
            if repair_metadata():
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            else:
                warnings.append("missing-metadata")
                warnings.append("filename-not-inferable")
        else:
            warnings.append("missing-metadata")
    else:
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if repair and repair_metadata():
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            else:
                warnings.append("invalid-metadata-json")
    if metadata:
        if int(metadata.get("row_count") or -1) != row_count:
            warnings.append("row-count-mismatch")
        if metadata.get("sha256") != checksum:
            warnings.append("checksum-mismatch")
        for key in ("source", "symbol", "interval", "month", "url"):
            if not metadata.get(key):
                warnings.append(f"missing-{key}")
    return {
        "path": str(path),
        "metadata_path": str(meta_path),
        "row_count": row_count,
        "sha256": checksum,
        "ok": not warnings,
        "warnings": warnings,
    }


def infer_binance_file(path: Path) -> dict | None:
    match = re.match(r"^(?P<symbol>[A-Z0-9]+)-(?P<interval>[^-]+)-(?P<month>\d{4}-\d{2})\.csv$", path.name)
    if not match:
        return None
    return match.groupdict()


def validate_cache(cache_dir: Path, limit: int = 0, repair: bool = False, market: str = "spot") -> list[dict]:
    paths = sorted(cache_dir.glob("*.csv"))
    if limit > 0:
        paths = paths[-limit:]
    return [validate_file(path, repair=repair, market=market) for path in paths]


def write_outputs(rows: list[dict]) -> None:
    generated_at = datetime.now(UTC).isoformat()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps({"generated_at": generated_at, "files": rows}, indent=2), encoding="utf-8")
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    ok_count = sum(1 for row in rows if row["ok"])
    lines = [
        "# Apex Cache Metadata Report",
        "",
        f"Generated: {generated_at}",
        f"Files checked: {len(rows)}",
        f"Clean: {ok_count}",
        f"Warnings: {len(rows) - ok_count}",
        "",
        "| File | Rows | Status | Warnings |",
        "|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {file} | {rows} | {status} | {warnings} |".format(
                file=Path(row["path"]).name,
                rows=row["row_count"],
                status="ok" if row["ok"] else "warn",
                warnings=", ".join(row["warnings"]) if row["warnings"] else "-",
            )
        )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--market", default="spot")
    parser.add_argument("--repair-missing", action="store_true")
    args = parser.parse_args()

    rows = validate_cache(Path(args.cache_dir), args.limit, repair=args.repair_missing, market=args.market)
    write_outputs(rows)
    warnings = sum(1 for row in rows if not row["ok"])
    print(f"checked={len(rows)} warnings={warnings}")
    print(OUTPUT_MD)


if __name__ == "__main__":
    main()
