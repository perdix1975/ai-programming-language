{
  "apl": "0.0.15",
  "module": "semantic_primitives",
  "capabilities": [],
  "limits": {
    "steps": 64,
    "output_lines": 0,
    "host_reads": 0
  },
  "invariants": [],
  "primitives": [
    {
      "id": "p_52aa7914c68bf4fa400731478171b5a56d16ffb5b5d18b819e8f4c26416e860c",
      "params": [
        {"name": "x", "type": "i64"}
      ],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "one", "type": "i64", "value": 1},
        {"op": "mul", "id": "square", "type": "i64", "args": ["x", "x"]},
        {"op": "add", "id": "result", "type": "i64", "args": ["square", "one"]},
        {"op": "return", "value": "result"}
      ]
    }
  ],
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "effects": [],
      "requires": [],
      "ensures": [],
      "body": [
        {"op": "const", "id": "x", "type": "i64", "value": 6},
        {
          "op": "primitive.call",
          "id": "answer",
          "type": "i64",
          "primitive": "p_52aa7914c68bf4fa400731478171b5a56d16ffb5b5d18b819e8f4c26416e860c",
          "args": ["x"]
        },
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
