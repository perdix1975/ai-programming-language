import json
from pathlib import Path

import pytest

from apl.errors import VerificationError
from apl.verify import verify_program


CORPUS_DIR = Path(__file__).parent / "negative"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_negative_corpus_manifest_is_complete_and_unique():
    cases = load_manifest()
    listed = [case["file"] for case in cases]
    assert len(listed) == len(set(listed)), "negative corpus manifest contains duplicate files"

    actual = sorted(path.name for path in CORPUS_DIR.glob("*.apl"))
    assert sorted(listed) == actual, "manifest and negative .apl corpus differ"


@pytest.mark.parametrize("case", load_manifest(), ids=lambda case: case["file"])
def test_negative_corpus_case(case):
    program = json.loads((CORPUS_DIR / case["file"]).read_text(encoding="utf-8"))

    with pytest.raises(VerificationError) as captured:
        verify_program(program)

    message = str(captured.value)
    for fragment in case["contains"]:
        assert fragment in message
