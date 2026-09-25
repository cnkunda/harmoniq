import { describe, expect, it } from "vitest";

import {
    chordToFretboardCells,
    formatChordDisplay,
    parseChordSymbol,
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

    it("plays correct A minor in low position with Em-shape root on string 6", () => {
      const cells = chordToFretboardCells("A:min", "full", "low");

      expect(cells.length).toBeGreaterThanOrEqual(4);

      // Verify all required chord tones are present
      expect(cells.some((c) => c.interval === 0)).toBe(true); // Root (A)
      expect(cells.some((c) => c.interval === 3)).toBe(true); // Minor 3rd (C)
      expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th (E)

      // Verify the root cell corresponds to A2 (MIDI 45) — Em-shape on string 6 or Am-shape on string 5
      const rootCells = cells.filter((c) => c.interval === 0);
      expect(rootCells.some((c) => c.midi === 45)).toBe(true);
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

    it("uses low fret positions for C major in low position (regression)", () => {
      const cells = chordToFretboardCells("C:maj", "full", "low");
      // C in low position should have root on string 5 (A-shape, fret 3) or string 6 (E-shape, fret 8).
      // The template selector should pick A-shape for the lower base fret.
      const rootCells = cells.filter((c) => c.interval === 0);
      expect(rootCells.length).toBeGreaterThanOrEqual(1);
      // The lowest root should be at fret ≤ 3 (A-shape on string 5)
      const minRootFret = Math.min(...rootCells.map((c) => c.fret));
      expect(minRootFret).toBeLessThanOrEqual(3);
    });

    it("uses low fret positions for G major in low position", () => {
      const cells = chordToFretboardCells("G:maj", "full", "low");
      // G in low position: E-shape on fret 3 (string 6) or G-shape on fret 3 (string 6).
      // The template selector should pick lowest base fret (fret 3).
      const rootCells = cells.filter((c) => c.interval === 0);
      expect(rootCells.length).toBeGreaterThanOrEqual(1);
      const minRootFret = Math.min(...rootCells.map((c) => c.fret));
      expect(minRootFret).toBeLessThanOrEqual(3);
    });

    it("plays correct D minor 7 shape with all chord tones", () => {
      const cells = chordToFretboardCells("D:min7", "full", "low");

      expect(cells.length).toBeGreaterThanOrEqual(3);

      // Verify all required chord tones for min7
      expect(cells.some((c) => c.interval === 0)).toBe(true); // Root (D)
      expect(cells.some((c) => c.interval === 3)).toBe(true); // Minor 3rd (F)
      expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th (A)
      expect(cells.some((c) => c.interval === 10)).toBe(true); // Minor 7th (C)

      // Should use 4 strings (Dm7-shape uses strings 1-4)
      const uniqueStrings = new Set(cells.map((c) => c.string));
      expect(uniqueStrings.size).toBeGreaterThanOrEqual(3);

      // Verify reasonable fret positions (Dm7-shape base + offsets)
      const frets = cells.map((c) => c.fret);
      expect(Math.max(...frets)).toBeLessThanOrEqual(8);
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

    it("handles 7b9 chord quality with correct intervals", () => {
      const cells = chordToFretboardCells("G:7b9", "compact", "low");
      expect(cells.length).toBeGreaterThanOrEqual(3);
      expect(cells.some((c) => c.interval === 0)).toBe(true);  // Root
      expect(cells.some((c) => c.interval === 4)).toBe(true);  // Major 3rd
      expect(cells.some((c) => c.interval === 10)).toBe(true); // Minor 7th
    });

    it("handles dim7 chord quality with correct intervals", () => {
      const cells = chordToFretboardCells("C:dim7", "compact", "low");
      expect(cells.length).toBeGreaterThanOrEqual(3);
      expect(cells.some((c) => c.interval === 0)).toBe(true);  // Root
      expect(cells.some((c) => c.interval === 3)).toBe(true);  // Minor 3rd
      expect(cells.some((c) => c.interval === 6)).toBe(true);  // Dim 5th
      expect(cells.some((c) => c.interval === 9)).toBe(true);  // Dim 7th
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

describe("parseChordSymbol (slash notation)", () => {
  it("parses slash chord C:maj/E", () => {
    const result = parseChordSymbol("C:maj/E");
    expect(result).toEqual({ root: "C", quality: "maj", bass: "E" });
  });

  it("parses slash chord G:7/F", () => {
    const result = parseChordSymbol("G:7/F");
    expect(result).toEqual({ root: "G", quality: "7", bass: "F" });
  });

  it("parses plain chord without bass", () => {
    const result = parseChordSymbol("A:min");
    expect(result).toEqual({ root: "A", quality: "min" });
  });

  it('returns null for "N"', () => {
    expect(parseChordSymbol("N")).toBeNull();
  });

  it("handles sharp roots with slash", () => {
    const result = parseChordSymbol("F#:min7/C#");
    expect(result).toEqual({ root: "F#", quality: "min7", bass: "C#" });
  });

  it("handles shorthand with slash", () => {
    const result = parseChordSymbol("Cm/G");
    expect(result).toEqual({ root: "C", quality: "min", bass: "G" });
  });
});

describe("formatChordDisplay (slash notation)", () => {
  it("formats slash chord C:maj/E as C/E", () => {
    expect(formatChordDisplay("C:maj/E")).toBe("C/E");
  });

  it("formats slash chord G:7/F as G7/F", () => {
    expect(formatChordDisplay("G:7/F")).toBe("G7/F");
  });

  it("formats minor slash chord A:min7/G as Am7/G", () => {
    expect(formatChordDisplay("A:min7/G")).toBe("Am7/G");
  });

  it("formats plain chord without bass as before", () => {
    expect(formatChordDisplay("C:maj")).toBe("C");
  });

  it("accepts explicit bass parameter override", () => {
    expect(formatChordDisplay("C:maj", "G")).toBe("C/G");
  });
});

describe("chordToFretboardCells with voicing", () => {
  it("renders full E-shape C major in low position with valid intervals", () => {
    // E-shape at fret 8 (C major barre) in full mode
    const cells = chordToFretboardCells("C:maj", "full", "low");
    expect(cells.length).toBeGreaterThanOrEqual(5);
    expect(cells.some((c) => c.interval === 0)).toBe(true); // Root present
    expect(cells.some((c) => c.interval === 4)).toBe(true); // Major 3rd
    expect(cells.some((c) => c.interval === 7)).toBe(true); // Perfect 5th
  });

  it("renders full A-shape D major in low position", () => {
    const cells = chordToFretboardCells("D:maj", "full", "low");
    // Should produce an A-shape voicing (root on string 5)
    expect(cells.length).toBeGreaterThanOrEqual(4);
    // Should have strings in the A-shape configuration
    expect(cells.every((c) => c.fret >= 0)).toBe(true);
  });

  it("renders full G-shape G major in open position", () => {
    const cells = chordToFretboardCells("G:maj", "full", "open");
    expect(cells.length).toBeGreaterThanOrEqual(5);
    expect(cells.some((c) => c.fret === 0)).toBe(true); // Some open strings
  });

  it("should not produce muted strings for basic major chords", () => {
    const cells = chordToFretboardCells("C:maj", "full", "low");
    for (const cell of cells) {
      expect(cell.fret).toBeGreaterThanOrEqual(0);
      expect(cell.midi).toBeGreaterThan(0);
    }
  });
});
