# APL — AI Programming Language

APL is an experimental programming language and execution architecture designed **AI-first, semantics-first, and verification-first**.

The normative program is not optimized for human typing. It is an explicit typed semantic representation that AI systems can generate, verify, transform, optimize, explain, and compile.

> Status: **pre-alpha / Draft 0.0.12**

## What exists now

The executable reference core includes:

- versioned JSON semantic IR;
- SSA-style value identities;
- types: `i64`, `bool`, `string`, `unit`;
- defined `i64` arithmetic, including truncating `div`/`rem`, plus equality and ordered comparisons;
- explicit `print` effect;
- typed function calls with forward references;
- structured value-producing `if` regions using `yield`;
- bounded structured `repeat` regions with an explicit static maximum and one typed carried value;
- immutable fixed-length arrays with structured type descriptors, checked indexing, and length queries;
- immutable structural records with named fields and compile-time checked field access;
- deterministic execution traps with stable machine-readable codes, source locations, and an explicit `trap` terminator;
- exact per-function host-effect annotations and exact module capability declarations;
- explicit runtime capability grants, with `console.write` as the first protected host effect;
- deterministic fixture-backed `fs.read_text` and `net.get_text` host operations;
- deterministic `steps`, `output_lines`, and `host_reads` execution budgets with optional stricter host limits;
- typed declarative function `requires`/`ensures` contracts with deterministic pre/postcondition traps;\n- structural bounded `i64` range types with explicit `range.check` refinement and `range.value` widening;
- static rejection of direct and mutual recursion in Draft 0.0.2;
- strict verifier;
- deterministic canonical encoding and SHA-256 identity;
- reference interpreter;
- CLI;
- conformance tests and CI on Python 3.11 and 3.13.

APL 0.0.1–0.0.11 programs remain supported. Draft 0.0.12 adds structural bounded `i64` range types with explicit runtime refinement checks and no implicit conversions.

The Python implementation is a bootstrap reference implementation, not the planned high-performance runtime.

## Try it

Requires Python 3.11+.

```bash
python -m pip install -e .
apl verify examples/hello.apl
apl run examples/hello.apl

apl verify examples/functions_if.apl
apl run examples/functions_if.apl

apl verify examples/arithmetic.apl
apl run examples/arithmetic.apl

apl verify examples/repeat_factorial.apl
apl run examples/repeat_factorial.apl

apl verify examples/arrays.apl
apl run examples/arrays.apl

apl verify examples/records.apl
apl run examples/records.apl

apl verify examples/trap.apl
apl run examples/trap.apl

apl verify examples/effects.apl
apl run examples/effects.apl --allow console.write

apl verify examples/host_io.apl
apl run examples/host_io.apl \
  --allow console.write \
  --allow fs.read_text \
  --allow net.get_text \
  --host-fixture examples/host_fixture.json

apl verify examples/limits.apl
apl run examples/limits.apl
apl run examples/limits.apl --max-steps 1

apl verify examples/contracts.apl
apl run examples/contracts.apl
apl run examples/contracts_fail.apl

apl verify examples/ranges.apl
apl run examples/ranges.apl
apl run examples/ranges_fail.apl

apl canonicalize examples/ranges.apl
apl hash examples/ranges.apl
```

## Why the IR looks like this

APL starts from semantic structure rather than conventional source syntax. For example, a conditional is a typed region with explicit branch-local instructions and a `yield` value. That makes data dependencies and result types machine-verifiable before execution.

Human-friendly surface syntax can be added later, but it will lower into the same semantic IR rather than define a second meaning for the program.

## Design documents

- [Language principles](docs/LANGUAGE_PRINCIPLES.md)
- [Draft v0 specification](docs/SPEC_v0.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Conformance testing](docs/CONFORMANCE.md)

## Long-term direction

```text
Human intent
    |
    v
AI planner / programmer
    |
    v
APL semantic IR
    |
    +--> verifier
    +--> reference execution
    +--> human audit projection
    +--> optimizer --> WASM/native/accelerator backend
```

M2 is complete and M3 now includes contracts plus bounded `i64` range refinements. The next work explores units/dimensions and reusable machine-checkable invariants.

## License

MIT.
