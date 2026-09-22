{
  "apl": "0.0.10",
  "module": "wasm_host_read_limit_fail",
  "capabilities": ["fs.read_text"],
  "limits": {"steps": 16, "output_lines": 0, "host_reads": 0},
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "string",
      "effects": ["fs.read_text"],
      "body": [
        {"op": "const", "id": "path", "type": "string", "value": "/message.txt"},
        {
          "op": "fs.read_text",
          "id": "message",
          "type": "string",
          "args": ["path"]
        },
        {"op": "return", "value": "message"}
      ]
    }
  ]
}
