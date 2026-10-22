import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import { Masthead } from "@/components/masthead";

import "./globals.css";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["SOFT", "WONK", "opsz"],
});
const plexSans = IBM_Plex_Sans({ variable: "--font-plex-sans", subsets: ["latin"], weight: ["400", "500", "600"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "El Parqué",
  description: "Recomendaciones de comprar, vender o mantener a partir de noticias y mercados de predicción",
};

// Every page reads live data from the API.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body className={`${fraunces.variable} ${plexSans.variable} ${plexMono.variable} antialiased`}>
        <Masthead />
        <main className="mx-auto max-w-6xl px-4 pb-20 pt-8">{children}</main>
        <footer className="mx-auto max-w-6xl border-t border-rule px-4 py-6 text-xs text-ink-3">
          Proyecto académico (ITBA, Tecnología para las Finanzas). Las recomendaciones son señales automáticas, no asesoramiento financiero.
        </footer>
      </body>
    </html>
  );
}
