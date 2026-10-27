"use client";

// The moving strip of the recommendations tape. It runs as a Web Animation on the compositor, so
// page work doesn't make it stutter, and on hover it eases down to a stop (and back up) instead of
// freezing at once.
import { useEffect, useRef, type ReactNode } from "react";

const DURATION_MS = 80_000; // one full loop
const EASE_MS = 450;

export function TapeTrack({ children }: { children: ReactNode }) {
  const track = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = track.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const anim = el.animate(
      [{ transform: "translate3d(0, 0, 0)" }, { transform: "translate3d(-50%, 0, 0)" }],
      { duration: DURATION_MS, iterations: Infinity },
    );
    let rate = 1;
    let frame = 0;
    const easeTo = (target: number) => {
      cancelAnimationFrame(frame);
      const from = rate;
      const start = performance.now();
      const step = (now: number) => {
        const k = Math.min(1, (now - start) / EASE_MS);
        rate = from + (target - from) * (1 - (1 - k) ** 3);
        anim.updatePlaybackRate(rate);
        if (k < 1) frame = requestAnimationFrame(step);
      };
      frame = requestAnimationFrame(step);
    };
    const slow = () => easeTo(0);
    const resume = () => easeTo(1);
    const box = el.parentElement;
    box?.addEventListener("pointerenter", slow);
    box?.addEventListener("pointerleave", resume);
    return () => {
      cancelAnimationFrame(frame);
      box?.removeEventListener("pointerenter", slow);
      box?.removeEventListener("pointerleave", resume);
      anim.cancel();
    };
  }, []);

  return (
    <div ref={track} className="tape-track flex">
      {children}
    </div>
  );
}
