#!/usr/bin/env python3
"""
Precompute ALL season-level data and save to a single cache file.

Everything that depends only on the season (not the club or simulation params)
is computed here so the simulator can load it instantly:
  - Active players with ML predicted values
  - Team market values (team_name -> total_market_value)
  - Athletic-eligible player IDs (for Athletic Bilbao buy/sell policy)

For "today": the file is named ``_today.json`` and includes a ``computed_date``
field.  The simulator checks freshness: if the difference between today and
computed_date is > 1 day, the cache is considered stale and recomputed on the fly.

Output: data/json/cache/season_data_{season}.json
        data/json/cache/season_data_today.json  (for --season today)

Usage:
  python scripts/precompute_active_players_cache.py --season today
  python scripts/precompute_active_players_cache.py --season today --date 2026-02-24
  python scripts/precompute_active_players_cache.py --season 2024-2025
  python scripts/precompute_active_players_cache.py --all-seasons
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from tqdm import tqdm

from scraping.utils.helpers import DATA_DIR, list_json_bases, load_json
from simulator.data_loader import get_active_players_at_season_start
from ml.feature_engineering import (
    build_prediction_context,
    build_prediction_dataset,
    load_team_league_mapping,
)
from ml.value_predictor import ValuePredictor, MODELS_DIR
from valuation import Valuation

# Re-use the constants from the simulator
from simulator.transfer_simulator import ATHLETIC_FAMILY_IDS, ATHLETIC_FAMILY_NAMES

CACHE_DIR = DATA_DIR / "cache"
CACHE_PREFIX = "season_data"


def _load_all_valuations(verbose: bool = False) -> List[Valuation]:
    """Load all valuations from every valuations_all_*.json file."""
    all_vals: List[Valuation] = []
    bases = list(list_json_bases("valuations_all_*.json"))
    for base in tqdm(bases, desc="Loading valuations", disable=not verbose):
        data = load_json(base)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    all_vals.append(Valuation.from_dict(item))
    return all_vals


def _calculate_team_market_values(players) -> Dict[str, float]:
    """Build {team_name: total_market_value} from all active players."""
    team_values: Dict[str, float] = {}
    for p in players:
        if p.team:
            team_values[p.team] = team_values.get(p.team, 0) + (p.market_value or 0)
    return team_values


def _load_athletic_eligible_ids(verbose: bool = False) -> Set[str]:
    """Scan transfer files for players who have been at an Athletic-family club."""
    eligible: Set[str] = set()
    bases = list(list_json_bases("transfers_all_*.json"))
    for base in tqdm(bases, desc="Athletic eligibility scan", disable=not verbose):
        data = load_json(base)
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            from_id = str(item.get("from_club_id", "") or "")
            from_name = (item.get("from_club_name") or item.get("from_club", "") or "").lower()
            to_id = str(item.get("to_club_id", "") or "")
            to_name = (item.get("to_club_name") or item.get("to_club", "") or "").lower()
            if (from_id in ATHLETIC_FAMILY_IDS or from_name in ATHLETIC_FAMILY_NAMES
                    or to_id in ATHLETIC_FAMILY_IDS or to_name in ATHLETIC_FAMILY_NAMES):
                pid = item.get("player_id", "")
                if pid:
                    eligible.add(str(pid))
    return eligible


def _get_cutoff_date(season: str, override_date: Optional[str] = None) -> datetime:
    """Return cutoff datetime for a season."""
    if season.lower() == "today":
        if override_date:
            return datetime.strptime(override_date, "%Y-%m-%d")
        return datetime.now()
    start_year = int(season.split("-")[0])
    return datetime(start_year, 7, 1)


def precompute_and_save(
    season: str,
    verbose: bool = True,
    override_date: Optional[str] = None,
) -> Path:
    """
    Compute everything for a season and save to a single JSON cache file.

    Args:
        season: e.g. "2024-2025" or "today"
        verbose: progress output
        override_date: YYYY-MM-DD string; used as "today" in GitHub Actions
                       so the cache knows what date it represents.

    Returns:
        Path to the saved cache file.
    """
    cutoff_date = _get_cutoff_date(season, override_date)

    if season.lower() == "today":
        model_path = ValuePredictor.get_latest_model()
    else:
        model_path = MODELS_DIR / f"value_model_{season}.joblib"

    if model_path is None or not Path(model_path).exists():
        raise FileNotFoundError(
            f"No model for season '{season}'. "
            f"Run: python -m ml.train_pipeline --season {season}"
        )

    if verbose:
        print(f"=== Precomputing season data for '{season}' ===")
        print(f"  Cutoff date : {cutoff_date.strftime('%Y-%m-%d')}")
        print(f"  Model       : {model_path}")

    # ── 1. Active players ────────────────────────────────────────────────
    if verbose:
        print("\n[1/5] Loading active players...")
    players = get_active_players_at_season_start(season, verbose=verbose)
    if not players:
        raise ValueError(f"No active players found for season '{season}'")
    if verbose:
        print(f"  → {len(players)} active players")

    # ── 2. Team market values ────────────────────────────────────────────
    if verbose:
        print("\n[2/5] Calculating team market values...")
    team_market_values = _calculate_team_market_values(players)
    if verbose:
        print(f"  → {len(team_market_values)} teams")

    # ── 3. Athletic eligible IDs ─────────────────────────────────────────
    if verbose:
        print("\n[3/5] Scanning Athletic-family eligibility...")
    athletic_eligible_ids = _load_athletic_eligible_ids(verbose=verbose)
    if verbose:
        print(f"  → {len(athletic_eligible_ids)} eligible players")

    # ── 4. ML predictions ────────────────────────────────────────────────
    if verbose:
        print("\n[4/5] Loading valuations + building prediction features...")
    all_valuations = _load_all_valuations(verbose=verbose)
    team_league_mapping = load_team_league_mapping(verbose=verbose)
    transfer_map, by_player, team_total_values = build_prediction_context(
        all_valuations, cutoff_date, verbose=verbose
    )

    player_dict = {p.player_id: p for p in players}
    features = build_prediction_dataset(
        all_valuations,
        cutoff_date,
        players=player_dict,
        team_league_mapping=team_league_mapping,
        transfer_map=transfer_map,
        by_player=by_player,
        team_total_values=team_total_values,
        verbose=verbose,
    )

    predictor = ValuePredictor(model_path)
    predictions = predictor.predict_batch(features)
    pred_map = {f.player_id: pred for f, pred in zip(features, predictions)}

    for p in players:
        p.predicted_value = pred_map.get(p.player_id, p.market_value)

    if verbose:
        print(f"  → Predicted values for {len(pred_map)} / {len(players)} players")

    # ── 5. Save ──────────────────────────────────────────────────────────
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if season.lower() == "today":
        cache_path = CACHE_DIR / f"{CACHE_PREFIX}_today.json"
    else:
        cache_path = CACHE_DIR / f"{CACHE_PREFIX}_{season}.json"

    computed_date_str = (
        override_date
        if override_date
        else datetime.now().strftime("%Y-%m-%d")
    )

    payload = {
        "season": season,
        "computed_date": computed_date_str,
        "player_count": len(players),
        "team_count": len(team_market_values),
        "athletic_eligible_count": len(athletic_eligible_ids),
        "players": [p.to_dict() for p in players],
        "team_market_values": team_market_values,
        "athletic_eligible_ids": sorted(athletic_eligible_ids),
    }

    if verbose:
        print(f"\n[5/5] Saving to {cache_path} ...")

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    size_mb = cache_path.stat().st_size / (1024 * 1024)
    if verbose:
        print(f"  → Saved ({size_mb:.1f} MB)")

    return cache_path


def main():
    parser = argparse.ArgumentParser(
        description="Precompute all season-level data (players, predictions, team values, athletic eligibility)"
    )
    parser.add_argument(
        "--season", type=str, default=None,
        help="Season to precompute (e.g. 2024-2025) or 'today'",
    )
    parser.add_argument(
        "--all-seasons", action="store_true",
        help="Precompute for every season found in teams_all_*.json",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Override 'today' date (YYYY-MM-DD). Passed from GitHub Actions.",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Reduce output",
    )
    args = parser.parse_args()
    verbose = not args.quiet

    if args.all_seasons:
        seasons = sorted(
            {base.replace("teams_all_", "")
             for base in list_json_bases("teams_all_*.json")
             if base.startswith("teams_all_")},
            reverse=True,
        )
        if verbose:
            print(f"Precomputing {len(seasons)} seasons: {seasons}\n")
        for s in seasons:
            try:
                precompute_and_save(s, verbose=verbose)
            except FileNotFoundError as e:
                if verbose:
                    print(f"  ⚠ Skipping {s}: {e}\n")
            except Exception as e:
                print(f"  ✗ Error for {s}: {e}")
                raise
    elif args.season:
        precompute_and_save(args.season, verbose=verbose, override_date=args.date)
    else:
        parser.error("Specify --season or --all-seasons")


if __name__ == "__main__":
    main()
