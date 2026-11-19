import json
import os

import pytest

from ledgerline import db
from ledgerline.llm.fake import CANNED_EXTRACTION, FakeClient
from ledgerline.reference import load_reference


@pytest.fixture(autouse=True)
def policy_flags_off(monkeypatch):
    """Every test starts with the Part 2 flags off, as AP_POLICY.md has it, whatever the shell exports."""
    for name in [key for key in os.environ if key.startswith("LEDGERLINE_FLAG_")]:
        monkeypatch.delenv(name)


@pytest.fixture
def ref():
    return load_reference()


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(str(tmp_path / "test.db"))
    yield connection
    connection.close()


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the real provider with the fake client for the duration of a test."""
    client = FakeClient([json.dumps(CANNED_EXTRACTION)] * 2)
    monkeypatch.setattr("ledgerline.extraction.get_client", lambda: client)
    return client
