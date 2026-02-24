import type { Club, Player, SimulationResult, BuyCounts, Approach } from "./types";

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

  loadSquad: (clubName: string, season: string) =>
    json<Player[]>("/api/load-squad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ club_name: clubName, season }),
    }),

  /** Synchronous simulate (no progress). */
  simulate: (params: {
    clubName: string;
    season: string;
    transferBudget: number;
    unlimited: boolean;
    playersToSell: string[];
    buyCounts: BuyCounts | null;
    approach: Approach;
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

  aiSummary: (apiKey: string, language: string) =>
    json<{ summary: string }>("/api/ai-summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, language }),
    }),
};
