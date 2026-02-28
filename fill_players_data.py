#!/usr/bin/env python
r"""
fill_players_data.py
====================
Scan every ``players_all_*.json`` file and fill missing player fields
by cross-referencing data across seasons and, when necessary, querying
the Transfermarkt player API.

Fields filled cross-season
--------------------------
name, position, main_position, other_positions, birth_date,
nationality, other_nationalities, height, preferred_foot,
img_url, profile_url

API fallback
------------
If critical fields are still missing after cross-season fill
(name, position, birth_date, height, preferred_foot, img_url, profile_url),
the Transfermarkt player API is queried.  For ``img_url``, only a truly
empty value counts as missing — a default placeholder image is NOT missing.

Age recomputation
-----------------
Age is recomputed as an integer from ``birth_date`` and the season cutoff
date (01/07 of the season's start year) for every record.

Usage::

    python fill_players_data.py              # scan + fill all files
    python fill_players_data.py --dry-run    # scan only, don't write
    python fill_players_data.py --no-api     # cross-season fill only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scraping.utils.helpers import (
    DATA_DIR,
    list_json_bases,
    load_json,
    save_json_with_parts,
)

# ── Configuration ────────────────────────────────────────────────────────────
TM_API_URL = "https://tmapi-alpha.transfermarkt.technology"
MAX_RETRIES = 5
RETRY_PAUSE = 10        # seconds between retries
REQUEST_DELAY = 0.3     # polite delay between API requests

DEFAULT_IMG_MARKERS = ["default.jpg", "default.png"]

FILLABLE_STRING_FIELDS = [
    "name", "position", "main_position", "birth_date",
    "nationality", "preferred_foot", "img_url", "profile_url",
]
FILLABLE_LIST_FIELDS = ["other_positions", "other_nationalities"]
FILLABLE_NUMBER_FIELDS = ["height"]

CRITICAL_FIELDS_FOR_API = [
    "name", "position", "birth_date", "height",
    "preferred_foot", "img_url", "profile_url",
]

POSITION_GROUP_MAP = {
    "GOALKEEPER": "GK",
    "DEFENDER": "DEF",
    "MIDFIELDER": "MID",
    "FORWARD": "ATT",
}
FOOT_MAP = {1: "left", 2: "right", 3: "both"}

# (base_name, season, records_list)
FileRecord = Tuple[str, str, list]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _season_sort_key(season: str) -> int:
    m = re.search(r"(\d{4})", season)
    return int(m.group(1)) if m else 0


def _season_cutoff(season: str) -> Optional[datetime]:
    m = re.search(r"(\d{4})", season)
    return datetime(int(m.group(1)), 7, 1) if m else None


def _compute_age(birth_date_str: str, cutoff: datetime) -> Optional[int]:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            bd = datetime.strptime(birth_date_str, fmt)
            age = cutoff.year - bd.year
            if (cutoff.month, cutoff.day) < (bd.month, bd.day):
                age -= 1
            return max(0, age)
        except ValueError:
            continue
    return None


def _is_default_img(url: str) -> bool:
    if not url:
        return True
    return any(m in url for m in DEFAULT_IMG_MARKERS)


def _is_empty_str(val: Any) -> bool:
    return val is None or (isinstance(val, str) and not val.strip())


def _is_empty_list(val: Any) -> bool:
    return not val or (isinstance(val, list) and len(val) == 0)


def _extract_season(base: str) -> str:
    m = re.search(r"(\d{4}-\d{4})", base)
    return m.group(1) if m else ""


# ── File loading ─────────────────────────────────────────────────────────────

def load_all_player_files() -> List[FileRecord]:
    result: List[FileRecord] = []
    bases = list_json_bases("players_all_*.json")
    print(f"Loading player files from {DATA_DIR} …")

    for base in bases:
        season = _extract_season(base)
        if not season:
            continue
        try:
            raw = load_json(base)
        except Exception as exc:
            print(f"  SKIP {base}: {exc}")
            continue
        if raw is None:
            continue
        records = raw["items"] if isinstance(raw, dict) and "items" in raw else raw
        if not isinstance(records, list):
            continue
        result.append((base, season, records))

    print(f"  Loaded {len(result)} files.\n")
    return result


# ── Build master player dict ─────────────────────────────────────────────────

def build_player_master(file_records: List[FileRecord]) -> Dict[str, dict]:
    """Best non-empty value per player_id across all seasons (newest wins)."""
    player_recs: Dict[str, List[Tuple[str, dict]]] = {}

    for _base, season, records in file_records:
        for rec in records:
            pid = rec.get("player_id")
            if not pid:
                continue
            player_recs.setdefault(str(pid), []).append((season, rec))

    for pid in player_recs:
        player_recs[pid].sort(key=lambda x: _season_sort_key(x[0]), reverse=True)

    master: Dict[str, dict] = {}

    for pid, srecs in player_recs.items():
        best: dict = {"player_id": pid}

        for field in FILLABLE_STRING_FIELDS:
            if field == "img_url":
                # 1st pass: non-default non-empty (newest)
                for _s, r in srecs:
                    v = r.get(field)
                    if not _is_empty_str(v) and not _is_default_img(v):
                        best[field] = v
                        break
                # 2nd pass: any non-empty
                if field not in best:
                    for _s, r in srecs:
                        v = r.get(field)
                        if not _is_empty_str(v):
                            best[field] = v
                            break
            elif field == "position":
                for _s, r in srecs:
                    v = r.get(field)
                    if v and v != "N/A":
                        best[field] = v
                        break
            else:
                for _s, r in srecs:
                    v = r.get(field)
                    if not _is_empty_str(v):
                        best[field] = v
                        break

        for field in FILLABLE_NUMBER_FIELDS:
            for _s, r in srecs:
                v = r.get(field)
                if v is not None:
                    best[field] = v
                    break

        for field in FILLABLE_LIST_FIELDS:
            longest: list = []
            for _s, r in srecs:
                v = r.get(field)
                if isinstance(v, list) and len(v) > len(longest):
                    longest = v
            if longest:
                best[field] = longest

        master[pid] = best

    return master


# ── Apply master to records ──────────────────────────────────────────────────

def apply_master(
    file_records: List[FileRecord],
    master: Dict[str, dict],
) -> Set[str]:
    """Fill missing fields in-place. Returns modified base names."""
    modified: Set[str] = set()

    for base, _season, records in file_records:
        changed = False
        for rec in records:
            pid = rec.get("player_id")
            if not pid or str(pid) not in master:
                continue
            best = master[str(pid)]

            for field in FILLABLE_STRING_FIELDS:
                if field not in best:
                    continue
                cur = rec.get(field)
                new = best[field]
                if field == "position":
                    if (cur == "N/A" or _is_empty_str(cur)) and new != "N/A":
                        rec[field] = new
                        changed = True
                elif field == "img_url":
                    if _is_empty_str(cur) and not _is_empty_str(new):
                        rec[field] = new
                        changed = True
                    elif _is_default_img(cur) and not _is_default_img(new):
                        rec[field] = new
                        changed = True
                else:
                    if _is_empty_str(cur) and not _is_empty_str(new):
                        rec[field] = new
                        changed = True

            for field in FILLABLE_NUMBER_FIELDS:
                if field not in best:
                    continue
                if rec.get(field) is None:
                    rec[field] = best[field]
                    changed = True

            for field in FILLABLE_LIST_FIELDS:
                if field not in best:
                    continue
                cur = rec.get(field) or []
                new = best[field]
                if len(new) > len(cur):
                    rec[field] = new
                    changed = True

        if changed:
            modified.add(base)

    return modified


# ── API helpers ──────────────────────────────────────────────────────────────

def _api_get(url: str, timeout: int = 30) -> Optional[dict]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return None
            if resp.status_code in (429, 500, 502, 503, 504):
                print(f"    Attempt {attempt}/{MAX_RETRIES}: HTTP {resp.status_code}")
            else:
                print(f"    HTTP {resp.status_code} – giving up for {url}")
                return None
        except Exception as exc:
            print(f"    Attempt {attempt}/{MAX_RETRIES}: {exc!r}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_PAUSE)
    return None


def _normalize_position_group(group: str) -> str:
    return POSITION_GROUP_MAP.get(group.upper(), "N/A") if group else "N/A"


def fetch_player_from_api(player_id: str) -> Optional[dict]:
    """Fetch one player from Transfermarkt API and normalise fields."""
    resp = _api_get(f"{TM_API_URL}/player/{player_id}")
    if not resp or not resp.get("success"):
        return None

    d = resp.get("data") or {}
    if not d:
        return None

    attrs = d.get("attributes") or {}
    life = d.get("lifeDates") or {}

    # birth_date (YYYY-MM-DD → DD/MM/YYYY)
    raw_bd = life.get("dateOfBirth", "")
    birth_date = ""
    if raw_bd:
        try:
            birth_date = datetime.strptime(raw_bd, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            pass

    # height (m → cm int)
    height: Optional[int] = None
    raw_h = attrs.get("height")
    if raw_h is not None:
        try:
            h_cm = int(round(float(raw_h) * 100))
            if h_cm > 100:
                height = h_cm
        except (ValueError, TypeError):
            pass

    # preferred_foot
    foot_obj = attrs.get("preferredFoot") or {}
    preferred_foot = foot_obj.get("name", "")
    if not preferred_foot:
        preferred_foot = FOOT_MAP.get(attrs.get("preferredFootId"), "")

    # position / main_position
    position = _normalize_position_group(attrs.get("positionGroup", ""))
    pos_obj = attrs.get("position") or {}
    main_position = pos_obj.get("name", "")

    # other_positions
    other_positions: List[str] = []
    for key in ("firstSidePosition", "secondSidePosition"):
        sp = attrs.get(key) or {}
        sp_name = sp.get("name", "")
        if sp_name and sp_name != main_position:
            other_positions.append(sp_name)

    # img_url (portraitUrl may or may not exist)
    img_url = d.get("portraitUrl", "")

    # profile_url
    rel = d.get("relativeUrl", "")
    profile_url = f"https://www.transfermarkt.com{rel}" if rel else ""

    return {
        "player_id": str(d.get("id", player_id)),
        "name": d.get("name", ""),
        "position": position,
        "main_position": main_position,
        "other_positions": other_positions,
        "birth_date": birth_date,
        "height": height,
        "preferred_foot": preferred_foot,
        "img_url": img_url,
        "profile_url": profile_url,
    }


# ── Find players needing API ─────────────────────────────────────────────────

def find_players_needing_api(master: Dict[str, dict]) -> Set[str]:
    needs: Set[str] = set()
    for pid, best in master.items():
        for field in CRITICAL_FIELDS_FOR_API:
            if field == "position":
                if best.get(field, "N/A") == "N/A":
                    needs.add(pid)
                    break
            elif field in FILLABLE_NUMBER_FIELDS:
                if best.get(field) is None:
                    needs.add(pid)
                    break
            elif field == "img_url":
                if _is_empty_str(best.get(field)):
                    needs.add(pid)
                    break
            else:
                if _is_empty_str(best.get(field)):
                    needs.add(pid)
                    break
    return needs


def fetch_and_update_master(
    player_ids: Set[str],
    master: Dict[str, dict],
) -> int:
    """Fetch from API and update master in-place.  Returns # updated."""
    ids = sorted(player_ids)
    print(f"\nFetching data for {len(ids)} players from API …")
    updated = 0

    for i, pid in enumerate(ids, 1):
        if i % 100 == 0 or i == len(ids):
            print(f"  Progress: {i}/{len(ids)}  (updated so far: {updated})")

        api = fetch_player_from_api(pid)
        if not api:
            continue

        best = master.setdefault(pid, {"player_id": pid})
        changed = False

        for field in FILLABLE_STRING_FIELDS:
            api_val = api.get(field)
            if _is_empty_str(api_val):
                continue
            cur = best.get(field)
            if field == "position":
                if cur == "N/A" or _is_empty_str(cur):
                    best[field] = api_val
                    changed = True
            elif field == "img_url":
                if _is_empty_str(cur):
                    best[field] = api_val
                    changed = True
                elif _is_default_img(cur) and not _is_default_img(api_val):
                    best[field] = api_val
                    changed = True
            else:
                if _is_empty_str(cur):
                    best[field] = api_val
                    changed = True

        for field in FILLABLE_NUMBER_FIELDS:
            api_val = api.get(field)
            if api_val is not None and best.get(field) is None:
                best[field] = api_val
                changed = True

        for field in FILLABLE_LIST_FIELDS:
            api_val = api.get(field)
            if isinstance(api_val, list) and len(api_val) > len(best.get(field) or []):
                best[field] = api_val
                changed = True

        if changed:
            updated += 1

    print(f"  Updated {updated} players from API.\n")
    return updated


# ── Age recomputation ────────────────────────────────────────────────────────

def build_age_lookup(
    master: Dict[str, dict],
    seasons: List[str],
) -> Dict[str, Dict[str, int]]:
    """Precompute ``{player_id: {season: age_int}}``."""
    cutoffs = {s: c for s in seasons if (c := _season_cutoff(s)) is not None}
    ages: Dict[str, Dict[str, int]] = {}

    for pid, best in master.items():
        bd = best.get("birth_date")
        if not bd:
            continue
        pa: Dict[str, int] = {}
        for s, c in cutoffs.items():
            a = _compute_age(bd, c)
            if a is not None:
                pa[s] = a
        if pa:
            ages[pid] = pa

    return ages


def apply_ages(
    file_records: List[FileRecord],
    age_lookup: Dict[str, Dict[str, int]],
) -> Set[str]:
    """Overwrite age in every record.  Returns modified base names."""
    modified: Set[str] = set()

    for base, season, records in file_records:
        changed = False
        for rec in records:
            pid = rec.get("player_id")
            if not pid:
                continue
            pa = age_lookup.get(str(pid))
            if not pa:
                continue
            new_age = pa.get(season)
            if new_age is not None and rec.get("age") != new_age:
                rec["age"] = new_age
                changed = True
        if changed:
            modified.add(base)

    return modified


# ── Write ────────────────────────────────────────────────────────────────────

def write_files(file_records: List[FileRecord], bases_to_write: Set[str]) -> None:
    if not bases_to_write:
        print("\nNo files to write.")
        return

    for base, _season, records in file_records:
        if base not in bases_to_write:
            continue
        save_json_with_parts(records, base)
        print(f"  Written: {base}")


# ── Stats ────────────────────────────────────────────────────────────────────

def print_stats(master: Dict[str, dict]) -> None:
    total = len(master)
    all_fields = FILLABLE_STRING_FIELDS + FILLABLE_NUMBER_FIELDS + FILLABLE_LIST_FIELDS
    stats: Dict[str, int] = {}

    for field in all_fields:
        missing = 0
        for best in master.values():
            v = best.get(field)
            if field == "position":
                if v == "N/A" or _is_empty_str(v):
                    missing += 1
            elif field in FILLABLE_NUMBER_FIELDS:
                if v is None:
                    missing += 1
            elif field in FILLABLE_LIST_FIELDS:
                if _is_empty_list(v):
                    missing += 1
            else:
                if _is_empty_str(v):
                    missing += 1
        if missing:
            stats[field] = missing

    print(f"\nCompleteness ({total} unique players):")
    if not stats:
        print("  All fields filled!")
    else:
        for field, m in sorted(stats.items(), key=lambda x: -x[1]):
            print(f"  {field}: {m} missing ({m / total * 100:.1f}%)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill missing player data across seasons and from API.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan and report but don't write changes.")
    parser.add_argument("--no-api", action="store_true",
                        help="Skip API calls (cross-season fill only).")
    args = parser.parse_args()

    if not DATA_DIR.exists():
        print(f"ERROR: {DATA_DIR} not found.")
        return

    # ── 1. Load ──────────────────────────────────────────────────────────
    file_records = load_all_player_files()
    if not file_records:
        print("No player files found.")
        return

    seasons = sorted({s for _, s, _ in file_records})
    total_recs = sum(len(r) for _, _, r in file_records)
    print(f"Seasons : {', '.join(seasons)}")
    print(f"Records : {total_recs}")

    # ── 2. Build master (cross-season best values) ───────────────────────
    print("\nBuilding master player dict …")
    master = build_player_master(file_records)
    print(f"  Unique players: {len(master)}")
    print_stats(master)

    # ── 3. Apply cross-season fill ───────────────────────────────────────
    print("\nApplying cross-season fill …")
    modified = apply_master(file_records, master)
    print(f"  Files modified: {len(modified)}")

    # ── 4. API fallback ──────────────────────────────────────────────────
    if not args.no_api:
        needs_api = find_players_needing_api(master)
        if needs_api:
            print(f"\n{len(needs_api)} players still missing critical fields.")
            n = fetch_and_update_master(needs_api, master)
            if n:
                print("Re-applying master after API fill …")
                api_mod = apply_master(file_records, master)
                modified |= api_mod
                print(f"  Additional files modified: {len(api_mod)}")
        else:
            print("\nAll critical fields present — no API calls needed.")

    # ── 5. Recompute ages ────────────────────────────────────────────────
    print("\nRecomputing ages …")
    age_lookup = build_age_lookup(master, seasons)
    print(f"  Players with computable age: {len(age_lookup)}")
    age_mod = apply_ages(file_records, age_lookup)
    modified |= age_mod
    print(f"  Files modified by age fix: {len(age_mod)}")

    # ── 6. Final stats ───────────────────────────────────────────────────
    master = build_player_master(file_records)
    print_stats(master)

    # ── 7. Write ─────────────────────────────────────────────────────────
    if args.dry_run:
        print(f"\n[DRY RUN] {len(modified)} files would be written.")
        return

    print(f"\nWriting {len(modified)} files …")
    write_files(file_records, modified)
    print("\n✓ Done!")


if __name__ == "__main__":
    main()
