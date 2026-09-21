# APL — AI Programming Language

APL is an experimental programming language and execution architecture designed **AI-first, semantics-first, and verification-first**.

The normative program is not optimized for human typing. It is an explicit typed semantic representation that AI systems can generate, verify, transform, optimize, explain, and compile.

> Status: **pre-alpha / Draft 0.0.4**

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
- static rejection of direct and mutual recursion in Draft 0.0.2;
- strict verifier;
- deterministic canonical encoding and SHA-256 identity;
- reference interpreter;
- CLI;
- conformance tests and CI on Python 3.11 and 3.13.

APL 0.0.1–0.0.3 programs remain supported. `call` and `if` require 0.0.2+, `div`/`rem` and ordered comparisons require 0.0.3+, and `repeat` requires 0.0.4+.

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

apl canonicalize examples/repeat_factorial.apl
apl hash examples/repeat_factorial.apl
```

## Why the IR looks like this

APL starts from semantic structure rather than conventional source syntax. For example, a conditional is a typed region with explicit branch-local instructions and a `yield` value. That makes data dependencies and result types machine-verifiable before execution.

Human-friendly surface syntax can be added later, but it will lower into the same semantic IR rather than define a second meaning for the program.

## Design documents

- [Language principles](docs/LANGUAGE_PRINCIPLES.md)
- [Draft v0 specification](docs/SPEC_v0.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)

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

The next work expands the real programming core with arrays/records and a first-class trap/error model before moving into capabilities, contracts, compilation, and AI-native learned primitives.

## License

MIT.
