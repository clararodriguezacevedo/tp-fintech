"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { createSessionToken, safeEqual, SESSION_COOKIE, SESSION_DAYS } from "@/lib/session";

export type LoginState = { error?: string };

/** Only allow redirects back into this site, never to another domain. */
function safeNext(next: FormDataEntryValue | null) {
  const n = typeof next === "string" ? next : "/";
  return n.startsWith("/") && !n.startsWith("//") ? n : "/";
}

export async function login(_prev: LoginState, form: FormData): Promise<LoginState> {
  const expected = process.env.SITE_PASSWORD ?? "";
  const given = String(form.get("password") ?? "");
  if (!expected || !safeEqual(given, expected)) {
    // A small delay makes guessing slower.
    await new Promise((r) => setTimeout(r, 600));
    return { error: "Contraseña incorrecta." };
  }
  (await cookies()).set(SESSION_COOKIE, await createSessionToken(expected), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_DAYS * 24 * 60 * 60,
  });
  redirect(safeNext(form.get("next")));
}

export async function logout() {
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/login");
}
