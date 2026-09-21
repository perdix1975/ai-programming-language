{
  "apl": "0.0.3",
  "module": "arithmetic",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "a", "type": "i64", "value": -7},
        {"op": "const", "id": "b", "type": "i64", "value": 3},
        {"op": "div", "id": "q", "type": "i64", "args": ["a", "b"]},
        {"op": "rem", "id": "r", "type": "i64", "args": ["a", "b"]},
        {"op": "lt", "id": "is_less", "type": "bool", "args": ["a", "b"]},
        {"op": "print", "args": ["q"]},
        {"op": "print", "args": ["r"]},
        {"op": "print", "args": ["is_less"]},
        {"op": "return", "value": "q"}
      ]
    }
  ]
}
