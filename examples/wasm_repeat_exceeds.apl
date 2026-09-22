{
  "apl": "0.0.4",
  "module": "wasm_repeat_exceeds",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "count", "type": "i64", "value": 6},
        {"op": "const", "id": "zero", "type": "i64", "value": 0},
        {
          "op": "repeat",
          "id": "result",
          "type": "i64",
          "count": "count",
          "max": 5,
          "init": "zero",
          "index": "i",
          "carry": "acc",
          "body": [
            {"op": "yield", "value": "acc"}
          ]
        },
        {"op": "return", "value": "result"}
      ]
    }
  ]
}
