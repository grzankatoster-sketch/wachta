export interface LiveAircraft {
  hex: string; flight: string | null; typeCode: string | null; isMilitary: boolean;
  lat: number; lon: number; altBaroFt: number | null; onGround: boolean;
  gsKt: number | null; trackDeg: number | null; ts: string;
}
export interface AlertDto {
  id: number; detector: string; entityId: string; startedAt: string;
  lat: number; lon: number; score: number; evidence: string; state: string;
}
export interface JammingDto { h3: string; nAircraft: number; nDegraded: number }
export interface ReplayPath { hex: string; flight: string | null; typeCode: string | null; path: [number, number][]; timestamps: number[] }
export interface SourceInfo { id: string; name: string; url: string; license: string; trustTier: number; attribution: string }

export interface AlertEvidence { flight?: string; type_code?: string; gap_minutes?: number }

/**
 * Reads an alert's `evidence` column, which is free-form jsonb written by the Python detectors.
 *
 * Anything that is not a JSON object yields an empty one. A detector shipping `null`, a bare number
 * or truncated text must cost a single line in the alert list, never the map: AlertsPanel renders
 * inside the same React tree as the map, so one throw here used to unmount the whole page.
 */
export function parseEvidence(raw: string | null | undefined): AlertEvidence {
  if (typeof raw !== "string") return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return {};
  }
  return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) ? (parsed as AlertEvidence) : {};
}

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}
