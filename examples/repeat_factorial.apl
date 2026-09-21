{
  "apl": "0.0.4",
  "module": "repeat_factorial",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "n", "type": "i64", "value": 5},
        {"op": "const", "id": "one", "type": "i64", "value": 1},
        {
          "op": "repeat",
          "id": "factorial",
          "type": "i64",
          "count": "n",
          "max": 10,
          "init": "one",
          "index": "i",
          "carry": "acc",
          "body": [
            {"op": "add", "id": "factor", "type": "i64", "args": ["i", "one"]},
            {"op": "mul", "id": "next", "type": "i64", "args": ["acc", "factor"]},
            {"op": "yield", "value": "next"}
          ]
        },
        {"op": "print", "args": ["factorial"]},
        {"op": "return", "value": "factorial"}
      ]
    }
  ]
}
