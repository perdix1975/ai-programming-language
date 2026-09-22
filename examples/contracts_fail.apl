{
  "apl": "0.0.11",
  "module": "contracts_fail",
  "capabilities": [],
  "limits": {
    "steps": 8,
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
      "requires": [
        {
          "id": "enabled",
          "message": "demonstration precondition failed",
          "predicate": {
            "const": {"type": "bool", "value": false}
          }
        }
      ],
      "ensures": [],
      "body": [
        {"op": "const", "id": "answer", "type": "i64", "value": 42},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
