import { useEffect, useState } from "react";
import { getJSON, type SourceInfo } from "../api";

export function SourcesFooter() {
  const [sources, setSources] = useState<SourceInfo[]>([]);
  useEffect(() => { getJSON<SourceInfo[]>("/api/sources").then(setSources).catch(() => setSources([])); }, []);
  const attributions = [...new Set(sources.map((s) => s.attribution))];
  return (
    <footer className="sources">
      Źródła: {attributions.join(" · ")} · Podkład: OpenFreeMap, © OpenStreetMap contributors
    </footer>
  );
}
