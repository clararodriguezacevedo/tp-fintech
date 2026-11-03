"use client";
// A table row that opens more rows below it: `detail` has to be <tr>s.
import { useState, type ReactNode } from "react";

export function ExpandableRow({ first, rest, detail, label }: {
  first: ReactNode; rest: ReactNode; detail: ReactNode; label: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="hover:bg-surface">
        <td className="py-3">
          <div className="flex items-start gap-2">
            <button
              type="button" aria-expanded={open} aria-label={`${open ? "Ocultar" : "Ver"} las operaciones de ${label}`} onClick={() => setOpen(!open)}
              className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-lg text-text-3 hover:text-text"
            >
              <span aria-hidden className={`text-xs transition-transform ${open ? "rotate-90" : ""}`}>▶</span>
            </button>
            <div className="min-w-0">{first}</div>
          </div>
        </td>
        {rest}
      </tr>
      {open && detail}
    </>
  );
}
