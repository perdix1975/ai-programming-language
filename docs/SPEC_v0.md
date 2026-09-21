# APL Specification v0

Status: **Draft 0.0.5**

This document defines the executable v0 subset of APL. The purpose of v0 is to establish stable semantic machinery before adding richer effects, contracts, capabilities, concurrency, or native compilation.

## 1. Versioning

The `apl` field is part of every program.

The current reference implementation supports:

- `0.0.1`: the original scalar/SSA semantic seed;
- `0.0.2`: a strict extension adding typed function calls and structured `if` regions;
- `0.0.3`: a strict extension adding defined integer division/remainder and ordered `i64` comparisons;
- `0.0.4`: a strict extension adding bounded structured `repeat` regions;
- `0.0.5`: a strict extension adding structured fixed-length array types and immutable array operations.

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
| `{"array": T, "len": N}` | immutable fixed-length array of `N` values of type `T` (0.0.5+) |

Integer constants are restricted to `[-2^63, 2^63-1]`.

Structured array types are represented directly as JSON objects, not encoded inside strings. Array lengths are integer literals in `[0, 65_536]`. Array element types may themselves be valid non-`unit` types, enabling nested fixed arrays.

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

## 10. Draft 0.0.5 instructions

### 10.1 structured fixed-array type

A fixed-array type is represented as:

```json
{"array":"i64","len":3}
```

The descriptor contains exactly two keys: `array` for the element type and `len` for the exact length. Length is part of the type, so arrays of lengths 3 and 4 are distinct types.

Array values are immutable. Mutation is not part of Draft 0.0.5.

### 10.2 `array`

Constructs an immutable fixed-length array from existing SSA values.

```json
{
  "op":"array",
  "id":"items",
  "type":{"array":"i64","len":3},
  "args":["a","b","c"]
}
```

Verification requires the number of arguments to exactly match the type length and every argument type to exactly match the element type.

### 10.3 `array.get`

Reads one element by runtime `i64` index.

```json
{"op":"array.get","id":"x","type":"i64","args":["items","index"]}
```

The index is zero-based. If the index is negative or greater than or equal to the fixed length, execution traps with an APL execution error. Negative indices never wrap from the end.

### 10.4 `array.len`

Returns the exact fixed length as an `i64`.

```json
{"op":"array.len","id":"n","type":"i64","args":["items"]}
```

### 10.5 equality

Two arrays may be compared with `eq` when their complete types are identical. Equality is structural and element-wise. Nested fixed arrays therefore compare recursively.

### 10.6 function and region typing

Structured array types may be used in function parameters, function return types, `if` results, and `repeat` carried values. Exact structural type equality is required; there are no implicit array conversions.

`print` remains scalar-only in Draft 0.0.5.

## 11. Verification

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

## 12. Canonical textual representation

The v0 canonical encoding is JSON with:

- object keys sorted lexicographically;
- no insignificant whitespace;
- UTF-8 output;
- non-ASCII characters retained;
- NaN and Infinity forbidden.

Canonical identity is SHA-256 over the UTF-8 bytes of that encoding.

This is an encoding identity, not yet a proof of semantic equivalence between differently structured programs.

## 13. Reference implementation

The Python implementation under `src/apl` is the executable reference for the current draft. Tests under `tests/` form a growing conformance suite.

## 14. Deliberately absent

Not yet defined:

- general recursion;
- unbounded/general loops;
- records and algebraic data types;
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
