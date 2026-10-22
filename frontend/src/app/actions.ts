"use server";

// Server actions: the browser posts a form, the call to the API (with the API key) happens here.
import { revalidatePath } from "next/cache";

import { api, ApiError, type Trade } from "@/lib/api/client";

export type BuyState =
  | { status: "idle" }
  | { status: "ok"; trade: Trade }
  | { status: "error"; message: string };

function apiMessage(e: unknown) {
  if (e instanceof ApiError) {
    const detail = (e.detail as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "Revisá los valores: alguno no es válido.";
    return `El servidor respondió ${e.status}.`;
  }
  return e instanceof Error ? e.message : "Error desconocido.";
}

export async function buyAction(_prev: BuyState, form: FormData): Promise<BuyState> {
  const num = (k: string) => Number(form.get(k));
  try {
    const trade = await api.buy({
      ticker: String(form.get("ticker") ?? ""),
      quantity: Math.floor(num("quantity")),
      stop_loss: num("stop_loss"),
      take_profit: num("take_profit"),
      recommendation_id: (form.get("recommendation_id") as string) || null,
    });
    revalidatePath("/operaciones");
    return { status: "ok", trade };
  } catch (e) {
    return { status: "error", message: apiMessage(e) };
  }
}

export async function closeTradeAction(form: FormData): Promise<void> {
  await api.closeTrade(String(form.get("trade_id")));
  revalidatePath("/operaciones");
}
