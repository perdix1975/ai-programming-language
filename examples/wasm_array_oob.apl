{
  "apl": "0.0.5",
  "module": "wasm_array_oob",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "value", "type": "i64", "value": 7},
        {
          "op": "array",
          "id": "items",
          "type": {"array": "i64", "len": 1},
          "args": ["value"]
        },
        {"op": "const", "id": "index", "type": "i64", "value": 1},
        {
          "op": "array.get",
          "id": "answer",
          "type": "i64",
          "args": ["items", "index"]
        },
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
