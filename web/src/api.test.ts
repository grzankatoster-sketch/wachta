import { describe, expect, it } from "vitest";
import { parseEvidence } from "./api";

describe("parseEvidence", () => {
  it("czyta normalny dowod detektora", () => {
    expect(parseEvidence('{"flight":"FORTE10","type_code":"Q4","gap_minutes":12}')).toEqual({
      flight: "FORTE10", type_code: "Q4", gap_minutes: 12,
    });
  });

  it("nie wywraca sie na dowodzie, ktory nie jest obiektem", () => {
    // jsonb NOT NULL przepuszcza JSON-owy null, liczbe i napis; kazdy z nich wczesniej wysadzal cala mape.
    for (const bad of ["null", "42", '"tekst"', "[1,2]", "{niepelny", "", null, undefined]) {
      expect(parseEvidence(bad as string), `dowod: ${String(bad)}`).toEqual({});
    }
  });

  it("zwrocony obiekt daje sie bezpiecznie odpytac o pola", () => {
    expect(parseEvidence("null").flight).toBeUndefined();
  });
});
