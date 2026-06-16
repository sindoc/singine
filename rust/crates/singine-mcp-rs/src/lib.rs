//! singine-mcp-rs — Rust MCP server foundation (JSON-RPC 2.0 over stdio).
//!
//! Provides the minimal JSON-RPC plumbing needed to expose Rust functions
//! as MCP tools. Python MCP servers (mcp-photo, mcp-silkpage-photo) remain
//! the primary MCP layer; this crate is for performance-critical paths.
//!
//! Protocol reference: https://spec.modelcontextprotocol.io/

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};

// ---------------------------------------------------------------------------
// JSON-RPC types
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
pub struct JsonRpcRequest {
    pub id: Option<Value>,
    pub method: String,
    pub params: Option<Value>,
}

#[derive(Serialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: &'static str,
    pub id: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<JsonRpcError>,
}

#[derive(Serialize)]
pub struct JsonRpcError {
    pub code: i32,
    pub message: String,
}

impl JsonRpcResponse {
    pub fn ok(id: Option<Value>, result: Value) -> Self {
        Self { jsonrpc: "2.0", id, result: Some(result), error: None }
    }

    pub fn err(id: Option<Value>, code: i32, message: impl Into<String>) -> Self {
        Self {
            jsonrpc: "2.0",
            id,
            result: None,
            error: Some(JsonRpcError { code, message: message.into() }),
        }
    }
}

// ---------------------------------------------------------------------------
// Tool registry
// ---------------------------------------------------------------------------

pub type ToolFn = Box<dyn Fn(Option<Value>) -> Value + Send + Sync>;

pub struct McpServer {
    name: String,
    version: String,
    tools: HashMap<String, (String, ToolFn)>,
}

impl McpServer {
    pub fn new(name: impl Into<String>, version: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            version: version.into(),
            tools: HashMap::new(),
        }
    }

    /// Register a tool. `description` is shown to the MCP client.
    pub fn tool(
        &mut self,
        name: impl Into<String>,
        description: impl Into<String>,
        f: impl Fn(Option<Value>) -> Value + Send + Sync + 'static,
    ) {
        self.tools.insert(name.into(), (description.into(), Box::new(f)));
    }

    /// Run the JSON-RPC stdio loop. Blocks until stdin closes.
    pub fn run(self) {
        let stdin = std::io::stdin();
        let stdout = std::io::stdout();
        let reader = BufReader::new(stdin.lock());
        let mut writer = std::io::BufWriter::new(stdout.lock());

        for line in reader.lines() {
            let line = match line {
                Ok(l) => l,
                Err(_) => break,
            };
            let line = line.trim();
            if line.is_empty() {
                continue;
            }

            let response = self.handle(line);
            let json = serde_json::to_string(&response).unwrap_or_else(|_| "{}".into());
            writeln!(writer, "{}", json).ok();
            writer.flush().ok();
        }
    }

    fn handle(&self, line: &str) -> JsonRpcResponse {
        let req: JsonRpcRequest = match serde_json::from_str(line) {
            Ok(r) => r,
            Err(e) => {
                return JsonRpcResponse::err(None, -32700, format!("parse error: {}", e));
            }
        };

        match req.method.as_str() {
            "initialize" => JsonRpcResponse::ok(
                req.id,
                serde_json::json!({
                    "protocolVersion": "2024-11-05",
                    "serverInfo": { "name": self.name, "version": self.version },
                    "capabilities": { "tools": {} }
                }),
            ),
            "tools/list" => {
                let tools: Vec<Value> = self
                    .tools
                    .iter()
                    .map(|(name, (desc, _))| {
                        serde_json::json!({
                            "name": name,
                            "description": desc,
                            "inputSchema": { "type": "object" }
                        })
                    })
                    .collect();
                JsonRpcResponse::ok(req.id, serde_json::json!({ "tools": tools }))
            }
            "tools/call" => {
                let params = req.params.unwrap_or(Value::Null);
                let tool_name = params
                    .get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                let arguments = params.get("arguments").cloned();

                match self.tools.get(&tool_name) {
                    Some((_, f)) => {
                        let result = f(arguments);
                        JsonRpcResponse::ok(
                            req.id,
                            serde_json::json!({
                                "content": [{ "type": "text", "text": result.to_string() }]
                            }),
                        )
                    }
                    None => JsonRpcResponse::err(
                        req.id,
                        -32601,
                        format!("tool not found: {}", tool_name),
                    ),
                }
            }
            "notifications/initialized" => {
                // No response required for notifications
                JsonRpcResponse::ok(req.id, Value::Null)
            }
            other => JsonRpcResponse::err(
                req.id,
                -32601,
                format!("method not found: {}", other),
            ),
        }
    }
}
