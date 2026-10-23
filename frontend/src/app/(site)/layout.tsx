import { Header } from "@/components/header";

export default function SiteLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      <Header />
      <main className="mx-auto max-w-5xl px-4 pb-16 pt-8">{children}</main>
      <footer className="mx-auto max-w-5xl px-4 pb-8 text-xs text-text-3">
        Recomendaciones automáticas con fines educativos. No es asesoramiento financiero.
      </footer>
    </>
  );
}
