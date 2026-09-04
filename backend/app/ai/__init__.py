"""LLM reasoning layer.

The LLM never sees raw project rows. It only receives the structured findings
produced by :mod:`app.analysis`, and it may only rewrite narrative fields -
evidence, scores and detected causes stay exactly as computed in Python.
"""
from .llm import LLMResult, enrich_findings  # noqa: F401
