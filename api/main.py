"""
FastAPI backend for Team Transfers Simulator.

Exposes the same functionality as the Streamlit app through REST endpoints.
Includes SSE streaming for long-running operations (simulation progress).
"""
from __future__ import annotations

import json as _json
import os
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scraping.utils.helpers import list_json_bases, load_json
from webapp.i18n import format_currency

TODAY_SEASON = "today"

LEAGUE_PRIORITY = {
    "laliga": 0, "la liga": 0,
    "premier league": 1,
    "serie a": 2, "seriea": 2,
    "bundesliga": 3,
    "ligue 1": 4, "ligue1": 4,
    "liga portugal": 5, "primeira liga": 5,
    "eredivisie": 6,
    "segunda división": 7, "segunda division": 7,
    "championship": 8,
}

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PlayerOut(BaseModel):
    player_id: str
    name: str
    team: str = ""
    team_id: str = ""
    position: str = "N/A"
    age: Optional[int] = None
    nationality: str = ""
    market_value: Optional[float] = None
    predicted_value: Optional[float] = None
    fair_price: Optional[float] = None
    img_url: str = ""
    on_loan: bool = False

class ClubOut(BaseModel):
    name: str
    league: str = ""
    logo_url: str = ""
    total_market_value: Optional[float] = None

class LoadSquadRequest(BaseModel):
    club_name: str
    season: str

class SimulateRequest(BaseModel):
    club_name: str
    season: str
    transfer_budget: int = 0
    unlimited: bool = False
    players_to_sell: List[str] = []
    buy_counts: Optional[Dict[str, Any]] = None
    approach: str = "max_value"
    objective: str = "smv"
    sim_speed: str = "standard"
    # Advanced filters
    league_filter: Optional[List[str]] = None
    banned_clubs: Optional[List[str]] = None
    banned_players: Optional[List[str]] = None
    exclude_top_n: int = 0
    min_market_value: Optional[float] = None
    horizon: int = 1

class SoldPlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    market_value: Optional[float] = None
    destination_team: Optional[str] = None
    was_sold: bool
    img_url: str = ""

class SimulationResultOut(BaseModel):
    club_name: str
    season: str
    initial_budget: int
    sales_revenue: int
    total_budget: int
    players_sold: List[SoldPlayerOut]
    formation_needed: List[int]
    recommended_signings: List[PlayerOut]
    recommended_formation: List[int]
    total_signing_cost: int
    total_predicted_value: float

class SellRecommendation(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    market_value: float
    predicted_value: float
    fair_price: Optional[float] = None
    decline: float
    decline_pct: float
    img_url: str = ""

class SellRecommendationsOut(BaseModel):
    peak_players: List[SellRecommendation]

class XGrowthPlayer(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    team: str
    market_value: float
    predicted_value: float
    xgrowth: float
    fair_price: float
    net_benefit: float = 0
    roi: float = 0
    growth_pct: float = 0
    img_url: str = ""

class SimilarPlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    team: str
    market_value: float
    predicted_value: float
    xgrowth: float
    fair_price: float
    similarity: float
    img_url: str = ""

class PlayerAnalysisOut(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    team: str
    market_value: float
    predicted_value: float
    xgrowth: float
    fair_price: float
    similar_players: List[SimilarPlayerOut]
    img_url: str = ""

class AnalyticsOut(BaseModel):
    xgrowth_ranking: List[XGrowthPlayer]
    signing_analysis: List[PlayerAnalysisOut]

class SearchPlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    team: str
    nationality: str
    market_value: float
    predicted_value: Optional[float]
    xgrowth: Optional[float]
    fair_price: Optional[float]
    img_url: str = ""

class SearchResults(BaseModel):
    players: List[SearchPlayerOut]
    total: int

class AISummaryRequest(BaseModel):
    api_key: str
    language: str = "es"

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Team Transfers Simulator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static assets mount — added at the bottom of the file to avoid
# conflicting with frontend/dist when the React build is present.
ASSETS_DIR = ROOT_DIR / "assets"

# In-memory cache for preloaded simulators
_sim_cache: Dict[str, Any] = {}
_last_result: Optional[Any] = None
# Cache horizon-extrapolated predicted values: key = "season|horizon"
_xgrowth_horizon_cache: Dict[str, Dict[str, float]] = {}


def _player_to_out(p) -> PlayerOut:
    return PlayerOut(
        player_id=p.player_id,
        name=p.name,
        team=p.team or "",
        team_id=p.team_id or "",
        position=p.position or "N/A",
        age=p.age,
        nationality=p.nationality or "",
        market_value=p.market_value,
        predicted_value=p.predicted_value,
        fair_price=round(_compute_fair_price(p), 0),
        img_url=p.img_url or "",
        on_loan=p.on_loan or False,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/seasons")
def get_seasons() -> List[str]:
    seasons: set[str] = set()
    for base in list_json_bases("teams_all_*.json"):
        s = base.replace("teams_all_", "")
        if s:
            seasons.add(s)
    # Also include seasons that have precomputed caches (e.g. future seasons)
    cache_dir = ROOT_DIR / "data" / "json" / "cache"
    if cache_dir.exists():
        for f in cache_dir.glob("season_data_*.json"):
            s = f.stem.replace("season_data_", "")
            if s and s != "today":
                seasons.add(s)
    return sorted(seasons, reverse=True)


@app.get("/api/clubs")
def get_clubs(season: str) -> List[ClubOut]:
    if season.lower() == TODAY_SEASON:
        bases = list_json_bases("teams_all_*.json")
        base = bases[-1] if bases else None
    else:
        base = f"teams_all_{season}"

    if base is None:
        return []
    data = load_json(base)
    # Fallback to latest available teams file (for future seasons without own data)
    if data is None or not isinstance(data, list):
        bases = list_json_bases("teams_all_*.json")
        base = bases[-1] if bases else None
        if base is None:
            return []
        data = load_json(base)
    if data is None or not isinstance(data, list):
        return []

    data.sort(key=lambda c: (
        LEAGUE_PRIORITY.get((c.get("league") or "").lower(), 99),
        -(c.get("total_market_value") or 0),
    ))

    return [
        ClubOut(
            name=c.get("name", ""),
            league=c.get("league", ""),
            logo_url=c.get("logo_url", ""),
            total_market_value=c.get("total_market_value"),
        )
        for c in data
        if c.get("name")
    ]


class LeagueOut(BaseModel):
    league_id: str
    name: str
    country: str = ""


@app.get("/api/leagues")
def get_leagues(season: str) -> List[LeagueOut]:
    """Return distinct leagues available for a season (from teams data)."""
    if season.lower() == TODAY_SEASON:
        bases = list_json_bases("teams_all_*.json")
        base = bases[-1] if bases else None
    else:
        base = f"teams_all_{season}"

    if base is None:
        return []
    data = load_json(base)
    if data is None or not isinstance(data, list):
        bases = list_json_bases("teams_all_*.json")
        base = bases[-1] if bases else None
        if base is None:
            return []
        data = load_json(base)
    if data is None or not isinstance(data, list):
        return []

    seen: Dict[str, LeagueOut] = {}
    for team in data:
        lid = team.get("league_id", "") or ""
        if lid and lid not in seen:
            seen[lid] = LeagueOut(
                league_id=lid,
                name=team.get("league", "") or lid,
                country=team.get("country", ""),
            )
    result = sorted(seen.values(), key=lambda l: l.name)
    return result


@app.get("/api/nationalities")
def get_nationalities() -> List[str]:
    """Return distinct nationalities across all cached simulators' player pools."""
    nats: set = set()
    for sim in _sim_cache.values():
        for p in sim.all_players:
            if p.nationality:
                nats.add(p.nationality)
            for n in (p.other_nationalities or []):
                if n:
                    nats.add(n)
    return sorted(nats)


@app.post("/api/load-squad")
def load_squad(req: LoadSquadRequest) -> List[PlayerOut]:
    from simulator.transfer_simulator import TransferSimulator

    cache_key = f"{req.club_name}|{req.season}"
    sim = TransferSimulator(
        club_name=req.club_name,
        season=req.season,
        transfer_budget=0,
    )
    try:
        squad = sim.preload_data(verbose=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _sim_cache[cache_key] = sim
    _xgrowth_horizon_cache.clear()
    return [_player_to_out(p) for p in squad]


@app.get("/api/sell-recommendations")
def sell_recommendations(club_name: str, season: str) -> SellRecommendationsOut:
    """Return sale recommendations for the loaded squad."""
    cache_key = f"{club_name}|{season}"
    sim = _sim_cache.get(cache_key)
    if sim is None:
        raise HTTPException(status_code=400, detail="Load squad first")

    squad = sim.club_players
    peak: List[SellRecommendation] = []
    for p in squad:
        mv = p.market_value or 0
        pv = getattr(p, "predicted_value", None)
        if pv is None or mv <= 0 or p.on_loan:
            continue
        delta = mv - pv
        peak.append(SellRecommendation(
            player_id=p.player_id,
            name=p.name,
            position=p.position or "N/A",
            age=p.age,
            market_value=mv,
            predicted_value=pv,
            fair_price=round(_compute_fair_price(p), 0),
            decline=delta,
            decline_pct=delta / mv if mv else 0,
            img_url=p.img_url or "",
        ))
    peak.sort(key=lambda r: r.decline, reverse=True)
    return SellRecommendationsOut(peak_players=peak)


def _compute_xgrowth(p) -> float:
    mv = p.market_value or 1
    pv = p.predicted_value or mv
    return (pv / mv) - 1 if mv > 0 else 0.0


def _compute_fair_price(p) -> float:
    """Fair price = previous season's model prediction, stored in p.fair_price."""
    return getattr(p, "fair_price", None) or p.predicted_value or p.market_value or 0


def _player_similarity(a, b) -> float:
    """0-1 financial similarity score between two players."""
    if (a.position or "") != (b.position or ""):
        return 0.0
    mv_a, mv_b = a.market_value or 1, b.market_value or 1
    age_a, age_b = a.age or 25, b.age or 25
    xg_a = ((a.predicted_value or mv_a) / mv_a) - 1 if mv_a > 0 else 0
    xg_b = ((b.predicted_value or mv_b) / mv_b) - 1 if mv_b > 0 else 0
    val_sim = 1 - min(abs(mv_a - mv_b) / max(mv_a, mv_b), 1)
    age_sim = 1 - min(abs(age_a - age_b) / 10, 1)
    xg_sim = 1 - min(abs(xg_a - xg_b) / max(abs(xg_a) + 0.01, abs(xg_b) + 0.01), 1)
    return 0.35 * val_sim + 0.25 * age_sim + 0.40 * xg_sim


@app.get("/api/analytics")
def get_analytics(club_name: str, season: str) -> AnalyticsOut:
    """Return xGrowth ranking and signing analysis with similar players."""
    cache_key = f"{club_name}|{season}"
    sim = _sim_cache.get(cache_key)
    if sim is None:
        raise HTTPException(status_code=400, detail="Load squad first")

    all_players = sim.all_players
    signings = _last_result.recommended_signings if _last_result else []
    signing_ids = {p.player_id for p in signings}
    club_ids = {p.player_id for p in sim.club_players}

    # xGrowth ranking: top players by growth potential from the full pool
    pool = [
        p for p in all_players
        if p.predicted_value is not None
        and (p.market_value or 0) > 0
        and not p.on_loan
        and p.player_id not in club_ids
    ]
    pool.sort(key=lambda p: _compute_xgrowth(p), reverse=True)
    xgrowth_ranking = [
        XGrowthPlayer(
            player_id=p.player_id,
            name=p.name,
            position=p.position or "N/A",
            age=p.age,
            team=p.team or "",
            market_value=p.market_value or 0,
            predicted_value=p.predicted_value or 0,
            xgrowth=round(_compute_xgrowth(p), 4),
            fair_price=round(_compute_fair_price(p), 0),
            img_url=p.img_url or "",
        )
        for p in pool[:30]
    ]

    # Signing analysis: for each recommended signing, find similar players
    signing_analysis = []
    for s in signings:
        candidates = [
            p for p in pool
            if p.player_id != s.player_id
            and p.player_id not in signing_ids
            and (p.position or "") == (s.position or "")
        ]
        scored = [(p, _player_similarity(s, p)) for p in candidates]
        scored.sort(key=lambda t: t[1], reverse=True)
        similar = [
            SimilarPlayerOut(
                player_id=p.player_id,
                name=p.name,
                position=p.position or "N/A",
                age=p.age,
                team=p.team or "",
                market_value=p.market_value or 0,
                predicted_value=p.predicted_value or 0,
                xgrowth=round(_compute_xgrowth(p), 4),
                fair_price=round(_compute_fair_price(p), 0),
                similarity=round(sim_score, 3),
                img_url=p.img_url or "",
            )
            for p, sim_score in scored[:5]
        ]
        signing_analysis.append(PlayerAnalysisOut(
            player_id=s.player_id,
            name=s.name,
            position=s.position or "N/A",
            age=s.age,
            team=s.team or "",
            market_value=s.market_value or 0,
            predicted_value=s.predicted_value or 0,
            xgrowth=round(_compute_xgrowth(s), 4),
            fair_price=round(_compute_fair_price(s), 0),
            similar_players=similar,
            img_url=s.img_url or "",
        ))

    return AnalyticsOut(
        xgrowth_ranking=xgrowth_ranking,
        signing_analysis=signing_analysis,
    )


class XGrowthRanges(BaseModel):
    age: List[int] = [0, 50]
    market_value: List[float] = [0, 0]
    predicted_value: List[float] = [0, 0]
    fair_price: List[float] = [0, 0]
    xgrowth: List[float] = [0, 0]
    net_benefit: List[float] = [0, 0]
    roi: List[float] = [0, 0]
    growth_pct: List[float] = [0, 0]

class XGrowthResults(BaseModel):
    players: List[XGrowthPlayer]
    total: int
    ranges: XGrowthRanges = XGrowthRanges()


def _get_horizon_pv(sim, season: str, horizon: int) -> Dict[str, float]:
    """Return {player_id: extrapolated_predicted_value} for given horizon.

    Caches results so repeated xGrowth requests with the same season+horizon
    don't recompute.
    """
    cache_key = f"{season}|{horizon}"
    if cache_key in _xgrowth_horizon_cache:
        return _xgrowth_horizon_cache[cache_key]

    from ml.value_predictor import clamp_prediction

    mapping: Dict[str, float] = {}
    for p in sim.all_players:
        pv_raw = p.predicted_value
        mv = p.market_value or 0
        if pv_raw is None or mv <= 0:
            continue
        if horizon <= 1:
            mapping[p.player_id] = pv_raw
        else:
            annual_ratio = pv_raw / mv if mv > 0 else 1.0
            current = mv
            for _ in range(horizon):
                projected = current * annual_ratio
                current = clamp_prediction(projected, current)
            mapping[p.player_id] = current

    _xgrowth_horizon_cache[cache_key] = mapping
    return mapping


@app.get("/api/xgrowth")
def get_xgrowth(
    season: str = "",
    position: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    club_name: Optional[str] = None,
    horizon: int = 1,
    league_filter: Optional[str] = None,
    exclude_top_n: int = 0,
    min_market_value: Optional[float] = None,
    sort_by: str = "xgrowth",
    limit: int = 50,
    # Slider filters (applied after range computation)
    f_age_min: Optional[int] = None,
    f_age_max: Optional[int] = None,
    f_mv_min: Optional[float] = None,
    f_mv_max: Optional[float] = None,
    f_pv_min: Optional[float] = None,
    f_pv_max: Optional[float] = None,
    f_fp_min: Optional[float] = None,
    f_fp_max: Optional[float] = None,
    f_xg_min: Optional[float] = None,
    f_nb_min: Optional[float] = None,
    f_roi_min: Optional[float] = None,
    f_gp_min: Optional[float] = None,
    team_query: Optional[str] = None,
    nationality_filter: Optional[str] = None,
    include_second_nationality: bool = False,
) -> XGrowthResults:
    """Top players by projected xGrowth with advanced filters."""
    sim = None
    for k, v in _sim_cache.items():
        if season and season in k:
            sim = v
            break
    if sim is None:
        for k, v in _sim_cache.items():
            sim = v
            break
    if sim is None:
        raise HTTPException(status_code=400, detail="Load squad first")

    # Club availability filter
    available_set: Optional[set] = None
    if club_name:
        target_key = f"{club_name}|{season}" if season else None
        target_sim = _sim_cache.get(target_key) if target_key else None
        if target_sim is None:
            target_sim = sim
        available_set = {
            p.player_id
            for p in target_sim._get_available_players(
                target_sim.all_players,
                target_sim.club_players,
                is_athletic=getattr(target_sim, "_is_athletic", False),
                athletic_eligible_ids=getattr(target_sim, "_athletic_eligible_ids", None),
            )
        }

    # League filter set
    league_set: Optional[set] = None
    if league_filter:
        league_set = {lid.strip() for lid in league_filter.split(",") if lid.strip()}

    # Nationality filter set
    nat_set: Optional[set] = None
    if nationality_filter:
        nat_set = {n.strip() for n in nationality_filter.split(",") if n.strip()}

    # Exclude top N clubs by market value
    excluded_clubs: Optional[set] = None
    if exclude_top_n > 0 and hasattr(sim, "team_market_values") and sim.team_market_values:
        sorted_teams = sorted(
            sim.team_market_values.items(), key=lambda kv: kv[1], reverse=True,
        )
        excluded_clubs = {name.lower() for name, _ in sorted_teams[:exclude_top_n]}

    # Team league mapping for league filtering
    team_league_map = None
    if league_set:
        from ml.feature_engineering import load_team_league_mapping
        team_league_map = load_team_league_mapping()

    # Horizon-extrapolated predicted values
    horizon_pv = _get_horizon_pv(sim, season, horizon)

    club_ids = {p.player_id for p in sim.club_players}
    min_mv_euros = (min_market_value or 0) * 1_000_000

    pool = []
    for p in sim.all_players:
        if p.player_id not in horizon_pv:
            continue
        if (p.market_value or 0) <= 0 or p.on_loan:
            continue
        if p.player_id in club_ids:
            continue
        if available_set is not None and p.player_id not in available_set:
            continue

        mv = p.market_value or 0

        if min_mv_euros and mv < min_mv_euros:
            continue
        if position and (p.position or "") != position:
            continue
        if min_value is not None and mv < min_value * 1_000_000:
            continue
        if max_value is not None and mv > max_value * 1_000_000:
            continue

        age = p.age or 0
        if min_age is not None and age < min_age:
            continue
        if max_age is not None and age > max_age:
            continue

        if excluded_clubs and (p.team or "").lower() in excluded_clubs:
            continue

        if league_set and team_league_map:
            player_league = (
                team_league_map
                .get((p.team_id or "").strip(), {})
                .get(sim.season, {})
                .get("league_id", "")
            )
            if player_league not in league_set:
                continue

        if nat_set:
            matched = (p.nationality or "") in nat_set
            if not matched and include_second_nationality:
                matched = any(n in nat_set for n in (p.other_nationalities or []))
            if not matched:
                continue

        pool.append(p)

    def _metrics(p):
        mv = p.market_value or 0
        pv = horizon_pv.get(p.player_id, p.predicted_value or mv)
        if mv > 0:
            xg = (pv / mv) - 1
            roi = (pv - mv) / mv
            gp = pv / mv
        else:
            xg = 9999.0 if pv > 0 else 0.0
            roi = 9999.0 if pv > 0 else 0.0
            gp = 9999.0 if pv > 0 else 0.0
        nb = pv - mv
        return pv, xg, nb, roi, gp

    sort_keys = {
        "xgrowth": lambda p: _metrics(p)[1],
        "predicted_value": lambda p: _metrics(p)[0],
        "net_benefit": lambda p: _metrics(p)[2],
        "roi": lambda p: _metrics(p)[3],
        "growth_pct": lambda p: _metrics(p)[4],
        "market_value": lambda p: p.market_value or 0,
    }
    key_fn = sort_keys.get(sort_by, sort_keys["xgrowth"])
    pool.sort(key=key_fn, reverse=True)

    # Compute ranges from the full pool before applying limit
    ranges = XGrowthRanges()
    if pool:
        ages = [p.age for p in pool if p.age]
        mvs = [p.market_value or 0 for p in pool]
        all_metrics = [_metrics(p) for p in pool]
        pvs = [m[0] for m in all_metrics]
        xgs = [m[1] for m in all_metrics]
        nbs = [m[2] for m in all_metrics]
        rois = [m[3] for m in all_metrics]
        gps = [m[4] for m in all_metrics]
        fps = [_compute_fair_price(p) for p in pool]
        ranges = XGrowthRanges(
            age=[min(ages) if ages else 15, max(ages) if ages else 45],
            market_value=[min(mvs), max(mvs)],
            predicted_value=[min(pvs), max(pvs)],
            fair_price=[min(fps), max(fps)],
            xgrowth=[round(min(xgs), 4), round(max(xgs), 4)],
            net_benefit=[round(min(nbs), 0), round(max(nbs), 0)],
            roi=[round(min(rois), 4), round(max(rois), 4)],
            growth_pct=[round(min(gps), 4), round(max(gps), 4)],
        )

    # Apply slider filters (after ranges, so ranges stay stable)
    tq = (team_query or "").lower().strip()
    filtered = []
    for p in pool:
        pv, xg, nb, roi_v, gp_v = _metrics(p)
        fp = _compute_fair_price(p)
        age = p.age or 0
        mv = p.market_value or 0
        if position and (p.position or "") != position:
            continue
        if tq and tq not in (p.team or "").lower():
            continue
        if f_age_min is not None and age < f_age_min:
            continue
        if f_age_max is not None and age > f_age_max:
            continue
        if f_mv_min is not None and mv < f_mv_min:
            continue
        if f_mv_max is not None and mv > f_mv_max:
            continue
        if f_pv_min is not None and pv < f_pv_min:
            continue
        if f_pv_max is not None and pv > f_pv_max:
            continue
        if f_fp_min is not None and fp < f_fp_min:
            continue
        if f_fp_max is not None and fp > f_fp_max:
            continue
        if f_xg_min is not None and xg < f_xg_min:
            continue
        if f_nb_min is not None and nb < f_nb_min:
            continue
        if f_roi_min is not None and roi_v < f_roi_min:
            continue
        if f_gp_min is not None and gp_v < f_gp_min:
            continue
        filtered.append(p)

    total = len(filtered)
    results = []
    for p in filtered[:limit]:
        mv = p.market_value or 1
        pv, xg, nb, roi_v, gp_v = _metrics(p)
        results.append(XGrowthPlayer(
            player_id=p.player_id,
            name=p.name,
            position=p.position or "N/A",
            age=p.age,
            team=p.team or "",
            market_value=p.market_value or 0,
            predicted_value=round(pv, 0),
            xgrowth=round(xg, 4),
            fair_price=round(_compute_fair_price(p), 0),
            net_benefit=round(nb, 0),
            roi=round(roi_v, 4),
            growth_pct=round(gp_v, 4),
            img_url=p.img_url or "",
        ))
    return XGrowthResults(players=results, total=total, ranges=ranges)


@app.get("/api/search-players")
def search_players(
    q: str = "",
    season: str = "",
    position: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    limit: int = 50,
) -> SearchResults:
    """Full-text player search with filters."""
    cache_key = None
    sim = None
    for k, v in _sim_cache.items():
        if season and season in k:
            sim = v
            cache_key = k
            break
    if sim is None:
        for k, v in _sim_cache.items():
            sim = v
            cache_key = k
            break
    if sim is None:
        raise HTTPException(status_code=400, detail="Load squad first")

    query_lower = q.strip().lower()
    results = []
    for p in sim.all_players:
        if query_lower and query_lower not in (p.name or "").lower():
            continue
        if position and (p.position or "") != position:
            continue
        mv = p.market_value or 0
        if min_value is not None and mv < min_value * 1_000_000:
            continue
        if max_value is not None and mv > max_value * 1_000_000:
            continue
        age = p.age or 0
        if min_age is not None and age < min_age:
            continue
        if max_age is not None and age > max_age:
            continue
        pv = p.predicted_value
        xg = None
        fp = round(_compute_fair_price(p), 0)
        if pv is not None and mv > 0:
            xg = round((pv / mv) - 1, 4)
        results.append(SearchPlayerOut(
            player_id=p.player_id,
            name=p.name,
            position=p.position or "N/A",
            age=p.age,
            team=p.team or "",
            nationality=p.nationality or "",
            market_value=mv,
            predicted_value=pv,
            xgrowth=xg,
            fair_price=fp,
            img_url=p.img_url or "",
        ))
    results.sort(key=lambda x: x.market_value, reverse=True)
    total = len(results)
    return SearchResults(players=results[:limit], total=total)


@app.post("/api/simulate")
def simulate(req: SimulateRequest):
    global _last_result
    from simulator.transfer_simulator import TransferSimulator

    cache_key = f"{req.club_name}|{req.season}"
    sim = _sim_cache.get(cache_key)
    if sim is None:
        sim = TransferSimulator(
            club_name=req.club_name,
            season=req.season,
            transfer_budget=req.transfer_budget,
        )
        try:
            sim.preload_data(verbose=False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        _sim_cache[cache_key] = sim

    sim.budget = req.transfer_budget if not req.unlimited else 999_999

    buy_counts = None
    if req.buy_counts:
        if "_formations" in req.buy_counts:
            buy_counts = {"_formations": req.buy_counts["_formations"]}
        else:
            buy_counts = {}
            for pos in ("GK", "DEF", "MID", "ATT"):
                if pos in req.buy_counts:
                    val = req.buy_counts[pos]
                    if isinstance(val, list) and len(val) == 2:
                        buy_counts[pos] = (val[0], val[1])

    try:
        result = sim.run(
            verbose=False,
            generate_summary=False,
            unlimited_budget=req.unlimited,
            players_to_sell=req.players_to_sell or None,
            buy_counts=buy_counts,
            approach=req.approach,
            objective=req.objective,
            sim_speed=req.sim_speed,
            league_filter=req.league_filter,
            banned_clubs=req.banned_clubs,
            banned_players=req.banned_players,
            exclude_top_n=req.exclude_top_n,
            min_market_value=req.min_market_value,
            horizon=req.horizon,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _last_result = result
    return _build_result_dict(result, sim=sim)


def _build_result_dict(result, sim=None) -> dict:
    """Serialize a TransferResult into the same shape as SimulationResultOut."""
    sold_out = []
    for sp in result.players_sold:
        p = sp.player
        sold_out.append({
            "player_id": p.player_id,
            "name": p.name,
            "position": p.position or "N/A",
            "market_value": p.market_value,
            "destination_team": sp.destination_team,
            "was_sold": sp.was_sold,
            "img_url": p.img_url or "",
        })

    signing_ids = {p.player_id for p in result.recommended_signings}
    signings_out = []
    for p in result.recommended_signings:
        out = _player_to_out(p).model_dump()
        if sim is not None:
            try:
                alts = sim.get_alternatives(p, exclude_ids=signing_ids, n=5)
                out["alternatives"] = [_player_to_out(a).model_dump() for a in alts]
            except Exception as exc:
                print(f"[WARN] Failed to compute alternatives for {p.name}: {exc}")
                out["alternatives"] = []
        else:
            out["alternatives"] = []
        signings_out.append(out)

    return {
        "club_name": result.club_name,
        "season": result.season,
        "initial_budget": result.initial_budget,
        "sales_revenue": result.sales_revenue,
        "total_budget": result.total_budget,
        "players_sold": sold_out,
        "formation_needed": result.formation_needed,
        "recommended_signings": signings_out,
        "recommended_formation": result.recommended_formation,
        "total_signing_cost": result.total_signing_cost,
        "total_predicted_value": result.total_predicted_value,
    }


@app.post("/api/simulate-stream")
def simulate_stream(req: SimulateRequest):
    """SSE endpoint: streams progress events, then the final result."""
    global _last_result
    from simulator.transfer_simulator import TransferSimulator

    q: queue.Queue = queue.Queue()

    def _run():
        try:
            cache_key = f"{req.club_name}|{req.season}"
            sim = _sim_cache.get(cache_key)
            if sim is None:
                sim = TransferSimulator(
                    club_name=req.club_name,
                    season=req.season,
                    transfer_budget=req.transfer_budget,
                )
                sim.preload_data(verbose=False)
                _sim_cache[cache_key] = sim

            sim.budget = req.transfer_budget if not req.unlimited else 999_999

            buy_counts = None
            if req.buy_counts:
                if "_formations" in req.buy_counts:
                    buy_counts = {"_formations": req.buy_counts["_formations"]}
                else:
                    buy_counts = {}
                    for pos in ("GK", "DEF", "MID", "ATT"):
                        if pos in req.buy_counts:
                            val = req.buy_counts[pos]
                            if isinstance(val, list) and len(val) == 2:
                                buy_counts[pos] = (val[0], val[1])

            def on_progress(pct: float, step_key: str):
                q.put({"type": "progress", "percent": round(pct * 100), "step": step_key})

            result = sim.run(
                verbose=False,
                generate_summary=False,
                progress_callback=on_progress,
                unlimited_budget=req.unlimited,
                players_to_sell=req.players_to_sell or None,
                buy_counts=buy_counts,
                approach=req.approach,
                objective=req.objective,
                sim_speed=req.sim_speed,
                league_filter=req.league_filter,
                banned_clubs=req.banned_clubs,
                banned_players=req.banned_players,
                exclude_top_n=req.exclude_top_n,
                min_market_value=req.min_market_value,
                horizon=req.horizon,
            )
            _last_result = result
            q.put({"type": "result", "data": _build_result_dict(result, sim=sim)})
        except Exception as exc:
            q.put({"type": "error", "detail": str(exc)})
        finally:
            q.put(None)

    threading.Thread(target=_run, daemon=True).start()

    def _event_stream():
        while True:
            msg = q.get()
            if msg is None:
                break
            yield f"data: {_json.dumps(msg)}\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@app.post("/api/ai-summary")
def ai_summary(req: AISummaryRequest) -> Dict[str, str]:
    if _last_result is None:
        raise HTTPException(status_code=400, detail="No simulation result available")

    k = (req.api_key or "").strip()
    if k.startswith("sk-ant-"):
        provider = "anthropic"
    elif k.startswith("sk-"):
        provider = "openai"
    else:
        provider = "gemini"

    summary = _last_result.generate_llm_summary(
        provider=provider,
        api_key=req.api_key,
        language=req.language,
    )
    if not summary:
        raise HTTPException(status_code=500, detail="Failed to generate summary")

    return {"summary": summary}


# Serve compiled frontend (production) or fall back to root assets
_FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
elif ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
