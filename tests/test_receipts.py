import os

import pytest

from services.websearch import WebSearchService


def test_receipts_whitelist(monkeypatch):
    monkeypatch.setenv("EVIDENCE_WHITELIST", "nature.com,nei.nih.gov")
    service = WebSearchService()

    assert service.validate_links("See https://nature.com/research") is True
    assert service.validate_links("Visit https://unknown.com/data") is False
    assert service.validate_links("No links here") is False

    assert service.has_valid_citation("https://nei.nih.gov/update") is True
    assert service.has_valid_citation("https://random.io") is False
