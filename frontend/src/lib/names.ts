// Plain names for the tickers the app follows most, so "YPFD" reads as "YPF".
import { api } from "@/lib/api/client";

const NAMES: Record<string, string> = {
  GGAL: "Grupo Galicia", YPFD: "YPF", PAMP: "Pampa Energía", BMA: "Banco Macro", TXAR: "Ternium Argentina",
  ALUA: "Aluar", CEPU: "Central Puerto", TGSU2: "Transportadora de Gas del Sur", LOMA: "Loma Negra",
  SUPV: "Banco Supervielle", BBAR: "BBVA Argentina", CRES: "Cresud", EDN: "Edenor", TECO2: "Telecom Argentina",
  VALO: "Grupo Valores", COME: "Sociedad Comercial del Plata", BYMA: "Bolsas y Mercados Argentinos",
  METR: "Metrogas", TGNO4: "Transportadora de Gas del Norte", TRAN: "Transener",
  AAPL: "Apple", MSFT: "Microsoft", NVDA: "Nvidia", GOOGL: "Google", AMZN: "Amazon", META: "Meta",
  TSLA: "Tesla", MELI: "Mercado Libre", KO: "Coca-Cola", XOM: "Exxon Mobil", JPM: "JPMorgan",
  VIST: "Vista Energy", SPY: "Fondo S&P 500", QQQ: "Fondo Nasdaq 100", GLD: "Fondo de oro",
  BRKB: "Berkshire Hathaway", WMT: "Walmart", DIS: "Disney", BABA: "Alibaba", PBR: "Petrobras",
  NU: "Nubank", TSM: "TSMC", XLP: "Fondo de consumo masivo",
  AL30: "Bono AL30", GD30: "Bono GD30", AL35: "Bono AL35", GD35: "Bono GD35", GD41: "Bono GD41",
  AE38: "Bono AE38", AO27: "Bono del Tesoro AO27", AO29: "Bono del Tesoro AO29", TXMD9: "Bono del Tesoro TXMD9",
};

export const nameOf = (ticker: string, fallback?: string) => NAMES[ticker] ?? fallback ?? ticker;

/** Every CEDEAR's ticker. Empty if the list can't be read. */
export async function cedearTickers(): Promise<Set<string>> {
  try {
    return new Set((await api.assets()).filter((a) => a.category === "cedears").map((a) => a.ticker));
  } catch {
    return new Set();
  }
}

/** ticker -> IOL's name for every asset, for nameOf's fallback. Empty if the list can't be read. */
export async function assetNames(): Promise<Record<string, string>> {
  try {
    return Object.fromEntries((await api.assets()).map((a) => [a.ticker, a.name]));
  } catch {
    return {};
  }
}
