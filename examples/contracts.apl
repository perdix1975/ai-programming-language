{
  "apl": "0.0.11",
  "module": "contracts",
  "capabilities": [],
  "limits": {
    "steps": 64,
    "output_lines": 0,
    "host_reads": 0
  },
  "entry": "main",
  "functions": [
    {
      "name": "double_positive",
      "params": [
        {"name": "x", "type": "i64"}
      ],
      "returns": "i64",
      "effects": [],
      "requires": [
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
      ],
      "ensures": [
        {
          "id": "larger_result",
          "message": "result must be larger than x",
          "predicate": {
            "op": "gt",
            "args": [
              {"result": true},
              {"var": "x"}
            ]
          }
        }
      ],
      "body": [
        {"op": "add", "id": "answer", "type": "i64", "args": ["x", "x"]},
        {"op": "return", "value": "answer"}
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
        {"op": "const", "id": "x", "type": "i64", "value": 3},
        {
          "op": "call",
          "id": "answer",
          "type": "i64",
          "function": "double_positive",
          "args": ["x"]
        },
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
