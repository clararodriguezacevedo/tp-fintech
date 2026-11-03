import { cookies } from "next/headers";

import { Header } from "@/components/header";
import { UnitsProvider, type Units } from "@/components/units";

function unitsFrom(cookie: string | undefined): Units {
  const [currency, mode] = (cookie ?? "").split(".");
  return { currency: currency === "USD" ? "USD" : "ARS", mode: mode === "pct" ? "pct" : "abs" };
}

export default async function SiteLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const units = unitsFrom((await cookies()).get("units")?.value);
  return (
    <UnitsProvider initial={units}>
      <Header />
      <main className="mx-auto max-w-5xl px-4 pb-16 pt-8">{children}</main>
      <footer className="mx-auto max-w-5xl px-4 pb-8 text-sm text-text-3">
        Recomendaciones automáticas con fines educativos. No es asesoramiento financiero.
      </footer>
    </UnitsProvider>
  );
}
