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
        {"op": "const", "id": "a", "type": "i64", "value": 10},
        {"op": "const", "id": "b", "type": "i64", "value": 20},
        {"op": "array", "id": "items", "type": {"array": "i64", "len": 2}, "args": ["a", "b"]},
        {"op": "const", "id": "idx", "type": "i64", "value": 2},
        {"op": "array.get", "id": "value", "type": "i64", "args": ["items", "idx"]},
        {"op": "return", "value": "value"}
      ]
    }
  ]
}
