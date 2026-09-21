{
  "apl": "0.0.9",
  "module": "host_io",
  "capabilities": ["console.write", "fs.read_text", "net.get_text"],
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "string",
      "effects": ["console.write", "fs.read_text", "net.get_text"],
      "body": [
        {"op": "const", "id": "path", "type": "string", "value": "/message.txt"},
        {
          "op": "const",
          "id": "url",
          "type": "string",
          "value": "https://example.test/message"
        },
        {
          "op": "fs.read_text",
          "id": "local",
          "type": "string",
          "args": ["path"]
        },
        {
          "op": "net.get_text",
          "id": "remote",
          "type": "string",
          "args": ["url"]
        },
        {"op": "print", "args": ["local"]},
        {"op": "print", "args": ["remote"]},
        {"op": "return", "value": "local"}
      ]
    }
  ]
}
