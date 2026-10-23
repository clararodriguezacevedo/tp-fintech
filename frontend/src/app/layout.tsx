import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Header } from "@/components/header";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "El Parqué",
  description: "Qué comprar, vender o mantener hoy",
};

// Every page reads live data from the API.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <Header />
        <main className="mx-auto max-w-5xl px-4 pb-16 pt-8">{children}</main>
        <footer className="mx-auto max-w-5xl px-4 pb-8 text-xs text-text-3">
          Recomendaciones automáticas con fines educativos. No es asesoramiento financiero.
        </footer>
      </body>
    </html>
  );
}
