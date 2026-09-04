"""Excel / CSV WBS import.

Column names in real world WBS files are never consistent, so the importer
matches headers against a synonym dictionary, and always lets the user correct
the mapping in the UI before the data is committed.
"""
from .column_mapping import FIELD_LABELS, FIELD_SYNONYMS, guess_mapping  # noqa: F401
from .excel import analyze_upload, commit_import, load_frame  # noqa: F401
