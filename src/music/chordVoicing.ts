/**
 * Chord voicing mapper - Convert chord symbols to guitar fretboard positions
 * Supports full voicings (authentic guitar shapes) and compact voicings (triads)
 */

import { allCellsForMidi, OPEN_MIDI_BY_ROW } from "./fretboardCell";

/** Interval semitones from root for common chord qualities */
const CHORD_QUALITY_INTERVALS: Record<string, number[]> = {
  maj: [0, 4, 7], // Root, major 3rd, perfect 5th
  min: [0, 3, 7], // Root, minor 3rd, perfect 5th
  dim: [0, 3, 6], // Root, minor 3rd, diminished 5th
  aug: [0, 4, 8], // Root, major 3rd, augmented 5th
  "7": [0, 4, 7, 10], // Dominant 7th
  maj7: [0, 4, 7, 11], // Major 7th
  min7: [0, 3, 7, 10], // Minor 7th
  "7sus4": [0, 5, 7, 10], // Dominant 7th suspended 4th
  sus4: [0, 5, 7], // Suspended 4th
  sus2: [0, 2, 7], // Suspended 2nd
  "6": [0, 4, 7, 9], // Major 6th
  min6: [0, 3, 7, 9], // Minor 6th
  "9": [0, 4, 7, 10, 14], // Dominant 9th (rootless voicings often used)
  maj9: [0, 4, 7, 11, 14], // Major 9th
  min9: [0, 3, 7, 10, 14], // Minor 9th
  "7b9": [0, 4, 7, 10, 13], // Dominant 7th flat 9
  "7#9": [0, 4, 7, 10, 15], // Dominant 7th sharp 9
  dim7: [0, 3, 6, 9], // Diminished 7th (fully diminished)
  "11": [0, 4, 7, 10, 14, 17], // Dominant 11th
  "13": [0, 4, 7, 10, 14, 17, 21], // Dominant 13th
};

type VoicingTemplate = {
  name: string;
  strings: number[]; // 1-6 (1 = high E)
  pattern: number[]; // Frets relative to root position, -1 = muted
  bassString: number;
  intervalMap: number[]; // Musical intervals for each string in the pattern
  shiftable: boolean; // true = can be shifted up/down like a barre; false = position-specific (open strings)
};

/** Common guitar chord voicing templates (string set + fret pattern) */
const FULL_VOICING_TEMPLATES: VoicingTemplate[] = [
  // E-shape barre (root on string 6, E open = root) - plays: R, 5, M3, R, 5, R
  {
    name: "E-shape",
    strings: [1, 2, 3, 4, 5, 6],
    pattern: [0, 0, 1, 2, 2, 0],
    bassString: 6,
    intervalMap: [0, 7, 4, 0, 7, 0],
    shiftable: true,
  },
  // A-shape barre (root on string 5, A open = root) - plays: 5, M3, R, 5, R
  {
    name: "A-shape",
    strings: [1, 2, 3, 4, 5],
    pattern: [0, 2, 2, 2, 0],
    bassString: 5,
    intervalMap: [7, 4, 0, 7, 0],
    shiftable: true,
  },
  // C-shape (root on string 5) - plays: M3, R, 5, M3, R
  {
    name: "C-shape",
    strings: [1, 2, 3, 4, 5],
    pattern: [0, 1, 0, 2, 3],
    bassString: 5,
    intervalMap: [4, 0, 7, 4, 0],
    shiftable: false,
  },
  // D-shape (root on string 4, higher voicing) - plays: M3, R, 5, R
  {
    name: "D-shape",
    strings: [1, 2, 3, 4],
    pattern: [2, 3, 2, 0],
    bassString: 4,
    intervalMap: [4, 0, 7, 0],
    shiftable: false,
  },
  // G-shape (root on string 6) - plays: R, 5, R, 5, M3, R
  {
    name: "G-shape",
    strings: [1, 2, 3, 4, 5, 6],
    pattern: [3, 3, 0, 0, 2, 3],
    bassString: 6,
    intervalMap: [0, 7, 0, 7, 4, 0],
    shiftable: false,
  },
];

/** Templates for minor chords (m3 instead of M3) */
const MINOR_VOICING_TEMPLATES: VoicingTemplate[] = [
  // E-minor shape (root on string 6, E open = root) - plays: R, 5, m3, R, 5, R
  {
    name: "Em-shape",
    strings: [1, 2, 3, 4, 5, 6],
    pattern: [0, 0, 0, 2, 2, 0],
    bassString: 6,
    intervalMap: [0, 7, 3, 0, 7, 0],
    shiftable: true,
  },
  // A-minor shape (root on string 5, A open = root) - plays: 5, m3, R, 5, R
  {
    name: "Am-shape",
    strings: [1, 2, 3, 4, 5],
    pattern: [0, 1, 2, 2, 0],
    bassString: 5,
    intervalMap: [7, 3, 0, 7, 0],
    shiftable: true,
  },
];

/** Templates for minor 7th chords (R, m3, 5, m7) */
const MINOR7_VOICING_TEMPLATES: VoicingTemplate[] = [
  // Dm7 shape (root on string 4, D open = root) - plays: m3, m7, 5, R
  {
    name: "Dm7-shape",
    strings: [1, 2, 3, 4],
    pattern: [1, 1, 2, 0],
    bassString: 4,
    intervalMap: [3, 10, 7, 0],
    shiftable: false,
  },
  // Em7 shape (root on string 6, E open = root) - plays: R, 5, m3, m7, 5, R
  {
    name: "Em7-shape",
    strings: [1, 2, 3, 4, 5, 6],
    pattern: [0, 0, 0, 0, 2, 0],
    bassString: 6,
    intervalMap: [0, 7, 3, 10, 7, 0],
    shiftable: true,
  },
  // Am7 shape (root on string 5, A open = root) - plays: 5, m3, m7, 5, R
  {
    name: "Am7-shape",
    strings: [1, 2, 3, 4, 5],
    pattern: [0, 1, 0, 2, 0],
    bassString: 5,
    intervalMap: [7, 3, 10, 7, 0],
    shiftable: true,
  },
];

export type VoicingMode = "full" | "compact";
export type PositionPreference = "open" | "low" | "mid";

export interface FretboardCell {
  string: number; // 1-6 (1 = high E)
  fret: number;
  midi: number;
  interval: number; // Semitones from root (0 = root, 4 = M3, etc.)
}

/**
 * Parse a chord symbol into root note and quality
 * Handles formats like "C:maj", "F#:min7", "Bb:7", "N" (no chord)
 */
export function parseChordSymbol(
  chordSymbol: string,
): { root: string; quality: string } | null {
  if (!chordSymbol || chordSymbol === "N") return null;

  // Extract root (1-2 chars: letter + optional # or b)
  const rootMatch = chordSymbol.match(/^([A-G][#b]?)/);
  if (!rootMatch) return null;
  const root = rootMatch[1];

  // Get the rest of the string after the root
  const afterRoot = chordSymbol.slice(rootMatch[0].length);

  // Extract quality (everything after optional colon, or the remainder if no colon)
  let quality = "maj"; // default

  if (afterRoot.startsWith(":")) {
    // Format: C:maj, C:min7, etc.
    quality = afterRoot.slice(1).trim();
  } else if (afterRoot.length > 0) {
    // Format: Cmaj, Cm, C7, etc. (no colon)
    quality = afterRoot.trim();
  }

  // Normalize quality names - be careful with order of checks
  const q = quality.toLowerCase();

  // Check for specific patterns first (longer/exact matches before shorter)
  if (q === "7b9" || q === "7♭9") quality = "7b9";
  else if (q === "7#9" || q === "7♯9") quality = "7#9";
  else if (q === "7b5" || q === "7♭5") quality = "7b5";
  else if (q === "7#5" || q === "7♯5") quality = "7#5";
  else if (q === "alt7") quality = "alt7";
  else if (q === "dim7" || q === "°7" || q === "o7") quality = "dim7";
  else if (q === "11") quality = "11";
  else if (q === "13") quality = "13";
  else if (q.includes("maj9")) quality = "maj9";
  else if (q.includes("maj7") || q === "M7") quality = "maj7";
  else if (q.includes("min9") || q === "m9") quality = "min9";
  else if (q.includes("min7") || q === "m7") quality = "min7";
  else if (q.includes("9")) quality = "9";
  else if (q.includes("7sus4")) quality = "7sus4";
  else if (q.includes("sus4")) quality = "sus4";
  else if (q.includes("sus2")) quality = "sus2";
  else if (q.includes("min6") || q === "m6") quality = "min6";
  else if (q.includes("6")) quality = "6";
  else if (q === "dim" || q === "°" || q === "o") quality = "dim";
  else if (q === "aug" || q === "+") quality = "aug";
  else if (q === "min" || q === "m" || q === "minor") quality = "min";
  else if (q === "maj" || q === "M" || q === "major" || q === "")
    quality = "maj";
  else if (q === "7") quality = "7";

  return { root, quality };
}

/**
 * Convert note name to MIDI pitch class (0-11)
 */
export function noteToPitchClass(note: string): number {
  const NOTE_MAP: Record<string, number> = {
    C: 0,
    "C#": 1,
    Db: 1,
    D: 2,
    "D#": 3,
    Eb: 3,
    E: 4,
    F: 5,
    "F#": 6,
    Gb: 6,
    G: 7,
    "G#": 8,
    Ab: 8,
    A: 9,
    "A#": 10,
    Bb: 10,
    B: 11,
  };
  return NOTE_MAP[note] ?? 0;
}

/**
 * Build a compact voicing (3-4 notes, close position, easy to read)
 */
function buildCompactVoicing(
  rootMidi: number,
  intervals: number[],
  position: PositionPreference,
): FretboardCell[] {
  // Use first 3-4 intervals (root position triad/quadad)
  const usedIntervals = intervals.slice(0, 4);

  // Find lowest fret position that can play all notes
  const cells: FretboardCell[] = [];
  const usedRows = new Set<number>(); // Track which string rows are already occupied

  for (const interval of usedIntervals) {
    const targetMidi = rootMidi + interval;
    const possibleCells = allCellsForMidi(targetMidi);

    if (possibleCells.length === 0) continue;

    // Pick cell based on position preference, avoiding already-used strings
    let selectedCell: { row: number; fret: number } | null = null;

    if (position === "open") {
      // Prefer open strings (fret 0) on unused strings
      selectedCell =
        possibleCells.find((c) => c.fret === 0 && !usedRows.has(c.row)) ??
        possibleCells.find((c) => !usedRows.has(c.row)) ??
        possibleCells[0];
    } else if (position === "low") {
      // Already sorted by lowest fret; prefer unused strings
      selectedCell =
        possibleCells.find((c) => !usedRows.has(c.row)) ??
        possibleCells[0];
    } else if (position === "mid") {
      // Prefer position around fret 5 on unused strings
      selectedCell =
        possibleCells.find((c) => c.fret >= 3 && c.fret <= 7 && !usedRows.has(c.row)) ??
        possibleCells.find((c) => !usedRows.has(c.row)) ??
        possibleCells.find((c) => c.fret >= 3 && c.fret <= 7) ??
        possibleCells[Math.floor(possibleCells.length / 2)];
    }

    if (!selectedCell) continue;

    usedRows.add(selectedCell.row);
    cells.push({
      string: selectedCell.row + 1, // Convert 0-indexed row to 1-indexed string
      fret: selectedCell.fret,
      midi: targetMidi,
      interval,
    });
  }

  // Ensure we have at least root + 2 more notes
  if (cells.length < 3) {
    // Fall back: add root on different string if needed
    const rootCells = allCellsForMidi(rootMidi);
    const extraRoot = rootCells.find((c) => !usedRows.has(c.row));
    if (extraRoot) {
      cells.push({
        string: extraRoot.row + 1,
        fret: extraRoot.fret,
        midi: rootMidi,
        interval: 0,
      });
    }
  }

  return cells;
}

/**
 * Build a full voicing (authentic guitar chord shape with proper voice leading)
 */
function buildFullVoicing(
  rootMidi: number,
  intervals: number[],
  position: PositionPreference,
): FretboardCell[] {
  const rootPc = rootMidi % 12;

  // Select template based on chord quality
  const isMinor = intervals.includes(3) && !intervals.includes(4);
  const isMinor7 = isMinor && intervals.includes(10);

  let allTemplates = FULL_VOICING_TEMPLATES;
  if (isMinor7) {
    allTemplates = MINOR7_VOICING_TEMPLATES;
  } else if (isMinor) {
    allTemplates = MINOR_VOICING_TEMPLATES;
  }

  const getStringPc = (stringIndex: number): number => {
    // String indices: 1=high E(4), 2=B(11), 3=G(7), 4=D(2), 5=A(9), 6=low E(4)
    return [4, 11, 7, 2, 9, 4][stringIndex - 1] ?? 4;
  };

  // Calculate baseFret per template: semitones from open bass string to root
  const baseFretForTemplate = (t: VoicingTemplate): number =>
    (rootPc - getStringPc(t.bassString) + 12) % 12;

  // Check if a non-shiftable template's fixed pattern produces the correct root
  const templateMatchesRoot = (t: VoicingTemplate): boolean => {
    const bassIdx = t.strings.indexOf(t.bassString);
    if (bassIdx < 0) return false;
    const patternFret = t.pattern[bassIdx];
    if (patternFret < 0) return false;
    const stringRow = t.bassString - 1;
    const notePc = (OPEN_MIDI_BY_ROW[stringRow] + patternFret) % 12;
    return notePc === rootPc;
  };

  // Select template: prefer non-shiftable (position-specific) first when they match,
  // otherwise fall back to shiftable (barre-able) templates
  const nonShiftableMatch = allTemplates.find(
    (t) => !t.shiftable && templateMatchesRoot(t),
  );

  let template: VoicingTemplate;
  let baseFret: number;

  if (nonShiftableMatch) {
    // Non-shiftable templates encode absolute fret positions in their pattern
    template = nonShiftableMatch;
    baseFret = 0;
  } else {
    // Use only shiftable (barre-able) templates for the position-based selection
    const shiftableTemplates = allTemplates.filter((t) => t.shiftable);
    if (shiftableTemplates.length === 0) {
      return buildCompactVoicing(rootMidi, intervals, position);
    }

    template = shiftableTemplates[0];
    baseFret = baseFretForTemplate(template);

    if (shiftableTemplates.length > 1) {
      if (position === "low") {
        // Find template with the lowest base fret (closest to nut)
        let bestBf = baseFret;
        let bestT = template;
        for (let i = 1; i < shiftableTemplates.length; i++) {
          const bf = baseFretForTemplate(shiftableTemplates[i]);
          if (bf < bestBf) { bestBf = bf; bestT = shiftableTemplates[i]; }
        }
        template = bestT;
        baseFret = bestBf;
      } else if (position === "open") {
        // For open position, find a template whose bassString naturally has the root
        // in a low fret position (preferably 0)
        let bestT = shiftableTemplates[0];
        const bf0 = baseFretForTemplate(shiftableTemplates[0]);
        let bestDist = Math.min(bf0, 12 - bf0); // circular distance
        for (let i = 1; i < shiftableTemplates.length; i++) {
          const bf = baseFretForTemplate(shiftableTemplates[i]);
          const dist = Math.min(bf, 12 - bf);
          if (dist < bestDist) {
            bestDist = dist;
            bestT = shiftableTemplates[i];
          }
        }
        template = bestT;
        baseFret = baseFretForTemplate(template);
      } else if (position === "mid") {
        // Find template with base fret in the 5-8 range, or lowest above 5
        let bestT = template;
        let bestBf = baseFret;
        for (let i = 1; i < shiftableTemplates.length; i++) {
          const bf = baseFretForTemplate(shiftableTemplates[i]);
          const adj = bf < 5 ? bf + 12 : bf;
          const bestAdj = bestBf < 5 ? bestBf + 12 : bestBf;
          if (adj < bestAdj) { bestBf = bf; bestT = shiftableTemplates[i]; }
        }
        template = bestT;
        baseFret = baseFretForTemplate(template);
        if (baseFret < 5) baseFret += 12;
      }
    }
  }

  // Build voicing from template using the intervalMap
  const cells: FretboardCell[] = [];

  for (let i = 0; i < template.strings.length; i++) {
    const stringNum = template.strings[i];
    const fretOffset = template.pattern[i];
    if (fretOffset < 0) continue; // Muted string

    const fret = baseFret + fretOffset;
    const stringRow = stringNum - 1; // Convert 1-indexed string to 0-indexed row (0 = high E)
    const midi = OPEN_MIDI_BY_ROW[stringRow] + fret;

    // Use the interval from the template's intervalMap
    const interval = template.intervalMap[i];

    cells.push({
      string: stringNum,
      fret,
      midi,
      interval,
    });
  }

  // If we have too few chord tones, fall back to compact voicing
  if (cells.length < 3) {
    return buildCompactVoicing(rootMidi, intervals, position);
  }

  return cells;
}

/**
 * Convert a chord symbol to fretboard positions
 *
 * @param chordSymbol - Chord symbol like "C:maj", "F#:min7", "N"
 * @param mode - 'full' for authentic guitar voicings, 'compact' for simplified triads
 * @param position - 'open', 'low', or 'mid' fretboard position preference
 * @returns Array of fretboard cells, or empty array if chord is "N" or unparseable
 */
export function chordToFretboardCells(
  chordSymbol: string,
  mode: VoicingMode = "compact",
  position: PositionPreference = "low",
): FretboardCell[] {
  const parsed = parseChordSymbol(chordSymbol);
  if (!parsed) return [];

  const { root, quality } = parsed;
  const rootPc = noteToPitchClass(root);

  // Determine octave - use octave 3 (MIDI 48-59) as base for E-string chords
  // This puts chords in playable range
  const baseOctave = 3;
  const rootMidi = rootPc + (baseOctave + 1) * 12; // MIDI 60 = C4 as reference

  // Get intervals for this quality
  const intervals =
    CHORD_QUALITY_INTERVALS[quality] ?? CHORD_QUALITY_INTERVALS.maj;

  // Build voicing based on mode
  if (mode === "compact") {
    return buildCompactVoicing(rootMidi, intervals, position);
  } else {
    return buildFullVoicing(rootMidi, intervals, position);
  }
}

/**
 * Get a display name for a chord quality
 */
export function getChordQualityDisplay(quality: string): string {
  const DISPLAY_NAMES: Record<string, string> = {
    maj: "",
    min: "m",
    dim: "°",
    dim7: "°7",
    aug: "+",
    "7": "7",
    maj7: "maj7",
    min7: "m7",
    "7sus4": "7sus4",
    sus4: "sus4",
    sus2: "sus2",
    "6": "6",
    min6: "m6",
    "9": "9",
    maj9: "maj9",
    min9: "m9",
    "7b9": "7♭9",
    "7#9": "7♯9",
    "7b5": "7♭5",
    "7#5": "7♯5",
    alt7: "alt7",
    "11": "11",
    "13": "13",
  };
  return DISPLAY_NAMES[quality] ?? quality;
}

/**
 * Format chord symbol for display (compact notation)
 * "C:maj" → "C", "F#:min7" → "F#m7", "Bb:maj7" → "Bbmaj7"
 */
export function formatChordDisplay(chordSymbol: string): string {
  const parsed = parseChordSymbol(chordSymbol);
  if (!parsed) return chordSymbol === "N" ? "—" : chordSymbol;

  const { root, quality } = parsed;
  const qualityDisplay = getChordQualityDisplay(quality);
  return `${root}${qualityDisplay}`;
}
