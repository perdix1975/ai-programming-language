{
  "apl": "0.0.14",
  "module": "invariants",
  "capabilities": [],
  "limits": {
    "steps": 64,
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
      "name": "identity_positive",
      "params": [
        {"name": "x", "type": "i64"}
      ],
      "returns": "i64",
      "effects": [],
      "requires": [
        {
          "id": "positive_input",
          "message": "input must satisfy positive",
          "predicate": {
            "invariant": "positive",
            "args": [
              {"var": "x"}
            ]
          }
        }
      ],
      "ensures": [
        {
          "id": "positive_result",
          "message": "result must satisfy positive",
          "predicate": {
            "invariant": "positive",
            "args": [
              {"result": true}
            ]
          }
        }
      ],
      "body": [
        {"op": "invariant.check", "invariant": "positive", "args": ["x"]},
        {"op": "return", "value": "x"}
      ]
    },
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "effects": [],
      "requires": [],
      "ensures": [],
      "body": [
        {"op": "const", "id": "x", "type": "i64", "value": 5},
        {
          "op": "call",
          "id": "answer",
          "type": "i64",
          "function": "identity_positive",
          "args": ["x"]
        },
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
