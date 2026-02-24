import { useState } from "react";
import type { Lang, SimulationResult, Club, Player } from "../types";
import { t, formatCurrency, POS_ORDER, POS_KEYS } from "../i18n";
import PlayerCard from "./PlayerCard";
import { api } from "../api";

/* ── MetricCard ─────────────────────────────────────────────────────────── */

function MetricCard({
  label, value, delta, deltaPositive,
}: {
  label: string; value: string; delta?: string; deltaPositive?: boolean;
}) {
  return (
    <div className="metric-card">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-xl font-bold text-primary-dark">{value}</div>
      {delta && (
        <div
          className={`text-sm font-semibold mt-0.5 ${
            deltaPositive ? "text-green-600" : "text-red-600"
          }`}
        >
          {delta}
        </div>
      )}
    </div>
  );
}

/* ── FinalSquad ─────────────────────────────────────────────────────────── */

function FinalSquad({
  lang, currentSquad, sold, signings,
}: {
  lang: Lang; currentSquad: Player[]; sold: string[]; signings: Player[];
}) {
  const soldSet = new Set(sold);
  const newIds = new Set(signings.map((p) => p.player_id));
  const remaining = currentSquad.filter((p) => !soldSet.has(p.player_id));
  const all = [...remaining, ...signings];

  const byPos: Record<string, Player[]> = {};
  for (const pos of POS_ORDER) byPos[pos] = [];
  for (const p of all) {
    const pos = POS_ORDER.includes(p.position as any) ? p.position : "DEF";
    byPos[pos].push(p);
  }
  for (const pos of POS_ORDER)
    byPos[pos].sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0));

  return (
    <div>
      {POS_ORDER.map((pos) => {
        const players = byPos[pos];
        if (!players.length) return null;
        return (
          <div key={pos} className="mb-4">
            <div className="font-semibold text-sm text-primary-dark mb-2">
              {t(lang, POS_KEYS[pos])} ({players.length})
            </div>
            <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
              {players.map((p) => {
                const isNew = newIds.has(p.player_id);
                return (
                  <div
                    key={p.player_id}
                    className={`text-center ${
                      isNew ? "border-l-[3px] border-green-500 pl-1.5" : ""
                    }`}
                  >
                    {p.img_url ? (
                      <img
                        src={p.img_url}
                        alt={p.name}
                        className="w-12 h-12 rounded-full object-cover mx-auto bg-gray-200"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = "none";
                        }}
                      />
                    ) : (
                      <div className="w-12 h-12 rounded-full bg-gray-200 mx-auto" />
                    )}
                    <div className="text-xs mt-1 leading-tight">
                      {p.name}
                      {isNew && (
                        <span className="ml-1 bg-green-500 text-white text-[9px] font-bold px-1 py-px rounded">
                          NEW
                        </span>
                      )}
                    </div>
                    <div className="text-[10px] text-gray-400">
                      {formatCurrency(p.market_value)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ── AIAnalysis ─────────────────────────────────────────────────────────── */

function AIAnalysis({ lang }: { lang: Lang }) {
  const [apiKey, setApiKey] = useState("");
  const [summary, setSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.aiSummary(apiKey, lang);
      setSummary(res.summary);
    } catch {
      setError(t(lang, "ai_error"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h3 className="section-title">{t(lang, "ai_analysis")}</h3>
      {summary ? (
        <div className="prose prose-sm max-w-none whitespace-pre-wrap text-sm text-gray-700">
          {summary}
        </div>
      ) : (
        <>
          <p className="text-xs text-gray-500 mb-1">{t(lang, "no_ai_key")}</p>
          <p className="text-xs text-gray-400 mb-3">{t(lang, "ai_supported_providers")}</p>
          <input
            type="password"
            placeholder={t(lang, "llm_api_key")}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="input-field mb-2"
          />
          <p className="text-[10px] text-gray-400 mb-3">{t(lang, "llm_api_key_help")}</p>
          <button
            onClick={generate}
            disabled={!apiKey || loading}
            className="btn-primary"
          >
            {loading ? t(lang, "generating") : t(lang, "generate_analysis")}
          </button>
          {error && <p className="text-red-500 text-xs mt-2">{error}</p>}
        </>
      )}
    </div>
  );
}

/* ── main export ────────────────────────────────────────────────────────── */

interface Props {
  lang: Lang;
  result: SimulationResult;
  clubs: Club[];
  squad: Player[];
}

export default function ResultsPanel({ lang, result, clubs, squad }: Props) {
  const clubLogo = clubs.find(
    (c) => c.name.toLowerCase() === result.club_name.toLowerCase()
  )?.logo_url;

  const isUnlimited = result.initial_budget >= 999_000;
  const inf = "€∞";

  const actualCost = result.recommended_signings.reduce(
    (s, p) => s + (p.market_value ?? 0), 0
  );
  const actualPredicted = result.recommended_signings.reduce(
    (s, p) => s + (p.predicted_value ?? 0), 0
  );
  const remaining = result.total_budget * 1e6 - actualCost;
  const netBenefit = actualPredicted - actualCost;

  const soldIds = result.players_sold
    .filter((sp) => sp.was_sold)
    .map((sp) => sp.player_id);

  const displaySeason =
    result.season.toLowerCase() === "today" ? t(lang, "today_option") : result.season;

  return (
    <div className="card space-y-6 mt-6 animate-fadeIn">
      {/* Title */}
      <div className="flex items-center gap-3">
        {clubLogo && (
          <img src={clubLogo} alt="" className="w-11 h-11 object-contain" />
        )}
        <h2 className="text-xl font-bold text-primary-dark">
          {t(lang, "simulation_title", { club: result.club_name, season: displaySeason })}
        </h2>
      </div>

      {/* Budget metrics */}
      <div>
        <h3 className="section-title">{t(lang, "budget_section")}</h3>
        <div className="grid grid-cols-3 gap-3">
          <MetricCard
            label={t(lang, "initial_budget")}
            value={isUnlimited ? inf : `€${result.initial_budget}M`}
          />
          <MetricCard
            label={t(lang, "sales_revenue")}
            value={`+€${result.sales_revenue}M`}
          />
          <MetricCard
            label={t(lang, "total_budget")}
            value={isUnlimited ? inf : `€${result.total_budget}M`}
          />
        </div>
      </div>

      {/* Sold / Bought */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Sold */}
        <div>
          <h3 className="section-title">{t(lang, "players_sold")}</h3>
          <p className="text-xs text-gray-400 mb-2">
            {POS_ORDER.map(
              (pos, i) => `${t(lang, POS_KEYS[pos])}: ${result.formation_needed[i]}`
            ).join(", ")}
          </p>
          {result.players_sold.map((sp) => {
            const detail = sp.was_sold
              ? `${t(lang, POS_KEYS[sp.position] || "pos_def")} · ${formatCurrency(sp.market_value)} ${t(lang, "to_team", { team: sp.destination_team ?? "" })}`
              : `${t(lang, POS_KEYS[sp.position] || "pos_def")} · ${formatCurrency(sp.market_value)} — ${t(lang, "no_buyer")}`;
            return (
              <PlayerCard
                key={sp.player_id}
                name={sp.name}
                imgUrl={sp.img_url}
                detail={detail}
                variant="sold"
              />
            );
          })}
        </div>

        {/* Bought */}
        <div>
          <h3 className="section-title">{t(lang, "players_bought")}</h3>
          {result.recommended_signings.length === 0 ? (
            <p className="text-sm text-gray-400">{t(lang, "no_signings")}</p>
          ) : (
            <>
              <p className="text-xs text-gray-400 mb-2">
                {POS_ORDER.map((pos) => {
                  const count = result.recommended_signings.filter(
                    (p) => p.position === pos
                  ).length;
                  return `${t(lang, POS_KEYS[pos])}: ${count}`;
                }).join(", ")}
              </p>
              {result.recommended_signings.map((p) => {
                const detail = `${t(lang, POS_KEYS[p.position] || "pos_def")} · ${formatCurrency(p.market_value)} → ${formatCurrency(p.predicted_value)} ${t(lang, "predicted")} · ${t(lang, "from_team", { team: p.team || "?" })}`;
                return (
                  <PlayerCard
                    key={p.player_id}
                    name={p.name}
                    imgUrl={p.img_url}
                    detail={detail}
                    variant="bought"
                  />
                );
              })}
            </>
          )}
        </div>
      </div>

      {/* Financial summary */}
      <div>
        <h3 className="section-title">{t(lang, "market_info")}</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard label={t(lang, "total_cost")} value={formatCurrency(actualCost)} />
          <MetricCard
            label={t(lang, "remaining_budget")}
            value={isUnlimited ? inf : formatCurrency(remaining)}
          />
          <MetricCard
            label={t(lang, "predicted_value_1y")}
            value={formatCurrency(actualPredicted)}
          />
          <MetricCard
            label={t(lang, "net_benefit")}
            value={formatCurrency(netBenefit)}
            delta={
              netBenefit >= 0
                ? `+${formatCurrency(netBenefit)}`
                : `-${formatCurrency(Math.abs(netBenefit))}`
            }
            deltaPositive={netBenefit >= 0}
          />
        </div>
      </div>

      {/* Final squad */}
      <div>
        <h3 className="section-title">{t(lang, "final_squad")}</h3>
        <FinalSquad
          lang={lang}
          currentSquad={squad}
          sold={soldIds}
          signings={result.recommended_signings}
        />
      </div>

      {/* AI Analysis */}
      <hr className="border-gray-200" />
      <AIAnalysis lang={lang} />
    </div>
  );
}
