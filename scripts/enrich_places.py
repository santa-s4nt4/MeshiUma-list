#!/usr/bin/env python3
"""Enrich restaurants.json with address / prefecture / city via Google Places API (New).

Usage:
  cp .env.example .env
  # .env に GOOGLE_MAPS_API_KEY を設定
  python3 scripts/enrich_places.py

Useful options:
  python3 scripts/enrich_places.py --limit 20
  python3 scripts/enrich_places.py --start 100 --limit 50
  python3 scripts/enrich_places.py --refresh
  python3 scripts/enrich_places.py --input public/data/restaurants.json --output public/data/restaurants.json

The script is resumable. API responses are cached in .cache/places-cache.json.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.addressComponents,places.googleMapsUri"
)
DEFAULT_INPUT = Path("public/data/restaurants.json")
DEFAULT_CACHE = Path(".cache/places-cache.json")


def load_env_file(path: Path = Path(".env")) -> None:
    """Minimal .env loader (no external dependency required).

    Existing environment variables take precedence over values in .env.
    Supports simple KEY=value lines and optional single/double quotes.
    """
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Google Places APIで店舗住所・都道府県・市区町村を補完します。"
    )
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=None,
                   help="省略時は --input を上書き")
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--start", type=int, default=0,
                   help="処理開始インデックス（0始まり）")
    p.add_argument("--limit", type=int, default=0,
                   help="API問い合わせ件数の上限。0=全件")
    p.add_argument("--delay", type=float, default=0.08,
                   help="API呼び出し間隔（秒）")
    p.add_argument("--refresh", action="store_true",
                   help="既存の住所情報・キャッシュがあっても再取得")
    p.add_argument("--country", default="",
                   help="検索クエリに国名を追加。例: Japan。海外店を含む場合は指定しない")
    return p.parse_args()


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").casefold()
    s = re.sub(r"[\s\-‐‑‒–—―・･_'\"“”‘’()（）\[\]【】]+", "", s)
    return s


def similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.92
    return difflib.SequenceMatcher(None, na, nb).ratio()


def cache_key(item: dict[str, Any]) -> str:
    return f"{item.get('name','')}|{item.get('url','')}"


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


def request_places(api_key: str, text_query: str, retries: int = 5) -> list[dict[str, Any]]:
    body = json.dumps({
        "textQuery": text_query,
        "languageCode": "ja",
        "pageSize": 5,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
    )

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=25) as res:
                payload = json.loads(res.read().decode("utf-8"))
                return payload.get("places", [])
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(1.5 * (2 ** attempt))
                continue
            raise RuntimeError(f"Places API HTTP {e.code}: {detail[:500]}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1:
                time.sleep(1.5 * (2 ** attempt))
                continue
            raise RuntimeError(f"Places API network error: {e}") from e
    return []


def choose_best(name: str, places: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    if not places:
        return None, 0.0
    scored = []
    for p in places:
        display = ((p.get("displayName") or {}).get("text") or "")
        scored.append((similarity(name, display), p))
    scored.sort(key=lambda x: x[0], reverse=True)
    score, place = scored[0]
    return place, score


def component_map(place: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for comp in place.get("addressComponents", []) or []:
        text = comp.get("longText") or comp.get("shortText") or ""
        for t in comp.get("types", []) or []:
            result.setdefault(t, text)
    return result


def parse_location(place: dict[str, Any]) -> dict[str, Any]:
    c = component_map(place)
    country = c.get("country", "")
    prefecture = c.get("administrative_area_level_1", "") if country == "日本" else ""

    # Japan: Google usually returns wards/cities as locality.
    # Fallbacks cover some municipalities / rural addresses.
    city = (
        c.get("locality")
        or c.get("administrative_area_level_2")
        or c.get("sublocality_level_1")
        or c.get("sublocality")
        or ""
    )

    display_name = ((place.get("displayName") or {}).get("text") or "")
    return {
        "placeId": place.get("id", ""),
        "placeName": display_name,
        "address": place.get("formattedAddress", ""),
        "country": country,
        "prefecture": prefecture,
        "city": city,
        "googleMapsUri": place.get("googleMapsUri", ""),
    }


def already_enriched(item: dict[str, Any]) -> bool:
    return bool(item.get("address") or item.get("placeId"))


def main() -> int:
    args = parse_args()
    load_env_file()
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GOOGLE_MAPS_API_KEY が見つかりません。", file=sys.stderr)
        print("  .env を作成して GOOGLE_MAPS_API_KEY=YOUR_API_KEY を設定してください。", file=sys.stderr)
        return 2

    output = args.output or args.input
    items = load_json(args.input, None)
    if not isinstance(items, list):
        print(f"ERROR: {args.input} がJSON配列ではありません。", file=sys.stderr)
        return 2

    cache: dict[str, Any] = load_json(args.cache, {})
    if not isinstance(cache, dict):
        cache = {}

    start = max(0, args.start)
    processed_api = 0
    matched = 0
    not_found = 0
    skipped = 0
    errors = 0

    print(f"入力: {args.input} ({len(items)}件)")
    print(f"出力: {output}")
    print(f"開始: {start}, API上限: {'全件' if args.limit == 0 else args.limit}")

    try:
        for i in range(start, len(items)):
            item = items[i]
            if not isinstance(item, dict):
                continue

            if already_enriched(item) and not args.refresh:
                skipped += 1
                continue

            key = cache_key(item)
            cached = cache.get(key)
            if cached is not None and not args.refresh:
                if cached.get("status") == "ok":
                    item.update(cached.get("data", {}))
                    item["placeMatchScore"] = cached.get("score", 0.0)
                    matched += 1
                else:
                    not_found += 1
                continue

            if args.limit and processed_api >= args.limit:
                break

            name = str(item.get("name") or "").strip()
            if not name:
                continue

            query = name
            if args.country:
                query += f" {args.country}"

            try:
                places = request_places(api_key, query)
                processed_api += 1
                best, score = choose_best(name, places)

                # Avoid attaching a clearly different place for ambiguous names.
                if best is None or score < 0.45:
                    cache[key] = {"status": "not_found", "query": query, "score": score}
                    not_found += 1
                    print(f"[{i+1}/{len(items)}] ? {name}  (候補なし/低一致 {score:.2f})")
                else:
                    data = parse_location(best)
                    item.update(data)
                    item["placeMatchScore"] = round(score, 4)
                    cache[key] = {
                        "status": "ok",
                        "query": query,
                        "score": round(score, 4),
                        "data": data,
                    }
                    matched += 1
                    print(
                        f"[{i+1}/{len(items)}] ✓ {name} → "
                        f"{data.get('prefecture') or data.get('country') or '住所不明'} "
                        f"{data.get('city','')} ({score:.2f})"
                    )

                # Save every request so Ctrl+C / errors do not lose progress.
                save_json_atomic(args.cache, cache)
                save_json_atomic(output, items)
                if args.delay > 0:
                    time.sleep(args.delay)

            except RuntimeError as e:
                errors += 1
                print(f"[{i+1}/{len(items)}] ERROR {name}: {e}", file=sys.stderr)
                save_json_atomic(args.cache, cache)
                save_json_atomic(output, items)
                # Authentication / billing errors are usually persistent, so stop.
                if "HTTP 400" in str(e) or "HTTP 401" in str(e) or "HTTP 403" in str(e):
                    return 3

    except KeyboardInterrupt:
        print("\n中断しました。ここまでの結果を保存します。")
    finally:
        save_json_atomic(args.cache, cache)
        save_json_atomic(output, items)

    print("\n完了")
    print(f"  API問い合わせ: {processed_api}")
    print(f"  住所取得/キャッシュ反映: {matched}")
    print(f"  見つからず: {not_found}")
    print(f"  既存情報のためスキップ: {skipped}")
    print(f"  エラー: {errors}")
    print(f"  キャッシュ: {args.cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
