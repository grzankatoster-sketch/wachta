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

/** Free-form jsonb: every detector writes its own shape, so every field is optional and unknown
 * keys are allowed. Reading it as one fixed shape is what made maritime alerts render as "?". */
export interface AlertEvidence {
  flight?: string;
  type_code?: string;
  gap_minutes?: number;
  name?: string;
  mmsi?: string;
  duration_minutes?: number;
  shift_km?: number;
  min_distance_km?: number;
  line_name?: string;
  listeners?: number;
  implied_kt?: number;
  [inne: string]: unknown;
}

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

import { zapytanie } from "./search-view";

export interface SearchHit {
  id: string;
  text: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface SearchResult {
  query: string;
  model: string;
  minScore: number;
  found: number;
  hits: SearchHit[];
  caveat: string;
}

/**
 * Searches the corpus by meaning.
 *
 * An empty `hits` is an ANSWER, not a failure: it means nothing in the corpus passed the similarity
 * floor. The caller must not turn that into "something went wrong", because the two look the same
 * on screen and mean the opposite. A model outage is a thrown error instead, so the difference
 * survives all the way to the user.
 */
export async function search(query: string, kind?: string, limit = 8): Promise<SearchResult> {
  return getJSON<SearchResult>(`/api/search?${zapytanie(query, kind, limit)}`);
}

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}
