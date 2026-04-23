/**
 * Discovery agent for song recommendations based on harmonic similarity and user progress (commit 91).
 * Suggests next songs based on mastered content to keep users engaged.
 */

import { calculateHarmonicSimilarity, type SongHarmonicProfile } from '@/src/music/harmonicSimilarity'

export interface SkillNode {
  id: string
  label?: string | null
  score?: number
}

export interface MasteredSong {
  job_id: string
  song_title: string | null
  artist: string | null
  key: string | null
  style_label: string | null
  tempo: number | null
}

export interface DiscoverySuggestion {
  job_id: string
  song_title: string | null
  artist: string | null
  key: string | null
  style_label: string | null
  tempo: number | null
  reasonLabel: string
  similarityScore: number
  techniqueFocus: string
}

/**
 * Generate a context-aware reason label for a recommendation.
 */
function generateReasonLabel(
  masteredSong: MasteredSong,
  recommendedSong: MasteredSong,
  similarity: number,
  skillNodes: SkillNode[]
): string {
  const masteredTitle = masteredSong.song_title || 'a song'
  const masteredKey = masteredSong.key || ''
  const recommendedTitle = recommendedSong.song_title || 'this song'
  const recommendedKey = recommendedSong.key || ''
  
  // Check for specific skill focus
  const highScoreNodes = skillNodes.filter(n => n.score && n.score > 0.8)
  if (highScoreNodes.length > 0) {
    const topSkill = highScoreNodes[0].label || 'a technique'
    return `You mastered ${topSkill} in ${masteredTitle}. Try ${recommendedTitle} to apply it in ${recommendedKey || 'a new key'}.`
  }
  
  // Key-based recommendations
  if (similarity > 0.8 && masteredKey && recommendedKey) {
    return `Similar harmonic structure to ${masteredTitle} (${masteredKey}). Try ${recommendedTitle} (${recommendedKey}) to reinforce your progress.`
  }
  
  if (similarity > 0.5) {
    return `Related harmonic material to ${masteredTitle}. ${recommendedTitle} will help you expand your ${recommendedKey || 'harmonic'} vocabulary.`
  }
  
  // Style-based recommendations
  if (masteredSong.style_label && recommendedSong.style_label && masteredSong.style_label === recommendedSong.style_label) {
    return `Build on your ${masteredSong.style_label} skills from ${masteredTitle}. ${recommendedTitle} offers a new challenge in the same style.`
  }
  
  return `Continue your musical journey from ${masteredTitle}. ${recommendedTitle} is a great next step to broaden your repertoire.`
}

/**
 * Extract technique focus from skill nodes.
 */
function extractTechniqueFocus(skillNodes: SkillNode[]): string {
  const techniqueMap: Record<string, string> = {
    'bend_accuracy': 'Bending',
    'vibrato_control': 'Vibrato',
    'timing': 'Timing',
    'phrasing': 'Phrasing',
    'pitch_accuracy': 'Pitch',
  }
  
  const highScoreNodes = skillNodes.filter(n => n.score && n.score > 0.7)
  if (highScoreNodes.length > 0) {
    const topNode = highScoreNodes[0]
    return techniqueMap[topNode.id] || 'Technique'
  }
  
  return 'Technique'
}

/**
 * Generate discovery suggestions based on user's mastered songs and skill progress.
 */
export function generateDiscoverySuggestions(
  masteredSongs: MasteredSong[],
  candidateSongs: MasteredSong[],
  skillNodes: SkillNode[],
  options?: { limit?: number; minSimilarity?: number }
): DiscoverySuggestion[] {
  const limit = options?.limit ?? 5
  const minSimilarity = options?.minSimilarity ?? 0.3
  
  if (masteredSongs.length === 0 || candidateSongs.length === 0) {
    return []
  }
  
  // Filter out already mastered songs from candidates
  const masteredIds = new Set(masteredSongs.map(s => s.job_id))
  const unmasteredCandidates = candidateSongs.filter(s => !masteredIds.has(s.job_id))
  
  if (unmasteredCandidates.length === 0) {
    return []
  }
  
  const suggestions: DiscoverySuggestion[] = []
  
  // For each mastered song, find similar candidates
  for (const mastered of masteredSongs) {
    const masteredProfile: SongHarmonicProfile = {
      key: mastered.key,
      style: mastered.style_label,
      tempo: mastered.tempo,
    }
    
    for (const candidate of unmasteredCandidates) {
      const candidateProfile: SongHarmonicProfile = {
        key: candidate.key,
        style: candidate.style_label,
        tempo: candidate.tempo,
      }
      
      const similarity = calculateHarmonicSimilarity(masteredProfile, candidateProfile)
      
      if (similarity >= minSimilarity) {
        const techniqueFocus = extractTechniqueFocus(skillNodes)
        const reasonLabel = generateReasonLabel(mastered, candidate, similarity, skillNodes)
        
        suggestions.push({
          job_id: candidate.job_id,
          song_title: candidate.song_title,
          artist: candidate.artist,
          key: candidate.key,
          style_label: candidate.style_label,
          tempo: candidate.tempo,
          reasonLabel,
          similarityScore: similarity,
          techniqueFocus,
        })
      }
    }
  }
  
  // Sort by similarity score and limit results
  const sorted = suggestions.sort((a, b) => b.similarityScore - a.similarityScore)
  const unique = Array.from(new Map(sorted.map(s => [s.job_id, s])).values())
  
  return unique.slice(0, limit)
}

/**
 * Generate discovery suggestions from a single mastered song.
 * Useful when user just completed a specific lesson.
 */
export function generateDiscoveryFromLesson(
  masteredSong: MasteredSong,
  candidateSongs: MasteredSong[],
  skillNodes: SkillNode[],
  options?: { limit?: number; minSimilarity?: number }
): DiscoverySuggestion[] {
  return generateDiscoverySuggestions([masteredSong], candidateSongs, skillNodes, options)
}
