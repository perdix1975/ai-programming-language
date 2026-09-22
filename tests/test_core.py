from apl.canonical import canonical_text, semantic_hash
from apl.errors import ExecutionError, VerificationError
from apl.host import DeterministicHost
from apl.interpreter import run_program
from apl.resources import ResourceLimits
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
        assert exc.code == "apl.i64_overflow"
        assert exc.where == "main[2]"
        assert "overflow" in str(exc)
    else:
        raise AssertionError("expected ExecutionError")


def test_canonical_encoding_and_hash_are_stable():
    p = sample_program()
    a = canonical_text(p)
    b = canonical_text(dict(reversed(list(p.items()))))
    assert a == b
    assert semantic_hash(p) == semantic_hash(dict(reversed(list(p.items()))))


def binary_program(op, a, b, result_type="i64"):
    return {
        "apl": "0.0.3",
        "module": "binary",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": result_type,
            "body": [
                {"op": "const", "id": "a", "type": "i64", "value": a},
                {"op": "const", "id": "b", "type": "i64", "value": b},
                {"op": op, "id": "r", "type": result_type, "args": ["a", "b"]},
                {"op": "return", "value": "r"},
            ],
        }],
    }


def test_division_truncates_toward_zero():
    assert run_program(binary_program("div", -7, 3), output=lambda _: None).value == -2
    assert run_program(binary_program("div", 7, -3), output=lambda _: None).value == -2
    assert run_program(binary_program("div", -7, -3), output=lambda _: None).value == 2


def test_remainder_matches_truncating_division():
    assert run_program(binary_program("rem", -7, 3), output=lambda _: None).value == -1
    assert run_program(binary_program("rem", 7, -3), output=lambda _: None).value == 1
    assert run_program(binary_program("rem", -7, -3), output=lambda _: None).value == -1


def test_division_by_zero_is_defined_trap():
    try:
        run_program(binary_program("div", 1, 0), output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.division_by_zero"
        assert "division by zero" in str(exc)
    else:
        raise AssertionError("expected ExecutionError")


def test_division_min_by_minus_one_overflows():
    try:
        run_program(binary_program("div", -(2**63), -1), output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.i64_overflow"
        assert "overflow" in str(exc)
    else:
        raise AssertionError("expected ExecutionError")


def test_remainder_min_by_minus_one_is_zero():
    assert run_program(binary_program("rem", -(2**63), -1), output=lambda _: None).value == 0


def test_ordered_i64_comparisons():
    cases = [
        ("lt", 2, 3, True),
        ("le", 3, 3, True),
        ("gt", 4, 3, True),
        ("ge", 3, 3, True),
        ("lt", 4, 3, False),
    ]
    for op, a, b, expected in cases:
        result = run_program(binary_program(op, a, b, "bool"), output=lambda _: None)
        assert result.value is expected
        assert result.type == "bool"


def test_v002_rejects_v003_ops():
    p = binary_program("div", 6, 3)
    p["apl"] = "0.0.2"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "requires APL 0.0.3" in str(exc)
    else:
        raise AssertionError("expected VerificationError")



def repeat_program(count=5, maximum=10):
    return {
        "apl": "0.0.4",
        "module": "repeat",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "body": [
                {"op": "const", "id": "n", "type": "i64", "value": count},
                {"op": "const", "id": "one", "type": "i64", "value": 1},
                {
                    "op": "repeat",
                    "id": "factorial",
                    "type": "i64",
                    "count": "n",
                    "max": maximum,
                    "init": "one",
                    "index": "i",
                    "carry": "acc",
                    "body": [
                        {"op": "add", "id": "factor", "type": "i64", "args": ["i", "one"]},
                        {"op": "mul", "id": "next", "type": "i64", "args": ["acc", "factor"]},
                        {"op": "yield", "value": "next"},
                    ],
                },
                {"op": "return", "value": "factorial"},
            ],
        }],
    }


def test_bounded_repeat_factorial_and_zero_based_index():
    result = run_program(repeat_program(), output=lambda _: None)
    assert result.value == 120
    assert result.type == "i64"


def test_repeat_zero_count_returns_init():
    result = run_program(repeat_program(count=0), output=lambda _: None)
    assert result.value == 1


def test_repeat_count_above_max_traps_before_body_effects():
    p = repeat_program(count=3, maximum=2)
    body = p["functions"][0]["body"][2]["body"]
    body.insert(0, {"op": "print", "args": ["acc"]})
    lines = []
    try:
        run_program(p, output=lines.append)
    except ExecutionError as exc:
        assert exc.code == "apl.repeat_count_exceeds_max"
        assert "exceeds declared max 2" in str(exc)
        assert lines == []
    else:
        raise AssertionError("expected ExecutionError")


def test_repeat_negative_count_traps():
    try:
        run_program(repeat_program(count=-1), output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.repeat_negative_count"
        assert "must be non-negative" in str(exc)
    else:
        raise AssertionError("expected ExecutionError")


def test_repeat_rejects_excessive_static_max():
    p = repeat_program()
    p["functions"][0]["body"][2]["max"] = 1_000_001
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "repeat max must be in [0, 1000000]" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_repeat_region_names_cannot_shadow_outer_ssa():
    p = repeat_program()
    p["functions"][0]["body"][2]["carry"] = "one"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "collides with an outer SSA id" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_v003_rejects_repeat():
    p = repeat_program()
    p["apl"] = "0.0.3"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "repeat requires APL 0.0.4" in str(exc)
    else:
        raise AssertionError("expected VerificationError")



def array_type_i64_3():
    return {"array": "i64", "len": 3}


def array_program():
    arr_t = array_type_i64_3()
    return {
        "apl": "0.0.5",
        "module": "arrays",
        "entry": "main",
        "functions": [
            {
                "name": "second",
                "params": [{"name": "items", "type": arr_t}],
                "returns": "i64",
                "body": [
                    {"op": "const", "id": "idx", "type": "i64", "value": 1},
                    {"op": "array.get", "id": "value", "type": "i64", "args": ["items", "idx"]},
                    {"op": "return", "value": "value"},
                ],
            },
            {
                "name": "main",
                "params": [],
                "returns": "i64",
                "body": [
                    {"op": "const", "id": "a", "type": "i64", "value": 10},
                    {"op": "const", "id": "b", "type": "i64", "value": 20},
                    {"op": "const", "id": "c", "type": "i64", "value": 30},
                    {"op": "array", "id": "items", "type": arr_t, "args": ["a", "b", "c"]},
                    {"op": "call", "id": "second_value", "type": "i64", "function": "second", "args": ["items"]},
                    {"op": "array.len", "id": "length", "type": "i64", "args": ["items"]},
                    {"op": "add", "id": "answer", "type": "i64", "args": ["second_value", "length"]},
                    {"op": "return", "value": "answer"},
                ],
            },
        ],
    }


def test_fixed_array_construction_get_len_and_function_signature():
    p = array_program()
    verify_program(p)
    result = run_program(p, output=lambda _: None)
    assert result.value == 23
    assert result.type == "i64"


def test_array_get_out_of_bounds_traps():
    p = array_program()
    p["functions"][0]["body"][0]["value"] = 3
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.array_index_oob"
        assert "array index 3 out of bounds for length 3" in str(exc)
    else:
        raise AssertionError("expected ExecutionError")


def test_array_get_negative_index_traps():
    p = array_program()
    p["functions"][0]["body"][0]["value"] = -1
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.array_index_oob"
        assert "array index -1 out of bounds for length 3" in str(exc)
    else:
        raise AssertionError("expected ExecutionError")


def test_array_constructor_rejects_wrong_arity():
    p = array_program()
    p["functions"][1]["body"][3]["args"] = ["a", "b"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "array type length is 3, got 2 values" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_array_constructor_rejects_element_type_mismatch():
    p = array_program()
    main_body = p["functions"][1]["body"]
    main_body.insert(3, {"op": "const", "id": "flag", "type": "bool", "value": True})
    main_body[4]["args"][1] = "flag"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "incompatible element type" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_array_structural_equality():
    arr_t = {"array": "i64", "len": 2}
    p = {
        "apl": "0.0.5",
        "module": "array_eq",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "bool",
            "body": [
                {"op": "const", "id": "a", "type": "i64", "value": 1},
                {"op": "const", "id": "b", "type": "i64", "value": 2},
                {"op": "array", "id": "x", "type": arr_t, "args": ["a", "b"]},
                {"op": "array", "id": "y", "type": arr_t, "args": ["a", "b"]},
                {"op": "eq", "id": "same", "type": "bool", "args": ["x", "y"]},
                {"op": "return", "value": "same"},
            ],
        }],
    }
    result = run_program(p, output=lambda _: None)
    assert result.value is True


def test_empty_fixed_array_len():
    empty_t = {"array": "i64", "len": 0}
    p = {
        "apl": "0.0.5",
        "module": "empty_array",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "body": [
                {"op": "array", "id": "items", "type": empty_t, "args": []},
                {"op": "array.len", "id": "length", "type": "i64", "args": ["items"]},
                {"op": "return", "value": "length"},
            ],
        }],
    }
    assert run_program(p, output=lambda _: None).value == 0


def test_array_type_length_cap():
    p = array_program()
    p["functions"][0]["params"][0]["type"]["len"] = 65_537
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "array length must be in [0, 65536]" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_v004_rejects_array_op():
    p = array_program()
    p["apl"] = "0.0.4"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "array types require APL 0.0.5" in str(exc)
    else:
        raise AssertionError("expected VerificationError")



def person_type():
    return {"record": {"name": "string", "age": "i64"}}


def record_program():
    p_type = person_type()
    return {
        "apl": "0.0.6",
        "module": "records",
        "entry": "main",
        "functions": [
            {
                "name": "age_of",
                "params": [{"name": "person", "type": p_type}],
                "returns": "i64",
                "body": [
                    {
                        "op": "record.get",
                        "id": "age",
                        "type": "i64",
                        "record": "person",
                        "field": "age",
                    },
                    {"op": "return", "value": "age"},
                ],
            },
            {
                "name": "main",
                "params": [],
                "returns": "i64",
                "body": [
                    {"op": "const", "id": "name", "type": "string", "value": "Ada"},
                    {"op": "const", "id": "age", "type": "i64", "value": 37},
                    {
                        "op": "record",
                        "id": "person",
                        "type": p_type,
                        "fields": {"age": "age", "name": "name"},
                    },
                    {
                        "op": "call",
                        "id": "answer",
                        "type": "i64",
                        "function": "age_of",
                        "args": ["person"],
                    },
                    {"op": "return", "value": "answer"},
                ],
            },
        ],
    }


def test_record_construction_get_and_function_signature():
    p = record_program()
    verify_program(p)
    result = run_program(p, output=lambda _: None)
    assert result.value == 37
    assert result.type == "i64"


def test_record_equality_is_structural_and_field_order_independent():
    p_type = person_type()
    p = {
        "apl": "0.0.6",
        "module": "record_eq",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "bool",
            "body": [
                {"op": "const", "id": "name", "type": "string", "value": "Ada"},
                {"op": "const", "id": "age", "type": "i64", "value": 37},
                {
                    "op": "record",
                    "id": "a",
                    "type": {"record": {"name": "string", "age": "i64"}},
                    "fields": {"name": "name", "age": "age"},
                },
                {
                    "op": "record",
                    "id": "b",
                    "type": {"record": {"age": "i64", "name": "string"}},
                    "fields": {"age": "age", "name": "name"},
                },
                {"op": "eq", "id": "same", "type": "bool", "args": ["a", "b"]},
                {"op": "return", "value": "same"},
            ],
        }],
    }
    result = run_program(p, output=lambda _: None)
    assert result.value is True


def test_record_constructor_requires_exact_field_set():
    p = record_program()
    p["functions"][1]["body"][2]["fields"] = {"name": "name"}
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "record fields must exactly match the record type" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_record_constructor_rejects_field_type_mismatch():
    p = record_program()
    p["functions"][1]["body"][2]["fields"]["age"] = "name"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "record field 'age' has incompatible type" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_record_get_rejects_unknown_field():
    p = record_program()
    get_op = p["functions"][0]["body"][0]
    get_op["field"] = "missing"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "record field 'missing' does not exist" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_record_can_contain_fixed_array_field():
    values_t = {"array": "i64", "len": 2}
    box_t = {"record": {"values": values_t}}
    p = {
        "apl": "0.0.6",
        "module": "nested_record",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "body": [
                {"op": "const", "id": "a", "type": "i64", "value": 4},
                {"op": "const", "id": "b", "type": "i64", "value": 9},
                {"op": "array", "id": "values", "type": values_t, "args": ["a", "b"]},
                {
                    "op": "record",
                    "id": "box",
                    "type": box_t,
                    "fields": {"values": "values"},
                },
                {
                    "op": "record.get",
                    "id": "unboxed",
                    "type": values_t,
                    "record": "box",
                    "field": "values",
                },
                {"op": "array.len", "id": "length", "type": "i64", "args": ["unboxed"]},
                {"op": "return", "value": "length"},
            ],
        }],
    }
    result = run_program(p, output=lambda _: None)
    assert result.value == 2


def test_empty_record_is_valid():
    empty_t = {"record": {}}
    p = {
        "apl": "0.0.6",
        "module": "empty_record",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "bool",
            "body": [
                {"op": "record", "id": "a", "type": empty_t, "fields": {}},
                {"op": "record", "id": "b", "type": empty_t, "fields": {}},
                {"op": "eq", "id": "same", "type": "bool", "args": ["a", "b"]},
                {"op": "return", "value": "same"},
            ],
        }],
    }
    assert run_program(p, output=lambda _: None).value is True


def test_record_field_cap():
    too_many = {"record": {f"f{i}": "i64" for i in range(257)}}
    p = record_program()
    p["functions"][0]["params"][0]["type"] = too_many
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "record may contain at most 256 fields" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_v005_rejects_record_type():
    p = record_program()
    p["apl"] = "0.0.5"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "record types require APL 0.0.6" in str(exc)
    else:
        raise AssertionError("expected VerificationError")



def explicit_trap_program(code="app.invalid_state", message="invalid state"):
    return {
        "apl": "0.0.7",
        "module": "explicit_trap",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "body": [
                {"op": "trap", "code": code, "message": message},
            ],
        }],
    }


def test_explicit_trap_is_valid_function_terminator():
    p = explicit_trap_program()
    verify_program(p)
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "app.invalid_state"
        assert exc.message == "invalid state"
        assert exc.where == "main[0]"
        assert str(exc) == "[app.invalid_state] main[0]: invalid state"
    else:
        raise AssertionError("expected ExecutionError")


def test_trap_can_terminate_one_if_branch():
    p = {
        "apl": "0.0.7",
        "module": "trap_if",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "body": [
                {"op": "const", "id": "cond", "type": "bool", "value": False},
                {
                    "op": "if",
                    "id": "result",
                    "type": "i64",
                    "cond": "cond",
                    "then": [
                        {"op": "trap", "code": "app.unreachable", "message": "bad branch"}
                    ],
                    "else": [
                        {"op": "const", "id": "value", "type": "i64", "value": 42},
                        {"op": "yield", "value": "value"},
                    ],
                },
                {"op": "return", "value": "result"},
            ],
        }],
    }
    assert run_program(p, output=lambda _: None).value == 42


def test_selected_trap_branch_aborts():
    p = {
        "apl": "0.0.7",
        "module": "trap_if_selected",
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "body": [
                {"op": "const", "id": "cond", "type": "bool", "value": True},
                {
                    "op": "if",
                    "id": "result",
                    "type": "i64",
                    "cond": "cond",
                    "then": [
                        {"op": "trap", "code": "app.selected", "message": "selected trap"}
                    ],
                    "else": [
                        {"op": "const", "id": "value", "type": "i64", "value": 42},
                        {"op": "yield", "value": "value"},
                    ],
                },
                {"op": "return", "value": "result"},
            ],
        }],
    }
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "app.selected"
        assert exc.where == "main[1].then[0]"
    else:
        raise AssertionError("expected ExecutionError")


def test_explicit_trap_cannot_use_reserved_apl_namespace():
    p = explicit_trap_program(code="apl.division_by_zero")
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "namespace 'apl.*' is reserved" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_explicit_trap_code_has_canonical_syntax():
    p = explicit_trap_program(code="Bad Code")
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "trap code must match" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_explicit_trap_message_is_bounded():
    p = explicit_trap_program(message="x" * 513)
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "trap message length must be in [1, 512]" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_instruction_after_trap_is_rejected():
    p = explicit_trap_program()
    p["functions"][0]["body"].append(
        {"op": "const", "id": "x", "type": "i64", "value": 1}
    )
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "instruction appears after terminator" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_v006_rejects_explicit_trap():
    p = explicit_trap_program()
    p["apl"] = "0.0.6"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "trap requires APL 0.0.7" in str(exc)
    else:
        raise AssertionError("expected VerificationError")



def effectful_program():
    return {
        "apl": "0.0.8",
        "module": "effects",
        "capabilities": ["console.write"],
        "entry": "main",
        "functions": [
            {
                "name": "emit",
                "params": [{"name": "message", "type": "string"}],
                "returns": "unit",
                "effects": ["console.write"],
                "body": [
                    {"op": "print", "args": ["message"]},
                    {"op": "return"},
                ],
            },
            {
                "name": "main",
                "params": [],
                "returns": "i64",
                "effects": ["console.write"],
                "body": [
                    {"op": "const", "id": "message", "type": "string", "value": "hello"},
                    {"op": "call", "function": "emit", "args": ["message"]},
                    {"op": "const", "id": "answer", "type": "i64", "value": 42},
                    {"op": "return", "value": "answer"},
                ],
            },
        ],
    }


def pure_v008_program():
    return {
        "apl": "0.0.8",
        "module": "pure",
        "capabilities": [],
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "effects": [],
            "body": [
                {"op": "const", "id": "answer", "type": "i64", "value": 42},
                {"op": "return", "value": "answer"},
            ],
        }],
    }


def test_v008_pure_program_needs_no_runtime_grants():
    p = pure_v008_program()
    verify_program(p)
    result = run_program(p, output=lambda _: None)
    assert result.value == 42


def test_effectful_program_verifies_with_exact_declarations():
    verify_program(effectful_program())


def test_effectful_program_requires_runtime_capability_grant():
    p = effectful_program()
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.capability_denied"
        assert exc.where == "<module>"
        assert "console.write" in exc.message
    else:
        raise AssertionError("expected ExecutionError")


def test_effectful_program_runs_with_grant():
    lines = []
    result = run_program(
        effectful_program(),
        output=lines.append,
        capabilities={"console.write"},
    )
    assert lines == ["hello"]
    assert result.value == 42


def test_caller_must_declare_callee_effects():
    p = effectful_program()
    p["functions"][1]["effects"] = []
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "declared effects [] do not match inferred effects ['console.write']" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_function_cannot_declare_unused_effect():
    p = pure_v008_program()
    p["functions"][0]["effects"] = ["console.write"]
    p["capabilities"] = ["console.write"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "declared effects ['console.write'] do not match inferred effects []" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_module_capabilities_must_exactly_match_function_effect_union():
    p = effectful_program()
    p["capabilities"] = []
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "capabilities must exactly match the union" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_capability_list_rejects_duplicates():
    p = effectful_program()
    p["capabilities"] = ["console.write", "console.write"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "sorted lexicographically with no duplicates" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_unknown_effect_is_rejected():
    p = pure_v008_program()
    p["functions"][0]["effects"] = ["network.telepathy"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "unsupported effect 'network.telepathy'" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_v008_requires_capabilities_and_function_effects_fields():
    p = pure_v008_program()
    del p["capabilities"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "capabilities must be a list" in str(exc)
    else:
        raise AssertionError("expected VerificationError")

    p = pure_v008_program()
    del p["functions"][0]["effects"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "main: effects must be a list" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_effect_in_unselected_if_branch_is_still_declared_statically():
    p = {
        "apl": "0.0.8",
        "module": "branch_effect",
        "capabilities": ["console.write"],
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "effects": ["console.write"],
            "body": [
                {"op": "const", "id": "cond", "type": "bool", "value": False},
                {"op": "const", "id": "a", "type": "i64", "value": 1},
                {"op": "const", "id": "b", "type": "i64", "value": 2},
                {
                    "op": "if",
                    "id": "result",
                    "type": "i64",
                    "cond": "cond",
                    "then": [
                        {"op": "print", "args": ["a"]},
                        {"op": "yield", "value": "a"},
                    ],
                    "else": [
                        {"op": "yield", "value": "b"},
                    ],
                },
                {"op": "return", "value": "result"},
            ],
        }],
    }
    verify_program(p)
    lines = []
    result = run_program(p, output=lines.append, capabilities={"console.write"})
    assert result.value == 2
    assert lines == []


def test_legacy_print_does_not_require_new_capability_grants():
    p = sample_program("0.0.1")
    p["functions"][0]["body"].insert(3, {"op": "print", "args": ["c"]})
    result = run_program(p, output=lambda _: None)
    assert result.value == 42



def host_io_program():
    return {
        "apl": "0.0.9",
        "module": "host_io",
        "capabilities": ["fs.read_text", "net.get_text"],
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "bool",
            "effects": ["fs.read_text", "net.get_text"],
            "body": [
                {"op": "const", "id": "path", "type": "string", "value": "/config.txt"},
                {
                    "op": "const",
                    "id": "url",
                    "type": "string",
                    "value": "https://example.test/data",
                },
                {
                    "op": "fs.read_text",
                    "id": "local",
                    "type": "string",
                    "args": ["path"],
                },
                {
                    "op": "net.get_text",
                    "id": "remote",
                    "type": "string",
                    "args": ["url"],
                },
                {"op": "eq", "id": "same", "type": "bool", "args": ["local", "remote"]},
                {"op": "return", "value": "same"},
            ],
        }],
    }


def host_fixture():
    return DeterministicHost(
        files={"/config.txt": "payload"},
        network={"https://example.test/data": "payload"},
    )


def test_deterministic_host_fs_and_network_reads():
    p = host_io_program()
    verify_program(p)
    result = run_program(
        p,
        output=lambda _: None,
        capabilities={"fs.read_text", "net.get_text"},
        host=host_fixture(),
    )
    assert result.value is True


def test_host_operations_require_interface_after_capability_grant():
    p = host_io_program()
    try:
        run_program(
            p,
            output=lambda _: None,
            capabilities={"fs.read_text", "net.get_text"},
        )
    except ExecutionError as exc:
        assert exc.code == "apl.host_unavailable"
        assert exc.where == "main[2]"
    else:
        raise AssertionError("expected ExecutionError")


def test_host_missing_resource_has_stable_trap():
    p = host_io_program()
    host = DeterministicHost(
        files={},
        network={"https://example.test/data": "payload"},
    )
    try:
        run_program(
            p,
            output=lambda _: None,
            capabilities={"fs.read_text", "net.get_text"},
            host=host,
        )
    except ExecutionError as exc:
        assert exc.code == "apl.host_resource_missing"
        assert "/config.txt" in exc.message
    else:
        raise AssertionError("expected ExecutionError")


def test_host_capability_denial_happens_before_execution():
    p = host_io_program()
    try:
        run_program(
            p,
            output=lambda _: None,
            capabilities={"fs.read_text"},
            host=host_fixture(),
        )
    except ExecutionError as exc:
        assert exc.code == "apl.capability_denied"
        assert exc.where == "<module>"
        assert "net.get_text" in exc.message
    else:
        raise AssertionError("expected ExecutionError")


def test_host_text_operation_requires_string_argument():
    p = host_io_program()
    p["functions"][0]["body"][0] = {
        "op": "const",
        "id": "path",
        "type": "i64",
        "value": 7,
    }
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "fs.read_text argument must have type 'string'" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_v008_rejects_v009_host_operation():
    p = {
        "apl": "0.0.8",
        "module": "old_host_op",
        "capabilities": [],
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "string",
            "effects": [],
            "body": [
                {"op": "const", "id": "path", "type": "string", "value": "/x"},
                {
                    "op": "fs.read_text",
                    "id": "value",
                    "type": "string",
                    "args": ["path"],
                },
                {"op": "return", "value": "value"},
            ],
        }],
    }
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "fs.read_text requires APL 0.0.9" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_v008_rejects_v009_effect_name():
    p = pure_v008_program()
    p["capabilities"] = ["fs.read_text"]
    p["functions"][0]["effects"] = ["fs.read_text"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "effect 'fs.read_text' requires APL 0.0.9" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_deterministic_host_copies_fixture_mappings():
    files = {"/a": "before"}
    network = {"https://example.test": "before"}
    host = DeterministicHost(files=files, network=network)
    files["/a"] = "after"
    network["https://example.test"] = "after"
    assert host.read_text("/a") == "before"
    assert host.get_text("https://example.test") == "before"


def test_deterministic_host_direct_constructor_validation():
    for files, network in [
        ({"/a": 1}, {}),
        ({}, {"https://example.test": 1}),
    ]:
        try:
            DeterministicHost(files=files, network=network)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")


def test_deterministic_host_json_fixture_validation():
    host = DeterministicHost.from_json_object(
        {
            "files": {"/a": "A"},
            "network": {"https://example.test": "B"},
        }
    )
    assert host.read_text("/a") == "A"
    assert host.get_text("https://example.test") == "B"

    for invalid in [
        [],
        {"files": {"/a": 1}},
        {"network": {"https://example.test": 1}},
        {"files": {}, "network": {}, "extra": {}},
    ]:
        try:
            DeterministicHost.from_json_object(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {invalid!r}")



def limited_pure_program(steps=2, output_lines=0, host_reads=0):
    return {
        "apl": "0.0.10",
        "module": "limited_pure",
        "capabilities": [],
        "limits": {
            "steps": steps,
            "output_lines": output_lines,
            "host_reads": host_reads,
        },
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "effects": [],
            "body": [
                {"op": "const", "id": "answer", "type": "i64", "value": 42},
                {"op": "return", "value": "answer"},
            ],
        }],
    }


def limited_print_program(output_lines=1):
    return {
        "apl": "0.0.10",
        "module": "limited_print",
        "capabilities": ["console.write"],
        "limits": {
            "steps": 10,
            "output_lines": output_lines,
            "host_reads": 0,
        },
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "effects": ["console.write"],
            "body": [
                {"op": "const", "id": "answer", "type": "i64", "value": 42},
                {"op": "print", "args": ["answer"]},
                {"op": "return", "value": "answer"},
            ],
        }],
    }


def limited_host_read_program(host_reads=1):
    return {
        "apl": "0.0.10",
        "module": "limited_host_read",
        "capabilities": ["fs.read_text"],
        "limits": {
            "steps": 10,
            "output_lines": 0,
            "host_reads": host_reads,
        },
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "string",
            "effects": ["fs.read_text"],
            "body": [
                {"op": "const", "id": "path", "type": "string", "value": "/x"},
                {
                    "op": "fs.read_text",
                    "id": "value",
                    "type": "string",
                    "args": ["path"],
                },
                {"op": "return", "value": "value"},
            ],
        }],
    }


def test_v010_exact_step_budget_succeeds():
    p = limited_pure_program(steps=2)
    verify_program(p)
    assert run_program(p, output=lambda _: None).value == 42


def test_v010_step_budget_exhaustion_is_deterministic():
    p = limited_pure_program(steps=1)
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.resource_limit"
        assert exc.where == "main[1]"
        assert "steps resource limit exhausted" in exc.message
    else:
        raise AssertionError("expected ExecutionError")


def test_host_step_limit_can_only_tighten_program_limit():
    p = limited_pure_program(steps=2)
    try:
        run_program(
            p,
            output=lambda _: None,
            limits=ResourceLimits(steps=1),
        )
    except ExecutionError as exc:
        assert exc.code == "apl.resource_limit"
        assert exc.where == "main[1]"
    else:
        raise AssertionError("expected ExecutionError")

    p = limited_pure_program(steps=1)
    try:
        run_program(
            p,
            output=lambda _: None,
            limits=ResourceLimits(steps=100),
        )
    except ExecutionError as exc:
        assert exc.code == "apl.resource_limit"
    else:
        raise AssertionError("host limit must not loosen program limit")


def test_output_line_budget_traps_before_output_effect():
    p = limited_print_program(output_lines=0)
    lines = []
    try:
        run_program(
            p,
            output=lines.append,
            capabilities={"console.write"},
        )
    except ExecutionError as exc:
        assert exc.code == "apl.resource_limit"
        assert exc.where == "main[1]"
        assert "output_lines resource limit exhausted" in exc.message
        assert lines == []
    else:
        raise AssertionError("expected ExecutionError")


def test_output_line_budget_allows_exact_number_of_lines():
    p = limited_print_program(output_lines=1)
    lines = []
    result = run_program(
        p,
        output=lines.append,
        capabilities={"console.write"},
    )
    assert lines == ["42"]
    assert result.value == 42


def test_host_read_budget_traps_before_lookup():
    p = limited_host_read_program(host_reads=0)
    host = DeterministicHost(files={"/x": "value"}, network={})
    try:
        run_program(
            p,
            output=lambda _: None,
            capabilities={"fs.read_text"},
            host=host,
        )
    except ExecutionError as exc:
        assert exc.code == "apl.resource_limit"
        assert exc.where == "main[1]"
        assert "host_reads resource limit exhausted" in exc.message
    else:
        raise AssertionError("expected ExecutionError")


def test_host_read_budget_allows_exact_number_of_reads():
    p = limited_host_read_program(host_reads=1)
    host = DeterministicHost(files={"/x": "value"}, network={})
    result = run_program(
        p,
        output=lambda _: None,
        capabilities={"fs.read_text"},
        host=host,
    )
    assert result.value == "value"


def test_v010_requires_exact_limits_object():
    p = limited_pure_program()
    del p["limits"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "limits must be an object" in str(exc)
    else:
        raise AssertionError("expected VerificationError")

    p = limited_pure_program()
    p["limits"]["extra"] = 1
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "limits must contain exactly" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_v010_rejects_invalid_program_limits():
    for field, value, fragment in [
        ("steps", -1, "limits.steps must be in [0, 10000000]"),
        ("steps", 10_000_001, "limits.steps must be in [0, 10000000]"),
        ("output_lines", -1, "limits.output_lines must be in [0, 1000000]"),
        ("host_reads", 1_000_001, "limits.host_reads must be in [0, 1000000]"),
    ]:
        p = limited_pure_program()
        p["limits"][field] = value
        try:
            verify_program(p)
        except VerificationError as exc:
            assert fragment in str(exc)
        else:
            raise AssertionError("expected VerificationError")


def test_resource_limits_python_api_validation():
    invalid = [
        {"steps": -1},
        {"steps": 10_000_001},
        {"output_lines": -1},
        {"host_reads": 1_000_001},
    ]
    for kwargs in invalid:
        try:
            ResourceLimits(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {kwargs}")


def test_explicit_host_limits_can_bound_legacy_programs():
    p = sample_program("0.0.1")
    try:
        run_program(
            p,
            output=lambda _: None,
            limits=ResourceLimits(steps=2),
        )
    except ExecutionError as exc:
        assert exc.code == "apl.resource_limit"
        assert exc.where == "main[2]"
    else:
        raise AssertionError("expected ExecutionError")



def contract_clause(contract_id, message, predicate):
    return {"id": contract_id, "message": message, "predicate": predicate}


def var(name):
    return {"var": name}


def result_ref():
    return {"result": True}


def contract_const(typ, value):
    return {"const": {"type": typ, "value": value}}


def predicate(op, *args):
    return {"op": op, "args": list(args)}


def contract_program(argument=3):
    return {
        "apl": "0.0.11",
        "module": "contracts",
        "capabilities": [],
        "limits": {"steps": 100, "output_lines": 0, "host_reads": 0},
        "entry": "main",
        "functions": [
            {
                "name": "double_positive",
                "params": [{"name": "x", "type": "i64"}],
                "returns": "i64",
                "effects": [],
                "requires": [
                    contract_clause(
                        "positive_input",
                        "x must be positive",
                        predicate("gt", var("x"), contract_const("i64", 0)),
                    )
                ],
                "ensures": [
                    contract_clause(
                        "larger_result",
                        "result must be larger than x",
                        predicate("gt", result_ref(), var("x")),
                    )
                ],
                "body": [
                    {"op": "add", "id": "answer", "type": "i64", "args": ["x", "x"]},
                    {"op": "return", "value": "answer"},
                ],
            },
            {
                "name": "main",
                "params": [],
                "returns": "i64",
                "effects": [],
                "requires": [],
                "ensures": [],
                "body": [
                    {"op": "const", "id": "x", "type": "i64", "value": argument},
                    {
                        "op": "call",
                        "id": "answer",
                        "type": "i64",
                        "function": "double_positive",
                        "args": ["x"],
                    },
                    {"op": "return", "value": "answer"},
                ],
            },
        ],
    }


def test_v011_preconditions_and_postconditions_pass():
    p = contract_program()
    verify_program(p)
    result = run_program(p, output=lambda _: None)
    assert result.value == 6


def test_precondition_failure_has_stable_trap():
    p = contract_program(argument=0)
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.precondition_failed"
        assert exc.where == "double_positive.requires[0]"
        assert "positive_input" in exc.message
        assert "x must be positive" in exc.message
    else:
        raise AssertionError("expected ExecutionError")


def test_precondition_failure_happens_before_body_effect():
    p = {
        "apl": "0.0.11",
        "module": "pre_effect",
        "capabilities": ["console.write"],
        "limits": {"steps": 100, "output_lines": 10, "host_reads": 0},
        "entry": "main",
        "functions": [
            {
                "name": "emit_positive",
                "params": [{"name": "x", "type": "i64"}],
                "returns": "i64",
                "effects": ["console.write"],
                "requires": [
                    contract_clause(
                        "positive",
                        "positive required",
                        predicate("gt", var("x"), contract_const("i64", 0)),
                    )
                ],
                "ensures": [],
                "body": [
                    {"op": "print", "args": ["x"]},
                    {"op": "return", "value": "x"},
                ],
            },
            {
                "name": "main",
                "params": [],
                "returns": "i64",
                "effects": ["console.write"],
                "requires": [],
                "ensures": [],
                "body": [
                    {"op": "const", "id": "x", "type": "i64", "value": 0},
                    {
                        "op": "call",
                        "id": "answer",
                        "type": "i64",
                        "function": "emit_positive",
                        "args": ["x"],
                    },
                    {"op": "return", "value": "answer"},
                ],
            },
        ],
    }
    lines = []
    try:
        run_program(p, output=lines.append, capabilities={"console.write"})
    except ExecutionError as exc:
        assert exc.code == "apl.precondition_failed"
        assert lines == []
    else:
        raise AssertionError("expected ExecutionError")


def test_postcondition_failure_occurs_after_body_effects():
    p = {
        "apl": "0.0.11",
        "module": "post_effect",
        "capabilities": ["console.write"],
        "limits": {"steps": 100, "output_lines": 10, "host_reads": 0},
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "effects": ["console.write"],
            "requires": [],
            "ensures": [
                contract_clause(
                    "impossible",
                    "result must be negative",
                    predicate("lt", result_ref(), contract_const("i64", 0)),
                )
            ],
            "body": [
                {"op": "const", "id": "answer", "type": "i64", "value": 42},
                {"op": "print", "args": ["answer"]},
                {"op": "return", "value": "answer"},
            ],
        }],
    }
    lines = []
    try:
        run_program(p, output=lines.append, capabilities={"console.write"})
    except ExecutionError as exc:
        assert exc.code == "apl.postcondition_failed"
        assert exc.where == "main.ensures[0]"
        assert lines == ["42"]
    else:
        raise AssertionError("expected ExecutionError")


def test_v011_requires_explicit_contract_lists():
    p = contract_program()
    del p["functions"][0]["requires"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "double_positive: requires must be a list" in str(exc)
    else:
        raise AssertionError("expected VerificationError")

    p = contract_program()
    del p["functions"][0]["ensures"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "double_positive: ensures must be a list" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_precondition_cannot_reference_result():
    p = contract_program()
    p["functions"][0]["requires"][0]["predicate"] = predicate(
        "gt", result_ref(), contract_const("i64", 0)
    )
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "function result is not available in this contract" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_unit_postcondition_cannot_reference_result():
    p = {
        "apl": "0.0.11",
        "module": "unit_contract",
        "capabilities": [],
        "limits": {"steps": 10, "output_lines": 0, "host_reads": 0},
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "unit",
            "effects": [],
            "requires": [],
            "ensures": [
                contract_clause(
                    "has_result",
                    "unit has no result",
                    predicate("eq", result_ref(), result_ref()),
                )
            ],
            "body": [{"op": "return"}],
        }],
    }
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "unit function has no result value" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_contract_predicate_must_be_bool():
    p = contract_program()
    p["functions"][0]["requires"][0]["predicate"] = var("x")
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "contract predicate must have type 'bool'" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_contract_unknown_variable_is_rejected():
    p = contract_program()
    p["functions"][0]["requires"][0]["predicate"] = predicate(
        "gt", var("missing"), contract_const("i64", 0)
    )
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "unknown contract variable 'missing'" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_contract_ids_unique_across_requires_and_ensures():
    p = contract_program()
    p["functions"][0]["ensures"][0]["id"] = "positive_input"
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "contract ids must be unique across requires/ensures" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_contract_eq_requires_identical_types():
    p = contract_program()
    p["functions"][0]["requires"][0]["predicate"] = predicate(
        "eq", var("x"), contract_const("string", "3")
    )
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "eq args must have identical types" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_contract_boolean_operators_are_eager_and_typed():
    p = contract_program()
    p["functions"][0]["requires"][0]["predicate"] = predicate(
        "and",
        predicate("gt", var("x"), contract_const("i64", 0)),
        predicate("lt", var("x"), contract_const("i64", 10)),
    )
    verify_program(p)
    assert run_program(p, output=lambda _: None).value == 6

    p = contract_program()
    p["functions"][0]["requires"][0]["predicate"] = predicate(
        "not", var("x")
    )
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "not requires bool arg" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_contract_or_is_eager_for_deterministic_step_accounting():
    p = {
        "apl": "0.0.11",
        "module": "eager_contract",
        "capabilities": [],
        "limits": {"steps": 2, "output_lines": 0, "host_reads": 0},
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "effects": [],
            "requires": [
                contract_clause(
                    "eager_or",
                    "both operands are evaluated",
                    predicate(
                        "or",
                        contract_const("bool", True),
                        contract_const("bool", True),
                    ),
                )
            ],
            "ensures": [],
            "body": [
                {"op": "const", "id": "answer", "type": "i64", "value": 42},
                {"op": "return", "value": "answer"},
            ],
        }],
    }
    # The OR root consumes step 1, the left constant consumes step 2,
    # and eager evaluation attempts the right constant as step 3.
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.resource_limit"
        assert exc.where == "main.requires[0].predicate.args[1]"
    else:
        raise AssertionError("expected eager right-operand evaluation")


def test_contract_predicate_nodes_consume_step_budget():
    p = contract_program()
    p["limits"]["steps"] = 4
    # main const + call consume two steps; precondition root and left leaf
    # consume the remaining two. The right const leaf is the fifth step.
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.resource_limit"
        assert exc.where == "double_positive.requires[0].predicate.args[1]"
    else:
        raise AssertionError("expected ExecutionError")


def test_legacy_v010_functions_do_not_require_contract_fields():
    p = limited_pure_program()
    verify_program(p)
    assert run_program(p, output=lambda _: None).value == 42



def test_pre_v011_rejects_contract_fields():
    p = limited_pure_program()
    p["functions"][0]["requires"] = []
    p["functions"][0]["ensures"] = []
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "function contracts require APL 0.0.11" in str(exc)
    else:
        raise AssertionError("expected VerificationError")



def range_type(minimum=0, maximum=100):
    return {"range": {"min": minimum, "max": maximum}}


def range_program(value=42, minimum=0, maximum=100):
    bounded = range_type(minimum, maximum)
    return {
        "apl": "0.0.12",
        "module": "ranges",
        "capabilities": [],
        "limits": {"steps": 50, "output_lines": 0, "host_reads": 0},
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "effects": [],
            "requires": [],
            "ensures": [],
            "body": [
                {"op": "const", "id": "raw", "type": "i64", "value": value},
                {
                    "op": "range.check",
                    "id": "bounded",
                    "type": bounded,
                    "args": ["raw"],
                },
                {
                    "op": "range.value",
                    "id": "wide",
                    "type": "i64",
                    "args": ["bounded"],
                },
                {"op": "return", "value": "wide"},
            ],
        }],
    }


def test_v012_range_check_and_explicit_widening():
    p = range_program()
    verify_program(p)
    result = run_program(p, output=lambda _: None)
    assert result.value == 42
    assert result.type == "i64"


def test_v012_range_violation_has_stable_trap():
    p = range_program(value=101)
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
        assert exc.code == "apl.range_violation"
        assert exc.where == "main[1]"
        assert "outside range [0, 100]" in exc.message
    else:
        raise AssertionError("expected ExecutionError")


def test_range_descriptor_requires_valid_i64_bounds():
    invalid = [
        range_type(5, 4),
        range_type(-(2**63) - 1, 0),
        range_type(0, 2**63),
        {"range": {"min": 0}},
        {"range": {"min": False, "max": 1}},
    ]
    fragments = [
        "range min must not exceed max",
        "range min must be within i64 bounds",
        "range max must be within i64 bounds",
        "range descriptor must contain exactly 'min' and 'max'",
        "range min must be an i64 integer literal",
    ]
    for typ, fragment in zip(invalid, fragments):
        p = range_program()
        p["functions"][0]["body"][1]["type"] = typ
        try:
            verify_program(p)
        except VerificationError as exc:
            assert fragment in str(exc)
        else:
            raise AssertionError(f"expected VerificationError for {typ!r}")


def test_v011_rejects_range_types():
    p = contract_program()
    p["apl"] = "0.0.11"
    p["functions"][0]["params"][0]["type"] = range_type()
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "range types require APL 0.0.12" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_range_check_requires_plain_i64_source():
    p = range_program()
    bounded = range_type()
    p["functions"][0]["body"].insert(
        2,
        {
            "op": "range.check",
            "id": "again",
            "type": bounded,
            "args": ["bounded"],
        },
    )
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "range.check source must have type 'i64'" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_range_value_requires_range_source():
    p = range_program()
    p["functions"][0]["body"][2]["args"] = ["raw"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "range.value source must be a range" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_range_values_do_not_implicitly_participate_in_i64_arithmetic():
    p = range_program()
    p["functions"][0]["body"].insert(
        2,
        {
            "op": "add",
            "id": "sum",
            "type": "i64",
            "args": ["bounded", "bounded"],
        },
    )
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "arithmetic requires i64 operands" in str(exc)
    else:
        raise AssertionError("expected VerificationError")


def test_range_type_is_exact_in_function_signatures():
    bounded = range_type(1, 10)
    p = {
        "apl": "0.0.12",
        "module": "range_call",
        "capabilities": [],
        "limits": {"steps": 100, "output_lines": 0, "host_reads": 0},
        "entry": "main",
        "functions": [
            {
                "name": "identity",
                "params": [{"name": "x", "type": bounded}],
                "returns": bounded,
                "effects": [],
                "requires": [],
                "ensures": [],
                "body": [{"op": "return", "value": "x"}],
            },
            {
                "name": "main",
                "params": [],
                "returns": "i64",
                "effects": [],
                "requires": [],
                "ensures": [],
                "body": [
                    {"op": "const", "id": "raw", "type": "i64", "value": 7},
                    {
                        "op": "range.check",
                        "id": "bounded",
                        "type": bounded,
                        "args": ["raw"],
                    },
                    {
                        "op": "call",
                        "id": "same",
                        "type": bounded,
                        "function": "identity",
                        "args": ["bounded"],
                    },
                    {
                        "op": "range.value",
                        "id": "wide",
                        "type": "i64",
                        "args": ["same"],
                    },
                    {"op": "return", "value": "wide"},
                ],
            },
        ],
    }
    verify_program(p)
    assert run_program(p, output=lambda _: None).value == 7

    p["functions"][1]["body"][1]["type"] = range_type(0, 10)
    p["functions"][1]["body"][2]["args"] = ["bounded"]
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "call arg 0 expects" in str(exc)
    else:
        raise AssertionError("range types are structural and exact")


def test_ranges_can_be_array_elements():
    bounded = range_type(0, 9)
    array_t = {"array": bounded, "len": 2}
    p = {
        "apl": "0.0.12",
        "module": "range_array",
        "capabilities": [],
        "limits": {"steps": 100, "output_lines": 0, "host_reads": 0},
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "effects": [],
            "requires": [],
            "ensures": [],
            "body": [
                {"op": "const", "id": "a_raw", "type": "i64", "value": 2},
                {"op": "const", "id": "b_raw", "type": "i64", "value": 7},
                {"op": "range.check", "id": "a", "type": bounded, "args": ["a_raw"]},
                {"op": "range.check", "id": "b", "type": bounded, "args": ["b_raw"]},
                {"op": "array", "id": "items", "type": array_t, "args": ["a", "b"]},
                {"op": "const", "id": "index", "type": "i64", "value": 1},
                {"op": "array.get", "id": "picked", "type": bounded, "args": ["items", "index"]},
                {"op": "range.value", "id": "wide", "type": "i64", "args": ["picked"]},
                {"op": "return", "value": "wide"},
            ],
        }],
    }
    verify_program(p)
    assert run_program(p, output=lambda _: None).value == 7


def test_contract_ordered_comparison_accepts_identical_range_types():
    bounded = range_type(0, 10)
    p = {
        "apl": "0.0.12",
        "module": "range_contract",
        "capabilities": [],
        "limits": {"steps": 100, "output_lines": 0, "host_reads": 0},
        "entry": "main",
        "functions": [
            {
                "name": "ordered",
                "params": [
                    {"name": "low", "type": bounded},
                    {"name": "high", "type": bounded},
                ],
                "returns": bounded,
                "effects": [],
                "requires": [
                    contract_clause(
                        "ordered",
                        "low must not exceed high",
                        predicate("le", var("low"), var("high")),
                    )
                ],
                "ensures": [],
                "body": [{"op": "return", "value": "high"}],
            },
            {
                "name": "main",
                "params": [],
                "returns": "i64",
                "effects": [],
                "requires": [],
                "ensures": [],
                "body": [
                    {"op": "const", "id": "a0", "type": "i64", "value": 2},
                    {"op": "const", "id": "b0", "type": "i64", "value": 8},
                    {"op": "range.check", "id": "a", "type": bounded, "args": ["a0"]},
                    {"op": "range.check", "id": "b", "type": bounded, "args": ["b0"]},
                    {
                        "op": "call",
                        "id": "answer",
                        "type": bounded,
                        "function": "ordered",
                        "args": ["a", "b"],
                    },
                    {"op": "range.value", "id": "wide", "type": "i64", "args": ["answer"]},
                    {"op": "return", "value": "wide"},
                ],
            },
        ],
    }
    verify_program(p)
    assert run_program(p, output=lambda _: None).value == 8


def test_contract_ordered_comparison_rejects_range_vs_i64():
    p = range_program()
    bounded = range_type()
    p["functions"][0]["requires"] = [
        contract_clause(
            "mixed",
            "no implicit widening",
            predicate("le", contract_const("i64", 0), contract_const("i64", 1)),
        )
    ]
    # Replace one literal with a range-typed parameter via a dedicated function.
    p["functions"].insert(
        0,
        {
            "name": "mixed",
            "params": [{"name": "x", "type": bounded}],
            "returns": bounded,
            "effects": [],
            "requires": [
                contract_clause(
                    "mixed_types",
                    "range and i64 must not compare implicitly",
                    predicate("le", var("x"), contract_const("i64", 10)),
                )
            ],
            "ensures": [],
            "body": [{"op": "return", "value": "x"}],
        },
    )
    try:
        verify_program(p)
    except VerificationError as exc:
        assert "requires identical i64 or range args" in str(exc)
    else:
        raise AssertionError("expected VerificationError")



def test_range_type_survives_if_and_repeat_regions():
    bounded = range_type(0, 10)
    p = {
        "apl": "0.0.12",
        "module": "range_regions",
        "capabilities": [],
        "limits": {"steps": 100, "output_lines": 0, "host_reads": 0},
        "entry": "main",
        "functions": [{
            "name": "main",
            "params": [],
            "returns": "i64",
            "effects": [],
            "requires": [],
            "ensures": [],
            "body": [
                {"op": "const", "id": "raw_a", "type": "i64", "value": 3},
                {"op": "const", "id": "raw_b", "type": "i64", "value": 7},
                {"op": "range.check", "id": "a", "type": bounded, "args": ["raw_a"]},
                {"op": "range.check", "id": "b", "type": bounded, "args": ["raw_b"]},
                {"op": "const", "id": "cond", "type": "bool", "value": True},
                {
                    "op": "if",
                    "id": "selected",
                    "type": bounded,
                    "cond": "cond",
                    "then": [{"op": "yield", "value": "a"}],
                    "else": [{"op": "yield", "value": "b"}],
                },
                {"op": "const", "id": "count", "type": "i64", "value": 2},
                {
                    "op": "repeat",
                    "id": "carried",
                    "type": bounded,
                    "count": "count",
                    "max": 2,
                    "init": "selected",
                    "index": "i",
                    "carry": "current",
                    "body": [{"op": "yield", "value": "current"}],
                },
                {"op": "range.value", "id": "wide", "type": "i64", "args": ["carried"]},
                {"op": "return", "value": "wide"},
            ],
        }],
    }
    verify_program(p)
    result = run_program(p, output=lambda _: None)
    assert result.value == 3



def test_range_bounds_are_inclusive():
    for value in (0, 100):
        result = run_program(range_program(value=value), output=lambda _: None)
        assert result.value == value

    for value in (-1, 101):
        try:
            run_program(range_program(value=value), output=lambda _: None)
        except ExecutionError as exc:
            assert exc.code == "apl.range_violation"
        else:
            raise AssertionError(f"expected range violation for {value}")
