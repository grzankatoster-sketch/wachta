import type { ReplayPath } from "./api";

export interface Trip { hex: string; label: string; path: [number, number][]; timestamps: number[] }

export function replayBounds(paths: ReplayPath[]): { start: number; end: number } | null {
  // No spread: 6 h of Baltic traffic is ~300k timestamps and Math.min(...all) blows the call stack.
  let start = Infinity;
  let end = -Infinity;
  for (const p of paths) {
    for (const t of p.timestamps) {
      if (t < start) start = t;
      if (t > end) end = t;
    }
  }
  return start === Infinity ? null : { start, end };
}

export function toTrips(paths: ReplayPath[], start: number): Trip[] {
  return paths.map((p) => ({
    hex: p.hex,
    label: `${p.flight ?? p.hex} ${p.typeCode ?? ""}`.trim(),
    path: p.path,
    timestamps: p.timestamps.map((t) => t - start),
  }));
}
