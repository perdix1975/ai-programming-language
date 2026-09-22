{
  "apl": "0.0.3",
  "module": "wasm_mul_overflow",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "a", "type": "i64", "value": 9223372036854775807},
        {"op": "const", "id": "b", "type": "i64", "value": 2},
        {"op": "mul", "id": "answer", "type": "i64", "args": ["a", "b"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
