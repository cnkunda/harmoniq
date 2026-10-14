import { describe, expect, it } from "vitest";

import {
    getChordPositionAtIndex,
    getChordPositions,
    isChordInDb,
} from "./chordDbAdapter";

/** Commit 155 — ChordDiagram path-selection matrix (primary vs algorithmic fallback). */
describe("chordDbAdapter Commit 155 matrix", () => {
  it("resolves open chords via the primary DB path (G:maj, C:maj)", () => {
    for (const symbol of ["G:maj", "C:maj"]) {
      expect(isChordInDb(symbol)).toBe(true);
      const pos = getChordPositionAtIndex(symbol, 0);
      expect(pos).not.toBeNull();
      expect(pos!.barres).toEqual([]);
    }
  });

  it("resolves barre chords with barre markers (F:maj, B:min)", () => {
    const f = getChordPositionAtIndex("F:maj", 0);
    expect(f).not.toBeNull();
    expect(f!.barres.length).toBeGreaterThan(0);

    const bm = getChordPositionAtIndex("B:min", 0);
    expect(bm).not.toBeNull();
    expect(bm!.barres.length).toBeGreaterThan(0);
  });

  it("misses the DB for rare qualities so ChordDiagram takes the fallback (C:add11)", () => {
    expect(getChordPositions("C:add11")).toBeNull();
    expect(isChordInDb("C:add11")).toBe(false);
  });

  it("resolves flat names, including via the enharmonic branch (Bb:maj, Db:maj)", () => {
    expect(isChordInDb("Bb:maj")).toBe(true);
    // Db has no chords-db key; the adapter falls through to C#.
    expect(isChordInDb("Db:maj")).toBe(true);
    expect(isChordInDb("A#:maj")).toBe(true);
  });

  it("returns null for N so ChordDiagram renders empty", () => {
    expect(getChordPositions("N")).toBeNull();
    expect(getChordPositionAtIndex("G:maj", 99)).toBeNull();
  });
});
