import type { Club, Player, SimulationResult, BuyCounts, Approach, Objective, SimSpeed, SellRecommendations, League, AdvancedFilters, Analytics, SearchResults } from "./types";

const BASE = "";

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, init);
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail);
  }
  return res.json();
}

export interface ProgressEvent {
  percent: number;
  step: string;
}

export const api = {
  getSeasons: () => json<string[]>("/api/seasons"),

  getClubs: (season: string) =>
    json<Club[]>(`/api/clubs?season=${encodeURIComponent(season)}`),

  getLeagues: (season: string) =>
    json<League[]>(`/api/leagues?season=${encodeURIComponent(season)}`),

  loadSquad: (clubName: string, season: string) =>
    json<Player[]>("/api/load-squad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ club_name: clubName, season }),
    }),

  getSellRecommendations: (clubName: string, season: string) =>
    json<SellRecommendations>(
      `/api/sell-recommendations?club_name=${encodeURIComponent(clubName)}&season=${encodeURIComponent(season)}`
    ),

  /** Synchronous simulate (no progress). */
  simulate: (params: {
    clubName: string;
    season: string;
    transferBudget: number;
    unlimited: boolean;
    playersToSell: string[];
    buyCounts: BuyCounts | null;
    approach: Approach;
    objective: Objective;
    simSpeed: SimSpeed;
    filters: AdvancedFilters;
  }) =>
    json<SimulationResult>("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        club_name: params.clubName,
        season: params.season,
        transfer_budget: params.transferBudget,
        unlimited: params.unlimited,
        players_to_sell: params.playersToSell,
        buy_counts: params.buyCounts,
        approach: params.approach,
        objective: params.objective,
        sim_speed: params.simSpeed,
        league_filter: params.filters.leagueFilter,
        banned_clubs: params.filters.bannedClubs,
        exclude_top_n: params.filters.excludeTopN,
        min_market_value: params.filters.minMarketValue,
        horizon: params.filters.horizon,
      }),
    }),

  /**
   * SSE simulate — streams progress events, then the final result.
   * Inspired by knapsack_football_formations/api.py calculate-stream.
   */
  simulateStream: async (
    params: {
      clubName: string;
      season: string;
      transferBudget: number;
      unlimited: boolean;
      playersToSell: string[];
      buyCounts: BuyCounts | null;
      approach: Approach;
      objective: Objective;
      simSpeed: SimSpeed;
      filters: AdvancedFilters;
    },
    onProgress: (ev: ProgressEvent) => void,
  ): Promise<SimulationResult> => {
    const res = await fetch(`${BASE}/api/simulate-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        club_name: params.clubName,
        season: params.season,
        transfer_budget: params.transferBudget,
        unlimited: params.unlimited,
        players_to_sell: params.playersToSell,
        buy_counts: params.buyCounts,
        approach: params.approach,
        objective: params.objective,
        sim_speed: params.simSpeed,
        league_filter: params.filters.leagueFilter,
        banned_clubs: params.filters.bannedClubs,
        exclude_top_n: params.filters.excludeTopN,
        min_market_value: params.filters.minMarketValue,
        horizon: params.filters.horizon,
      }),
    });

    if (!res.ok) {
      const detail = await res.text().catch(() => res.statusText);
      throw new Error(detail);
    }

    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result: SimulationResult | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;
        const payload = JSON.parse(trimmed.slice(6));

        if (payload.type === "progress") {
          onProgress({ percent: payload.percent, step: payload.step });
        } else if (payload.type === "result") {
          result = payload.data as SimulationResult;
        } else if (payload.type === "error") {
          throw new Error(payload.detail);
        }
      }
    }

    if (!result) throw new Error("No result received from stream");
    return result;
  },

  searchPlayers: (params: {
    q?: string; season?: string; position?: string;
    minValue?: number; maxValue?: number;
    minAge?: number; maxAge?: number; limit?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params.q) sp.set("q", params.q);
    if (params.season) sp.set("season", params.season);
    if (params.position) sp.set("position", params.position);
    if (params.minValue) sp.set("min_value", String(params.minValue));
    if (params.maxValue) sp.set("max_value", String(params.maxValue));
    if (params.minAge) sp.set("min_age", String(params.minAge));
    if (params.maxAge) sp.set("max_age", String(params.maxAge));
    sp.set("limit", String(params.limit ?? 50));
    return json<SearchResults>(`/api/search-players?${sp.toString()}`);
  },

  getAnalytics: (clubName: string, season: string) =>
    json<Analytics>(
      `/api/analytics?club_name=${encodeURIComponent(clubName)}&season=${encodeURIComponent(season)}`
    ),

  aiSummary: (apiKey: string, language: string) =>
    json<{ summary: string }>("/api/ai-summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, language }),
    }),
};
