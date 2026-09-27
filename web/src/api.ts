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

export async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}
