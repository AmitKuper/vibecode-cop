"""Barrier-distillation experiment (2026-08-21 overnight, research-only).

Question: can a NET learn the barrier behavior of the search stack
(minimax d4 + stall-squeeze) by imitation, in the sighted (chebyshev)
regime where barriers actually matter?

Production firewall: nothing here touches MANIFEST.json, champions, or any
serving path. Checkpoints land in results/barrier_distill/ (gitignored);
the only committed outputs are this package and the results doc.
"""
