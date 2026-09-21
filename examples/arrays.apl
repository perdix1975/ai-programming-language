{
  "apl": "0.0.5",
  "module": "arrays",
  "entry": "main",
  "functions": [
    {
      "name": "second",
      "params": [
        {"name": "items", "type": {"array": "i64", "len": 3}}
      ],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "idx", "type": "i64", "value": 1},
        {"op": "array.get", "id": "value", "type": "i64", "args": ["items", "idx"]},
        {"op": "return", "value": "value"}
      ]
    },
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "a", "type": "i64", "value": 10},
        {"op": "const", "id": "b", "type": "i64", "value": 20},
        {"op": "const", "id": "c", "type": "i64", "value": 30},
        {
          "op": "array",
          "id": "items",
          "type": {"array": "i64", "len": 3},
          "args": ["a", "b", "c"]
        },
        {"op": "call", "id": "second_value", "type": "i64", "function": "second", "args": ["items"]},
        {"op": "array.len", "id": "length", "type": "i64", "args": ["items"]},
        {"op": "add", "id": "answer", "type": "i64", "args": ["second_value", "length"]},
        {"op": "print", "args": ["answer"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
