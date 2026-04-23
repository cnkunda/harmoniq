"""
Discovery agent for song recommendations based on harmonic similarity (commit 91).
Suggests next songs based on mastered content to keep users engaged.
"""

from dataclasses import dataclass
from typing import Iterable

from app.schemas import LessonJSON, SkillNode


@dataclass(frozen=True)
class SongHarmonicProfile:
    """Harmonic profile of a song for similarity calculation."""
    key: str | None
    style: str | None
    tempo: float | None


def _parse_key_label(key_label: str | None) -> tuple[str | None, str | None]:
    """Extract root note and mode from key label."""
    if not key_label:
        return (None, None)
    
    # Parse key format: "C major", "A minor", "C", "A", etc.
    parts = key_label.strip().split()
    if not parts:
        return (None, None)
    
    root = parts[0]
    mode = parts[1].lower() if len(parts) > 1 else "major"
    
    if mode not in ("major", "minor"):
        mode = "major"
    
    return (root, mode)


def _key_similarity(key1: str | None, key2: str | None) -> float:
    """Calculate harmonic similarity between two keys (0.0 to 1.0)."""
    if not key1 or not key2:
        return 0.0
    if key1 == key2:
        return 1.0
    
    root1, mode1 = _parse_key_label(key1)
    root2, mode2 = _parse_key_label(key2)
    
    if not root1 or not root2:
        return 0.0
    
    # Identical root and mode
    if root1 == root2 and mode1 == mode2:
        return 1.0
    
    # Relative major/minor relationship (e.g., C major ↔ A minor)
    if root1 == root2 and mode1 != mode2:
        return 0.8
    
    # Perfect fourth/fifth relationships
    note_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    try:
        idx1 = note_names.index(root1)
        idx2 = note_names.index(root2)
    except ValueError:
        return 0.0
    
    interval = abs(idx2 - idx1)
    
    # Perfect fifth (7 semitones) or perfect fourth (5 semitones)
    if interval == 7 or interval == 5:
        return 0.7
    
    # Third relationships (3 or 4 semitones)
    if interval == 3 or interval == 4:
        return 0.5
    
    # Second relationships (1 or 2 semitones)
    if interval == 1 or interval == 2:
        return 0.3
    
    return 0.2


def _style_similarity(style1: str | None, style2: str | None) -> float:
    """Calculate style similarity between two songs (0.0 to 1.0)."""
    if not style1 or not style2:
        return 0.0
    if style1 == style2:
        return 1.0
    
    s1 = style1.lower().strip()
    s2 = style2.lower().strip()
    
    # Partial matches
    if s1 in s2 or s2 in s1:
        return 0.7
    
    # Related style groups
    style_groups = {
        "rock": ["rock", "blues rock", "hard rock", "classic rock"],
        "blues": ["blues", "blues rock", "delta blues"],
        "jazz": ["jazz", "fusion", "smooth jazz"],
        "folk": ["folk", "acoustic", "singer-songwriter"],
        "metal": ["metal", "heavy metal", "thrash"],
        "pop": ["pop", "indie pop"],
        "country": ["country", "country rock"],
    }
    
    for base, variants in style_groups.items():
        if any(s1 in v for v in variants) and any(s2 in v for v in variants):
            return 0.6
    
    return 0.2


def _tempo_similarity(tempo1: float | None, tempo2: float | None) -> float:
    """Calculate tempo similarity between two songs (0.0 to 1.0)."""
    if not tempo1 or not tempo2:
        return 0.0
    
    diff = abs(tempo1 - tempo2)
    
    if diff <= 5:
        return 1.0
    if diff <= 15:
        return 0.8
    if diff <= 30:
        return 0.5
    
    return 0.2


def calculate_harmonic_similarity(song1: SongHarmonicProfile, song2: SongHarmonicProfile) -> float:
    """Calculate overall harmonic similarity between two songs (0.0 to 1.0)."""
    key_score = _key_similarity(song1.key, song2.key)
    style_score = _style_similarity(song1.style, song2.style)
    tempo_score = _tempo_similarity(song1.tempo, song2.tempo)
    
    # Weighted average: key is most important for harmonic similarity
    return key_score * 0.5 + style_score * 0.3 + tempo_score * 0.2


def _extract_technique_focus(skill_nodes: list[SkillNode]) -> str:
    """Extract technique focus from skill nodes."""
    technique_map = {
        "bend_accuracy": "Bending",
        "vibrato_control": "Vibrato",
        "timing": "Timing",
        "phrasing": "Phrasing",
        "pitch_accuracy": "Pitch",
    }
    
    high_score_nodes = [n for n in skill_nodes if n.score and n.score > 0.7]
    if high_score_nodes:
        top_node = high_score_nodes[0]
        return technique_map.get(top_node.id, "Technique")
    
    return "Technique"


def _generate_reason_label(
    mastered_song: LessonJSON,
    recommended_song: LessonJSON,
    similarity: float,
    skill_nodes: list[SkillNode],
) -> str:
    """Generate a context-aware reason label for a recommendation."""
    mastered_title = mastered_song.song_title or "a song"
    mastered_key = mastered_song.key or ""
    recommended_title = recommended_song.song_title or "this song"
    recommended_key = recommended_song.key or ""
    
    # Check for specific skill focus
    high_score_nodes = [n for n in skill_nodes if n.score and n.score > 0.8]
    if high_score_nodes:
        top_skill = high_score_nodes[0].label or "a technique"
        return f"You mastered {top_skill} in {mastered_title}. Try {recommended_title} to apply it in {recommended_key or 'a new key'}."
    
    # Key-based recommendations
    if similarity > 0.8 and mastered_key and recommended_key:
        return f"Similar harmonic structure to {mastered_title} ({mastered_key}). Try {recommended_title} ({recommended_key}) to reinforce your progress."
    
    if similarity > 0.5:
        return f"Related harmonic material to {mastered_title}. {recommended_title} will help you expand your {recommended_key or 'harmonic'} vocabulary."
    
    # Style-based recommendations
    if mastered_song.style_label and recommended_song.style_label and mastered_song.style_label == recommended_song.style_label:
        return f"Build on your {mastered_song.style_label} skills from {mastered_title}. {recommended_title} offers a new challenge in the same style."
    
    return f"Continue your musical journey from {mastered_title}. {recommended_title} is a great next step to broaden your repertoire."


@dataclass(frozen=True)
class DiscoverySuggestion:
    """A single discovery suggestion."""
    job_id: str
    song_title: str | None
    artist: str | None
    key: str | None
    style_label: str | None
    tempo: float | None
    reason_label: str
    similarity_score: float
    technique_focus: str


def generate_discovery_suggestions(
    mastered_lessons: list[LessonJSON],
    candidate_lessons: list[LessonJSON],
    skill_nodes: list[SkillNode],
    limit: int = 5,
    min_similarity: float = 0.3,
) -> list[DiscoverySuggestion]:
    """
    Generate discovery suggestions based on user's mastered songs and skill progress.
    
    Args:
        mastered_lessons: Lessons the user has completed/mastered
        candidate_lessons: Lessons to consider as recommendations
        skill_nodes: User's skill progress data
        limit: Maximum number of suggestions to return
        min_similarity: Minimum similarity score threshold
    
    Returns:
        List of discovery suggestions sorted by similarity score (descending)
    """
    if not mastered_lessons or not candidate_lessons:
        return []
    
    # Filter out already mastered lessons from candidates
    mastered_ids = {(l.job_id or "").strip() for l in mastered_lessons if l.job_id}
    unmastered_candidates = [l for l in candidate_lessons if (l.job_id or "").strip() not in mastered_ids]
    
    if not unmastered_candidates:
        return []
    
    suggestions: list[DiscoverySuggestion] = []
    
    # For each mastered lesson, find similar candidates
    for mastered in mastered_lessons:
        mastered_profile = SongHarmonicProfile(
            key=mastered.key,
            style=mastered.style_label,
            tempo=float(mastered.tempo) if mastered.tempo else None,
        )
        
        for candidate in unmastered_candidates:
            candidate_profile = SongHarmonicProfile(
                key=candidate.key,
                style=candidate.style_label,
                tempo=float(candidate.tempo) if candidate.tempo else None,
            )
            
            similarity = calculate_harmonic_similarity(mastered_profile, candidate_profile)
            
            if similarity >= min_similarity:
                technique_focus = _extract_technique_focus(skill_nodes)
                reason_label = _generate_reason_label(mastered, candidate, similarity, skill_nodes)
                
                suggestions.append(
                    DiscoverySuggestion(
                        job_id=(candidate.job_id or "").strip(),
                        song_title=candidate.song_title,
                        artist=candidate.artist,
                        key=candidate.key,
                        style_label=candidate.style_label,
                        tempo=float(candidate.tempo) if candidate.tempo else None,
                        reason_label=reason_label,
                        similarity_score=round(similarity, 6),
                        technique_focus=technique_focus,
                    )
                )
    
    # Sort by similarity score and limit results
    sorted_suggestions = sorted(suggestions, key=lambda s: (-s.similarity_score, s.job_id))
    
    # Remove duplicates by job_id
    seen_ids = set()
    unique_suggestions = []
    for s in sorted_suggestions:
        if s.job_id not in seen_ids:
            seen_ids.add(s.job_id)
            unique_suggestions.append(s)
    
    return unique_suggestions[:limit]
