{
  "apl": "0.0.1",
  "module": "hello",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "a", "type": "i64", "value": 40},
        {"op": "const", "id": "b", "type": "i64", "value": 2},
        {"op": "add", "id": "answer", "type": "i64", "args": ["a", "b"]},
        {"op": "print", "args": ["answer"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
