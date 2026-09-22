# APL Specification v0

Status: **Draft 0.0.12**

This document defines the executable v0 subset of APL. The purpose of v0 is to establish stable semantic machinery before adding richer type invariants, concurrency, or native compilation.

## 1. Versioning

The `apl` field is part of every program.

The current reference implementation supports:

- `0.0.1`: the original scalar/SSA semantic seed;
- `0.0.2`: a strict extension adding typed function calls and structured `if` regions;
- `0.0.3`: a strict extension adding defined integer division/remainder and ordered `i64` comparisons;
- `0.0.4`: a strict extension adding bounded structured `repeat` regions;
- `0.0.5`: a strict extension adding structured fixed-length array types and immutable array operations;
- `0.0.6`: a strict extension adding immutable structural record types and named-field access;
- `0.0.7`: a strict extension adding deterministic machine-readable traps and an explicit `trap` terminator;
- `0.0.8`: a strict extension adding exact function effects, exact module capability declarations, and explicit host grants;
- `0.0.9`: a strict extension adding deterministic fixture-backed filesystem and network read operations;
- `0.0.10`: a strict extension adding deterministic execution resource budgets and host-side tightening;
- `0.0.11`: a strict extension adding typed declarative function preconditions and postconditions;
- `0.0.12`: a strict extension adding structural bounded `i64` range types and explicit refinement/widening.

Older programs retain their declared-version meaning. An operation is valid only when introduced by that program's declared version or an earlier one.

## 2. Program representation

The normative v0 interchange format is UTF-8 JSON.

A program object contains:

- `apl`: supported language version;
- `module`: non-empty module name;
- `entry`: entry function name;
- `functions`: non-empty list of function objects;
- `capabilities`: in Draft 0.0.8+, the exact sorted list of host capabilities required by the module;
- `limits`: in Draft 0.0.10+, the exact deterministic execution-budget object.

The entry function must exist and require zero parameters.

## 3. Function representation

A function contains:

- `name`: unique non-empty name;
- `params`: ordered typed parameters;
- `returns`: return type;
- `effects`: in Draft 0.0.8+, the exact sorted list of host effects the function may perform directly or through calls;
- `requires`: in Draft 0.0.11+, the ordered precondition clause list;
- `ensures`: in Draft 0.0.11+, the ordered postcondition clause list;
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
| `{"record": {"field": T, ...}}` | immutable structural record with named fields (0.0.6+) |
| `{"range":{"min":A,"max":B}}` | structural bounded `i64` refinement type (0.0.12+) |

Integer constants are restricted to `[-2^63, 2^63-1]`.

Structured types are represented directly as JSON objects, not encoded inside strings. Array lengths are integer literals in `[0, 65_536]`. Array element types may themselves be valid non-`unit` types. Record field names are non-empty strings, each record may contain at most 256 fields, and field types may be any valid non-`unit` type. Arrays and records may therefore nest recursively.

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

In Draft 0.0.8+, `print` contributes the `console.write` effect and requires the corresponding module capability plus a host runtime grant.

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

`print` remains scalar-only through Draft 0.0.11.

## 11. Draft 0.0.6 instructions

### 11.1 structural record type

A record type is represented as:

```json
{
  "record": {
    "name": "string",
    "age": "i64"
  }
}
```

Record types are structural. Field order is not part of the type: two record descriptors with the same field names and exactly equal field types denote the same type regardless of JSON member order.

Record field names must be non-empty strings. A record may contain at most 256 fields. Empty records are valid. Record fields may not have type `unit`.

### 11.2 `record`

Constructs an immutable record from existing SSA values.

```json
{
  "op":"record",
  "id":"person",
  "type":{"record":{"name":"string","age":"i64"}},
  "fields":{"name":"name_value","age":"age_value"}
}
```

Verification requires the supplied field-name set to exactly equal the type's field-name set. Each field source must be an SSA id whose type exactly matches the declared field type. There are no optional, implicit, or extra fields in Draft 0.0.6.

### 11.3 `record.get`

Reads one field named by a compile-time string literal.

```json
{
  "op":"record.get",
  "id":"age",
  "type":"i64",
  "record":"person",
  "field":"age"
}
```

The source must be a record and the requested field must exist in its type. The result type is exactly the declared field type. Because field membership is checked by the verifier, a verified `record.get` does not perform a missing-field runtime trap.

### 11.4 equality and canonical field order

Records of exactly equal structural type may be compared with `eq`. Equality is recursive and field-wise. Runtime field storage order is not observable and does not affect equality.

The reference interpreter stores record fields in deterministic lexicographic field-name order. This is an implementation strategy consistent with the semantics, not a user-visible ordering guarantee.

### 11.5 nesting and function/region typing

Records may contain arrays or other records, and arrays may contain records. Record types may be used in function parameters/returns, `if` results, and `repeat` carried values. Exact structural type equality is required throughout.

Records are immutable values. Draft 0.0.6 defines no field mutation operation.

## 12. Draft 0.0.7 trap model

### 12.1 deterministic trap

A **trap** is abrupt program termination with three observable diagnostic components:

- `code`: a stable machine-readable identifier;
- `message`: human-readable diagnostic text;
- `where`: the logical IR execution location reported by the runtime.

A trap produces no normal value. Draft 0.0.7 defines no catch, recovery, resume, or handler mechanism: a trap propagates through structured regions and function calls until execution of the whole program terminates.

The stable semantic interface is the trap `code`. Diagnostic wording may be improved in future compatible implementations without changing the meaning of the code.

### 12.2 explicit `trap`

User programs may terminate deliberately:

```json
{
  "op":"trap",
  "code":"app.invalid_state",
  "message":"invalid state"
}
```

`trap` is a block terminator. It may terminate a function body, an `if` branch, or a `repeat` body in place of that block's ordinary `return` or `yield`. Instructions after it in the same block are invalid.

User-defined trap codes:

- must match `[a-z][a-z0-9_.-]{0,63}`;
- must not equal `apl` or begin with the reserved `apl.` namespace.

The explicit message must contain from 1 through 512 Unicode code points.

### 12.3 reserved runtime trap codes

The `apl.*` namespace is reserved by the language/runtime. Draft 0.0.7 standardizes these runtime trap codes:

| Code | Condition |
|---|---|
| `apl.i64_overflow` | a trapping signed `i64` operation overflows |
| `apl.division_by_zero` | `div` or `rem` uses divisor zero |
| `apl.array_index_oob` | `array.get` index is negative or at least the array length |
| `apl.repeat_negative_count` | `repeat` runtime count is negative |
| `apl.repeat_count_exceeds_max` | `repeat` runtime count exceeds its declared static `max` |

These codes replace no prior semantics: they assign stable identities to execution failures whose conditions were already defined in earlier drafts.

The reference implementation also uses `apl.internal_invalid_execution` as a defensive implementation guard. A verified conforming program must not reach that condition; it is not an ordinary language-level trap that programs should depend on.

### 12.4 logical location

The reference location format identifies the dynamic structured IR position using function and instruction-region paths, for example:

```text
main[2]
main[1].then[0]
main[3].body[2]
```

The location is diagnostic metadata. It is not part of type identity, canonical program identity, or the stable trap-code namespace.

### 12.5 side effects and propagation

Effects completed before a trap remain completed. Instructions and effects after the trapping instruction do not execute. An unselected `if` branch still does not execute, so a `trap` in an unselected branch has no effect.

For runtime precondition traps that are specified to occur before entering a region, such as invalid `repeat` count, no body effect occurs before the trap.

## 13. Draft 0.0.8 effects and capabilities

### 13.1 purpose

Draft 0.0.8 separates three concepts that must not be conflated:

1. **inferred effects**: host-visible effects reachable from a function body;
2. **declared effects**: the function's exact static effect contract;
3. **runtime grants**: capabilities the host actually authorizes for this execution.

A declaration never grants authority by itself.

### 13.2 function `effects`

Every 0.0.8+ function contains an `effects` list.

```json
{
  "name":"emit",
  "params":[{"name":"message","type":"string"}],
  "returns":"unit",
  "effects":["console.write"],
  "body":[
    {"op":"print","args":["message"]},
    {"op":"return"}
  ]
}
```

The list must:

- contain only effects defined by the declared language version;
- be lexicographically sorted;
- contain no duplicates;
- exactly equal the verifier-inferred effect set of the function.

A pure function therefore declares `"effects":[]`.

Effects propagate transitively through function calls. Structured regions contribute the union of effects in all statically possible branches/bodies, regardless of which branch is selected at runtime. This makes the effect contract conservative and execution-independent.

Draft 0.0.8 defines one host effect:

| Effect | Introduced by |
|---|---|
| `console.write` | `print` |

### 13.3 module `capabilities`

Every 0.0.8+ program contains a module-level `capabilities` list.

```json
"capabilities":["console.write"]
```

It must be the exact lexicographically sorted, duplicate-free union of every function's declared effects. Extra capabilities are rejected as over-declaration; missing capabilities are rejected as under-declaration.

Thus a module's static authority footprint is explicit in canonical IR and participates in canonical identity/hash.

### 13.4 runtime host grants

Verification proves what authority a program declares it needs. Execution separately receives a set of capabilities granted by the host.

Before executing the entry function of a 0.0.8+ program, the runtime verifies that every declared module capability is present in the host grant set. If any required capability is absent, execution traps before program effects begin with the Draft 0.0.8 runtime trap code:

```text
apl.capability_denied
```

This code is introduced by Draft 0.0.8; it is not part of the earlier Draft 0.0.7 runtime-trap set.

Hosts may grant a superset, but the program may use only effects present in its verified module declaration.

The reference CLI grants capabilities explicitly with repeatable `--allow` arguments, for example:

```text
apl run examples/effects.apl --allow console.write
```

### 13.5 compatibility

Programs declaring APL 0.0.1 through 0.0.7 retain their earlier semantics. They are not retroactively required to contain `effects` or `capabilities`, and their legacy `print` behavior is unchanged.

### 13.6 security boundary

Effect annotations are a static audit contract. Capability declarations are the module's requested authority. Host grants are the enforcement boundary.

A conforming 0.0.8 runtime must not perform a protected host effect without the corresponding grant, even if the program has a syntactically valid capability declaration.

## 14. Draft 0.0.9 deterministic host interface

### 14.1 host model

Draft 0.0.9 introduces the first filesystem/network capability prototypes through a deterministic host interface.

The reference semantic model exposes two immutable string-to-string resource maps:

- `files`: exact path key -> UTF-8 text value;
- `network`: exact URL key -> text response value.

APL 0.0.9 does **not** define direct operating-system filesystem access, sockets, DNS, HTTP redirects, headers, status codes, clocks, retries, or ambient environment access. A host may obtain resource values however it chooses before execution, but the APL program observes only the deterministic mapping supplied for that run.

Lookup keys are exact Unicode strings. No path normalization, URL canonicalization, case folding, or implicit encoding conversion occurs.

### 14.2 `fs.read_text`

```json
{
  "op":"fs.read_text",
  "id":"content",
  "type":"string",
  "args":["path"]
}
```

Verification requires exactly one `string` SSA argument and a `string` result. The operation contributes the `fs.read_text` effect.

Execution requires:

- the module to declare `fs.read_text`;
- the host to grant `fs.read_text`;
- a deterministic host interface to be present;
- the exact path key to exist in the host's `files` map.

The returned value is the exact mapped string.

### 14.3 `net.get_text`

```json
{
  "op":"net.get_text",
  "id":"content",
  "type":"string",
  "args":["url"]
}
```

Verification requires exactly one `string` SSA argument and a `string` result. The operation contributes the `net.get_text` effect.

Execution uses an exact key lookup in the host's `network` map. The operation name anticipates a future network adapter, but Draft 0.0.9 itself defines no live HTTP semantics.

### 14.4 new effects

Draft 0.0.9 adds:

| Effect / capability | Operation |
|---|---|
| `fs.read_text` | deterministic file-text lookup |
| `net.get_text` | deterministic network-text lookup |

These effects follow all Draft 0.0.8 exact-declaration and runtime-grant rules. A 0.0.8 program cannot name them.

### 14.5 host traps

Draft 0.0.9 adds two runtime trap codes:

| Code | Condition |
|---|---|
| `apl.host_unavailable` | a host-backed operation executes without a host interface |
| `apl.host_resource_missing` | the requested exact path/URL key is absent from the deterministic host resources |

Capability preflight happens first. If a required capability grant is missing, `apl.capability_denied` occurs before host lookup.

### 14.6 reference fixture format

The reference CLI accepts a deterministic JSON fixture using `--host-fixture`:

```json
{
  "files": {
    "/message.txt": "local fixture"
  },
  "network": {
    "https://example.test/message": "network fixture"
  }
}
```

Both maps are optional and default to empty. Keys and values must be strings. Unknown top-level fixture keys are rejected.

The fixture is host configuration, not part of the APL program and therefore not part of the program's canonical hash. Reproducible execution requires preserving both the canonical APL program and the host fixture supplied to it.

## 15. Draft 0.0.10 deterministic resource limits

### 15.1 program-declared budgets

Every Draft 0.0.10+ program contains an exact `limits` object:

```json
{
  "limits": {
    "steps": 1000,
    "output_lines": 10,
    "host_reads": 5
  }
}
```

The object contains exactly these three integer fields:

| Field | Meaning | Valid range |
|---|---|---:|
| `steps` | dynamically executed IR instructions | 0..10,000,000 |
| `output_lines` | successful `print` output lines | 0..1,000,000 |
| `host_reads` | `fs.read_text` + `net.get_text` lookups | 0..1,000,000 |

Boolean values are not integers for this purpose. Negative values, values above the stated maxima, missing fields, or extra fields are verification errors.

The `limits` object is part of the APL program. It therefore participates in canonical encoding and canonical program identity/hash.

### 15.2 deterministic step accounting

One `steps` unit is consumed for every dynamically executed IR instruction immediately before that instruction's semantics begin.

This includes:

- scalar/data instructions;
- `call`, `if`, and `repeat` outer instructions;
- instructions in the selected `if` branch;
- instructions in every actually executed `repeat` iteration;
- `print`, host-read operations, `return`, `yield`, and explicit `trap`.

An unselected `if` branch consumes no runtime steps. A `repeat` consumes one step for the outer `repeat` instruction plus the dynamic instructions in each executed body iteration.

When no step remains, execution traps **before** the next instruction performs its behavior. Thus resource exhaustion can prevent a `print`, host read, return, yield, or explicit trap from taking effect.

This is a semantic instruction budget, not a wall-clock, CPU-time, or scheduler-time limit. Its result is independent of host machine speed.

### 15.3 output-line accounting

Each executed `print` must consume one `output_lines` unit after capability authorization and before the output callback is invoked.

If the output-line budget is exhausted, execution traps before that line is emitted. Previously emitted lines remain emitted.

### 15.4 host-read accounting

Each executed `fs.read_text` or `net.get_text` must consume one `host_reads` unit after capability authorization and after confirming that a host interface exists, but before resource lookup.

Therefore:

- a missing capability produces `apl.capability_denied` before host-read budget use;
- a missing host produces `apl.host_unavailable` before host-read budget use;
- once a read attempt reaches deterministic lookup, it consumes one host-read unit even if the exact resource key is absent.

### 15.5 resource-limit trap

Draft 0.0.10 introduces:

```text
apl.resource_limit
```

The trap location is the instruction that attempted to consume an exhausted resource. The diagnostic message identifies `steps`, `output_lines`, or `host_reads`.

### 15.6 host-side tightening

The execution host may independently provide optional limits for the same three resource dimensions.

For each dimension, the effective limit is:

- the program-declared value when the host provides no override;
- the host value for pre-0.0.10 programs that have no language-level declaration;
- the minimum of program and host values when both exist.

The host therefore may tighten a program's budget but may never enlarge it.

The reference CLI exposes host policy through:

```text
--max-steps N
--max-output-lines N
--max-host-reads N
```

Host-side overrides are execution configuration. They are not part of the APL program and do not alter its canonical hash.

### 15.7 compatibility and remaining resource dimensions

APL 0.0.1 through 0.0.9 programs are not retroactively required to contain a `limits` object. Their language-defined resource budgets are unlimited, although a host may impose explicit runtime limits.

Draft 0.0.10 does not define memory-size, wall-clock, CPU-time, stack-size, host-response-size, or output-byte limits. Such dimensions must not be inferred from the three budgets defined here.

## 16. Draft 0.0.11 typed function contracts

### 16.1 explicit contract lists

Every Draft 0.0.11+ function contains both `requires` and `ensures` lists, even when either list is empty.

A contract clause has exactly:

```json
{
  "id": "positive_input",
  "message": "x must be positive",
  "predicate": {
    "op": "gt",
    "args": [
      {"var": "x"},
      {"const": {"type": "i64", "value": 0}}
    ]
  }
}
```

Each list may contain at most 64 clauses. Clause identifiers:

- match `[a-z][a-z0-9_.-]{0,63}`;
- are unique within the function across both `requires` and `ensures`.

A clause message contains 1 through 512 Unicode code points.

Contract clauses are part of canonical APL IR and therefore participate in canonical program identity/hash.

### 16.2 predicate value nodes

A predicate is a typed expression tree. Draft 0.0.11 defines these leaf forms.

Parameter reference:

```json
{"var":"x"}
```

The name must identify a function parameter. Contract predicates cannot reference SSA values created by the function body.

Postcondition result reference:

```json
{"result":true}
```

The result reference is valid only inside `ensures` of a non-`unit` function. It has exactly the declared function return type. Preconditions execute before a result exists, and `unit` functions have no result value.

Primitive literal:

```json
{"const":{"type":"i64","value":0}}
```

Contract literals are limited to the same primitive `i64`, `bool`, and `string` values accepted by ordinary `const`. Structured values can still participate through parameter/result references.

### 16.3 predicate operators

Operator nodes contain exactly `op` and `args`.

Draft 0.0.11 defines:

| Operator | Arity | Operand rule | Result |
|---|---:|---|---|
| `eq` | 2 | identical non-`unit` types | `bool` |
| `lt`, `le`, `gt`, `ge` | 2 | both `i64`; from 0.0.12, also identical range types | `bool` |
| `not` | 1 | `bool` | `bool` |
| `and`, `or` | 2 | both `bool` | `bool` |

The root of every contract predicate must have type `bool`.

`and` and `or` are deliberately **eager** in Draft 0.0.11: operands are evaluated left-to-right and both operands are evaluated. Contracts have no effectful predicate operations, so this avoids value-dependent resource accounting and gives a fixed evaluation shape.

A single predicate is limited to 1,024 nodes and depth 64.

### 16.4 precondition execution

For every function invocation, including the entry function:

1. parameters are bound;
2. `requires` clauses are evaluated in declaration order;
3. only if all preconditions pass does the function body begin.

The first false precondition traps with:

```text
apl.precondition_failed
```

The trap location is `<function>.requires[<index>]`. The diagnostic message contains the clause identifier and human message.

A failed precondition occurs before any effect in that function body. Effects performed by the caller before making the call remain completed.

### 16.5 postcondition execution

After a function body completes with a normal `return`, `ensures` clauses are evaluated in declaration order with access to:

- the original parameter values;
- the normal return value through `{"result":true}` for non-`unit` functions.

The first false postcondition traps with:

```text
apl.postcondition_failed
```

The trap location is `<function>.ensures[<index>]`.

Postconditions run **after** body effects have occurred. If the function body traps instead of returning normally, postconditions do not run.

### 16.6 purity and static checking

Contract predicates are declarative expressions, not general instruction regions. They cannot call functions, print, access host capabilities, mutate values, loop, or explicitly trap.

The verifier fully type-checks every predicate before execution. A verified predicate therefore has no dynamic name lookup or type ambiguity.

Contract checking does not add to a function's effect set or module capability requirements.

### 16.7 resource accounting

Draft 0.0.11 extends the Draft 0.0.10 `steps` budget: each dynamically evaluated contract predicate node consumes one step immediately before that node is evaluated.

Contract-clause metadata itself consumes no additional step. Eager boolean operators therefore consume steps for both operands.

If the step budget is exhausted during contract evaluation, `apl.resource_limit` occurs at the predicate-node location before a precondition/postcondition result is produced. Resource exhaustion therefore takes precedence over a contract-failure trap when the predicate cannot finish evaluating.

### 16.8 compatibility

APL 0.0.1 through 0.0.10 functions are not retroactively required to contain `requires` or `ensures`. The contract fields themselves are version-gated and are rejected when declared before 0.0.11, preventing legacy programs from silently acquiring newer semantics.

## 17. Draft 0.0.12 structural range types

### 17.1 type descriptor

Draft 0.0.12 introduces a bounded structural refinement of `i64`:

```json
{"range":{"min":0,"max":100}}
```

A range descriptor contains exactly `min` and `max`. Both are non-Boolean integer literals inside the full signed `i64` domain and `min <= max`.

The bounds are part of type identity. Therefore:

```json
{"range":{"min":0,"max":10}}
```

and

```json
{"range":{"min":0,"max":100}}
```

are distinct types even though one mathematical interval is contained in the other.

Range types are structural and may appear anywhere another non-`unit` value type may appear, including:

- function parameters and return types;
- arrays and record fields;
- `if` result types;
- `repeat` carried values.

The runtime representation of a range value is the same mathematical integer value as its underlying `i64`, but the static APL type remains the exact range descriptor.

### 17.2 explicit refinement with `range.check`

```json
{
  "op":"range.check",
  "id":"percent",
  "type":{"range":{"min":0,"max":100}},
  "args":["raw"]
}
```

Verification requires:

- Draft 0.0.12+;
- exactly one source SSA id;
- source type exactly `i64`;
- result type a valid range descriptor.

Execution checks the source value against the inclusive range bounds.

If the value is inside the range, the operation produces the same integer value with the declared range type.

If the value is outside the range, execution traps with:

```text
apl.range_violation
```

The trap occurs at the `range.check` instruction before a refined SSA value is bound.

### 17.3 explicit widening with `range.value`

```json
{
  "op":"range.value",
  "id":"raw",
  "type":"i64",
  "args":["percent"]
}
```

Verification requires exactly one source SSA id whose type is a range descriptor. The result type is exactly `i64`.

Execution preserves the mathematical integer value and removes the static refinement type.

### 17.4 no implicit conversions

Draft 0.0.12 deliberately defines no implicit subtype coercion.

Consequences include:

- a range value is not accepted where plain `i64` is required;
- plain `i64` is not accepted where a range type is required;
- two different range descriptors are not interchangeable;
- arithmetic instructions continue to require plain `i64` operands;
- changing from one range type to another requires `range.value` followed by a new `range.check`.

This explicit conversion discipline keeps verification local and makes every dynamic refinement check visible in IR.

### 17.5 equality and contracts

Two values of the exact same range type may be compared with ordinary `eq`.

Draft 0.0.11 contract predicates are extended so `lt`, `le`, `gt`, and `ge` may compare two values of the exact same range type. A range value and plain `i64`, or two different range types, are not implicitly comparable through those ordered contract operators.

Range refinement itself adds no host effect and requires no capability.

### 17.6 resource accounting

`range.check` and `range.value` are ordinary IR instructions and therefore each consume one Draft 0.0.10 `steps` unit before their semantics begin.

No additional hidden step is charged for the bounds comparison inside `range.check`.

If the step budget is exhausted at `range.check`, `apl.resource_limit` occurs before range validation. Otherwise an out-of-range value produces `apl.range_violation`.

### 17.7 compatibility

APL 0.0.1 through 0.0.11 do not recognize range type descriptors or the two range operations. Use before 0.0.12 is rejected by verification.

## 18. Verification

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
- malformed, ill-typed, or out-of-scope function contract predicates;
- duplicate function-local contract identifiers;
- malformed or out-of-bounds range descriptors and invalid explicit range conversions;
- use of an operation before the language version that introduced it.

Execution is defined only for verified programs.

## 19. Canonical textual representation

The v0 canonical encoding is JSON with:

- object keys sorted lexicographically;
- no insignificant whitespace;
- UTF-8 output;
- non-ASCII characters retained;
- NaN and Infinity forbidden.

Canonical identity is SHA-256 over the UTF-8 bytes of that encoding.

This is an encoding identity, not yet a proof of semantic equivalence between differently structured programs.

## 20. Reference implementation

The Python implementation under `src/apl` is the executable reference for the current draft. Tests under `tests/` form a growing conformance suite.

## 21. Deliberately absent

Not yet defined:

- general recursion;
- unbounded/general loops;
- algebraic data types;
- trap recovery, handlers, and resumable exceptions;
- general predicate-backed refinement types and reusable type invariants;
- live filesystem/network adapters and database capability semantics;
- file/network/database access;
- concurrency;
- memory, wall-clock, CPU-time, and byte-size resource bounds;
- module imports;
- binary canonical IR;
- optimizer/compiler backends;
- AI-generated primitives.

Conventional-language behavior for these features must not be assumed until formally specified.
