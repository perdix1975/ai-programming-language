{
  "apl": "0.0.12",
  "module": "ranges",
  "capabilities": [],
  "limits": {
    "steps": 32,
    "output_lines": 0,
    "host_reads": 0
  },
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
        {"op": "const", "id": "raw", "type": "i64", "value": 42},
        {
          "op": "range.check",
          "id": "percent",
          "type": {"range": {"min": 0, "max": 100}},
          "args": ["raw"]
        },
        {
          "op": "range.value",
          "id": "wide",
          "type": "i64",
          "args": ["percent"]
        },
        {"op": "return", "value": "wide"}
      ]
    }
  ]
}
