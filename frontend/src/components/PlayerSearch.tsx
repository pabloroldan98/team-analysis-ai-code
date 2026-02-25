import { useState, useCallback } from "react";
import type { Lang, SearchPlayer } from "../types";
import { t, formatCurrency, POS_ORDER, POS_KEYS } from "../i18n";
import { api } from "../api";

interface Props {
  lang: Lang;
  season: string;
}

export default function PlayerSearch({ lang, season }: Props) {
  const [query, setQuery] = useState("");
  const [position, setPosition] = useState("");
  const [minValue, setMinValue] = useState("");
  const [maxValue, setMaxValue] = useState("");
  const [minAge, setMinAge] = useState("");
  const [maxAge, setMaxAge] = useState("");
  const [results, setResults] = useState<SearchPlayer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const doSearch = useCallback(async () => {
    setLoading(true);
    setSearched(true);
    try {
      const res = await api.searchPlayers({
        q: query || undefined,
        season: season || undefined,
        position: position || undefined,
        minValue: minValue ? Number(minValue) : undefined,
        maxValue: maxValue ? Number(maxValue) : undefined,
        minAge: minAge ? Number(minAge) : undefined,
        maxAge: maxAge ? Number(maxAge) : undefined,
        limit: 50,
      });
      setResults(res.players);
      setTotal(res.total);
    } catch {
      setResults([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [query, season, position, minValue, maxValue, minAge, maxAge]);

  return (
    <div className="card mt-4">
      <h3 className="section-title">{t(lang, "search_title")}</h3>

      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-2 mb-3">
        <input
          className="input-field col-span-2"
          placeholder={t(lang, "search_placeholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doSearch()}
        />
        <select
          className="input-field"
          value={position}
          onChange={(e) => setPosition(e.target.value)}
        >
          <option value="">{t(lang, "search_position")}</option>
          {POS_ORDER.map((p) => (
            <option key={p} value={p}>{t(lang, POS_KEYS[p])}</option>
          ))}
        </select>
        <input
          className="input-field"
          type="number"
          placeholder={t(lang, "search_min_value")}
          value={minValue}
          onChange={(e) => setMinValue(e.target.value)}
        />
        <input
          className="input-field"
          type="number"
          placeholder={t(lang, "search_max_value")}
          value={maxValue}
          onChange={(e) => setMaxValue(e.target.value)}
        />
        <input
          className="input-field"
          type="number"
          placeholder={t(lang, "search_min_age")}
          value={minAge}
          onChange={(e) => setMinAge(e.target.value)}
        />
        <input
          className="input-field"
          type="number"
          placeholder={t(lang, "search_max_age")}
          value={maxAge}
          onChange={(e) => setMaxAge(e.target.value)}
        />
      </div>

      <button onClick={doSearch} disabled={loading} className="btn-primary mb-3">
        {loading ? "..." : t(lang, "search_btn")}
      </button>

      {searched && (
        <p className="text-xs text-gray-500 mb-2">
          <strong>{total}</strong> {t(lang, "search_results")}
        </p>
      )}

      {searched && results.length === 0 && !loading && (
        <p className="text-sm text-gray-400">{t(lang, "search_no_results")}</p>
      )}

      {results.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs text-gray-500">
                <th className="py-2 pr-3">#</th>
                <th className="py-2 pr-3">{lang === "es" ? "Jugador" : "Player"}</th>
                <th className="py-2 pr-3">{lang === "es" ? "Equipo" : "Team"}</th>
                <th className="py-2 pr-3">Pos</th>
                <th className="py-2 pr-3">{lang === "es" ? "Edad" : "Age"}</th>
                <th className="py-2 pr-3 text-right">{lang === "es" ? "Valor" : "Value"}</th>
                <th className="py-2 pr-3 text-right">{lang === "es" ? "Predicción" : "Predicted"}</th>
                <th className="py-2 pr-3 text-right">xGrowth</th>
                <th className="py-2 text-right">{t(lang, "fair_price")}</th>
              </tr>
            </thead>
            <tbody>
              {results.map((p, i) => (
                <tr key={p.player_id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-1.5 pr-3 text-xs text-gray-400">{i + 1}</td>
                  <td className="py-1.5 pr-3 font-medium">
                    <div className="flex items-center gap-2">
                      {p.img_url ? (
                        <img src={p.img_url} alt="" className="w-6 h-6 rounded-full object-cover bg-gray-200" />
                      ) : (
                        <div className="w-6 h-6 rounded-full bg-gray-200" />
                      )}
                      <span>{p.name}</span>
                    </div>
                  </td>
                  <td className="py-1.5 pr-3 text-xs text-gray-500">{p.team}</td>
                  <td className="py-1.5 pr-3 text-xs">{p.position}</td>
                  <td className="py-1.5 pr-3 text-xs">{p.age ?? "?"}</td>
                  <td className="py-1.5 pr-3 text-right text-xs">{formatCurrency(p.market_value)}</td>
                  <td className="py-1.5 pr-3 text-right text-xs">
                    {p.predicted_value != null ? formatCurrency(p.predicted_value) : "—"}
                  </td>
                  <td className={`py-1.5 pr-3 text-right text-xs font-semibold ${
                    p.xgrowth != null && p.xgrowth >= 0 ? "text-green-600" : "text-red-600"
                  }`}>
                    {p.xgrowth != null ? `${(p.xgrowth >= 0 ? "+" : "")}${(p.xgrowth * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td className="py-1.5 text-right text-xs">
                    {p.fair_price != null ? formatCurrency(p.fair_price) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
