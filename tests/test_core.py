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
        assert "division by zero" in str(exc)
    else:
        raise AssertionError("expected ExecutionError")


def test_division_min_by_minus_one_overflows():
    try:
        run_program(binary_program("div", -(2**63), -1), output=lambda _: None)
    except ExecutionError as exc:
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
        assert "exceeds declared max 2" in str(exc)
        assert lines == []
    else:
        raise AssertionError("expected ExecutionError")


def test_repeat_negative_count_traps():
    try:
        run_program(repeat_program(count=-1), output=lambda _: None)
    except ExecutionError as exc:
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
        assert "array index 3 out of bounds for length 3" in str(exc)
    else:
        raise AssertionError("expected ExecutionError")


def test_array_get_negative_index_traps():
    p = array_program()
    p["functions"][0]["body"][0]["value"] = -1
    try:
        run_program(p, output=lambda _: None)
    except ExecutionError as exc:
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
        assert "structured types require APL 0.0.5" in str(exc)
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
