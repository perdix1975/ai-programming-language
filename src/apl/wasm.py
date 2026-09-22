from __future__ import annotations

from dataclasses import dataclass
import json
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

CAPABILITY_BITS = {
    "console.write": 1,
    "fs.read_text": 2,
    "net.get_text": 4,
}
RESOURCE_ORDER = ("steps", "output_lines", "host_reads")


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


def _packed_string_handle(pointer: int, length: int) -> int:
    if not (0 <= pointer <= 0xFFFFFFFF and 0 <= length <= 0xFFFFFFFF):
        raise CompilationError("WASM string pointer/length exceed packed i64 ABI")
    raw = (pointer << 32) | length
    return raw if raw < 2**63 else raw - 2**64


def _is_array_type(typ: Any) -> bool:
    return isinstance(typ, dict) and set(typ) == {"array", "len"}


def _is_record_type(typ: Any) -> bool:
    return isinstance(typ, dict) and set(typ) == {"record"}


def _type_descriptor_text(typ: Any) -> str:
    return json.dumps(
        typ,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _is_i64_slot_type(typ: Any) -> bool:
    return (
        (isinstance(typ, str) and typ in {"i64", "string"})
        or is_range_type(typ)
        or is_quantity_type(typ)
    )


def _value_type(typ: Any) -> int:
    if typ == "i64" or is_range_type(typ) or is_quantity_type(typ):
        return WASM_I64
    if typ == "bool":
        return WASM_I32
    if typ == "string":
        return WASM_I64
    if _is_array_type(typ) or _is_record_type(typ):
        return WASM_I32
    raise CompilationError(
        "WASM backend does not support this value type yet: "
        f"{typ!r}"
    )


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
        import_indices: dict[str, int],
        budget_global_indices: dict[str, int],
        string_handles: dict[str, int],
        entry_capability_mask: int,
    ) -> None:
        self.fn = fn
        self.function_indices = function_indices
        self.signatures = signatures
        self.import_indices = import_indices
        self.budget_global_indices = budget_global_indices
        self.string_handles = string_handles
        self.entry_capability_mask = entry_capability_mask
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

    def _binary_i64(
        self,
        op: dict[str, Any],
        opcode: int,
    ) -> bytes:
        a, b = op["args"]
        dest = self._index(op["id"])
        return self._arg(a) + self._arg(b) + _op(opcode) + _local_set(dest)

    def _store_slot(self, value_id: str, *, offset: int = 0) -> bytes:
        typ = self.types[value_id]
        value = self._arg(value_id)
        if not _is_i64_slot_type(typ):
            value += _op(0xAD)  # i64.extend_i32_u
        return value + _op(0x37, _u32(3), _u32(offset))

    def _load_slot(
        self,
        typ: Any,
        *,
        offset: int = 0,
    ) -> bytes:
        code = _op(0x29, _u32(3), _u32(offset))  # i64.load
        if not _is_i64_slot_type(typ):
            code += _op(0xA7)  # i32.wrap_i64
        return code

    def _consume_resource(self, resource: str) -> bytes:
        index = self.budget_global_indices.get(resource)
        if index is None:
            return b""
        exhausted = _op(0x23, _u32(index), 0x50)
        decrement = (
            _op(0x23, _u32(index))
            + _op(0x42, _sleb(1, 64), 0x7D)
            + _op(0x24, _u32(index))
        )
        return _guard_if(exhausted, _trap(TRAP_STEP_RESOURCE_LIMIT)) + decrement

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
            return self._consume_resource("steps")

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
            if op["type"] == "string":
                handle = self.string_handles[op["value"]]
                return _op(0x42, _sleb(handle, 64)) + _local_set(dest)
            raise CompilationError(f"unsupported WASM constant type {op['type']!r}")

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
            comparison_type = self.types[op["args"][0]]
            if (
                name == "value.eq"
                and (_is_array_type(comparison_type) or _is_record_type(comparison_type))
            ):
                descriptor = _type_descriptor_text(comparison_type)
                descriptor_handle = self.string_handles[descriptor]
                a, b = op["args"]
                return (
                    _op(0x42, _sleb(descriptor_handle, 64))
                    + self._arg(a)
                    + self._arg(b)
                    + _call(self.import_indices["struct_eq"])
                    + _local_set(self._index(op["id"]))
                )
            if (
                name == "value.eq"
                and comparison_type == "string"
            ):
                a, b = op["args"]
                return (
                    self._arg(a)
                    + self._arg(b)
                    + _call(self.import_indices["string_eq"])
                    + _local_set(self._index(op["id"]))
                )
            return self._value_comparison(op)

        if name == "console.write":
            source = op["arg"]
            typ = self.types[source]
            import_name = {
                "i64": "console_write_i64",
                "bool": "console_write_bool",
                "string": "console_write_string",
            }.get(typ)
            if import_name is None:
                raise CompilationError(
                    f"console.write does not support compiled type {typ!r}"
                )
            return (
                self._consume_resource("output_lines")
                + self._arg(source)
                + _call(self.import_indices[import_name])
            )

        if name in {"host.fs.read_text", "host.net.get_text"}:
            import_name = (
                "fs_read_text"
                if name == "host.fs.read_text"
                else "net_get_text"
            )
            host_kind = 1 if name == "host.fs.read_text" else 2
            return (
                _op(0x41, _sleb(host_kind, 32))
                + _call(self.import_indices["require_host"])
                + self._consume_resource("host_reads")
                + self._arg(op["arg"])
                + _call(self.import_indices[import_name])
                + _local_set(self._index(op["id"]))
            )

        if name == "array.make":
            dest = self._index(op["id"])
            size = op["type"]["len"] * 8
            code = (
                _op(0x41, _sleb(size, 32))
                + _call(self.import_indices["alloc"])
                + _local_set(dest)
            )
            for index, source in enumerate(op["args"]):
                code += self._arg(op["id"])
                code += self._store_slot(source, offset=index * 8)
            return code

        if name == "array.get":
            array_id, index_id = op["args"]
            length = self.types[array_id]["len"]
            negative = (
                self._arg(index_id)
                + _op(0x42, _sleb(0, 64), 0x53)
            )
            too_high = (
                self._arg(index_id)
                + _op(0x42, _sleb(length, 64), 0x59)
            )
            address = (
                self._arg(array_id)
                + self._arg(index_id)
                + _op(0xA7)
                + _op(0x41, _sleb(8, 32), 0x6C, 0x6A)
            )
            return (
                _guard_if(negative, _trap(TRAP_ARRAY_INDEX_OOB))
                + _guard_if(too_high, _trap(TRAP_ARRAY_INDEX_OOB))
                + address
                + self._load_slot(op["type"])
                + _local_set(self._index(op["id"]))
            )

        if name == "array.len":
            source_type = self.types[op["arg"]]
            return (
                _op(0x42, _sleb(source_type["len"], 64))
                + _local_set(self._index(op["id"]))
            )

        if name == "record.make":
            dest = self._index(op["id"])
            fields = sorted(op["type"]["record"])
            code = (
                _op(0x41, _sleb(len(fields) * 8, 32))
                + _call(self.import_indices["alloc"])
                + _local_set(dest)
            )
            for index, field in enumerate(fields):
                source = op["fields"][field]
                code += self._arg(op["id"])
                code += self._store_slot(source, offset=index * 8)
            return code

        if name == "record.get":
            record_type = self.types[op["record"]]
            fields = sorted(record_type["record"])
            offset = fields.index(op["field"]) * 8
            return (
                self._arg(op["record"])
                + self._load_slot(op["type"], offset=offset)
                + _local_set(self._index(op["id"]))
            )

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
            try:
                code_handle = self.string_handles[term["code"]]
                message_handle = self.string_handles[term["message"]]
                where_handle = self.string_handles[term["where"]]
            except KeyError as exc:
                raise CompilationError(
                    f"{self.fn['name']}: missing explicit-trap string in WASM pool"
                ) from exc
            return (
                _op(0x42, _sleb(code_handle, 64))
                + _op(0x42, _sleb(message_handle, 64))
                + _op(0x42, _sleb(where_handle, 64))
                + _call(self.import_indices["application_trap"])
                + _op(0x00)
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

        if self.entry_capability_mask:
            code.extend(_op(0x41, _sleb(self.entry_capability_mask, 32)))
            code.extend(_call(self.import_indices["require_capabilities"]))

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


def _function_value_types(fn: dict[str, Any]) -> dict[str, Any]:
    types = {param["id"]: param["type"] for param in fn["params"]}
    for block in fn["blocks"]:
        for param in block["params"]:
            types[param["id"]] = param["type"]
        for op in block["ops"]:
            if "id" in op:
                types[op["id"]] = op["type"]
    return types


def _collect_runtime_needs(
    lir: dict[str, Any],
) -> tuple[set[str], set[str], bool, bool, bool, bool, bool]:
    string_constants: set[str] = set()
    console_types: set[str] = set()
    needs_string_eq = False
    needs_fs = False
    needs_net = False
    needs_application_trap = False
    needs_struct_eq = False

    for fn in lir["functions"]:
        types = _function_value_types(fn)
        for block in fn["blocks"]:
            for op in block["ops"]:
                name = op["op"]
                if name == "const" and op.get("type") == "string":
                    string_constants.add(op["value"])
                elif name == "value.eq":
                    comparison_type = types[op["args"][0]]
                    if comparison_type == "string":
                        needs_string_eq = True
                    elif _is_array_type(comparison_type) or _is_record_type(comparison_type):
                        needs_struct_eq = True
                        string_constants.add(
                            _type_descriptor_text(comparison_type)
                        )
                elif name == "console.write":
                    console_types.add(types[op["arg"]])
                elif name == "host.fs.read_text":
                    needs_fs = True
                elif name == "host.net.get_text":
                    needs_net = True

            term = block["term"]
            if term["op"] == "trap":
                needs_application_trap = True
                string_constants.update(
                    (term["code"], term["message"], term["where"])
                )

    return (
        string_constants,
        console_types,
        needs_string_eq,
        needs_fs,
        needs_net,
        needs_application_trap,
        needs_struct_eq,
    )


def _build_string_pool(
    values: set[str],
) -> tuple[dict[str, int], list[tuple[int, bytes]], int]:
    handles: dict[str, int] = {}
    segments: list[tuple[int, bytes]] = []
    offset = 0

    for value in sorted(values):
        encoded = value.encode("utf-8")
        handles[value] = _packed_string_handle(offset, len(encoded))
        if encoded:
            segments.append((offset, encoded))
            offset += len(encoded)

    if offset > 0x7FFFFFFF:
        raise CompilationError("WASM static UTF-8 string data exceeds i32 memory ABI")
    return handles, segments, offset


def compile_lir_to_wasm(lir: dict[str, Any]) -> WasmArtifact:
    verify_lir(lir)

    runtime = lir["runtime"]
    functions = lir["functions"]
    signatures = {
        fn["name"]: ([param["type"] for param in fn["params"]], fn["returns"])
        for fn in functions
    }

    (
        string_constants,
        console_types,
        needs_string_eq,
        needs_fs,
        needs_net,
        needs_application_trap,
        needs_struct_eq,
    ) = _collect_runtime_needs(lir)
    string_handles, string_segments, static_end = _build_string_pool(
        string_constants
    )

    needs_structured_memory = any(
        _is_array_type(typ) or _is_record_type(typ)
        for fn in functions
        for typ in (
            [fn["returns"]]
            + [param["type"] for param in fn["params"]]
            + [
                param["type"]
                for block in fn["blocks"]
                for param in block["params"]
            ]
            + [
                op["type"]
                for block in fn["blocks"]
                for op in block["ops"]
                if "type" in op
            ]
        )
    )
    needs_alloc = any(
        op["op"] in {"array.make", "record.make"}
        for fn in functions
        for block in fn["blocks"]
        for op in block["ops"]
    )

    needs_memory = (
        bool(string_constants)
        or needs_fs
        or needs_net
        or needs_string_eq
        or needs_application_trap
        or needs_struct_eq
        or needs_structured_memory
        or "string" in console_types
        or any(
        fn["returns"] == "string"
        or any(param["type"] == "string" for param in fn["params"])
        or any(
            param["type"] == "string"
            for block in fn["blocks"]
            for param in block["params"]
        )
        or any(
            op.get("type") == "string"
            for block in fn["blocks"]
            for op in block["ops"]
            if "type" in op
        )
        for fn in functions
        )
    )

    capabilities = runtime["capabilities"]
    inferred_capability_mask = 0
    for capability in capabilities:
        try:
            inferred_capability_mask |= CAPABILITY_BITS[capability]
        except KeyError as exc:
            raise CompilationError(
                f"unsupported WASM capability {capability!r}"
            ) from exc
    capability_mask = (
        inferred_capability_mask
        if runtime["capability_grants_required"]
        else 0
    )

    import_specs: list[tuple[str, list[Any], Any]] = [
        ("trap", ["bool"], "unit"),
    ]
    if capability_mask:
        import_specs.append(("require_capabilities", ["bool"], "unit"))
    if needs_string_eq:
        import_specs.append(("string_eq", ["string", "string"], "bool"))
    if needs_struct_eq:
        import_specs.append(
            ("struct_eq", ["string", "bool", "bool"], "bool")
        )
    if needs_application_trap:
        import_specs.append(
            ("application_trap", ["string", "string", "string"], "unit")
        )
    if needs_alloc:
        import_specs.append(("alloc", ["bool"], "bool"))
    for typ, import_name in (
        ("i64", "console_write_i64"),
        ("bool", "console_write_bool"),
        ("string", "console_write_string"),
    ):
        if typ in console_types:
            import_specs.append((import_name, [typ], "unit"))
    if needs_fs:
        import_specs.append(("fs_read_text", ["string"], "string"))
    if needs_fs or needs_net:
        import_specs.append(("require_host", ["bool"], "unit"))
    if needs_net:
        import_specs.append(("net_get_text", ["string"], "string"))

    import_indices = {
        name: index
        for index, (name, _, _) in enumerate(import_specs)
    }

    type_entries = [
        _function_type(params, result)
        for _, params, result in import_specs
    ] + [
        _function_type(
            [param["type"] for param in fn["params"]],
            fn["returns"],
        )
        for fn in functions
    ]
    type_section = _section(1, _vec(type_entries))

    import_entries = [
        _name("apl")
        + _name(name)
        + bytes([0x00])
        + _u32(type_index)
        for type_index, (name, _, _) in enumerate(import_specs)
    ]
    import_section = _section(2, _vec(import_entries))

    import_count = len(import_specs)
    function_indices = {
        fn["name"]: import_count + index
        for index, fn in enumerate(functions)
    }
    function_section = _section(
        3,
        _vec([
            _u32(import_count + index)
            for index in range(len(functions))
        ]),
    )

    memory_section = b""
    if needs_memory:
        minimum_pages = max(1, (max(static_end, 1) + 65535) // 65536)
        memory_entry = bytes([0x00]) + _u32(minimum_pages)
        memory_section = _section(5, _vec([memory_entry]))

    global_entries: list[bytes] = []
    budget_global_indices: dict[str, int] = {}
    for resource in RESOURCE_ORDER:
        limit = runtime["limits"][resource]
        if limit is not None:
            budget_global_indices[resource] = len(global_entries)
            global_entries.append(
                bytes([WASM_I64, 0x01])
                + _op(0x42, _sleb(limit, 64), 0x0B)
            )

    static_end_global_index: int | None = None
    if needs_memory:
        static_end_global_index = len(global_entries)
        global_entries.append(
            bytes([WASM_I32, 0x00])
            + _op(0x41, _sleb(static_end, 32), 0x0B)
        )
    global_section = _section(6, _vec(global_entries)) if global_entries else b""

    entry_name = lir["entry"]
    entry_index = function_indices[entry_name]
    export_entries = [
        _name("apl_entry") + bytes([0x00]) + _u32(entry_index)
    ]
    if needs_memory:
        export_entries.append(
            _name("memory") + bytes([0x02]) + _u32(0)
        )
        if static_end_global_index is None:
            raise RuntimeError("memory requires apl_static_end global")
        export_entries.append(
            _name("apl_static_end")
            + bytes([0x03])
            + _u32(static_end_global_index)
        )
    export_section = _section(7, _vec(export_entries))

    code_entries = [
        _FunctionCompiler(
            fn,
            function_indices=function_indices,
            signatures=signatures,
            import_indices=import_indices,
            budget_global_indices=budget_global_indices,
            string_handles=string_handles,
            entry_capability_mask=(
                capability_mask if fn["name"] == entry_name else 0
            ),
        ).compile()
        for fn in functions
    ]
    code_section = _section(10, _vec(code_entries))

    data_section = b""
    if string_segments:
        data_entries = [
            bytes([0x00])
            + _op(0x41, _sleb(offset, 32), 0x0B)
            + _u32(len(data))
            + data
            for offset, data in string_segments
        ]
        data_section = _section(11, _vec(data_entries))

    binary = (
        WASM_MAGIC_VERSION
        + type_section
        + import_section
        + function_section
        + memory_section
        + global_section
        + export_section
        + code_section
        + data_section
    )
    return WasmArtifact(
        binary=binary,
        entry_export="apl_entry",
        source_apl=lir["source_apl"],
        module=lir["module"],
    )


def compile_program_to_wasm(program: dict[str, Any]) -> WasmArtifact:
    return compile_lir_to_wasm(lower_program(program))
