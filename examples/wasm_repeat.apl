{
  "apl": "0.0.4",
  "module": "wasm_repeat",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "count", "type": "i64", "value": 5},
        {"op": "const", "id": "one", "type": "i64", "value": 1},
        {
          "op": "repeat",
          "id": "factorial",
          "type": "i64",
          "count": "count",
          "max": 5,
          "init": "one",
          "index": "i",
          "carry": "acc",
          "body": [
            {"op": "add", "id": "factor", "type": "i64", "args": ["i", "one"]},
            {"op": "mul", "id": "next", "type": "i64", "args": ["acc", "factor"]},
            {"op": "yield", "value": "next"}
          ]
        },
        {"op": "return", "value": "factorial"}
      ]
    }
  ]
}
