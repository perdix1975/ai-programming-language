from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import CompilationError
from .lir import lower_program, verify_lir
from .quantities import is_quantity_type
from .ranges import is_range_type, range_bounds


WASM_MAGIC_VERSION = b"\x00asm\x01\x00\x00\x00"
WASM_I32 = 0x7F
WASM_I64 = 0x7E
WASM_FUNC = 0x60

TRAP_I64_OVERFLOW = 1
TRAP_DIVISION_BY_ZERO = 2
TRAP_REPEAT_NEGATIVE_COUNT = 3
TRAP_REPEAT_COUNT_EXCEEDS_MAX = 4
TRAP_STEP_RESOURCE_LIMIT = 5
TRAP_PRECONDITION_FAILED = 6
TRAP_POSTCONDITION_FAILED = 7
TRAP_INVARIANT_FAILED = 8
TRAP_RANGE_VIOLATION = 9
TRAP_ARRAY_INDEX_OOB = 10


def _u32(value: int) -> bytes:
    if value < 0:
        raise ValueError("u32 LEB128 requires non-negative value")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _sleb(value: int, bits: int) -> bytes:
    out = bytearray()
    more = True
    while more:
        byte = value & 0x7F
        value >>= 7
        sign = byte & 0x40
        if (value == 0 and not sign) or (value == -1 and sign):
            more = False
        else:
            byte |= 0x80
        out.append(byte)
    return bytes(out)


def _vec(items: list[bytes]) -> bytes:
    return _u32(len(items)) + b"".join(items)


def _name(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return _u32(len(encoded)) + encoded


def _section(section_id: int, payload: bytes) -> bytes:
    return bytes([section_id]) + _u32(len(payload)) + payload


def _is_array_type(typ: Any) -> bool:
    return isinstance(typ, dict) and set(typ) == {"array", "len"}


def _is_record_type(typ: Any) -> bool:
    return isinstance(typ, dict) and set(typ) == {"record"}


def _is_aggregate_type(typ: Any) -> bool:
    return _is_array_type(typ) or _is_record_type(typ)


def _value_type(typ: Any) -> int:
    if typ == "i64" or is_range_type(typ) or is_quantity_type(typ):
        return WASM_I64
    if typ == "bool" or _is_aggregate_type(typ):
        return WASM_I32
    raise CompilationError(
        "WASM backend supports i64/bool/range/quantity/array/record values, "
        f"got {typ!r}"
    )


def _storage_size(typ: Any) -> int:
    return 8 if _value_type(typ) == WASM_I64 else 4


def _record_layout(typ: Any) -> dict[str, tuple[int, Any]]:
    if not _is_record_type(typ):
        raise CompilationError(f"expected record type, got {typ!r}")
    offset = 0
    layout: dict[str, tuple[int, Any]] = {}
    for name, field_type in sorted(typ["record"].items()):
        layout[name] = (offset, field_type)
        offset += _storage_size(field_type)
    return layout


def _function_type(params: list[Any], result: Any) -> bytes:
    param_bytes = [bytes([_value_type(typ)]) for typ in params]
    result_bytes = [] if result == "unit" else [bytes([_value_type(result)])]
    return bytes([WASM_FUNC]) + _vec(param_bytes) + _vec(result_bytes)


def _op(*values: int | bytes) -> bytes:
    out = bytearray()
    for value in values:
        if isinstance(value, int):
            out.append(value)
        else:
            out.extend(value)
    return bytes(out)


def _local_get(index: int) -> bytes:
    return _op(0x20, _u32(index))


def _local_set(index: int) -> bytes:
    return _op(0x21, _u32(index))


def _memarg(align: int, offset: int) -> bytes:
    return _u32(align) + _u32(offset)


def _call(index: int) -> bytes:
    return _op(0x10, _u32(index))


def _trap(code: int) -> bytes:
    # Host contract: apl.trap(code) must throw. unreachable preserves trapping
    # behavior even if a nonconforming host import returns normally.
    return _op(0x41, _sleb(code, 32), _call(0), 0x00)


def _guard_if(condition: bytes, body: bytes) -> bytes:
    return condition + _op(0x04, 0x40) + body + _op(0x0B)


def _if_else(condition: bytes, then_body: bytes, else_body: bytes = b"") -> bytes:
    code = condition + _op(0x04, 0x40) + then_body
    if else_body:
        code += _op(0x05) + else_body
    return code + _op(0x0B)


@dataclass(frozen=True)
class WasmArtifact:
    binary: bytes
    entry_export: str
    source_apl: str
    module: str


class _FunctionCompiler:
    def __init__(
        self,
        fn: dict[str, Any],
        *,
        function_indices: dict[str, int],
        signatures: dict[str, tuple[list[Any], Any]],
        step_global_index: int | None,
        heap_global_index: int | None,
    ) -> None:
        self.fn = fn
        self.function_indices = function_indices
        self.signatures = signatures
        self.step_global_index = step_global_index
        self.heap_global_index = heap_global_index
        self.types: dict[str, Any] = {
            param["id"]: param["type"] for param in fn["params"]
        }
        for block in fn["blocks"]:
            for param in block["params"]:
                self.types[param["id"]] = param["type"]
            for op in block["ops"]:
                if "id" in op:
                    self.types[op["id"]] = op["type"]

    def _index(self, value_id: str) -> int:
        if not value_id.startswith("v") or not value_id[1:].isdigit():
            raise CompilationError(f"non-normalized LIR value id {value_id!r}")
        return int(value_id[1:])

    def _arg(self, value_id: str) -> bytes:
        return _local_get(self._index(value_id))

    def _allocate(self, size: int, dest_index: int) -> bytes:
        if self.heap_global_index is None:
            raise CompilationError("aggregate allocation requested without WASM memory")
        heap = self.heap_global_index

        code = bytearray()
        code.extend(_op(0x23, _u32(heap), 0xA7))
        code.extend(_local_set(dest_index))
        code.extend(_op(0x23, _u32(heap)))
        code.extend(_op(0x42, _sleb(size, 64), 0x7C))
        code.extend(_op(0x24, _u32(heap)))

        too_large = (
            _op(0x23, _u32(heap))
            + _op(0x42, _sleb(0xFFFFFFFF, 64), 0x56)
        )
        code.extend(_guard_if(too_large, _op(0x00)))

        required_pages = (
            _op(0x23, _u32(heap))
            + _op(0x42, _sleb(65535, 64), 0x7C)
            + _op(0x42, _sleb(16, 64), 0x88)
        )
        current_pages = _op(0x3F, 0x00, 0xAD)
        need_grow = required_pages + current_pages + _op(0x56)
        grow_failed = (
            required_pages
            + current_pages
            + _op(0x7D, 0xA7, 0x40, 0x00)
            + _op(0x41, _sleb(-1, 32), 0x46)
        )
        code.extend(_guard_if(need_grow, _guard_if(grow_failed, _op(0x00))))
        return bytes(code)

    def _store_at(
        self,
        base_id: str,
        source_id: str,
        typ: Any,
        offset: int,
    ) -> bytes:
        wasm_type = _value_type(typ)
        opcode = 0x37 if wasm_type == WASM_I64 else 0x36
        align = 3 if wasm_type == WASM_I64 else 2
        return (
            self._arg(base_id)
            + self._arg(source_id)
            + _op(opcode, _memarg(align, offset))
        )

    def _load_static(self, base_id: str, typ: Any, offset: int) -> bytes:
        wasm_type = _value_type(typ)
        opcode = 0x29 if wasm_type == WASM_I64 else 0x28
        align = 3 if wasm_type == WASM_I64 else 2
        return self._arg(base_id) + _op(opcode, _memarg(align, offset))

    def _binary_i64(
        self,
        op: dict[str, Any],
        opcode: int,
    ) -> bytes:
        a, b = op["args"]
        dest = self._index(op["id"])
        return self._arg(a) + self._arg(b) + _op(opcode) + _local_set(dest)

    def _checked_add(self, op: dict[str, Any]) -> bytes:
        a, b = op["args"]
        dest = self._index(op["id"])
        code = (
            self._arg(a)
            + self._arg(b)
            + _op(0x7C)
            + _local_set(dest)
        )
        # overflow iff ((a ^ result) & (b ^ result)) < 0
        condition = (
            self._arg(a)
            + self._arg(op["id"])
            + _op(0x85)
            + self._arg(b)
            + self._arg(op["id"])
            + _op(0x85, 0x83)
            + _op(0x42, _sleb(0, 64), 0x53)
        )
        return code + _guard_if(condition, _trap(TRAP_I64_OVERFLOW))

    def _checked_sub(self, op: dict[str, Any]) -> bytes:
        a, b = op["args"]
        dest = self._index(op["id"])
        code = (
            self._arg(a)
            + self._arg(b)
            + _op(0x7D)
            + _local_set(dest)
        )
        # overflow iff ((a ^ b) & (a ^ result)) < 0
        condition = (
            self._arg(a)
            + self._arg(b)
            + _op(0x85)
            + self._arg(a)
            + self._arg(op["id"])
            + _op(0x85, 0x83)
            + _op(0x42, _sleb(0, 64), 0x53)
        )
        return code + _guard_if(condition, _trap(TRAP_I64_OVERFLOW))

    def _checked_mul(self, op: dict[str, Any]) -> bytes:
        a, b = op["args"]
        dest = self._index(op["id"])
        zero = _op(0x42, _sleb(0, 64))
        max_i64 = _op(0x42, _sleb(2**63 - 1, 64))
        min_i64 = _op(0x42, _sleb(-(2**63), 64))

        a_gt_zero = self._arg(a) + zero + _op(0x55)
        a_lt_zero = self._arg(a) + zero + _op(0x53)
        b_gt_zero = self._arg(b) + zero + _op(0x55)
        b_lt_zero = self._arg(b) + zero + _op(0x53)

        # a > 0, b > 0: a > MAX / b
        pos_pos_overflow = (
            self._arg(a)
            + max_i64
            + self._arg(b)
            + _op(0x7F, 0x55)
        )
        # a > 0, b < 0: b < MIN / a
        pos_neg_overflow = (
            self._arg(b)
            + min_i64
            + self._arg(a)
            + _op(0x7F, 0x53)
        )
        # a < 0, b > 0: a < MIN / b
        neg_pos_overflow = (
            self._arg(a)
            + min_i64
            + self._arg(b)
            + _op(0x7F, 0x53)
        )
        # a < 0, b < 0: b < MAX / a
        neg_neg_overflow = (
            self._arg(b)
            + max_i64
            + self._arg(a)
            + _op(0x7F, 0x53)
        )

        positive_a = _if_else(
            b_gt_zero,
            _guard_if(pos_pos_overflow, _trap(TRAP_I64_OVERFLOW)),
            _if_else(
                b_lt_zero,
                _guard_if(pos_neg_overflow, _trap(TRAP_I64_OVERFLOW)),
            ),
        )
        negative_a = _if_else(
            b_gt_zero,
            _guard_if(neg_pos_overflow, _trap(TRAP_I64_OVERFLOW)),
            _if_else(
                b_lt_zero,
                _guard_if(neg_neg_overflow, _trap(TRAP_I64_OVERFLOW)),
            ),
        )

        return (
            _if_else(
                a_gt_zero,
                positive_a,
                _if_else(a_lt_zero, negative_a),
            )
            + self._arg(a)
            + self._arg(b)
            + _op(0x7E)
            + _local_set(dest)
        )

    def _checked_div(self, op: dict[str, Any]) -> bytes:
        a, b = op["args"]
        dest = self._index(op["id"])
        zero = self._arg(b) + _op(0x50)
        overflow = (
            self._arg(a)
            + _op(0x42, _sleb(-(2**63), 64), 0x51)
            + self._arg(b)
            + _op(0x42, _sleb(-1, 64), 0x51)
            + _op(0x71)
        )
        return (
            _guard_if(zero, _trap(TRAP_DIVISION_BY_ZERO))
            + _guard_if(overflow, _trap(TRAP_I64_OVERFLOW))
            + self._arg(a)
            + self._arg(b)
            + _op(0x7F)
            + _local_set(dest)
        )

    def _checked_rem(self, op: dict[str, Any]) -> bytes:
        a, b = op["args"]
        dest = self._index(op["id"])
        zero = self._arg(b) + _op(0x50)
        return (
            _guard_if(zero, _trap(TRAP_DIVISION_BY_ZERO))
            + self._arg(a)
            + self._arg(b)
            + _op(0x81)
            + _local_set(dest)
        )

    def _comparison(self, op: dict[str, Any]) -> bytes:
        a, b = op["args"]
        dest = self._index(op["id"])
        mapping = {
            "i64.lt": 0x53,
            "i64.gt": 0x55,
            "i64.le": 0x57,
            "i64.ge": 0x59,
        }
        return (
            self._arg(a)
            + self._arg(b)
            + _op(mapping[op["op"]])
            + _local_set(dest)
        )

    def _value_comparison(self, op: dict[str, Any]) -> bytes:
        a, b = op["args"]
        dest = self._index(op["id"])
        typ = self.types[a]
        name = op["op"]
        wasm_type = _value_type(typ)
        if name == "value.eq":
            opcode = 0x51 if wasm_type == WASM_I64 else 0x46 if wasm_type == WASM_I32 else None
        elif wasm_type == WASM_I64:
            opcode = {
                "value.lt": 0x53,
                "value.gt": 0x55,
                "value.le": 0x57,
                "value.ge": 0x59,
            }.get(name)
        else:
            opcode = None
        if opcode is None:
            raise CompilationError(
                f"WASM scalar backend cannot compile {name} for {typ!r}"
            )
        return self._arg(a) + self._arg(b) + _op(opcode) + _local_set(dest)

    def compile_op(self, op: dict[str, Any]) -> bytes:
        name = op["op"]

        if name == "budget.step":
            if self.step_global_index is None:
                return b""
            index = self.step_global_index
            exhausted = _op(0x23, _u32(index), 0x50)
            decrement = (
                _op(0x23, _u32(index))
                + _op(0x42, _sleb(1, 64), 0x7D)
                + _op(0x24, _u32(index))
            )
            return (
                _guard_if(exhausted, _trap(TRAP_STEP_RESOURCE_LIMIT))
                + decrement
            )

        if name == "guard":
            trap_code = {
                "apl.precondition_failed": TRAP_PRECONDITION_FAILED,
                "apl.postcondition_failed": TRAP_POSTCONDITION_FAILED,
                "apl.invariant_failed": TRAP_INVARIANT_FAILED,
            }.get(op["code"])
            if trap_code is None:
                raise CompilationError(
                    f"unsupported normalized guard code {op['code']!r}"
                )
            failed = self._arg(op["cond"]) + _op(0x45)
            return _guard_if(failed, _trap(trap_code))

        if name == "range.check":
            source = op["arg"]
            dest = self._index(op["id"])
            minimum, maximum = range_bounds(op["type"])
            below = (
                self._arg(source)
                + _op(0x42, _sleb(minimum, 64), 0x53)
            )
            above = (
                self._arg(source)
                + _op(0x42, _sleb(maximum, 64), 0x55)
            )
            return (
                _guard_if(below, _trap(TRAP_RANGE_VIOLATION))
                + _guard_if(above, _trap(TRAP_RANGE_VIOLATION))
                + self._arg(source)
                + _local_set(dest)
            )

        if name in {"range.value", "quantity.attach", "quantity.value"}:
            return (
                self._arg(op["arg"])
                + _local_set(self._index(op["id"]))
            )

        if name == "quantity.add":
            return self._checked_add(op)
        if name == "quantity.sub":
            return self._checked_sub(op)
        if name == "quantity.mul":
            return self._checked_mul(op)
        if name == "quantity.div":
            return self._checked_div(op)

        if name == "repeat.guard":
            count = op["count"]
            negative = self._arg(count) + _op(0x42, _sleb(0, 64), 0x53)
            exceeds = (
                self._arg(count)
                + _op(0x42, _sleb(op["max"], 64), 0x55)
            )
            return (
                _guard_if(negative, _trap(TRAP_REPEAT_NEGATIVE_COUNT))
                + _guard_if(exceeds, _trap(TRAP_REPEAT_COUNT_EXCEEDS_MAX))
            )

        if name == "const":
            dest = self._index(op["id"])
            if op["type"] == "i64":
                return _op(0x42, _sleb(op["value"], 64)) + _local_set(dest)
            if op["type"] == "bool":
                return _op(0x41, _sleb(1 if op["value"] else 0, 32)) + _local_set(dest)
            raise CompilationError("WASM scalar backend does not support string constants")

        if name == "i64.add":
            return self._checked_add(op)
        if name == "i64.sub":
            return self._checked_sub(op)
        if name == "i64.mul":
            return self._checked_mul(op)
        if name == "i64.div":
            return self._checked_div(op)
        if name == "i64.rem":
            return self._checked_rem(op)
        if name in {"i64.lt", "i64.le", "i64.gt", "i64.ge"}:
            return self._comparison(op)
        if name in {"value.eq", "value.lt", "value.le", "value.gt", "value.ge"}:
            return self._value_comparison(op)

        if name == "bool.not":
            src = op["args"][0]
            return self._arg(src) + _op(0x45) + _local_set(self._index(op["id"]))
        if name in {"bool.and", "bool.or"}:
            a, b = op["args"]
            opcode = 0x71 if name == "bool.and" else 0x72
            return (
                self._arg(a)
                + self._arg(b)
                + _op(opcode)
                + _local_set(self._index(op["id"]))
            )

        if name == "call":
            target = op["function"]
            code = b"".join(self._arg(arg) for arg in op["args"])
            code += _call(self.function_indices[target])
            if "id" in op:
                code += _local_set(self._index(op["id"]))
            return code

        raise CompilationError(
            f"WASM scalar backend does not support LIR op '{name}'"
        )

    def _edge_transfer(
        self,
        edge: dict[str, Any],
        *,
        blocks_by_id: dict[str, dict[str, Any]],
        pc_index: int,
    ) -> bytes:
        target = blocks_by_id[edge["target"]]
        args = edge["args"]
        params = target["params"]
        if len(args) != len(params):
            raise CompilationError(
                f"{self.fn['name']}: malformed CFG edge to {target['id']}"
            )

        # Branch arguments are parallel assignments. Push every source first,
        # then pop into destination block parameters in reverse order.
        code = bytearray()
        for source in args:
            code.extend(self._arg(source))
        for param in reversed(params):
            code.extend(_local_set(self._index(param["id"])))
        code.extend(_op(0x41, _sleb(int(target["id"][1:]), 32)))
        code.extend(_local_set(pc_index))
        return bytes(code)

    def _compile_term(
        self,
        term: dict[str, Any],
        *,
        blocks_by_id: dict[str, dict[str, Any]],
        pc_index: int,
    ) -> bytes:
        op = term["op"]

        if op == "br":
            return (
                self._edge_transfer(
                    term,
                    blocks_by_id=blocks_by_id,
                    pc_index=pc_index,
                )
                + _op(0x0C, _u32(1))
            )

        if op == "cond_br":
            condition = self._arg(term["cond"])
            then_code = self._edge_transfer(
                term["then"],
                blocks_by_id=blocks_by_id,
                pc_index=pc_index,
            )
            else_code = self._edge_transfer(
                term["else"],
                blocks_by_id=blocks_by_id,
                pc_index=pc_index,
            )
            # After the inner if closes we remain inside the dispatch block
            # check, so br depth 1 targets the surrounding dispatch loop.
            return _if_else(condition, then_code, else_code) + _op(0x0C, _u32(1))

        if op == "return":
            code = b""
            if "value" in term:
                code += self._arg(term["value"])
            return code + _op(0x0F)

        if op == "trap":
            raise CompilationError(
                f"{self.fn['name']}: explicit LIR traps are not supported by the WASM ABI yet"
            )

        raise CompilationError(
            f"{self.fn['name']}: unsupported WASM CFG terminator '{op}'"
        )

    def compile(self) -> bytes:
        blocks = self.fn["blocks"]
        if not blocks or blocks[0]["id"] != "b0" or blocks[0]["params"]:
            raise CompilationError(
                f"{self.fn['name']}: WASM scalar backend requires canonical b0 entry"
            )
        if self.fn["effects"]:
            raise CompilationError(
                f"{self.fn['name']}: WASM scalar backend requires a pure function"
            )

        for param in self.fn["params"]:
            _value_type(param["type"])
        if self.fn["returns"] != "unit":
            _value_type(self.fn["returns"])

        local_types: list[tuple[int, int]] = []
        for block in blocks:
            for param in block["params"]:
                local_types.append(
                    (self._index(param["id"]), _value_type(param["type"]))
                )
            for op in block["ops"]:
                if "id" in op:
                    local_types.append(
                        (self._index(op["id"]), _value_type(op["type"]))
                    )

        param_count = len(self.fn["params"])
        local_types.sort()
        expected = list(range(param_count, param_count + len(local_types)))
        actual = [index for index, _ in local_types]
        if actual != expected:
            raise CompilationError(
                f"{self.fn['name']}: scalar WASM locals are not dense after parameters"
            )

        pc_index = param_count + len(local_types)
        local_decls = [
            *[_u32(1) + bytes([typ]) for _, typ in local_types],
            _u32(1) + bytes([WASM_I32]),
        ]
        code = bytearray(_vec(local_decls))

        # Program-counter CFG dispatcher. This deliberately follows verified
        # LIR block order rather than reconstructing high-level source syntax.
        code.extend(_op(0x41, _sleb(0, 32)))
        code.extend(_local_set(pc_index))
        code.extend(_op(0x03, 0x40))  # loop $dispatch

        blocks_by_id = {block["id"]: block for block in blocks}
        for block in blocks:
            block_number = int(block["id"][1:])
            condition = (
                _local_get(pc_index)
                + _op(0x41, _sleb(block_number, 32), 0x46)
            )
            block_code = bytearray()
            for op in block["ops"]:
                block_code.extend(self.compile_op(op))
            block_code.extend(
                self._compile_term(
                    block["term"],
                    blocks_by_id=blocks_by_id,
                    pc_index=pc_index,
                )
            )
            code.extend(_if_else(condition, bytes(block_code)))

        # Verified LIR has no path with an unknown block id. Keep a hard WASM
        # trap for corrupted backend state instead of falling through.
        code.extend(_op(0x00))
        code.extend(_op(0x0B))  # end loop
        code.extend(_op(0x00))  # loop may not fall through to function end
        code.extend(_op(0x0B))
        body = bytes(code)
        return _u32(len(body)) + body


def compile_lir_to_wasm(lir: dict[str, Any]) -> WasmArtifact:
    verify_lir(lir)

    runtime = lir["runtime"]
    if runtime["capabilities"]:
        raise CompilationError(
            "WASM scalar backend does not support host capabilities yet"
        )
    step_limit = runtime["limits"]["steps"]
    step_global_index = 0 if step_limit is not None else None

    functions = lir["functions"]
    signatures = {
        fn["name"]: ([param["type"] for param in fn["params"]], fn["returns"])
        for fn in functions
    }

    # Function index 0 is reserved for the imported apl.trap function.
    function_indices = {
        fn["name"]: index + 1
        for index, fn in enumerate(functions)
    }

    type_entries = [
        _function_type(["bool"], "unit"),
        *[
            _function_type(
                [param["type"] for param in fn["params"]],
                fn["returns"],
            )
            for fn in functions
        ],
    ]
    type_section = _section(1, _vec(type_entries))

    import_entry = (
        _name("apl")
        + _name("trap")
        + bytes([0x00])
        + _u32(0)
    )
    import_section = _section(2, _vec([import_entry]))

    function_section = _section(
        3,
        _vec([_u32(index + 1) for index in range(len(functions))]),
    )

    entry_name = lir["entry"]
    entry_index = function_indices[entry_name]
    export_entry = _name("apl_entry") + bytes([0x00]) + _u32(entry_index)
    export_section = _section(7, _vec([export_entry]))

    global_section = b""
    if step_limit is not None:
        global_entry = (
            bytes([WASM_I64, 0x01])
            + _op(0x42, _sleb(step_limit, 64), 0x0B)
        )
        global_section = _section(6, _vec([global_entry]))

    code_entries = [
        _FunctionCompiler(
            fn,
            function_indices=function_indices,
            signatures=signatures,
            step_global_index=step_global_index,
        ).compile()
        for fn in functions
    ]
    code_section = _section(10, _vec(code_entries))

    binary = (
        WASM_MAGIC_VERSION
        + type_section
        + import_section
        + function_section
        + global_section
        + export_section
        + code_section
    )
    return WasmArtifact(
        binary=binary,
        entry_export="apl_entry",
        source_apl=lir["source_apl"],
        module=lir["module"],
    )


def compile_program_to_wasm(program: dict[str, Any]) -> WasmArtifact:
    return compile_lir_to_wasm(lower_program(program))
