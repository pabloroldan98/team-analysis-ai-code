import { useState } from "react";
import type { Lang, Player, Club, BuyMode, Approach, BuyCounts } from "../types";
import { t, formatCurrency, POS_ORDER, POS_KEYS } from "../i18n";

/* ── helpers ────────────────────────────────────────────────────────────── */

function totalCombinations(total: number, maxPerPos = 3): number[][] {
  const combos: number[][] = [];
  for (let gk = 0; gk <= Math.min(total, maxPerPos); gk++)
    for (let df = 0; df <= Math.min(total - gk, maxPerPos); df++)
      for (let mid = 0; mid <= Math.min(total - gk - df, maxPerPos); mid++) {
        const att = total - gk - df - mid;
        if (att >= 0 && att <= maxPerPos) combos.push([gk, df, mid, att]);
      }
  return combos;
}

const APPROACHES: Approach[] = ["max_value", "young_talents", "max_profit", "balanced"];

/* ── sub-components ─────────────────────────────────────────────────────── */

function SeasonClubSelector({
  lang, seasons, clubs, season, clubName,
  onSeasonChange, onClubChange,
}: {
  lang: Lang; seasons: string[]; clubs: Club[];
  season: string; clubName: string;
  onSeasonChange: (s: string) => void; onClubChange: (c: string) => void;
}) {
  const todayLabel = t(lang, "today_option");
  return (
    <div className="grid grid-cols-2 gap-4">
      <div>
        <label className="block text-sm font-medium mb-1">{t(lang, "select_season")}</label>
        <select
          className="input-field"
          value={season}
          onChange={(e) => onSeasonChange(e.target.value)}
        >
          <option value="today">{todayLabel}</option>
          {seasons.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">{t(lang, "select_club")}</label>
        <select
          className="input-field"
          value={clubName}
          onChange={(e) => onClubChange(e.target.value)}
        >
          {clubs.map((c) => (
            <option key={c.name} value={c.name}>{c.name}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

function SellSelection({
  lang, squad, selected, onChange,
}: {
  lang: Lang; squad: Player[]; selected: string[]; onChange: (ids: string[]) => void;
}) {
  const byPos: Record<string, Player[]> = {};
  for (const pos of POS_ORDER) byPos[pos] = [];
  for (const p of squad) {
    const pos = POS_ORDER.includes(p.position as any) ? p.position : "DEF";
    byPos[pos].push(p);
  }
  for (const pos of POS_ORDER)
    byPos[pos].sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0));

  const toggle = (id: string) => {
    onChange(
      selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]
    );
  };

  return (
    <div>
      <h3 className="section-title">{t(lang, "select_players_to_sell")}</h3>
      <p className="text-xs text-gray-500 mb-3">{t(lang, "sell_selection_help")}</p>
      {POS_ORDER.map((pos) => {
        const players = byPos[pos];
        if (!players.length) return null;
        return (
          <div key={pos} className="mb-3">
            <div className="text-sm font-semibold text-primary-dark mb-1">
              {t(lang, POS_KEYS[pos])}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {players.map((p) => {
                const active = selected.includes(p.player_id);
                return (
                  <button
                    key={p.player_id}
                    onClick={() => toggle(p.player_id)}
                    className={`chip ${active ? "chip-active" : "chip-inactive"}`}
                  >
                    {p.name}
                    <span className="opacity-70 text-[10px]">
                      {formatCurrency(p.market_value)}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function BuyCountsSelector({
  lang, buyMode, setBuyMode, exactCounts, setExactCounts,
  rangeCounts, setRangeCounts, totalCount, setTotalCount,
}: {
  lang: Lang;
  buyMode: BuyMode; setBuyMode: (m: BuyMode) => void;
  exactCounts: Record<string, number>; setExactCounts: (c: Record<string, number>) => void;
  rangeCounts: Record<string, [number, number]>;
  setRangeCounts: (c: Record<string, [number, number]>) => void;
  totalCount: number; setTotalCount: (n: number) => void;
}) {
  return (
    <div>
      <h3 className="section-title">{t(lang, "signings_per_position")}</h3>
      <div className="flex gap-2 mb-3">
        {(["exact", "range", "total"] as BuyMode[]).map((m) => (
          <button
            key={m}
            onClick={() => setBuyMode(m)}
            className={`chip ${buyMode === m ? "chip-active" : "chip-inactive"}`}
          >
            {t(lang, `buy_mode_${m}`)}
          </button>
        ))}
      </div>

      {buyMode === "exact" && (
        <>
          <p className="text-xs text-gray-500 mb-2">{t(lang, "signings_exact_help")}</p>
          <div className="grid grid-cols-4 gap-3">
            {POS_ORDER.map((pos) => (
              <div key={pos}>
                <label className="block text-xs font-medium mb-1">
                  {t(lang, POS_KEYS[pos])}
                </label>
                <input
                  type="number" min={0} max={3}
                  value={exactCounts[pos] ?? 1}
                  onChange={(e) =>
                    setExactCounts({ ...exactCounts, [pos]: Number(e.target.value) })
                  }
                  className="input-field"
                />
              </div>
            ))}
          </div>
        </>
      )}

      {buyMode === "range" && (
        <>
          <p className="text-xs text-gray-500 mb-2">{t(lang, "signings_range_help")}</p>
          <div className="grid grid-cols-4 gap-3">
            {POS_ORDER.map((pos) => {
              const [lo, hi] = rangeCounts[pos] ?? [0, 2];
              return (
                <div key={pos}>
                  <div className="text-xs font-semibold mb-1">{t(lang, POS_KEYS[pos])}</div>
                  <input
                    type="number" min={0} max={2} value={lo}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      setRangeCounts({
                        ...rangeCounts,
                        [pos]: [v, Math.max(v, hi)],
                      });
                    }}
                    className="input-field mb-1"
                    placeholder={t(lang, "buy_min")}
                  />
                  <input
                    type="number" min={lo} max={2} value={hi}
                    onChange={(e) =>
                      setRangeCounts({
                        ...rangeCounts,
                        [pos]: [lo, Number(e.target.value)],
                      })
                    }
                    className="input-field"
                    placeholder={t(lang, "buy_max")}
                  />
                </div>
              );
            })}
          </div>
        </>
      )}

      {buyMode === "total" && (
        <>
          <p className="text-xs text-gray-500 mb-2">{t(lang, "signings_total_help")}</p>
          <input
            type="number" min={0} max={10} value={totalCount}
            onChange={(e) => setTotalCount(Number(e.target.value))}
            className="input-field w-40"
          />
          <p className="text-xs text-gray-400 mt-1">
            {totalCombinations(totalCount).length} {lang === "es" ? "combinaciones" : "combinations"}
          </p>
        </>
      )}
    </div>
  );
}

function BudgetInput({
  lang, budget, setBudget, unlimited, setUnlimited,
}: {
  lang: Lang; budget: number; setBudget: (n: number) => void;
  unlimited: boolean; setUnlimited: (b: boolean) => void;
}) {
  return (
    <div>
      <h3 className="section-title">{t(lang, "budget_title")}</h3>
      <p className="text-xs text-gray-500 mb-2">{t(lang, "budget_extra_note")}</p>
      <div className="flex items-end gap-4">
        <div className="flex-1">
          <input
            type="number" min={-2000} max={2000} step={10}
            value={budget} disabled={unlimited}
            onChange={(e) => setBudget(Number(e.target.value))}
            className="input-field"
          />
        </div>
        <label className="flex items-center gap-2 pb-1 cursor-pointer select-none">
          <input
            type="checkbox" checked={unlimited}
            onChange={(e) => setUnlimited(e.target.checked)}
            className="w-4 h-4 accent-primary rounded"
          />
          <span className="text-sm">{t(lang, "unlimited_budget")}</span>
        </label>
      </div>
    </div>
  );
}

function ApproachSelector({
  lang, approach, setApproach,
}: {
  lang: Lang; approach: Approach; setApproach: (a: Approach) => void;
}) {
  return (
    <div>
      <h3 className="section-title">{t(lang, "approach_title")}</h3>
      <div className="flex flex-wrap gap-2 mb-2">
        {APPROACHES.map((a) => (
          <button
            key={a}
            onClick={() => setApproach(a)}
            className={`chip ${approach === a ? "chip-active" : "chip-inactive"}`}
          >
            {t(lang, `approach_${a}`)}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-500">{t(lang, `approach_${approach}_help`)}</p>
    </div>
  );
}

/* ── main export ────────────────────────────────────────────────────────── */

export interface ConfigState {
  season: string;
  clubName: string;
  playersToSell: string[];
  buyCounts: BuyCounts | null;
  transferBudget: number;
  unlimited: boolean;
  approach: Approach;
}

interface Props {
  lang: Lang;
  seasons: string[];
  clubs: Club[];
  squad: Player[] | null;
  loadingSquad: boolean;
  onSeasonChange: (s: string) => void;
  onClubChange: (c: string) => void;
  onLoadSquad: () => void;
  onSimulate: (cfg: ConfigState) => void;
  simulating: boolean;
  season: string;
  clubName: string;
}

export default function ConfigPanel({
  lang, seasons, clubs, squad, loadingSquad,
  onSeasonChange, onClubChange, onLoadSquad, onSimulate, simulating,
  season, clubName,
}: Props) {
  const [playersToSell, setPlayersToSell] = useState<string[]>([]);
  const [buyMode, setBuyMode] = useState<BuyMode>("exact");
  const [exactCounts, setExactCounts] = useState<Record<string, number>>(
    { GK: 1, DEF: 1, MID: 1, ATT: 1 }
  );
  const [rangeCounts, setRangeCounts] = useState<Record<string, [number, number]>>(
    { GK: [0, 2], DEF: [0, 2], MID: [0, 2], ATT: [0, 2] }
  );
  const [totalCount, setTotalCount] = useState(5);
  const [budget, setBudget] = useState(0);
  const [unlimited, setUnlimited] = useState(false);
  const [approach, setApproach] = useState<Approach>("max_value");

  const buildBuyCounts = (): BuyCounts | null => {
    if (buyMode === "exact") {
      const bc: BuyCounts = {};
      for (const pos of POS_ORDER) {
        const n = exactCounts[pos] ?? 1;
        bc[pos] = [n, n];
      }
      return bc;
    }
    if (buyMode === "range") {
      const bc: BuyCounts = {};
      for (const pos of POS_ORDER) bc[pos] = rangeCounts[pos] ?? [0, 2];
      return bc;
    }
    return { _formations: totalCombinations(totalCount) };
  };

  const handleSimulate = () => {
    onSimulate({
      season,
      clubName,
      playersToSell,
      buyCounts: buildBuyCounts(),
      transferBudget: budget,
      unlimited,
      approach,
    });
  };

  return (
    <div className="card space-y-6">
      <SeasonClubSelector
        lang={lang} seasons={seasons} clubs={clubs}
        season={season} clubName={clubName}
        onSeasonChange={onSeasonChange} onClubChange={onClubChange}
      />

      <button
        onClick={onLoadSquad}
        disabled={loadingSquad || !clubName}
        className="btn-secondary"
      >
        {loadingSquad ? t(lang, "loading_data") : t(lang, "load_data")}
      </button>

      {!squad && !loadingSquad && (
        <p className="text-xs text-gray-400">{t(lang, "load_data_hint")}</p>
      )}

      {squad && (
        <>
          <div className="bg-primary-light text-primary-dark text-sm font-medium px-4 py-2 rounded-lg">
            {t(lang, "data_loaded")} — {t(lang, "squad_loaded", { count: squad.length })}
          </div>

          <SellSelection
            lang={lang} squad={squad}
            selected={playersToSell} onChange={setPlayersToSell}
          />

          <BuyCountsSelector
            lang={lang}
            buyMode={buyMode} setBuyMode={setBuyMode}
            exactCounts={exactCounts} setExactCounts={setExactCounts}
            rangeCounts={rangeCounts} setRangeCounts={setRangeCounts}
            totalCount={totalCount} setTotalCount={setTotalCount}
          />

          <BudgetInput
            lang={lang} budget={budget} setBudget={setBudget}
            unlimited={unlimited} setUnlimited={setUnlimited}
          />

          <ApproachSelector
            lang={lang} approach={approach} setApproach={setApproach}
          />

          <button
            onClick={handleSimulate}
            disabled={simulating}
            className="btn-primary text-lg py-3"
          >
            {simulating ? t(lang, "simulating") : t(lang, "run_simulation")}
          </button>

          {simulating && (
            <p className="text-xs text-gray-400 text-center animate-pulse">
              {t(lang, "sim_may_take")}
            </p>
          )}
        </>
      )}
    </div>
  );
}
