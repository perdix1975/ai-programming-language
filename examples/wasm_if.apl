{
  "apl": "0.0.2",
  "module": "wasm_if",
  "entry": "main",
  "functions": [
    {
      "name": "choose",
      "params": [
        {"name": "flag", "type": "bool"},
        {"name": "a", "type": "i64"},
        {"name": "b", "type": "i64"}
      ],
      "returns": "i64",
      "body": [
        {
          "op": "if",
          "id": "selected",
          "type": "i64",
          "cond": "flag",
          "then": [{"op": "yield", "value": "a"}],
          "else": [{"op": "yield", "value": "b"}]
        },
        {"op": "return", "value": "selected"}
      ]
    },
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "flag", "type": "bool", "value": true},
        {"op": "const", "id": "x", "type": "i64", "value": 42},
        {"op": "const", "id": "y", "type": "i64", "value": 7},
        {
          "op": "call",
          "id": "answer",
          "type": "i64",
          "function": "choose",
          "args": ["flag", "x", "y"]
        },
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
