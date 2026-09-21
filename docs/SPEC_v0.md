# APL Specification v0

Status: **Draft 0.0.1**

This document defines the first executable subset of APL. It is deliberately small. The purpose of v0 is to establish stable semantic machinery before adding richer control flow, effects, contracts, capabilities, concurrency, or native compilation.

## 1. Program representation

The normative v0 interchange format is UTF-8 JSON.

A program is an object with:

- `apl`: language version; v0 requires `"0.0.1"`.
- `module`: non-empty module name.
- `entry`: name of the entry function.
- `functions`: non-empty list of function objects.

The v0 entry function must have no parameters.

## 2. Function representation

A function contains:

- `name`: unique non-empty function name.
- `params`: ordered list of parameters.
- `returns`: return type.
- `body`: ordered list of instructions.

Every v0 body terminates with `return`. Instructions after a terminator are invalid.

## 3. Types

v0 defines:

| Type | Meaning |
|---|---|
| `i64` | signed 64-bit integer |
| `bool` | Boolean |
| `string` | Unicode string |
| `unit` | no value |

Integer constants must be in the inclusive range `[-2^63, 2^63-1]`.

## 4. SSA identity

Value-producing instructions bind an `id`. Within a function:

- an id is defined at most once;
- an id must be defined before use;
- parameter names share the same namespace as instruction ids.

This v0 rule makes data dependencies explicit and removes mutable local variables from the trusted core.

## 5. Instructions

### 5.1 `const`

Creates an `i64`, `bool`, or `string` value.

```json
{"op":"const","id":"x","type":"i64","value":42}
```

### 5.2 `add`, `sub`, `mul`

Each requires exactly two `i64` operands and produces an `i64`.

```json
{"op":"add","id":"c","type":"i64","args":["a","b"]}
```

Signed overflow has defined behavior: execution traps with an APL execution error. Wraparound is not implicit.

### 5.3 `eq`

Requires two operands of identical, non-`unit` type and produces `bool`.

```json
{"op":"eq","id":"same","type":"bool","args":["a","b"]}
```

### 5.4 `print`

Print is the first explicit observable effect in v0. It accepts exactly one value id.

```json
{"op":"print","args":["x"]}
```

Reference textual rendering is:

- `bool`: `true` or `false`;
- `i64`: base-10 integer;
- `string`: string contents.

Each reference `print` call emits one output line.

### 5.5 `return`

A non-`unit` function returns exactly one previously defined value whose type exactly matches the function return type.

```json
{"op":"return","value":"answer"}
```

A `unit` function returns without a value.

## 6. Verification

A conforming v0 verifier must reject at least:

- unknown language versions;
- malformed program/function/instruction structures;
- duplicate functions;
- missing entry function;
- unsupported types or operations;
- duplicate SSA ids;
- use-before-definition;
- operand type mismatches;
- result type mismatches;
- missing or invalid terminators;
- return type mismatches.

Execution is defined only for verified programs.

## 7. Canonical textual representation

The v0 canonical encoding is JSON with:

- object keys sorted lexicographically;
- no insignificant whitespace;
- UTF-8 output;
- non-ASCII characters retained;
- NaN and Infinity forbidden.

Canonical identity is SHA-256 over the UTF-8 bytes of that encoding.

This is an **encoding identity**, not yet a proof of semantic equivalence between differently structured programs.

## 8. Reference implementation

The Python interpreter in `src/apl` is the executable reference for Draft 0.0.1. Tests in `tests/` are conformance examples, but the specification remains the intended normative definition.

## 9. Deliberately absent from v0

The following are planned but not defined yet:

- calls and multi-function execution;
- branches and loops;
- collections and structured types;
- arithmetic beyond add/sub/mul;
- contracts and refinement types;
- explicit capability/effect system;
- file/network/database access;
- concurrency;
- resource bounds;
- modules/imports;
- binary canonical IR;
- optimizer and compiler backends;
- AI-generated primitives.

They must not be inferred from conventional language behavior until formally specified.
