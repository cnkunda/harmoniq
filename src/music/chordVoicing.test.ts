import { describe, expect, it } from "vitest";

import {
    chordToFretboardCells,
    formatChordDisplay
} from "./chordVoicing";

describe("chordToFretboardCells", () => {
  describe("Compact voicings", () => {
    it("returns C major triad in low position", () => {
      const cells = chordToFretboardCells("C:maj", "compact", "low");

      expect(cells.length).toBeGreaterThanOrEqual(3);
      expect(cells.some((c) => c.interval === 0)).toBe(true); // Root
      expect(cells.some((c) => c.interval === 4)).toBe(true); // Major 3rd
      expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th
    });

    it("returns A minor triad with correct intervals", () => {
      const cells = chordToFretboardCells("A:min", "compact", "low");

      expect(cells.length).toBeGreaterThanOrEqual(3);
      expect(cells.some((c) => c.interval === 0)).toBe(true); // Root
      expect(cells.some((c) => c.interval === 3)).toBe(true); // Minor 3rd
      expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th
    });

    it('returns empty array for "N" (no chord)', () => {
      const cells = chordToFretboardCells("N", "compact", "low");
      expect(cells).toEqual([]);
    });

    it("returns empty array for empty string", () => {
      const cells = chordToFretboardCells("", "compact", "low");
      expect(cells).toEqual([]);
    });

    it("handles sharp roots like F#", () => {
      const cells = chordToFretboardCells("F#:maj", "compact", "low");
      expect(cells.length).toBeGreaterThanOrEqual(3);
    });

    it("handles flat roots like Bb", () => {
      const cells = chordToFretboardCells("Bb:min", "compact", "low");
      expect(cells.length).toBeGreaterThanOrEqual(3);
    });

    it("handles dominant 7th chords with 4 notes", () => {
      const cells = chordToFretboardCells("G:7", "compact", "low");

      expect(cells.length).toBeGreaterThanOrEqual(3);
      expect(cells.some((c) => c.interval === 0)).toBe(true); // Root
      expect(cells.some((c) => c.interval === 4)).toBe(true); // Major 3rd
      expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th
      expect(cells.some((c) => c.interval === 10)).toBe(true); // Minor 7th
    });

    it("respects position preference for open position", () => {
      const openCells = chordToFretboardCells("E:maj", "compact", "open");
      const lowCells = chordToFretboardCells("E:maj", "compact", "low");

      // Open position should favor fret 0 when available
      const openFrets = openCells.map((c) => c.fret);
      const lowFrets = lowCells.map((c) => c.fret);

      expect(Math.min(...openFrets)).toBeLessThanOrEqual(Math.min(...lowFrets));
    });
  });

  describe("Full voicings", () => {
    it("returns more notes for full voicing than compact", () => {
      const compact = chordToFretboardCells("C:maj", "compact", "low");
      const full = chordToFretboardCells("C:maj", "full", "low");

      // Full voicing typically has 4-6 notes, compact has 3-4
      expect(full.length).toBeGreaterThanOrEqual(compact.length);
    });

    it("includes notes on multiple strings for full voicing", () => {
      const cells = chordToFretboardCells("G:maj", "full", "low");

      const uniqueStrings = new Set(cells.map((c) => c.string));
      expect(uniqueStrings.size).toBeGreaterThanOrEqual(3);
    });

    it("handles minor 7th chords in full voicing", () => {
      const cells = chordToFretboardCells("D:min7", "full", "low");

      expect(cells.length).toBeGreaterThanOrEqual(3);
      expect(cells.some((c) => c.interval === 0)).toBe(true); // Root
      expect(cells.some((c) => c.interval === 3)).toBe(true); // Minor 3rd
      expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th
      expect(cells.some((c) => c.interval === 10)).toBe(true); // Minor 7th
    });
  });

  describe("Edge cases", () => {
    it("handles unknown quality gracefully with major fallback", () => {
      const cells = chordToFretboardCells("C:xyz", "compact", "low");
      // Should fall back to major triad
      expect(cells.length).toBeGreaterThanOrEqual(3);
    });

    it('handles shorthand notation "Cm"', () => {
      const cells = chordToFretboardCells("Cm", "compact", "low");
      expect(cells.length).toBeGreaterThanOrEqual(3);
      expect(cells.some((c) => c.interval === 3)).toBe(true); // Minor 3rd
    });

    it("returns valid midi numbers for all cells", () => {
      const cells = chordToFretboardCells("F:maj7", "compact", "low");

      for (const cell of cells) {
        expect(cell.midi).toBeGreaterThanOrEqual(40); // Low E open
        expect(cell.midi).toBeLessThanOrEqual(88); // High E fret 24
        expect(cell.string).toBeGreaterThanOrEqual(1);
        expect(cell.string).toBeLessThanOrEqual(6);
        expect(cell.fret).toBeGreaterThanOrEqual(0);
      }
    });
  });

  describe("Open chord shapes (full voicing)", () => {
    it("plays correct open A minor shape with all chord tones", () => {
      const cells = chordToFretboardCells("A:min", "full", "low");

      // Should have multiple notes from the full voicing
      expect(cells.length).toBeGreaterThanOrEqual(4);

      // Verify all required chord tones are present
      expect(cells.some((c) => c.interval === 0)).toBe(true); // Root (A)
      expect(cells.some((c) => c.interval === 3)).toBe(true); // Minor 3rd (C)
      expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th (E)

      // Verify all strings are used (5 strings in Am-shape or Em-shape templates)
      const uniqueStrings = new Set(cells.map((c) => c.string));
      expect(uniqueStrings.size).toBeGreaterThanOrEqual(4);

      // Verify frets are in valid range for open position
      const frets = cells.map((c) => c.fret);
      expect(Math.max(...frets)).toBeLessThanOrEqual(5); // Open chords rarely need high frets
    });

    it("plays correct open E minor shape with all chord tones", () => {
      const cells = chordToFretboardCells("E:min", "full", "low");

      expect(cells.length).toBeGreaterThanOrEqual(4);

      // Verify all required chord tones
      expect(cells.some((c) => c.interval === 0)).toBe(true); // Root (E)
      expect(cells.some((c) => c.interval === 3)).toBe(true); // Minor 3rd (G)
      expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th (B)

      // Em-shape uses 6 strings
      const uniqueStrings = new Set(cells.map((c) => c.string));
      expect(uniqueStrings.size).toBeGreaterThanOrEqual(5);
    });

    it("plays correct open D minor 7 shape with all chord tones", () => {
      const cells = chordToFretboardCells("D:min7", "full", "open");

      // Should have at least 4 chord tones (root, m3, 5, m7)
      expect(cells.length).toBeGreaterThanOrEqual(3);

      // Verify all required chord tones for min7
      expect(cells.some((c) => c.interval === 0)).toBe(true); // Root (D)
      expect(cells.some((c) => c.interval === 3)).toBe(true); // Minor 3rd (F)
      expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th (A)
      expect(cells.some((c) => c.interval === 10)).toBe(true); // Minor 7th (C)

      // Should use 4 strings (Dm7-shape uses strings 1-4)
      const uniqueStrings = new Set(cells.map((c) => c.string));
      expect(uniqueStrings.size).toBeGreaterThanOrEqual(3);

      // Verify reasonable fret positions
      const frets = cells.map((c) => c.fret);
      expect(Math.max(...frets)).toBeLessThanOrEqual(6);
    });
  });
});

describe("formatChordDisplay", () => {
  it("formats major chords without suffix", () => {
    expect(formatChordDisplay("C:maj")).toBe("C");
    expect(formatChordDisplay("G:maj")).toBe("G");
  });

  it("formats minor chords with m suffix", () => {
    expect(formatChordDisplay("A:min")).toBe("Am");
    expect(formatChordDisplay("F#:min")).toBe("F#m");
  });

  it("formats 7th chords correctly", () => {
    expect(formatChordDisplay("G:7")).toBe("G7");
    expect(formatChordDisplay("C:maj7")).toBe("Cmaj7");
    expect(formatChordDisplay("D:min7")).toBe("Dm7");
  });

  it("formats diminished and augmented", () => {
    expect(formatChordDisplay("B:dim")).toBe("B°");
    expect(formatChordDisplay("C#:aug")).toBe("C#+");
  });

  it('returns em-dash for "N" (no chord)', () => {
    expect(formatChordDisplay("N")).toBe("—");
  });

  it("returns original for unparseable symbols", () => {
    expect(formatChordDisplay("???")).toBe("???");
  });

  it("handles shorthand notation", () => {
    expect(formatChordDisplay("Cm")).toBe("Cm");
    expect(formatChordDisplay("C7")).toBe("C7");
  });
});
