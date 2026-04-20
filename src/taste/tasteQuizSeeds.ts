/**
 * 24 curated artists for cold-start taste quiz (PRIORITIES §69) — static, not fetched.
 * Six styles × four artists; style tag is shown as a chip (not Spotify genres).
 */
export type TasteQuizArtist = {
  id: string
  name: string
  styleTag: string
}

export const TASTE_QUIZ_ARTISTS: readonly TasteQuizArtist[] = [
  { id: 'bb-king', name: 'B.B. King', styleTag: 'Blues' },
  { id: 'srv', name: 'Stevie Ray Vaughan', styleTag: 'Blues' },
  { id: 'buddy-guy', name: 'Buddy Guy', styleTag: 'Blues' },
  { id: 'albert-king', name: 'Albert King', styleTag: 'Blues' },
  { id: 'zeppelin', name: 'Led Zeppelin', styleTag: 'Rock' },
  { id: 'acdc', name: 'AC/DC', styleTag: 'Rock' },
  { id: 'queen', name: 'Queen', styleTag: 'Rock' },
  { id: 'foo-fighters', name: 'Foo Fighters', styleTag: 'Rock' },
  { id: 'chet-atkins', name: 'Chet Atkins', styleTag: 'Fingerstyle' },
  { id: 'tommy-emmanuel', name: 'Tommy Emmanuel', styleTag: 'Fingerstyle' },
  { id: 'leo-kottke', name: 'Leo Kottke', styleTag: 'Fingerstyle' },
  { id: 'michael-hedges', name: 'Michael Hedges', styleTag: 'Fingerstyle' },
  { id: 'miles-davis', name: 'Miles Davis', styleTag: 'Jazz' },
  { id: 'coltrane', name: 'John Coltrane', styleTag: 'Jazz' },
  { id: 'herbie', name: 'Herbie Hancock', styleTag: 'Jazz' },
  { id: 'wes-montgomery', name: 'Wes Montgomery', styleTag: 'Jazz' },
  { id: 'johnny-cash', name: 'Johnny Cash', styleTag: 'Country' },
  { id: 'willie-nelson', name: 'Willie Nelson', styleTag: 'Country' },
  { id: 'brad-paisley', name: 'Brad Paisley', styleTag: 'Country' },
  { id: 'alison-krauss', name: 'Alison Krauss', styleTag: 'Country' },
  { id: 'metallica', name: 'Metallica', styleTag: 'Metal' },
  { id: 'iron-maiden', name: 'Iron Maiden', styleTag: 'Metal' },
  { id: 'black-sabbath', name: 'Black Sabbath', styleTag: 'Metal' },
  { id: 'judas-priest', name: 'Judas Priest', styleTag: 'Metal' },
] as const

export type TasteQuizVibeId = 'blues' | 'rock' | 'fingerstyle' | 'jazz'

export const TASTE_QUIZ_VIBE_CARDS: ReadonlyArray<{
  id: TasteQuizVibeId
  title: string
  blurb: string
}> = [
  {
    id: 'blues',
    title: 'Blues feel',
    blurb: 'Bends, call-and-response phrasing, and room to breathe behind the beat.',
  },
  {
    id: 'rock',
    title: 'Rock energy',
    blurb: 'Power, drive, and big riffs — tight rhythm and confident downstrokes.',
  },
  {
    id: 'fingerstyle',
    title: 'Fingerstyle calm',
    blurb: 'Thumb independence, soft dynamics, and chord melody textures.',
  },
  {
    id: 'jazz',
    title: 'Jazz complexity',
    blurb: 'Extensions, voice-leading, and comping vocabulary over changes.',
  },
]
