"""AI/ML enhanced quantitative trading system — Python research layer.

Invariants (AGENTS.md):
  1. Causality is one-directional: any computation only uses data with
     available_at <= bar.close.
  2. Every accept/reject decision is auditable.
  3. Thresholds come from distributions, never from performance grid search.
"""

__version__ = "0.2.0-data"
