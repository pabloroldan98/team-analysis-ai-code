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

ASSETS_DIR = ROOT_DIR / "assets"
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

# In-memory cache for preloaded simulators
_sim_cache: Dict[str, Any] = {}
_last_result: Optional[Any] = None


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
        img_url=p.img_url or "",
        on_loan=p.on_loan or False,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/seasons")
def get_seasons() -> List[str]:
    seasons = []
    for base in list_json_bases("teams_all_*.json"):
        s = base.replace("teams_all_", "")
        if s and s not in seasons:
            seasons.append(s)
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
        if delta > 0:
            peak.append(SellRecommendation(
                player_id=p.player_id,
                name=p.name,
                position=p.position or "N/A",
                age=p.age,
                market_value=mv,
                predicted_value=pv,
                decline=delta,
                decline_pct=delta / mv,
                img_url=p.img_url or "",
            ))
    peak.sort(key=lambda r: r.decline, reverse=True)
    return SellRecommendationsOut(peak_players=peak)


def _compute_xgrowth(p) -> float:
    mv = p.market_value or 1
    pv = p.predicted_value or mv
    return (pv / mv) - 1 if mv > 0 else 0.0


def _compute_fair_price(p) -> float:
    """Fair price = predicted_value (break-even point for the buyer)."""
    return p.predicted_value or p.market_value or 0


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
        fp = None
        if pv is not None and mv > 0:
            xg = round((pv / mv) - 1, 4)
            fp = round(pv, 0)
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
def simulate(req: SimulateRequest) -> SimulationResultOut:
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
            exclude_top_n=req.exclude_top_n,
            min_market_value=req.min_market_value,
            horizon=req.horizon,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _last_result = result

    sold_out = []
    for sp in result.players_sold:
        p = sp.player
        sold_out.append(SoldPlayerOut(
            player_id=p.player_id,
            name=p.name,
            position=p.position or "N/A",
            market_value=p.market_value,
            destination_team=sp.destination_team,
            was_sold=sp.was_sold,
            img_url=p.img_url or "",
        ))

    return SimulationResultOut(
        club_name=result.club_name,
        season=result.season,
        initial_budget=result.initial_budget,
        sales_revenue=result.sales_revenue,
        total_budget=result.total_budget,
        players_sold=sold_out,
        formation_needed=result.formation_needed,
        recommended_signings=[_player_to_out(p) for p in result.recommended_signings],
        recommended_formation=result.recommended_formation,
        total_signing_cost=result.total_signing_cost,
        total_predicted_value=result.total_predicted_value,
    )


def _build_result_dict(result) -> dict:
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
    return {
        "club_name": result.club_name,
        "season": result.season,
        "initial_budget": result.initial_budget,
        "sales_revenue": result.sales_revenue,
        "total_budget": result.total_budget,
        "players_sold": sold_out,
        "formation_needed": result.formation_needed,
        "recommended_signings": [_player_to_out(p).model_dump() for p in result.recommended_signings],
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
                exclude_top_n=req.exclude_top_n,
                min_market_value=req.min_market_value,
                horizon=req.horizon,
            )
            _last_result = result
            q.put({"type": "result", "data": _build_result_dict(result)})
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


# Serve compiled frontend (production)
_FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
