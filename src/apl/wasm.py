from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import CompilationError
from .lir import lower_program, verify_lir


WASM_MAGIC_VERSION = b"\x00asm\x01\x00\x00\x00"
WASM_I32 = 0x7F
WASM_I64 = 0x7E
WASM_FUNC = 0x60

TRAP_I64_OVERFLOW = 1
TRAP_DIVISION_BY_ZERO = 2


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


def _value_type(typ: Any) -> int:
    if typ == "i64":
        return WASM_I64
    if typ == "bool":
        return WASM_I32
    raise CompilationError(
        f"WASM scalar backend supports only i64/bool values, got {typ!r}"
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
    ) -> None:
        self.fn = fn
        self.function_indices = function_indices
        self.signatures = signatures
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
        if name == "value.eq":
            opcode = 0x51 if typ == "i64" else 0x46 if typ == "bool" else None
        elif typ == "i64":
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
            return b""

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

        # Current normalized LIR routes every semantic return through a final
        # exit block. Support either a direct single-block return or exactly
        # that canonical b0 -> exit -> return trampoline. General CFG remains
        # deliberately unsupported in this checkpoint.
        if len(blocks) == 1:
            entry = blocks[0]
            exit_block = None
        elif len(blocks) == 2:
            entry, exit_block = blocks
            edge = entry["term"]
            if (
                edge.get("op") != "br"
                or edge.get("target") != exit_block["id"]
                or exit_block["ops"]
                or exit_block["term"].get("op") != "return"
            ):
                raise CompilationError(
                    f"{self.fn['name']}: WASM scalar backend does not support general CFG yet"
                )
        else:
            raise CompilationError(
                f"{self.fn['name']}: WASM scalar backend does not support general CFG yet"
            )

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

        local_decls = [
            _u32(1) + bytes([typ])
            for _, typ in local_types
        ]
        code = bytearray(_vec(local_decls))
        for op in entry["ops"]:
            code.extend(self.compile_op(op))

        if exit_block is None:
            term = entry["term"]
        else:
            edge = entry["term"]
            target_params = exit_block["params"]
            args = edge["args"]
            if len(args) != len(target_params):
                raise CompilationError(
                    f"{self.fn['name']}: malformed canonical exit branch"
                )
            for source, target in zip(args, target_params):
                code.extend(self._arg(source))
                code.extend(_local_set(self._index(target["id"])))
            term = exit_block["term"]

        if term["op"] != "return":
            raise CompilationError(
                f"{self.fn['name']}: WASM scalar backend requires return terminator"
            )
        if "value" in term:
            code.extend(self._arg(term["value"]))
        code.append(0x0B)
        body = bytes(code)
        return _u32(len(body)) + body


def compile_lir_to_wasm(lir: dict[str, Any]) -> WasmArtifact:
    verify_lir(lir)

    runtime = lir["runtime"]
    if runtime["capabilities"]:
        raise CompilationError(
            "WASM scalar backend does not support host capabilities yet"
        )
    if any(value is not None for value in runtime["limits"].values()):
        raise CompilationError(
            "WASM scalar backend does not support APL resource budgets yet"
        )

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

    code_entries = [
        _FunctionCompiler(
            fn,
            function_indices=function_indices,
            signatures=signatures,
        ).compile()
        for fn in functions
    ]
    code_section = _section(10, _vec(code_entries))

    binary = (
        WASM_MAGIC_VERSION
        + type_section
        + import_section
        + function_section
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
