"""Viterbi decoder for chord progression smoothing (Commit 99).

Implements the Viterbi algorithm to find the optimal chord sequence
given per-beat emission probabilities and a transition probability matrix.
Supports duration-aware penalties for sub-beat chord events.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger("harmoniq.inference.viterbi")

_LOG_FLOOR = 1e-30
_DOMINANT_QUALITIES: set[str] = set()  # empty in 25-class MIREX vocab


def _parse_quality(chord_label: str) -> str:
    """Extract quality from 'C:maj7' → 'maj7'. 'N' → 'N'."""
    if chord_label == "N":
        return "N"
    return chord_label.split(":", 1)[1]


def _build_dominant_mask(chord_vocab: list[str]) -> np.ndarray:
    """Pre-compute boolean mask for dominant chord qualities."""
    return np.array([_parse_quality(c) in _DOMINANT_QUALITIES for c in chord_vocab])


class ViterbiChordDecoder:
    """Viterbi decoder for chord sequence optimization.

    Uses a pre-computed log transition probability matrix and per-beat
    emission log-probabilities to find the most likely chord path.
    """

    def __init__(
        self,
        transition_log_probs: np.ndarray,
        vocab_size: int = 25,
        chord_vocab: list[str] | None = None,
    ):
        """Initialize decoder with transition probabilities.

        Args:
            transition_log_probs: Shape [vocab_size, vocab_size],
                pre-computed log probabilities of chord transitions.
            vocab_size: Number of chord classes (default 277).
            chord_vocab: List of chord labels for duration-penalty logic.
        """
        self.vocab_size = vocab_size
        self.transition_log_probs = transition_log_probs.astype(np.float64)
        self.chord_vocab = chord_vocab
        self._dominant_mask = _build_dominant_mask(chord_vocab) if chord_vocab else None

    def decode(
        self,
        emission_log_probs: np.ndarray,
        duration_beats: np.ndarray | None = None,
        duration_penalty_weight: float = 0.5,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run Viterbi decoding to find optimal chord sequence.

        Args:
            emission_log_probs: Shape [T, vocab_size], log-probability of
                each chord at each time step.
            duration_beats: Shape [T], duration of each step in beat units.
                Values < 1.0 trigger duration penalties.
            duration_penalty_weight: Lambda for sub-beat penalty strength.

        Returns:
            Tuple of (optimal_path, path_log_probs):
                - optimal_path: Shape [T], chord index at each time step.
                - path_log_probs: Shape [T], cumulative log prob at each step.
        """
        T = emission_log_probs.shape[0]
        N = self.vocab_size

        if T == 0:
            return np.array([], dtype=np.int32), np.array([], dtype=np.float64)

        if T == 1:
            path = np.array([int(np.argmax(emission_log_probs[0]))], dtype=np.int32)
            return path, emission_log_probs[0, path[0]]

        # Pre-allocate forward trellis and backpointers
        delta = np.full((T, N), -np.inf, dtype=np.float64)
        psi = np.zeros((T, N), dtype=np.int32)

        # --- Initialization (t=0) ---
        delta[0] = self._apply_duration_penalty(
            emission_log_probs[0].copy(),
            duration_beats[0] if duration_beats is not None else 1.0,
            duration_penalty_weight,
            state_idx=None,
        )

        # --- Forward pass ---
        for t in range(1, T):
            # Vectorized: scores[i,j] = delta[t-1,i] + trans_log[i,j]
            scores = delta[t - 1][:, None] + self.transition_log_probs

            # Best predecessor for each state j
            psi[t] = np.argmax(scores, axis=0)
            delta[t] = np.max(scores, axis=0)

            # Apply emission + duration penalty
            dur = duration_beats[t] if duration_beats is not None else 1.0
            delta[t] += self._apply_duration_penalty(
                emission_log_probs[t].copy(),
                dur,
                duration_penalty_weight,
                state_idx=None,  # full vector penalty
            )

            # Numerical stability guard
            max_delta = np.max(delta[t])
            if max_delta < -1e6:
                logger.warning(
                    "Viterbi delta collapsed at t=%d (max=%.1f). "
                    "All paths have very low probability.",
                    t, max_delta,
                )

        # --- Backtracking ---
        optimal_path = np.zeros(T, dtype=np.int32)
        optimal_path[T - 1] = int(np.argmax(delta[T - 1]))

        for t in range(T - 2, -1, -1):
            optimal_path[t] = psi[t + 1, optimal_path[t + 1]]

        path_log_probs = delta[np.arange(T), optimal_path]

        logger.info(
            "Viterbi decoded %d steps, final log-prob=%.2f",
            T, path_log_probs[-1],
        )

        return optimal_path, path_log_probs

    def _apply_duration_penalty(
        self,
        emission_lp: np.ndarray,
        duration: float,
        penalty_weight: float,
        state_idx: int | None = None,
    ) -> np.ndarray:
        """Apply duration-aware penalty to emission log-probabilities.

        Sub-beat chords (duration < 1.0) are penalized unless they are
        dominant-type chords that naturally resolve quickly.
        """
        if duration >= 1.0:
            return emission_lp

        base_penalty = penalty_weight * (1.0 - duration)

        if self._dominant_mask is None:
            if state_idx is not None:
                emission_lp[state_idx] -= base_penalty
            else:
                emission_lp -= base_penalty
            return emission_lp

        if state_idx is not None:
            if self._dominant_mask[state_idx]:
                emission_lp[state_idx] -= base_penalty * 0.5
            else:
                emission_lp[state_idx] -= base_penalty
        else:
            emission_lp -= base_penalty
            emission_lp[self._dominant_mask] += base_penalty * 0.5

        return emission_lp


def probs_to_log_probs(probs: np.ndarray, floor: float = _LOG_FLOOR) -> np.ndarray:
    """Convert probability distributions to log-probabilities with floor guard.

    Args:
        probs: Array of probabilities (any shape).
        floor: Minimum value before taking log to avoid -inf.

    Returns:
        Log-probabilities of same shape as input.
    """
    return np.log(np.maximum(probs, floor))
