"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Portada" },
  { href: "/cartera", label: "Mi cartera" },
  { href: "/operaciones", label: "Operaciones" },
  { href: "/historial", label: "Historial" },
  { href: "/noticias", label: "Noticias y mercados" },
];

export function NavLinks() {
  const path = usePathname();
  return (
    <nav aria-label="Secciones" className="-mx-4 overflow-x-auto px-4">
      <ul className="flex gap-6 whitespace-nowrap text-sm">
        {LINKS.map((l) => {
          const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
          return (
            <li key={l.href}>
              <Link
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`inline-block border-b-2 py-2 transition-colors ${
                  active ? "border-ink text-ink" : "border-transparent text-ink-2 hover:text-ink"
                }`}
              >
                {l.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
