"""
websearch.py
------------

The websearch module implements a minimal evidence gate for the
DaLeoBanks agent. Its primary purpose is to validate that generated
content includes at least one citation to a credible external source.
Because network requests may not be possible in the deployment
environment, the implementation uses simple heuristics rather than
actual web search APIs.

Credible citations are recognized via URL patterns. Domains ending in
``.gov``, ``.edu`` or well‑known international news sources are
considered trustworthy. This list can be extended over time. The
``WebSearchService`` exposes helper methods to extract URLs from
content and to verify their credibility.
"""

from __future__ import annotations

import re
from typing import List


class WebSearchService:
    """Evidence gate that validates citations in generated content."""

    # Regular expression to find URLs in text. This pattern is simple
    # and intentionally permissive. It can be tightened if needed.
    URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)

    # Domains that are treated as trustworthy by default. News sources
    # can be added here; wildcards are not supported.
    TRUSTED_DOMAINS = [
        "gov",
        "edu",
        "bbc.co.uk",
        "nytimes.com",
        "theguardian.com",
        "reuters.com",
        "apnews.com",
        "bloomberg.com",
    ]

    def extract_urls(self, text: str) -> List[str]:
        """Return all URL substrings found in the input text."""
        if not text:
            return []
        return self.URL_REGEX.findall(text)

    def is_trusted(self, url: str) -> bool:
        """Check whether the given URL belongs to a trusted domain."""
        try:
            domain = url.split("//", 1)[-1].split("/", 1)[0]
        except Exception:
            return False
        for trusted in self.TRUSTED_DOMAINS:
            if domain.endswith(trusted):
                return True
        return False

    def has_valid_citation(self, text: str) -> bool:
        """Determine whether at least one credible citation exists in text.

        The method extracts all URLs from the input and returns True as
        soon as it finds one belonging to a trusted domain. If no
        trusted domains are present, it returns False.
        """
        for url in self.extract_urls(text):
            if self.is_trusted(url):
                return True
        return False


__all__ = ["WebSearchService"]