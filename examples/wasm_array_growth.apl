{
  "apl": "0.0.5",
  "module": "wasm_array_growth",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "count", "type": "i64", "value": 5000},
        {"op": "const", "id": "a", "type": "i64", "value": 10},
        {"op": "const", "id": "b", "type": "i64", "value": 20},
        {"op": "const", "id": "c", "type": "i64", "value": 30},
        {"op": "array", "id": "initial", "type": {"array": "i64", "len": 3}, "args": ["a", "b", "c"]},
        {
          "op": "repeat",
          "id": "last",
          "type": {"array": "i64", "len": 3},
          "count": "count",
          "max": 5000,
          "init": "initial",
          "index": "i",
          "carry": "previous",
          "body": [
            {"op": "array", "id": "next", "type": {"array": "i64", "len": 3}, "args": ["a", "b", "c"]},
            {"op": "yield", "value": "next"}
          ]
        },
        {"op": "const", "id": "idx", "type": "i64", "value": 1},
        {"op": "array.get", "id": "answer", "type": "i64", "args": ["last", "idx"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
