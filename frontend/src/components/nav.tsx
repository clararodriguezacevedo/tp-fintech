"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Hoy" },
  { href: "/cartera", label: "Mi cartera" },
  { href: "/operaciones", label: "Operaciones" },
  { href: "/historial", label: "Resultados" },
  { href: "/noticias", label: "Noticias" },
  { href: "/como-decide", label: "Cómo decide" },
  { href: "/perfil", label: "Perfil" },
];

export function NavLinks() {
  const path = usePathname();
  return (
    <nav aria-label="Secciones" className="-mx-4 overflow-x-auto px-4">
      <ul className="flex gap-1 whitespace-nowrap text-sm">
        {LINKS.map((l) => {
          const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
          return (
            <li key={l.href}>
              <Link
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`inline-block rounded-md px-3 py-1.5 transition-colors ${
                  active ? "bg-surface font-medium text-text" : "text-text-2 hover:text-text"
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
