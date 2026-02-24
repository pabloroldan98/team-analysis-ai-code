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
