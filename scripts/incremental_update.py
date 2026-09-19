#!/usr/bin/env python3
"""Incrementally update restaurants.json from a Google Maps CSV.

What this script does:
  1. Compare the latest CSV with csv/prev_メシウマ.csv using Google Maps URL as the key.
  2. Convert the latest CSV to the site's JSON shape (including genre inference).
  3. Reuse Places-enriched fields for restaurants that already existed.
  4. Send only newly-added restaurants to scripts/enrich_places.py.
  5. Drop restaurants that disappeared from the latest CSV.
  6. After every newly-added item has been processed, copy the latest CSV to
     csv/prev_メシウマ.csv for the next run.

Default usage:
  python3 scripts/incremental_update.py

Custom latest CSV:
  python3 scripts/incremental_update.py path/to/メシウマ.csv

The first run has no previous CSV, so every current restaurant is treated as new.
After that, only additions are sent to Google Places API.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Allow importing sibling script directly.
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from convert_google_maps_csv import read_takeout_csv  # noqa: E402

DEFAULT_CURRENT = ROOT / "メシウマ.csv"
DEFAULT_PREV = ROOT / "csv" / "prev_メシウマ.csv"
DEFAULT_JSON = ROOT / "public" / "data" / "restaurants.json"
DEFAULT_CACHE = ROOT / ".cache" / "places-cache.json"
TEMP_NEW = ROOT / ".cache" / "new-restaurants.json"

BASE_FIELDS = {"name", "memo", "url", "tags", "comment", "genre"}
# These are produced by enrich_places.py. Keeping this explicit prevents stale
# CSV-side values from overwriting the latest CSV fields.
ENRICH_FIELDS = {
    "placeId",
    "placeName",
    "address",
    "country",
    "prefecture",
    "city",
    "googleMapsUri",
    "placeMatchScore",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="最新CSVと前回CSVを比較し、新規店だけPlaces APIで補完します。"
    )
    p.add_argument(
        "current_csv",
        nargs="?",
        type=Path,
        default=DEFAULT_CURRENT,
        help="最新CSV。省略時はプロジェクト直下の メシウマ.csv",
    )
    p.add_argument("--prev", type=Path, default=DEFAULT_PREV)
    p.add_argument("--json", type=Path, default=DEFAULT_JSON)
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="追加/削除件数だけ確認し、ファイル更新やAPI呼び出しをしない",
    )
    # Forwarded to enrich_places.py. Useful for a test run. If not all new
    # restaurants are processed, prev CSV is intentionally NOT advanced.
    p.add_argument("--limit", type=int, default=0, help="新規店へのAPI問い合わせ上限。0=全件")
    p.add_argument("--delay", type=float, default=0.08, help="API呼び出し間隔（秒）")
    p.add_argument("--country", default="", help="Places検索時に国名を追加。海外店があるなら空欄推奨")
    p.add_argument("--refresh", action="store_true", help="新規店についてキャッシュを無視して再取得")
    return p.parse_args()


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return fallback


def save_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def item_key(item: dict[str, Any]) -> str:
    """Use Google Maps URL as the stable key, falling back to name only if needed."""
    url = str(item.get("url") or "").strip()
    if url:
        return f"url:{url}"
    return f"name:{str(item.get('name') or '').strip()}"


def cache_key(item: dict[str, Any]) -> str:
    # Must match enrich_places.py exactly.
    return f"{item.get('name','')}|{item.get('url','')}"


def index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item_key(x): x for x in items if isinstance(x, dict)}


def carry_enrichment(base: dict[str, Any], old: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(base)
    if old:
        for field in ENRICH_FIELDS:
            if field in old:
                result[field] = old[field]
    return result


def processed_new_item(item: dict[str, Any], cache: dict[str, Any]) -> bool:
    """True when a new item has either matched or received a cached not-found result."""
    if item.get("address") or item.get("placeId"):
        return True
    return cache_key(item) in cache


def main() -> int:
    args = parse_args()
    current_path = args.current_csv.resolve()
    prev_path = args.prev.resolve()
    json_path = args.json.resolve()
    cache_path = args.cache.resolve()

    if not current_path.exists():
        print(f"ERROR: 最新CSVが見つかりません: {current_path}", file=sys.stderr)
        return 2

    try:
        current_items = read_takeout_csv(current_path)
        prev_items = read_takeout_csv(prev_path) if prev_path.exists() else []
    except Exception as e:
        print(f"ERROR: CSVを読み込めません: {e}", file=sys.stderr)
        return 2

    old_json = load_json(json_path, [])
    if not isinstance(old_json, list):
        old_json = []

    current_by_key = index(current_items)
    prev_by_key = index(prev_items)
    old_by_key = index(old_json)

    current_keys = set(current_by_key)
    prev_keys = set(prev_by_key)
    added_keys = current_keys - prev_keys
    removed_keys = prev_keys - current_keys

    print("========================================")
    print("Google Maps CSV 差分更新")
    print("========================================")
    print(f"最新CSV: {len(current_items)}件")
    print(f"前回CSV: {len(prev_items)}件")
    print(f"新規追加: {len(added_keys)}件")
    print(f"削除:     {len(removed_keys)}件")
    print(f"継続:     {len(current_keys & prev_keys)}件")

    if args.dry_run:
        if added_keys:
            print("\n[追加]")
            for k in sorted(added_keys):
                print(f"  + {current_by_key[k].get('name','')}")
        if removed_keys:
            print("\n[削除]")
            for k in sorted(removed_keys):
                print(f"  - {prev_by_key[k].get('name','')}")
        return 0

    # Build the complete latest list. CSV-side fields always come from the newest
    # CSV; previously-enriched location fields are carried across for existing URLs.
    merged: list[dict[str, Any]] = []
    merged_by_key: dict[str, dict[str, Any]] = {}
    for base in current_items:
        k = item_key(base)
        item = carry_enrichment(base, old_by_key.get(k))
        merged.append(item)
        merged_by_key[k] = item

    # Only entries that are NEW compared with prev CSV are eligible for API calls.
    new_items = [merged_by_key[item_key(x)] for x in current_items if item_key(x) in added_keys]

    if new_items:
        TEMP_NEW.parent.mkdir(parents=True, exist_ok=True)
        save_json_atomic(TEMP_NEW, new_items)

        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "enrich_places.py"),
            "--input",
            str(TEMP_NEW),
            "--output",
            str(TEMP_NEW),
            "--cache",
            str(cache_path),
            "--delay",
            str(args.delay),
        ]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        if args.country:
            cmd += ["--country", args.country]
        if args.refresh:
            cmd.append("--refresh")

        print("\n新規店だけ Google Places API で補完します…")
        result = subprocess.run(cmd, cwd=ROOT)

        # Merge whatever enrichment completed, even if the process was interrupted;
        # prev CSV will not advance unless all new items were processed.
        enriched_new = load_json(TEMP_NEW, [])
        if isinstance(enriched_new, list):
            for item in enriched_new:
                if not isinstance(item, dict):
                    continue
                k = item_key(item)
                if k in merged_by_key:
                    for field in ENRICH_FIELDS:
                        if field in item:
                            merged_by_key[k][field] = item[field]

        save_json_atomic(json_path, merged)

        if result.returncode != 0:
            print(
                "\nPlaces API処理が完了しなかったため、restaurants.json は途中結果を保存しましたが、"
                "prev CSV は更新していません。次回同じコマンドで続きから処理できます。",
                file=sys.stderr,
            )
            return result.returncode

        cache = load_json(cache_path, {})
        if not isinstance(cache, dict):
            cache = {}
        pending = [x for x in enriched_new if isinstance(x, dict) and not processed_new_item(x, cache)]
        if pending:
            print(
                f"\n新規 {len(new_items)}件のうち {len(pending)}件が未処理です。"
                "--limit 等で途中まで処理したため prev CSV は更新しません。"
            )
            print("次回 ./update_data.sh を実行すると残りを続けて処理します。")
            return 0
    else:
        # No new restaurants means no API key is needed at all.
        save_json_atomic(json_path, merged)
        print("\n新規店がないため Places API は呼び出しません。")

    # Advance baseline only after all additions have been handled. Removed items are
    # already absent from `merged`, so this also finalizes deletions.
    prev_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(current_path, prev_path)

    print("\n========================================")
    print("更新完了")
    print("========================================")
    print(f"JSON: {json_path}")
    print(f"前回CSV更新: {prev_path}")
    print(f"追加反映: {len(added_keys)}件")
    print(f"削除反映: {len(removed_keys)}件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
