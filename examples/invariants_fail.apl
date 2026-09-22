{
  "apl": "0.0.14",
  "module": "invariants_fail",
  "capabilities": [],
  "limits": {
    "steps": 32,
    "output_lines": 0,
    "host_reads": 0
  },
  "invariants": [
    {
      "name": "positive",
      "params": [
        {"name": "x", "type": "i64"}
      ],
      "message": "x must be positive",
      "predicate": {
        "op": "gt",
        "args": [
          {"var": "x"},
          {"const": {"type": "i64", "value": 0}}
        ]
      }
    }
  ],
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "effects": [],
      "requires": [],
      "ensures": [],
      "body": [
        {"op": "const", "id": "x", "type": "i64", "value": 0},
        {"op": "invariant.check", "invariant": "positive", "args": ["x"]},
        {"op": "return", "value": "x"}
      ]
    }
  ]
}
