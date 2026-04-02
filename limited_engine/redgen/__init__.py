"""
RedGen v2 Package
=================
Cybersecurity test case generator using templates, payloads, and LLM paraphrasing.
"""

from .generator import TestCaseGenerator
from .utils.output import save_outputs

__all__ = ["TestCaseGenerator", "save_outputs"]