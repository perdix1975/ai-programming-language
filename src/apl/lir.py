from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import SUPPORTED_LANGUAGE_VERSIONS
from .canonical import semantic_hash
from .errors import VerificationError
from .quantities import combine_quantity_types, is_quantity_type
from .ranges import is_range_type
from .verify import _validate_type, verify_program


LIR_VERSION = "0.1"


def _version_at_least(version: str, target: tuple[int, int, int]) -> bool:
    return tuple(int(part) for part in version.split(".")) >= target


def _fail(message: str) -> None:
    raise VerificationError(message)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _type_key(value: tuple[str, Any]) -> Any:
    return value[1]


def _infer_effects(program: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    functions = {fn["name"]: fn for fn in program["functions"]}
    memo: dict[str, tuple[str, ...]] = {}

    def sequence_effects(instructions: list[dict[str, Any]]) -> set[str]:
        effects: set[str] = set()
        for ins in instructions:
            op = ins["op"]
            if op == "print":
                effects.add("console.write")
            elif op in {"fs.read_text", "net.get_text"}:
                effects.add(op)
            elif op == "call":
                effects.update(function_effects(ins["function"]))
            elif op == "if":
                effects.update(sequence_effects(ins["then"]))
                effects.update(sequence_effects(ins["else"]))
            elif op == "repeat":
                effects.update(sequence_effects(ins["body"]))
        return effects

    def function_effects(name: str) -> tuple[str, ...]:
        if name in memo:
            return memo[name]
        result = tuple(sorted(sequence_effects(functions[name]["body"])))
        memo[name] = result
        return result

    for name in functions:
        function_effects(name)
    return memo


@dataclass
class _Block:
    id: str
    params: list[dict[str, Any]]
    ops: list[dict[str, Any]]
    term: dict[str, Any] | None = None

    def json(self) -> dict[str, Any]:
        if self.term is None:
            raise RuntimeError(f"lowering left block {self.id} unterminated")
        return {
            "id": self.id,
            "params": self.params,
            "ops": self.ops,
            "term": self.term,
        }


class _FunctionLowerer:
    def __init__(
        self,
        *,
        program: dict[str, Any],
        fn: dict[str, Any],
        invariant_definitions: dict[str, dict[str, Any]],
        inferred_effects: tuple[str, ...],
    ) -> None:
        self.program = program
        self.fn = fn
        self.invariants = invariant_definitions
        self.inferred_effects = inferred_effects
        self.value_counter = 0
        self.block_counter = 0
        self.blocks: list[_Block] = []
        self.current: _Block | None = None
        self.value_types: dict[str, Any] = {}
        self.exit_block: _Block | None = None
        self.exit_env: dict[str, tuple[str, Any]] | None = None
        self.exit_result: tuple[str, Any] | None = None

        self.param_env: dict[str, tuple[str, Any]] = {}
        self.params: list[dict[str, Any]] = []
        for param in fn["params"]:
            value_id = self._new_value(param["type"])
            self.params.append({"id": value_id, "type": param["type"]})
            self.param_env[param["name"]] = (value_id, param["type"])

    def _new_value(self, typ: Any) -> str:
        value_id = f"v{self.value_counter}"
        self.value_counter += 1
        self.value_types[value_id] = typ
        return value_id

    def _new_block(
        self,
        param_types: list[Any] | None = None,
    ) -> tuple[_Block, list[tuple[str, Any]]]:
        block_id = f"b{self.block_counter}"
        self.block_counter += 1
        params: list[dict[str, Any]] = []
        values: list[tuple[str, Any]] = []
        for typ in param_types or []:
            value_id = self._new_value(typ)
            params.append({"id": value_id, "type": typ})
            values.append((value_id, typ))
        block = _Block(block_id, params, [])
        self.blocks.append(block)
        return block, values

    def _switch(self, block: _Block) -> None:
        self.current = block

    def _append(self, op: dict[str, Any]) -> None:
        if self.current is None or self.current.term is not None:
            raise RuntimeError("cannot append to terminated/no current block")
        self.current.ops.append(op)

    def _terminate(self, term: dict[str, Any]) -> None:
        if self.current is None or self.current.term is not None:
            raise RuntimeError("cannot terminate terminated/no current block")
        self.current.term = term

    def _tick(self, where: str) -> None:
        self._append({"op": "budget.step", "where": where})

    def _emit_value(
        self,
        op: str,
        typ: Any,
        **fields: Any,
    ) -> tuple[str, Any]:
        value_id = self._new_value(typ)
        payload = {"op": op, "id": value_id, "type": typ}
        payload.update(fields)
        self._append(payload)
        return value_id, typ

    def _edge(
        self,
        target: _Block,
        args: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        return {"target": target.id, "args": [value_id for value_id, _ in args]}

    def _clone_env_block(
        self,
        env: dict[str, tuple[str, Any]],
        extra_types: list[Any] | None = None,
    ) -> tuple[_Block, dict[str, tuple[str, Any]], list[tuple[str, Any]]]:
        env_items = list(env.items())
        types = [typ for _, (_, typ) in env_items] + list(extra_types or [])
        block, values = self._new_block(types)
        cloned: dict[str, tuple[str, Any]] = {}
        for (name, _), value in zip(env_items, values):
            cloned[name] = value
        extras = values[len(env_items):]
        return block, cloned, extras

    def _env_args(self, env: dict[str, tuple[str, Any]]) -> list[tuple[str, Any]]:
        return list(env.values())

    def _lower_predicate(
        self,
        expr: dict[str, Any],
        *,
        env: dict[str, tuple[str, Any]],
        result: tuple[str, Any] | None,
        where: str,
    ) -> tuple[str, Any]:
        self._tick(where)

        if set(expr) == {"var"}:
            return env[expr["var"]]

        if set(expr) == {"result"}:
            if result is None:
                raise RuntimeError("verified result reference missing during lowering")
            return result

        if set(expr) == {"const"}:
            raw = expr["const"]
            return self._emit_value(
                "const",
                raw["type"],
                value=raw["value"],
            )

        if set(expr) == {"invariant", "args"}:
            name = expr["invariant"]
            definition = self.invariants[name]
            arg_values = [
                self._lower_predicate(
                    arg,
                    env=env,
                    result=result,
                    where=f"{where}.args[{index}]",
                )
                for index, arg in enumerate(expr["args"])
            ]
            invariant_env = {
                param["name"]: value
                for param, value in zip(definition["params"], arg_values)
            }
            return self._lower_predicate(
                definition["predicate"],
                env=invariant_env,
                result=None,
                where=f"{where}.invariant[{name}]",
            )

        op = expr["op"]
        arg_values = [
            self._lower_predicate(
                arg,
                env=env,
                result=result,
                where=f"{where}.args[{index}]",
            )
            for index, arg in enumerate(expr["args"])
        ]
        args = [value_id for value_id, _ in arg_values]

        if op == "eq":
            return self._emit_value("value.eq", "bool", args=args)
        if op in {"lt", "le", "gt", "ge"}:
            return self._emit_value(f"value.{op}", "bool", args=args)
        if op == "not":
            return self._emit_value("bool.not", "bool", args=args)
        if op in {"and", "or"}:
            return self._emit_value(f"bool.{op}", "bool", args=args)
        raise RuntimeError(f"unsupported verified predicate op {op!r}")

    def _lower_contracts(
        self,
        clauses: list[dict[str, Any]],
        *,
        env: dict[str, tuple[str, Any]],
        result: tuple[str, Any] | None,
        kind: str,
    ) -> None:
        trap_code = (
            "apl.precondition_failed"
            if kind == "requires"
            else "apl.postcondition_failed"
        )
        for index, clause in enumerate(clauses):
            where = f"{self.fn['name']}.{kind}[{index}]"
            cond, _ = self._lower_predicate(
                clause["predicate"],
                env=env,
                result=result,
                where=f"{where}.predicate",
            )
            self._append(
                {
                    "op": "guard",
                    "cond": cond,
                    "code": trap_code,
                    "message": (
                        f"contract '{clause['id']}' failed: {clause['message']}"
                    ),
                    "where": where,
                }
            )

    def _get_exit(self) -> tuple[_Block, dict[str, tuple[str, Any]], tuple[str, Any] | None]:
        if self.exit_block is not None:
            return self.exit_block, self.exit_env or {}, self.exit_result

        param_names = list(self.param_env)
        param_types = [self.param_env[name][1] for name in param_names]
        if self.fn["returns"] != "unit":
            param_types.append(self.fn["returns"])

        block, values = self._new_block(param_types)
        exit_env: dict[str, tuple[str, Any]] = {}
        for name, value in zip(param_names, values):
            exit_env[name] = value
        exit_result = values[-1] if self.fn["returns"] != "unit" else None

        self.exit_block = block
        self.exit_env = exit_env
        self.exit_result = exit_result
        return block, exit_env, exit_result

    def _lower_invariant_check(
        self,
        ins: dict[str, Any],
        env: dict[str, tuple[str, Any]],
        where: str,
    ) -> None:
        definition = self.invariants[ins["invariant"]]
        invariant_env = {
            param["name"]: env[arg]
            for param, arg in zip(definition["params"], ins["args"])
        }
        cond, _ = self._lower_predicate(
            definition["predicate"],
            env=invariant_env,
            result=None,
            where=f"{where}.predicate",
        )
        self._append(
            {
                "op": "guard",
                "cond": cond,
                "code": "apl.invariant_failed",
                "message": (
                    f"invariant '{ins['invariant']}' failed: "
                    f"{definition['message']}"
                ),
                "where": where,
            }
        )

    def _lower_if(
        self,
        ins: dict[str, Any],
        env: dict[str, tuple[str, Any]],
        where: str,
    ) -> dict[str, tuple[str, Any]]:
        outer_env = dict(env)
        then_block, then_env, _ = self._clone_env_block(outer_env)
        else_block, else_env, _ = self._clone_env_block(outer_env)
        merge_block, merge_env, merge_extra = self._clone_env_block(
            outer_env, [ins["type"]]
        )
        merge_result = merge_extra[0]

        cond = outer_env[ins["cond"]][0]
        outer_args = self._env_args(outer_env)
        self._terminate(
            {
                "op": "cond_br",
                "cond": cond,
                "then": self._edge(then_block, outer_args),
                "else": self._edge(else_block, outer_args),
            }
        )

        self._switch(then_block)
        self._lower_sequence(
            ins["then"],
            then_env,
            where_prefix=f"{where}.then",
            terminator="yield",
            continuation=(merge_block, merge_env),
        )

        self._switch(else_block)
        self._lower_sequence(
            ins["else"],
            else_env,
            where_prefix=f"{where}.else",
            terminator="yield",
            continuation=(merge_block, merge_env),
        )

        self._switch(merge_block)
        result_env = dict(merge_env)
        result_env[ins["id"]] = merge_result
        return result_env

    def _lower_repeat(
        self,
        ins: dict[str, Any],
        env: dict[str, tuple[str, Any]],
        where: str,
    ) -> dict[str, tuple[str, Any]]:
        outer_env = dict(env)
        carry_type = outer_env[ins["init"]][1]

        header, header_env, header_extra = self._clone_env_block(
            outer_env, ["i64", carry_type]
        )
        header_index, header_carry = header_extra

        body, body_env, body_extra = self._clone_env_block(
            outer_env, ["i64", carry_type]
        )
        body_index, body_carry = body_extra
        body_env[ins["index"]] = body_index
        body_env[ins["carry"]] = body_carry

        exit_block, exit_env, exit_extra = self._clone_env_block(
            outer_env, [carry_type]
        )
        exit_carry = exit_extra[0]

        count = outer_env[ins["count"]][0]
        self._append(
            {
                "op": "repeat.guard",
                "count": count,
                "max": ins["max"],
                "where": where,
            }
        )
        zero = self._emit_value("const", "i64", value=0)
        self._terminate(
            {
                "op": "br",
                **self._edge(
                    header,
                    self._env_args(outer_env) + [zero, outer_env[ins["init"]]],
                ),
            }
        )

        self._switch(header)
        header_count = header_env[ins["count"]][0]
        loop_cond = self._emit_value(
            "i64.lt",
            "bool",
            args=[header_index[0], header_count],
        )
        header_args = self._env_args(header_env)
        self._terminate(
            {
                "op": "cond_br",
                "cond": loop_cond[0],
                "then": self._edge(
                    body,
                    header_args + [header_index, header_carry],
                ),
                "else": self._edge(
                    exit_block,
                    header_args + [header_carry],
                ),
            }
        )

        self._switch(body)
        continuation = (header, header_env)
        self._lower_sequence(
            ins["body"],
            body_env,
            where_prefix=f"{where}.body",
            terminator="yield",
            continuation=continuation,
            repeat_backedge=(
                outer_env,
                ins["index"],
                header,
            ),
        )

        self._switch(exit_block)
        result_env = dict(exit_env)
        result_env[ins["id"]] = exit_carry
        return result_env

    def _lower_simple(
        self,
        ins: dict[str, Any],
        env: dict[str, tuple[str, Any]],
        where: str,
    ) -> None:
        op = ins["op"]

        if op == "const":
            value = self._emit_value("const", ins["type"], value=ins["value"])
            env[ins["id"]] = value
            return

        binary_map = {
            "add": "i64.add",
            "sub": "i64.sub",
            "mul": "i64.mul",
            "div": "i64.div",
            "rem": "i64.rem",
            "lt": "i64.lt",
            "le": "i64.le",
            "gt": "i64.gt",
            "ge": "i64.ge",
            "eq": "value.eq",
        }
        if op in binary_map:
            typ = "bool" if op in {"lt", "le", "gt", "ge", "eq"} else ins["type"]
            value = self._emit_value(
                binary_map[op],
                typ,
                args=[env[name][0] for name in ins["args"]],
                where=where,
            )
            env[ins["id"]] = value
            return

        if op == "print":
            self._append(
                {
                    "op": "console.write",
                    "arg": env[ins["args"][0]][0],
                    "where": where,
                }
            )
            return

        if op == "call":
            args = [env[name][0] for name in ins["args"]]
            target = ins["function"]
            target_fn = next(
                fn for fn in self.program["functions"] if fn["name"] == target
            )
            returns = target_fn["returns"]
            if returns == "unit":
                self._append(
                    {
                        "op": "call",
                        "function": target,
                        "args": args,
                        "where": where,
                    }
                )
            else:
                value = self._emit_value(
                    "call",
                    returns,
                    function=target,
                    args=args,
                    where=where,
                )
                env[ins["id"]] = value
            return

        if op == "array":
            value = self._emit_value(
                "array.make",
                ins["type"],
                args=[env[name][0] for name in ins["args"]],
            )
            env[ins["id"]] = value
            return

        if op == "array.get":
            value = self._emit_value(
                "array.get",
                ins["type"],
                args=[env[name][0] for name in ins["args"]],
                where=where,
            )
            env[ins["id"]] = value
            return

        if op == "array.len":
            value = self._emit_value(
                "array.len",
                "i64",
                arg=env[ins["args"][0]][0],
            )
            env[ins["id"]] = value
            return

        if op == "record":
            value = self._emit_value(
                "record.make",
                ins["type"],
                fields={
                    field: env[source][0]
                    for field, source in sorted(ins["fields"].items())
                },
            )
            env[ins["id"]] = value
            return

        if op == "record.get":
            value = self._emit_value(
                "record.get",
                ins["type"],
                record=env[ins["record"]][0],
                field=ins["field"],
            )
            env[ins["id"]] = value
            return

        if op == "range.check":
            value = self._emit_value(
                "range.check",
                ins["type"],
                arg=env[ins["args"][0]][0],
                where=where,
            )
            env[ins["id"]] = value
            return

        if op == "range.value":
            value = self._emit_value(
                "range.value",
                "i64",
                arg=env[ins["args"][0]][0],
            )
            env[ins["id"]] = value
            return

        if op == "quantity.attach":
            value = self._emit_value(
                "quantity.attach",
                ins["type"],
                arg=env[ins["args"][0]][0],
            )
            env[ins["id"]] = value
            return

        if op == "quantity.value":
            value = self._emit_value(
                "quantity.value",
                "i64",
                arg=env[ins["args"][0]][0],
            )
            env[ins["id"]] = value
            return

        if op in {"quantity.add", "quantity.sub", "quantity.mul", "quantity.div"}:
            value = self._emit_value(
                op,
                ins["type"],
                args=[env[name][0] for name in ins["args"]],
                where=where,
            )
            env[ins["id"]] = value
            return

        if op in {"fs.read_text", "net.get_text"}:
            value = self._emit_value(
                f"host.{op}",
                "string",
                arg=env[ins["args"][0]][0],
                where=where,
            )
            env[ins["id"]] = value
            return

        raise RuntimeError(f"unsupported verified source op {op!r}")

    def _lower_sequence(
        self,
        instructions: list[dict[str, Any]],
        env: dict[str, tuple[str, Any]],
        *,
        where_prefix: str,
        terminator: str,
        continuation: tuple[_Block, dict[str, tuple[str, Any]]] | None = None,
        repeat_backedge: tuple[
            dict[str, tuple[str, Any]],
            str,
            _Block,
        ] | None = None,
    ) -> None:
        for index, ins in enumerate(instructions):
            where = f"{where_prefix}[{index}]"
            op = ins["op"]
            self._tick(where)

            if op == terminator:
                if terminator == "return":
                    exit_block, _, _ = self._get_exit()
                    args = [
                        env[name]
                        for name in self.param_env
                    ]
                    if self.fn["returns"] != "unit":
                        args.append(env[ins["value"]])
                    self._terminate(
                        {"op": "br", **self._edge(exit_block, args)}
                    )
                    return

                if repeat_backedge is not None:
                    outer_env, index_name, header = repeat_backedge
                    yielded = env[ins["value"]]
                    one = self._emit_value("const", "i64", value=1)
                    next_index = self._emit_value(
                        "i64.add",
                        "i64",
                        args=[env[index_name][0], one[0]],
                    )
                    back_args = [
                        env[name]
                        for name in outer_env
                    ] + [next_index, yielded]
                    self._terminate(
                        {"op": "br", **self._edge(header, back_args)}
                    )
                    return

                if continuation is None:
                    raise RuntimeError("yield missing lowering continuation")
                target, continuation_env = continuation
                args = [
                    env[name]
                    for name in continuation_env
                ] + [env[ins["value"]]]
                self._terminate({"op": "br", **self._edge(target, args)})
                return

            if op == "trap":
                self._terminate(
                    {
                        "op": "trap",
                        "code": ins["code"],
                        "message": ins["message"],
                        "where": where,
                    }
                )
                return

            if op == "if":
                env = self._lower_if(ins, env, where)
                continue

            if op == "repeat":
                env = self._lower_repeat(ins, env, where)
                continue

            if op == "invariant.check":
                self._lower_invariant_check(ins, env, where)
                continue

            self._lower_simple(ins, env, where)

        raise RuntimeError(f"verified sequence {where_prefix} did not terminate")

    def lower(self) -> dict[str, Any]:
        entry, _ = self._new_block()
        self._switch(entry)
        env = dict(self.param_env)

        if "requires" in self.fn:
            self._lower_contracts(
                self.fn["requires"],
                env=env,
                result=None,
                kind="requires",
            )

        self._lower_sequence(
            self.fn["body"],
            env,
            where_prefix=self.fn["name"],
            terminator="return",
        )

        if self.exit_block is not None:
            self._switch(self.exit_block)
            if "ensures" in self.fn:
                self._lower_contracts(
                    self.fn["ensures"],
                    env=self.exit_env or {},
                    result=self.exit_result,
                    kind="ensures",
                )
            if self.fn["returns"] == "unit":
                self._terminate({"op": "return"})
            else:
                if self.exit_result is None:
                    raise RuntimeError("non-unit lowering has no exit result")
                self._terminate(
                    {"op": "return", "value": self.exit_result[0]}
                )

        return {
            "name": self.fn["name"],
            "params": self.params,
            "returns": self.fn["returns"],
            "effects": list(self.inferred_effects),
            "blocks": [block.json() for block in self.blocks],
        }


def lower_program(program: dict[str, Any]) -> dict[str, Any]:
    """Verify and deterministically lower semantic APL IR to normalized CFG LIR."""
    verify_program(program)
    version = program["apl"]
    effects = _infer_effects(program)
    invariant_definitions = {
        item["name"]: item
        for item in program.get("invariants", [])
    }

    inferred_capabilities = sorted(
        {
            effect
            for function_effects in effects.values()
            for effect in function_effects
        }
    )

    limits = (
        dict(program["limits"])
        if _version_at_least(version, (0, 0, 10))
        else {
            "steps": None,
            "output_lines": None,
            "host_reads": None,
        }
    )

    functions = [
        _FunctionLowerer(
            program=program,
            fn=fn,
            invariant_definitions=invariant_definitions,
            inferred_effects=effects[fn["name"]],
        ).lower()
        for fn in sorted(program["functions"], key=lambda item: item["name"])
    ]

    lir = {
        "apl_lir": LIR_VERSION,
        "source_apl": version,
        "module": program["module"],
        "entry": program["entry"],
        "runtime": {
            "capability_grants_required": _version_at_least(version, (0, 0, 8)),
            "capabilities": inferred_capabilities,
            "limits": limits,
        },
        "functions": functions,
    }
    verify_lir(lir)
    return lir


def lower_hash(program: dict[str, Any]) -> str:
    return semantic_hash(lower_program(program))


def _is_integer_like(typ: Any) -> bool:
    return typ == "i64" or is_range_type(typ) or is_quantity_type(typ)


def _check_id(value: Any, prefix: str, where: str) -> str:
    _expect(
        isinstance(value, str)
        and value.startswith(prefix)
        and value[len(prefix):].isdigit(),
        f"{where}: expected normalized {prefix}N id",
    )
    return value


def verify_lir(lir: Any) -> None:
    """Verify normalized APL LIR independently of the source program."""
    _expect(isinstance(lir, dict), "LIR root must be an object")
    _expect(
        set(lir) == {
            "apl_lir",
            "source_apl",
            "module",
            "entry",
            "runtime",
            "functions",
        },
        "LIR root has unexpected or missing fields",
    )
    _expect(lir.get("apl_lir") == LIR_VERSION, f"unsupported APL LIR version '{lir.get('apl_lir')}'")
    source_apl = lir.get("source_apl")
    _expect(
        source_apl in SUPPORTED_LANGUAGE_VERSIONS,
        f"unsupported source APL version '{source_apl}'",
    )
    _expect(
        isinstance(lir.get("module"), str) and bool(lir["module"]),
        "LIR module must be a non-empty string",
    )
    _expect(
        isinstance(lir.get("entry"), str) and bool(lir["entry"]),
        "LIR entry must be a non-empty string",
    )

    runtime = lir.get("runtime")
    _expect(
        isinstance(runtime, dict)
        and set(runtime) == {
            "capability_grants_required",
            "capabilities",
            "limits",
        },
        "LIR runtime must contain exactly capability_grants_required, capabilities, and limits",
    )
    _expect(
        isinstance(runtime["capability_grants_required"], bool),
        "LIR capability_grants_required must be bool",
    )
    capabilities = runtime["capabilities"]
    _expect(
        isinstance(capabilities, list)
        and capabilities == sorted(set(capabilities))
        and all(isinstance(item, str) for item in capabilities),
        "LIR capabilities must be a sorted unique string list",
    )
    limits = runtime["limits"]
    _expect(
        isinstance(limits, dict)
        and set(limits) == {"steps", "output_lines", "host_reads"},
        "LIR limits must contain exactly steps, output_lines, and host_reads",
    )
    for name, value in limits.items():
        _expect(
            value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0),
            f"LIR limit {name} must be a non-negative integer or null",
        )

    functions = lir.get("functions")
    _expect(
        isinstance(functions, list) and bool(functions),
        "LIR functions must be a non-empty list",
    )
    names = [fn.get("name") for fn in functions if isinstance(fn, dict)]
    _expect(
        len(names) == len(functions)
        and all(isinstance(name, str) and bool(name) for name in names),
        "LIR function names must be non-empty strings",
    )
    _expect(names == sorted(names), "LIR functions must be sorted by name")
    _expect(len(names) == len(set(names)), "LIR function names must be unique")
    _expect(lir["entry"] in names, f"LIR entry function '{lir['entry']}' does not exist")

    signatures: dict[str, tuple[list[Any], Any]] = {}
    for fn in functions:
        params = fn.get("params")
        returns = fn.get("returns")
        _expect(isinstance(params, list), f"{fn['name']}: LIR params must be a list")
        for index, param in enumerate(params):
            _expect(
                isinstance(param, dict) and set(param) == {"id", "type"},
                f"{fn['name']}: param {index} must contain id and type",
            )
            _validate_type(param["type"], source_apl, f"{fn['name']}: param {index}")
        _validate_type(returns, source_apl, f"{fn['name']}: return type")
        signatures[fn["name"]] = ([param["type"] for param in params], returns)

    for fn in functions:
        _verify_lir_function(fn, source_apl, signatures)


def _verify_lir_function(
    fn: dict[str, Any],
    source_apl: str,
    signatures: dict[str, tuple[list[Any], Any]],
) -> None:
    name = fn["name"]
    _expect(
        set(fn) == {"name", "params", "returns", "effects", "blocks"},
        f"{name}: LIR function has unexpected or missing fields",
    )
    effects = fn["effects"]
    _expect(
        isinstance(effects, list)
        and effects == sorted(set(effects))
        and all(isinstance(item, str) for item in effects),
        f"{name}: LIR effects must be a sorted unique string list",
    )
    blocks = fn["blocks"]
    _expect(
        isinstance(blocks, list) and bool(blocks),
        f"{name}: LIR blocks must be a non-empty list",
    )
    expected_block_ids = [f"b{i}" for i in range(len(blocks))]
    actual_block_ids = [block.get("id") for block in blocks if isinstance(block, dict)]
    _expect(
        actual_block_ids == expected_block_ids,
        f"{name}: LIR block ids must be dense b0..bN in serialization order",
    )

    block_params: dict[str, list[tuple[str, Any]]] = {}
    all_ids: set[str] = set()
    fn_param_ids: list[str] = []
    for index, param in enumerate(fn["params"]):
        value_id = _check_id(param["id"], "v", f"{name}: param {index}")
        _expect(value_id not in all_ids, f"{name}: duplicate LIR value id '{value_id}'")
        all_ids.add(value_id)
        fn_param_ids.append(value_id)

    for block in blocks:
        _expect(
            isinstance(block, dict)
            and set(block) == {"id", "params", "ops", "term"},
            f"{name}.{block.get('id', '?')}: block has unexpected or missing fields",
        )
        params = block["params"]
        _expect(isinstance(params, list), f"{name}.{block['id']}: params must be a list")
        typed_params: list[tuple[str, Any]] = []
        for index, param in enumerate(params):
            _expect(
                isinstance(param, dict) and set(param) == {"id", "type"},
                f"{name}.{block['id']}: block param {index} must contain id and type",
            )
            value_id = _check_id(
                param["id"], "v", f"{name}.{block['id']}: block param {index}"
            )
            _validate_type(
                param["type"],
                source_apl,
                f"{name}.{block['id']}: block param {index}",
            )
            _expect(value_id not in all_ids, f"{name}: duplicate LIR value id '{value_id}'")
            all_ids.add(value_id)
            typed_params.append((value_id, param["type"]))
        block_params[block["id"]] = typed_params

    _expect(
        blocks[0]["params"] == [],
        f"{name}.b0: entry block must not have block parameters",
    )

    target_map = {block["id"]: block for block in blocks}
    function_param_types = {
        param["id"]: param["type"]
        for param in fn["params"]
    }

    for block in blocks:
        available: dict[str, Any] = {
            value_id: typ for value_id, typ in block_params[block["id"]]
        }
        if block["id"] == "b0":
            available.update(function_param_types)

        ops = block["ops"]
        _expect(isinstance(ops, list), f"{name}.{block['id']}: ops must be a list")
        for index, op in enumerate(ops):
            where = f"{name}.{block['id']}.ops[{index}]"
            result = _verify_lir_op(
                op,
                available,
                source_apl,
                signatures,
                where,
            )
            if result is not None:
                value_id, typ = result
                _expect(value_id not in all_ids, f"{name}: duplicate LIR value id '{value_id}'")
                all_ids.add(value_id)
                available[value_id] = typ

        _verify_lir_term(
            block["term"],
            available,
            block_params,
            target_map,
            fn["returns"],
            f"{name}.{block['id']}.term",
        )

    indices = sorted(int(value_id[1:]) for value_id in all_ids)
    _expect(
        indices == list(range(len(indices))),
        f"{name}: LIR value ids must be dense v0..vN",
    )


def _lookup(available: dict[str, Any], value_id: Any, where: str) -> Any:
    _expect(
        isinstance(value_id, str) and value_id in available,
        f"{where}: value '{value_id}' is not available in this block",
    )
    return available[value_id]


def _verify_result_id(op: dict[str, Any], where: str) -> str:
    return _check_id(op.get("id"), "v", where)


def _verify_lir_op(
    op: Any,
    available: dict[str, Any],
    source_apl: str,
    signatures: dict[str, tuple[list[Any], Any]],
    where: str,
) -> tuple[str, Any] | None:
    _expect(isinstance(op, dict), f"{where}: op must be an object")
    name = op.get("op")
    _expect(isinstance(name, str), f"{where}: op name must be a string")

    if name == "budget.step":
        _expect(
            set(op) == {"op", "where"} and isinstance(op["where"], str),
            f"{where}: budget.step must contain op and where",
        )
        return None

    if name == "guard":
        _expect(
            set(op) == {"op", "cond", "code", "message", "where"},
            f"{where}: guard has unexpected or missing fields",
        )
        _expect(_lookup(available, op["cond"], where) == "bool", f"{where}: guard cond must be bool")
        _expect(
            all(isinstance(op[key], str) and bool(op[key]) for key in ("code", "message", "where")),
            f"{where}: guard code/message/where must be non-empty strings",
        )
        return None

    if name == "repeat.guard":
        _expect(
            set(op) == {"op", "count", "max", "where"},
            f"{where}: repeat.guard has unexpected or missing fields",
        )
        _expect(_lookup(available, op["count"], where) == "i64", f"{where}: repeat count must be i64")
        _expect(
            isinstance(op["max"], int)
            and not isinstance(op["max"], bool)
            and 0 <= op["max"] <= 1_000_000,
            f"{where}: repeat max is invalid",
        )
        _expect(isinstance(op["where"], str), f"{where}: repeat.guard where must be string")
        return None

    if name == "console.write":
        _expect(set(op) == {"op", "arg", "where"}, f"{where}: console.write fields invalid")
        typ = _lookup(available, op["arg"], where)
        _expect(typ in {"i64", "bool", "string"}, f"{where}: console.write requires scalar")
        return None

    if name == "const":
        _expect(set(op) == {"op", "id", "type", "value"}, f"{where}: const fields invalid")
        value_id = _verify_result_id(op, where)
        typ = op["type"]
        _expect(typ in {"i64", "bool", "string"}, f"{where}: const type invalid")
        value = op["value"]
        valid = (
            (typ == "i64" and isinstance(value, int) and not isinstance(value, bool) and -(2**63) <= value <= 2**63 - 1)
            or (typ == "bool" and isinstance(value, bool))
            or (typ == "string" and isinstance(value, str))
        )
        _expect(valid, f"{where}: const value/type mismatch")
        return value_id, typ

    binary_i64 = {"i64.add", "i64.sub", "i64.mul", "i64.div", "i64.rem"}
    binary_cmp = {"i64.lt", "i64.le", "i64.gt", "i64.ge"}
    if name in binary_i64 | binary_cmp:
        expected_fields = {"op", "id", "type", "args"}
        if "where" in op:
            expected_fields.add("where")
        _expect(set(op) == expected_fields, f"{where}: {name} fields invalid")
        args = op["args"]
        _expect(isinstance(args, list) and len(args) == 2, f"{where}: {name} requires two args")
        _expect(all(_lookup(available, arg, where) == "i64" for arg in args), f"{where}: {name} args must be i64")
        result_type = "bool" if name in binary_cmp else "i64"
        _expect(op["type"] == result_type, f"{where}: {name} result type mismatch")
        return _verify_result_id(op, where), result_type

    if name in {"value.eq", "value.lt", "value.le", "value.gt", "value.ge"}:
        expected_fields = {"op", "id", "type", "args"}
        if "where" in op:
            expected_fields.add("where")
        _expect(
            set(op) == expected_fields,
            f"{where}: {name} fields invalid",
        )
        args = op["args"]
        _expect(isinstance(args, list) and len(args) == 2, f"{where}: {name} requires two args")
        left = _lookup(available, args[0], where)
        right = _lookup(available, args[1], where)
        _expect(left == right and left != "unit", f"{where}: {name} args must have identical non-unit types")
        if name != "value.eq":
            _expect(_is_integer_like(left), f"{where}: ordered value comparison requires integer-like types")
        _expect(op["type"] == "bool", f"{where}: {name} result must be bool")
        return _verify_result_id(op, where), "bool"

    if name == "bool.not":
        _expect(set(op) == {"op", "id", "type", "args"}, f"{where}: bool.not fields invalid")
        args = op["args"]
        _expect(isinstance(args, list) and len(args) == 1, f"{where}: bool.not requires one arg")
        _expect(_lookup(available, args[0], where) == "bool", f"{where}: bool.not arg must be bool")
        _expect(op["type"] == "bool", f"{where}: bool.not result must be bool")
        return _verify_result_id(op, where), "bool"

    if name in {"bool.and", "bool.or"}:
        _expect(set(op) == {"op", "id", "type", "args"}, f"{where}: {name} fields invalid")
        args = op["args"]
        _expect(isinstance(args, list) and len(args) == 2, f"{where}: {name} requires two args")
        _expect(all(_lookup(available, arg, where) == "bool" for arg in args), f"{where}: {name} args must be bool")
        _expect(op["type"] == "bool", f"{where}: {name} result must be bool")
        return _verify_result_id(op, where), "bool"

    if name == "call":
        target = op.get("function")
        _expect(isinstance(target, str) and target in signatures, f"{where}: unknown call target '{target}'")
        param_types, returns = signatures[target]
        args = op.get("args")
        _expect(isinstance(args, list) and len(args) == len(param_types), f"{where}: call arity mismatch")
        for index, (arg, expected) in enumerate(zip(args, param_types)):
            _expect(_lookup(available, arg, where) == expected, f"{where}: call arg {index} type mismatch")
        if returns == "unit":
            _expect(
                set(op) == {"op", "function", "args", "where"},
                f"{where}: unit call fields invalid",
            )
            return None
        _expect(
            set(op) == {"op", "id", "type", "function", "args", "where"},
            f"{where}: value call fields invalid",
        )
        _expect(op["type"] == returns, f"{where}: call result type mismatch")
        return _verify_result_id(op, where), returns

    if name == "array.make":
        _expect(set(op) == {"op", "id", "type", "args"}, f"{where}: array.make fields invalid")
        typ = op["type"]
        _validate_type(typ, source_apl, f"{where}.type")
        _expect(isinstance(typ, dict) and set(typ) == {"array", "len"}, f"{where}: array.make result type invalid")
        args = op["args"]
        _expect(isinstance(args, list) and len(args) == typ["len"], f"{where}: array.make arity mismatch")
        _expect(all(_lookup(available, arg, where) == typ["array"] for arg in args), f"{where}: array.make element type mismatch")
        return _verify_result_id(op, where), typ

    if name == "array.get":
        _expect(set(op) == {"op", "id", "type", "args", "where"}, f"{where}: array.get fields invalid")
        args = op["args"]
        _expect(isinstance(args, list) and len(args) == 2, f"{where}: array.get requires two args")
        array_type = _lookup(available, args[0], where)
        _expect(isinstance(array_type, dict) and set(array_type) == {"array", "len"}, f"{where}: array.get source must be array")
        _expect(_lookup(available, args[1], where) == "i64", f"{where}: array.get index must be i64")
        _expect(op["type"] == array_type["array"], f"{where}: array.get result type mismatch")
        return _verify_result_id(op, where), op["type"]

    if name == "array.len":
        _expect(set(op) == {"op", "id", "type", "arg"}, f"{where}: array.len fields invalid")
        array_type = _lookup(available, op["arg"], where)
        _expect(isinstance(array_type, dict) and set(array_type) == {"array", "len"}, f"{where}: array.len source must be array")
        _expect(op["type"] == "i64", f"{where}: array.len result must be i64")
        return _verify_result_id(op, where), "i64"

    if name == "record.make":
        _expect(set(op) == {"op", "id", "type", "fields"}, f"{where}: record.make fields invalid")
        typ = op["type"]
        _validate_type(typ, source_apl, f"{where}.type")
        _expect(isinstance(typ, dict) and set(typ) == {"record"}, f"{where}: record.make result type invalid")
        fields = op["fields"]
        _expect(isinstance(fields, dict) and list(fields) == sorted(fields), f"{where}: record.make fields must be sorted")
        _expect(set(fields) == set(typ["record"]), f"{where}: record.make field set mismatch")
        for field, value_id in fields.items():
            _expect(_lookup(available, value_id, where) == typ["record"][field], f"{where}: record field '{field}' type mismatch")
        return _verify_result_id(op, where), typ

    if name == "record.get":
        _expect(set(op) == {"op", "id", "type", "record", "field"}, f"{where}: record.get fields invalid")
        record_type = _lookup(available, op["record"], where)
        _expect(isinstance(record_type, dict) and set(record_type) == {"record"}, f"{where}: record.get source must be record")
        field = op["field"]
        _expect(isinstance(field, str) and field in record_type["record"], f"{where}: record.get field invalid")
        _expect(op["type"] == record_type["record"][field], f"{where}: record.get result type mismatch")
        return _verify_result_id(op, where), op["type"]

    if name == "range.check":
        _expect(set(op) == {"op", "id", "type", "arg", "where"}, f"{where}: range.check fields invalid")
        _expect(_lookup(available, op["arg"], where) == "i64", f"{where}: range.check source must be i64")
        _validate_type(op["type"], source_apl, f"{where}.type")
        _expect(is_range_type(op["type"]), f"{where}: range.check result must be range")
        return _verify_result_id(op, where), op["type"]

    if name == "range.value":
        _expect(set(op) == {"op", "id", "type", "arg"}, f"{where}: range.value fields invalid")
        _expect(is_range_type(_lookup(available, op["arg"], where)), f"{where}: range.value source must be range")
        _expect(op["type"] == "i64", f"{where}: range.value result must be i64")
        return _verify_result_id(op, where), "i64"

    if name == "quantity.attach":
        _expect(set(op) == {"op", "id", "type", "arg"}, f"{where}: quantity.attach fields invalid")
        _expect(_lookup(available, op["arg"], where) == "i64", f"{where}: quantity.attach source must be i64")
        _validate_type(op["type"], source_apl, f"{where}.type")
        _expect(is_quantity_type(op["type"]), f"{where}: quantity.attach result must be quantity")
        return _verify_result_id(op, where), op["type"]

    if name == "quantity.value":
        _expect(set(op) == {"op", "id", "type", "arg"}, f"{where}: quantity.value fields invalid")
        _expect(is_quantity_type(_lookup(available, op["arg"], where)), f"{where}: quantity.value source must be quantity")
        _expect(op["type"] == "i64", f"{where}: quantity.value result must be i64")
        return _verify_result_id(op, where), "i64"

    if name in {"quantity.add", "quantity.sub", "quantity.mul", "quantity.div"}:
        _expect(set(op) == {"op", "id", "type", "args", "where"}, f"{where}: {name} fields invalid")
        args = op["args"]
        _expect(isinstance(args, list) and len(args) == 2, f"{where}: {name} requires two args")
        left = _lookup(available, args[0], where)
        right = _lookup(available, args[1], where)
        _expect(is_quantity_type(left) and is_quantity_type(right), f"{where}: {name} requires quantities")
        inferred = left
        if name in {"quantity.add", "quantity.sub"}:
            _expect(left == right, f"{where}: {name} requires identical quantity types")
        else:
            try:
                inferred = combine_quantity_types(left, right, divide=name == "quantity.div")
            except ValueError as exc:
                _fail(f"{where}: {exc}")
        _expect(op["type"] == inferred, f"{where}: {name} result type mismatch")
        return _verify_result_id(op, where), inferred

    if name in {"host.fs.read_text", "host.net.get_text"}:
        _expect(set(op) == {"op", "id", "type", "arg", "where"}, f"{where}: {name} fields invalid")
        _expect(_lookup(available, op["arg"], where) == "string", f"{where}: {name} arg must be string")
        _expect(op["type"] == "string", f"{where}: {name} result must be string")
        return _verify_result_id(op, where), "string"

    _fail(f"{where}: unsupported LIR op '{name}'")


def _verify_edge(
    edge: Any,
    available: dict[str, Any],
    block_params: dict[str, list[tuple[str, Any]]],
    where: str,
) -> None:
    _expect(
        isinstance(edge, dict) and set(edge) == {"target", "args"},
        f"{where}: branch edge must contain target and args",
    )
    target = edge["target"]
    _expect(isinstance(target, str) and target in block_params, f"{where}: unknown branch target '{target}'")
    args = edge["args"]
    expected = block_params[target]
    _expect(isinstance(args, list) and len(args) == len(expected), f"{where}: branch arity mismatch for {target}")
    for index, (arg, (_, expected_type)) in enumerate(zip(args, expected)):
        actual = _lookup(available, arg, where)
        _expect(actual == expected_type, f"{where}: branch arg {index} type mismatch for {target}")


def _verify_lir_term(
    term: Any,
    available: dict[str, Any],
    block_params: dict[str, list[tuple[str, Any]]],
    target_map: dict[str, Any],
    return_type: Any,
    where: str,
) -> None:
    _expect(isinstance(term, dict), f"{where}: terminator must be an object")
    op = term.get("op")

    if op == "br":
        _expect(set(term) == {"op", "target", "args"}, f"{where}: br fields invalid")
        _verify_edge(
            {"target": term["target"], "args": term["args"]},
            available,
            block_params,
            where,
        )
        return

    if op == "cond_br":
        _expect(set(term) == {"op", "cond", "then", "else"}, f"{where}: cond_br fields invalid")
        _expect(_lookup(available, term["cond"], where) == "bool", f"{where}: cond_br condition must be bool")
        _verify_edge(term["then"], available, block_params, f"{where}.then")
        _verify_edge(term["else"], available, block_params, f"{where}.else")
        return

    if op == "return":
        if return_type == "unit":
            _expect(set(term) == {"op"}, f"{where}: unit return must have no value")
        else:
            _expect(set(term) == {"op", "value"}, f"{where}: value return must have value")
            _expect(_lookup(available, term["value"], where) == return_type, f"{where}: return type mismatch")
        return

    if op == "trap":
        _expect(
            set(term) == {"op", "code", "message", "where"}
            and all(isinstance(term[key], str) and bool(term[key]) for key in ("code", "message", "where")),
            f"{where}: trap fields invalid",
        )
        return

    _fail(f"{where}: unsupported LIR terminator '{op}'")
