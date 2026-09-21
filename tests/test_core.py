from apl.canonical import canonical_text, semantic_hash
from apl.errors import ExecutionError, VerificationError
from apl.interpreter import run_program
from apl.verify import verify_program


def sample_program():
    return {
        "apl": "0.0.1",
        "module": "test",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "body": [
                {"op": "const", "id": "a", "type": "i64", "value": 40},
                {"op": "const", "id": "b", "type": "i64", "value": 2},
                {"op": "add", "id": "c", "type": "i64", "args": ["a", "b"]},
                {"op": "return", "value": "c"},
            ],
        }],
    }


def test_verify_and_run():
    p = sample_program()
    verify_program(p)
    result = run_program(p, output=lambda _: None)
    assert result.value == 42
    assert result.type == "i64"


def test_rejects_use_before_definition():
    p = sample_program()
    p["functions"][0]["body"][2]["args"][0] = "missing"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "not defined before use" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_rejects_duplicate_ssa_id():
    p = sample_program()
    p["functions"][0]["body"][1]["id"] = "a"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "already defined" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_i64_overflow_is_defined_as_runtime_error():
    p = sample_program()
    p["functions"][0]["body"][0]["value"] = 2**63 - 1
    p["functions"][0]["body"][1]["value"] = 1
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert "overflow" in str(exc)
    else:
        raise AssertionError("expected ExecutionError")


def test_canonical_encoding_and_hash_are_stable():
    p = sample_program()
    a = canonical_text(p)
    b = canonical_text(dict(reversed(list(p.items()))))
    assert a == b
    assert semantic_hash(p) == semantic_hash(dict(reversed(list(p.items()))))
