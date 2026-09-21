{
  "apl": "0.0.8",
  "module": "effects",
  "capabilities": ["console.write"],
  "entry": "main",
  "functions": [
    {
      "name": "emit",
      "params": [
        {"name": "message", "type": "string"}
      ],
      "returns": "unit",
      "effects": ["console.write"],
      "body": [
        {"op": "print", "args": ["message"]},
        {"op": "return"}
      ]
    },
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "effects": ["console.write"],
      "body": [
        {"op": "const", "id": "message", "type": "string", "value": "hello from APL"},
        {"op": "call", "function": "emit", "args": ["message"]},
        {"op": "const", "id": "answer", "type": "i64", "value": 42},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
