from apl.canonical import canonical_text, semantic_hash
from apl.errors import ExecutionError, VerificationError
from apl.interpreter import run_program
from apl.verify import verify_program


def sample_program(version="0.0.1"):
    return {
        "apl": version,
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


def functions_if_program():
    return {
        "apl": "0.0.2",
        "module": "functions_if",
        "entry": "main",
        "functions": [
            {
                "name": "choose",
                "params": [
                    {"name": "flag", "type": "bool"},
                    {"name": "a", "type": "i64"},
                    {"name": "b", "type": "i64"},
                ],
                "returns": "i64",
                "body": [
                    {
                        "op": "if",
                        "id": "selected",
                        "type": "i64",
                        "cond": "flag",
                        "then": [{"op": "yield", "value": "a"}],
                        "else": [{"op": "yield", "value": "b"}],
                    },
                    {"op": "return", "value": "selected"},
                ],
            },
            {
                "name": "main",
                "params": [],
                "returns": "i64",
                "body": [
                    {"op": "const", "id": "flag", "type": "bool", "value": True},
                    {"op": "const", "id": "x", "type": "i64", "value": 42},
                    {"op": "const", "id": "y", "type": "i64", "value": 7},
                    {
                        "op": "call",
                        "id": "answer",
                        "type": "i64",
                        "function": "choose",
                        "args": ["flag", "x", "y"],
                    },
                    {"op": "return", "value": "answer"},
                ],
            },
        ],
    }


def test_verify_and_run():
    p = sample_program()
    verify_program(p)
    result = run_program(p, output=lambda _: None)
    assert result.value == 42
    assert result.type == "i64"


def test_v001_remains_supported():
    verify_program(sample_program("0.0.1"))


def test_functions_and_structured_if():
    p = functions_if_program()
    verify_program(p)
    result = run_program(p, output=lambda _: None)
    assert result.value == 42
    assert result.type == "i64"


def test_if_executes_only_selected_branch():
    p = functions_if_program()
    choose = p["functions"][0]
    choose["body"][0]["then"] = [
        {"op": "const", "id": "t", "type": "string", "value": "then"},
        {"op": "print", "args": ["t"]},
        {"op": "yield", "value": "a"},
    ]
    choose["body"][0]["else"] = [
        {"op": "const", "id": "e", "type": "string", "value": "else"},
        {"op": "print", "args": ["e"]},
        {"op": "yield", "value": "b"},
    ]
    lines = []
    result = run_program(p, output=lines.append)
    assert result.value == 42
    assert lines == ["then"]


def test_forward_function_reference_is_valid():
    p = functions_if_program()
    p["functions"].reverse()
    verify_program(p)
    assert run_program(p, output=lambda _: None).value == 42


def test_rejects_call_type_mismatch():
    p = functions_if_program()
    call = p["functions"][1]["body"][3]
    call["args"][0] = "x"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "expects 'bool', got 'i64'" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_rejects_recursive_call_cycle():
    p = {
        "apl": "0.0.2",
        "module": "recursive",
        "entry": "main",
        "functions": [
            {
                "name": "main",
                "params": [],
                "returns": "i64",
                "body": [
                    {"op": "call", "id": "x", "type": "i64", "function": "loop", "args": []},
                    {"op": "return", "value": "x"},
                ],
            },
            {
                "name": "loop",
                "params": [],
                "returns": "i64",
                "body": [
                    {"op": "call", "id": "x", "type": "i64", "function": "loop", "args": []},
                    {"op": "return", "value": "x"},
                ],
            },
        ],
    }
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "recursive call cycle" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_v001_rejects_v002_ops():
    p = functions_if_program()
    p["apl"] = "0.0.1"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "requires APL 0.0.2" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


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
