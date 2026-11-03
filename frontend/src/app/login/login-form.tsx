"use client";

import { useActionState } from "react";

import { BUTTON } from "@/components/ui";

import { login, type LoginState } from "./actions";

export function LoginForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState<LoginState, FormData>(login, {});
  return (
    <form action={action} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <div>
        <label htmlFor="password" className="mb-1.5 block text-sm text-text-2">Contraseña</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          autoFocus
          required
          className="w-full rounded-lg border border-border bg-bg px-3 py-2.5 focus:border-text"
        />
      </div>
      {state.error && <p className="text-sm" role="alert" style={{ color: "var(--sell)" }}>{state.error}</p>}
      <button
        type="submit"
        disabled={pending}
        className={`w-full ${BUTTON}`}
      >
        {pending ? "Entrando..." : "Entrar"}
      </button>
    </form>
  );
}
