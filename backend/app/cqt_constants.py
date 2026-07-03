"""Shared CQT feature constants for training and inference.

Single source of truth — all extraction scripts, training, and inference
import from here instead of re-declaring constants.
"""

BINS_PER_OCTAVE = 24
NUM_OCTAVES = 6
CHROMA_BINS = BINS_PER_OCTAVE * NUM_OCTAVES  # 144
BASS_BINS = 0
FEATURE_DIM = CHROMA_BINS  # 144
WINDOW = 128
HOP_FRAMES = 64
TARGET_SR = 44100
HOP_SEC = 0.1
