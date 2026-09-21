# APL Specification v0

Status: **Draft 0.0.4**

This document defines the executable v0 subset of APL. The purpose of v0 is to establish stable semantic machinery before adding richer effects, contracts, capabilities, concurrency, or native compilation.

## 1. Versioning

The `apl` field is part of every program.

The current reference implementation supports:

- `0.0.1`: the original scalar/SSA semantic seed;
- `0.0.2`: a strict extension adding typed function calls and structured `if` regions;
- `0.0.3`: a strict extension adding defined integer division/remainder and ordered `i64` comparisons;\n- `0.0.4`: a strict extension adding bounded structured `repeat` regions.

Older programs retain their declared-version meaning. An operation is valid only when introduced by that program's declared version or an earlier one.

## 2. Program representation

The normative v0 interchange format is UTF-8 JSON.

A program object contains:

- `apl`: supported language version;
- `module`: non-empty module name;
- `entry`: entry function name;
- `functions`: non-empty list of function objects.

The entry function must exist and require zero parameters.

## 3. Function representation

A function contains:

- `name`: unique non-empty name;
- `params`: ordered typed parameters;
- `returns`: return type;
- `body`: ordered instruction list.

Function declarations are visible module-wide, so a call may target a function appearing later in the file.

Draft 0.0.2 and later reject direct and mutual recursion. The module call graph must be acyclic.

## 4. Types

v0 defines:

| Type | Meaning |
|---|---|
| `i64` | signed 64-bit integer |
| `bool` | Boolean |
| `string` | Unicode string |
| `unit` | no value |

Integer constants are restricted to `[-2^63, 2^63-1]`.

## 5. SSA identity and regions

Value-producing instructions bind an `id`.

Within a function or structured region:

- an id is defined at most once in that environment;
- an id must be defined before use;
- parameter names share the function SSA namespace;
- branch-local bindings do not leak out of the branch;
- an `if` or `repeat` exposes only its own result id to the enclosing environment.

## 6. Core instructions

### 6.1 `const`

Creates an `i64`, `bool`, or `string`.

```json
{"op":"const","id":"x","type":"i64","value":42}
```

### 6.2 `add`, `sub`, `mul`

Require two `i64` operands and produce `i64`.

Signed overflow has defined behavior: execution traps with an APL execution error. Wraparound is not implicit.

### 6.3 `eq`

Requires two operands of identical, non-`unit` type and produces `bool`.

### 6.4 `print`

An explicit observable effect accepting one value id.

Reference rendering is:

- `bool`: `true` or `false`;
- `i64`: base-10 integer;
- `string`: string contents.

Each call emits one output line.

### 6.5 `return`

Terminates a function. A non-`unit` function returns one previously defined value of exactly the declared function return type. A `unit` function returns no value.

## 7. Draft 0.0.2 instructions

### 7.1 `call`

A call names a module function and supplies SSA ids as arguments.

```json
{
  "op":"call",
  "id":"answer",
  "type":"i64",
  "function":"choose",
  "args":["flag","x","y"]
}
```

Verification requires:

- target function exists;
- argument count matches exactly;
- each argument type matches its parameter type exactly;
- a non-`unit` result binds an id with the exact declared return type;
- a `unit` result binds no id;
- the complete module call graph remains acyclic.

### 7.2 structured `if`

Draft 0.0.2 `if` is a value-producing structured region.

```json
{
  "op":"if",
  "id":"selected",
  "type":"i64",
  "cond":"flag",
  "then":[{"op":"yield","value":"a"}],
  "else":[{"op":"yield","value":"b"}]
}
```

Rules:

- `cond` must reference `bool`;
- `type` must currently be non-`unit`;
- both branches are non-empty instruction lists;
- each branch terminates with `yield`;
- both yielded values must exactly match the `if` result type;
- only the selected branch executes;
- branch-local SSA bindings do not escape;
- effects in the unselected branch do not occur.

### 7.3 `yield`

`yield` is a structured-region terminator. In 0.0.2 it terminates an `if` branch; in 0.0.4 it also terminates a `repeat` body iteration. It yields one SSA value to the enclosing structured operation.

It is not a function return.

## 8. Draft 0.0.3 instructions

### 8.1 `div`

`div` requires two `i64` operands and produces `i64`. Division truncates toward zero.

Defined traps:

- divisor equal to zero -> execution error;
- `INT64_MIN / -1` -> signed `i64` overflow execution error.

No host-language or target-CPU division semantics may override these rules.

### 8.2 `rem`

`rem` requires two `i64` operands and produces `i64`. For nonzero divisor it is defined by the truncating quotient:

`r = a - trunc(a / b) * b`

The sign of a nonzero remainder therefore follows the dividend. Division by zero traps. The edge case `INT64_MIN rem -1` is explicitly defined as `0` and does not overflow.

### 8.3 ordered comparisons

`lt`, `le`, `gt`, and `ge` each require two `i64` operands and produce `bool`. They use ordinary signed mathematical integer ordering.

## 9. Draft 0.0.4 instructions

### 9.1 bounded `repeat`

`repeat` is a value-producing structured iteration region with an explicit static execution bound.

```json
{
  "op":"repeat",
  "id":"factorial",
  "type":"i64",
  "count":"n",
  "max":10,
  "init":"one",
  "index":"i",
  "carry":"acc",
  "body":[
    {"op":"add","id":"factor","type":"i64","args":["i","one"]},
    {"op":"mul","id":"next","type":"i64","args":["acc","factor"]},
    {"op":"yield","value":"next"}
  ]
}
```

Verification requires that `count` is `i64`; `max` is an integer literal in `[0, 1_000_000]`; `init` is non-`unit`; the result type equals the `init` type; `index` and `carry` are distinct region-local names that do not collide with outer SSA ids; and the body ends in a `yield` of the carried type.

Execution first validates the runtime count. A negative count, or a count greater than `max`, traps before any body effect. Otherwise the body executes exactly `count` times. The iteration index is zero-based. The first `carry` is `init`; each body `yield` becomes the next carry. Each iteration receives a fresh region-local SSA environment. The final carry is the operation result. For `count = 0`, the body does not execute and the result is exactly `init`.

Because every verified `repeat` contains a statically capped `max`, it cannot execute an unbounded number of iterations.

## 10. Verification

A conforming verifier rejects at least:

- unsupported versions;
- malformed program/function/instruction structures;
- duplicate functions;
- missing or parameterized entry functions;
- unsupported types or operations;
- duplicate SSA ids;
- use-before-definition;
- operand/result type mismatches;
- invalid block terminators;
- return/yield type mismatches;
- unknown function targets;
- call arity/type mismatches;
- recursive call cycles;
- use of an operation before the language version that introduced it.

Execution is defined only for verified programs.

## 11. Canonical textual representation

The v0 canonical encoding is JSON with:

- object keys sorted lexicographically;
- no insignificant whitespace;
- UTF-8 output;
- non-ASCII characters retained;
- NaN and Infinity forbidden.

Canonical identity is SHA-256 over the UTF-8 bytes of that encoding.

This is an encoding identity, not yet a proof of semantic equivalence between differently structured programs.

## 12. Reference implementation

The Python implementation under `src/apl` is the executable reference for the current draft. Tests under `tests/` form a growing conformance suite.

## 13. Deliberately absent

Not yet defined:

- general recursion;
- loops/iteration;
- arrays, records, algebraic data types;
- explicit trap values/handlers;
- contracts and refinement types;
- formal effect/capability declarations;
- file/network/database access;
- concurrency;
- resource bounds;
- module imports;
- binary canonical IR;
- optimizer/compiler backends;
- AI-generated primitives.

Conventional-language behavior for these features must not be assumed until formally specified.
