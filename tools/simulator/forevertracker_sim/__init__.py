"""Synthetic ForeverTracker data. DEVELOPMENT ONLY.

Everything produced here is marked ``synthetic: true``. The production API refuses synthetic
batches, and dungeon/encounter IDs are in the synthetic 990000+ range so they can never be
mistaken for real Forever IDs.
"""

from forevertracker_sim.world import SimConfig, simulate

__all__ = ["SimConfig", "simulate"]
