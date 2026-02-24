import type { Lang } from "./types";

const TEXT: Record<Lang, Record<string, string>> = {
  es: {
    title: "Simulador de Fichajes",
    subtitle: "Simula ventanas de fichajes con IA",
    spanish: "Español",
    english: "English",

    today_option: "Hoy",
    select_season: "Temporada",
    select_club: "Club",
    transfer_budget: "Presupuesto de fichajes (€M)",
    unlimited_budget: "Presupuesto ilimitado",
    run_simulation: "Simular ventana de fichajes",

    step_loading: "Cargando datos de la temporada...",
    step_team: "Identificando plantilla...",
    step_team_values: "Calculando valores del equipo...",
    step_predicting: "Prediciendo valores futuros...",
    step_selling: "Simulando ventas...",
    step_knapsack: "Optimizando fichajes...",
    step_summary: "Generando resumen...",
    step_done: "Simulación completada",
    loading_data: "Cargando datos...",
    data_loaded: "Datos cargados correctamente",
    squad_loaded: "plantilla de {count} jugadores cargada",
    load_data: "Cargar datos del equipo",
    load_data_hint: "Carga los datos del equipo para poder configurar la simulación.",
    simulating: "Simulando...",
    sim_may_take: "Puede tardar unos minutos",

    simulation_title: "Simulación: {club} ({season})",
    budget_section: "Presupuesto",
    initial_budget: "Inicial",
    sales_revenue: "Ventas",
    total_budget: "Total",
    players_sold: "Jugadores Vendidos",
    players_bought: "Fichajes Recomendados",
    no_buyer: "SIN COMPRADOR",
    from_team: "desde {team}",
    to_team: "→ {team}",
    predicted: "predicción",
    market_info: "Resumen Financiero",
    total_cost: "Coste total",
    remaining_budget: "Presupuesto restante",
    predicted_value_1y: "Valor predicho (1 año)",
    net_benefit: "Beneficio neto esperado (1 año)",
    final_squad: "Plantilla Final",
    no_signings: "No se encontraron fichajes óptimos para esta configuración.",

    select_players_to_sell: "Jugadores a vender",
    sell_selection_help: "Elige qué jugadores quieres vender.",
    signings_per_position: "Fichajes por posición",
    buy_mode_exact: "Número exacto",
    buy_mode_range: "Rango (mín–máx)",
    buy_mode_total: "Total de fichajes",
    signings_exact_help: "Elige cuántos jugadores fichar en cada posición.",
    signings_range_help:
      "Elige el rango por posición. Se probará cada combinación y se elegirá la mejor.",
    signings_total_help:
      "Elige cuántos jugadores fichar en total. Se probarán todas las combinaciones de posiciones (máx. 3 por posición) y se elegirá la mejor.",
    total_players: "Jugadores a fichar",
    buy_min: "Mín",
    buy_max: "Máx",
    budget_title: "Presupuesto adicional",
    budget_extra_note: "Este presupuesto es adicional al dinero obtenido por las ventas.",

    approach_title: "Estrategia de fichajes",
    approach_max_value: "Máximo valor",
    approach_max_value_help:
      "Ficha a los jugadores con mayor valor predicho futuro. Tiende a fichar estrellas caras.",
    approach_young_talents: "Jóvenes promesas",
    approach_young_talents_help:
      "Solo considera jugadores de 23 años o menos. Ideal para construir un proyecto a largo plazo.",
    approach_max_profit: "Máximo beneficio",
    approach_max_profit_help:
      "Optimiza el beneficio esperado (valor predicho − coste). Encuentra gangas infravaloradas.",
    approach_balanced: "Equilibrado",
    approach_balanced_help:
      "Prioriza jugadores en su mejor edad (25-29) con alto valor predicho. Equilibra rendimiento inmediato y valor.",

    pos_gk: "POR",
    pos_def: "DEF",
    pos_mid: "MED",
    pos_att: "DEL",

    ai_analysis: "Análisis IA",
    no_ai_key: "Introduce una API key de LLM para obtener análisis generado por IA.",
    ai_supported_providers: "Proveedores soportados: OpenAI, Anthropic y Gemini.",
    llm_api_key: "API Key del LLM",
    llm_api_key_help:
      "Se detecta automáticamente: sk-... = OpenAI, sk-ant-... = Anthropic, otro = Gemini",
    generate_analysis: "Generar análisis",
    generating: "Generando análisis...",
    ai_error: "No se pudo generar el análisis. Comprueba tu API key.",

    footer: "Datos de Transfermarkt · Predicciones con XGBoost · Optimización con Knapsack",
    created_by: "Creado por",
  },
  en: {
    title: "Transfer Simulator",
    subtitle: "Simulate transfer windows with AI",
    spanish: "Español",
    english: "English",

    today_option: "Today",
    select_season: "Season",
    select_club: "Club",
    transfer_budget: "Transfer budget (€M)",
    unlimited_budget: "Unlimited budget",
    run_simulation: "Simulate transfer window",

    step_loading: "Loading season data...",
    step_team: "Identifying squad...",
    step_team_values: "Calculating team values...",
    step_predicting: "Predicting future values...",
    step_selling: "Simulating sales...",
    step_knapsack: "Optimizing signings...",
    step_summary: "Generating summary...",
    step_done: "Simulation complete",
    loading_data: "Loading data...",
    data_loaded: "Data loaded successfully",
    squad_loaded: "squad of {count} players loaded",
    load_data: "Load team data",
    load_data_hint: "Load team data to configure the simulation.",
    simulating: "Simulating...",
    sim_may_take: "This may take a few minutes",

    simulation_title: "Simulation: {club} ({season})",
    budget_section: "Budget",
    initial_budget: "Initial",
    sales_revenue: "Sales",
    total_budget: "Total",
    players_sold: "Players Sold",
    players_bought: "Recommended Signings",
    no_buyer: "NO BUYER",
    from_team: "from {team}",
    to_team: "→ {team}",
    predicted: "predicted",
    market_info: "Financial Summary",
    total_cost: "Total cost",
    remaining_budget: "Remaining budget",
    predicted_value_1y: "Predicted value (1 year)",
    net_benefit: "Expected net benefit (1 year)",
    final_squad: "Final Squad",
    no_signings: "No optimal signings found for this configuration.",

    select_players_to_sell: "Players to sell",
    sell_selection_help: "Choose which players you want to sell.",
    signings_per_position: "Signings per position",
    buy_mode_exact: "Exact number",
    buy_mode_range: "Range (min–max)",
    buy_mode_total: "Total signings",
    signings_exact_help: "Choose how many players to sign per position.",
    signings_range_help:
      "Choose the range per position. Every combination will be tested and the best one selected.",
    signings_total_help:
      "Choose how many players to sign in total. All position combinations (max 3 per position) will be tested and the best one selected.",
    total_players: "Players to sign",
    buy_min: "Min",
    buy_max: "Max",
    budget_title: "Additional budget",
    budget_extra_note: "This budget is on top of the money obtained from player sales.",

    approach_title: "Signing strategy",
    approach_max_value: "Maximum value",
    approach_max_value_help:
      "Sign the players with the highest predicted future value. Tends to sign expensive stars.",
    approach_young_talents: "Young talents",
    approach_young_talents_help:
      "Only considers players aged 23 or under. Great for building a long-term project.",
    approach_max_profit: "Maximum profit",
    approach_max_profit_help:
      "Optimizes expected profit (predicted value − cost). Finds undervalued bargains.",
    approach_balanced: "Balanced",
    approach_balanced_help:
      "Prioritizes prime-age players (25-29) with high predicted value. Balances immediate performance and value.",

    pos_gk: "GK",
    pos_def: "DEF",
    pos_mid: "MID",
    pos_att: "FWD",

    ai_analysis: "AI Analysis",
    no_ai_key: "Enter an LLM API key to get an AI-generated analysis.",
    ai_supported_providers: "Supported providers: OpenAI, Anthropic and Gemini.",
    llm_api_key: "LLM API Key",
    llm_api_key_help:
      "Auto-detected: sk-... = OpenAI, sk-ant-... = Anthropic, other = Gemini",
    generate_analysis: "Generate analysis",
    generating: "Generating analysis...",
    ai_error: "Could not generate analysis. Check your API key.",

    footer: "Data from Transfermarkt · Predictions by XGBoost · Optimization with Knapsack",
    created_by: "Created by",
  },
};

export function t(lang: Lang, key: string, vars?: Record<string, string | number>): string {
  let text = TEXT[lang]?.[key] ?? TEXT.en[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replace(`{${k}}`, String(v));
    }
  }
  return text;
}

export function formatCurrency(value: number | null | undefined, decimals = 1): string {
  if (value == null) return "N/A";
  const v = Number(value);
  if (Math.abs(v) >= 1_000_000_000) return `€${(v / 1e9).toFixed(decimals)}B`;
  if (Math.abs(v) >= 1_000_000) return `€${(v / 1e6).toFixed(decimals)}M`;
  if (Math.abs(v) >= 1_000) return `€${(v / 1e3).toFixed(0)}K`;
  return `€${v.toFixed(0)}`;
}

export const POS_ORDER = ["GK", "DEF", "MID", "ATT"] as const;
export const POS_KEYS: Record<string, string> = {
  GK: "pos_gk",
  DEF: "pos_def",
  MID: "pos_mid",
  ATT: "pos_att",
};
