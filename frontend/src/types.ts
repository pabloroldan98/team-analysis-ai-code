export type Lang = "es" | "en";

export interface Club {
  name: string;
  league: string;
  logo_url: string;
  total_market_value: number | null;
}

export interface Player {
  player_id: string;
  name: string;
  team: string;
  team_id: string;
  position: string;
  age: number | null;
  nationality: string;
  market_value: number | null;
  predicted_value: number | null;
  img_url: string;
  on_loan: boolean;
}

export interface SoldPlayer {
  player_id: string;
  name: string;
  position: string;
  market_value: number | null;
  destination_team: string | null;
  was_sold: boolean;
  img_url: string;
}

export interface SimulationResult {
  club_name: string;
  season: string;
  initial_budget: number;
  sales_revenue: number;
  total_budget: number;
  players_sold: SoldPlayer[];
  formation_needed: number[];
  recommended_signings: Player[];
  recommended_formation: number[];
  total_signing_cost: number;
  total_predicted_value: number;
}

export type BuyMode = "exact" | "range" | "total";
export type Approach = "max_value" | "young_talents" | "max_profit" | "balanced";

export interface BuyCounts {
  [key: string]: [number, number] | number[][] | undefined;
  _formations?: number[][];
}
