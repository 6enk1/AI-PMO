"""Structured (deterministic) project analysis.

The AI PMO pipeline is intentionally layered:

    Structured Analysis (this package)  ->  LLM Reasoning  ->  Recommendation

Every number an LLM ever sees is computed here first, in plain Python, so that
findings are reproducible and every recommendation can cite its evidence.
"""
