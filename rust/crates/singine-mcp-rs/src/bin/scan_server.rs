//! MCP server that exposes singine-photo-scan as an MCP tool.
//!
//! Register with:
//!   claude mcp add singine-scan --transport stdio -- \
//!       singine-mcp-scan
//!
//! Tool exposed:
//!   scan_photos(dir: string, ext?: string) → NDJSON string of PhotoRecord objects

use serde_json::Value;
use singine_mcp_rs::McpServer;

fn main() {
    let mut server = McpServer::new("singine-scan", "0.1.0");

    server.tool(
        "scan_photos",
        "Walk a photo directory recursively. Returns NDJSON where each line is a \
         PhotoRecord with path, filename, size_bytes, sha256, and EXIF metadata \
         (taken, make, model, gps_lat, gps_lon, width, height). \
         Feed the output directly to singine-photo/batch_classify.",
        |args: Option<Value>| {
            let args = args.unwrap_or(Value::Null);
            let dir = args
                .get("dir")
                .and_then(|v| v.as_str())
                .unwrap_or(".");
            let ext = args
                .get("ext")
                .and_then(|v| v.as_str())
                .unwrap_or("jpg,jpeg,png,heic,webp,tiff,tif,raw,arw,cr2,nef,dng");

            // Delegate to singine-photo-scan binary via subprocess.
            // When compiled into the same workspace this could be a direct call,
            // but subprocess keeps the server process lean and avoids rayon init cost.
            let output = std::process::Command::new("singine-photo-scan")
                .arg(dir)
                .arg("--ext")
                .arg(ext)
                .output();

            match output {
                Ok(out) if out.status.success() => {
                    let ndjson = String::from_utf8_lossy(&out.stdout).into_owned();
                    let line_count = ndjson.lines().count();
                    serde_json::json!({
                        "ok": true,
                        "dir": dir,
                        "record_count": line_count,
                        "ndjson": ndjson
                    })
                }
                Ok(out) => {
                    let stderr = String::from_utf8_lossy(&out.stderr).into_owned();
                    serde_json::json!({ "ok": false, "error": stderr })
                }
                Err(e) => {
                    serde_json::json!({ "ok": false, "error": e.to_string() })
                }
            }
        },
    );

    server.run();
}
