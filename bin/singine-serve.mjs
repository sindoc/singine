#!/usr/bin/env node
/**
 * singine-serve — lightweight HTTP appserver for SilkPage documents.
 *
 * Serves the SilkPage www/ webroot via singine's execution engine.
 * Follows the same Node.js + ESM pattern as singine-mcp.
 *
 * Usage:
 *   node bin/singine-serve.mjs [port] [webroot]
 *   singine serve [port]           # via singine CLI shim (future)
 *
 * Defaults:
 *   port    = 4242
 *   webroot = ../../silkpage/main/silkpage/www  (relative to singine repo root)
 *
 * Routes:
 *   GET /          → webroot/index.html
 *   GET /cv/       → webroot/cv/index.html    ← CV preview
 *   GET /**        → static file from webroot
 *
 * MIME types handled: html, css, js, mjs, json, xml, xsl, svg,
 *                     png, jpg, gif, webp, ico, pdf, ttf, woff2
 */

import http    from 'node:http';
import fs      from 'node:fs';
import path    from 'node:path';
import { URL } from 'node:url';

// ── Config ─────────────────────────────────────────────────────────────────

const PORT    = parseInt(process.argv[2] ?? process.env.SINGINE_PORT ?? '4242', 10);
const __dir   = path.dirname(new URL(import.meta.url).pathname);
const REPO    = path.resolve(__dir, '..');
const WEBROOT = process.argv[3]
  ?? process.env.SINGINE_WEBROOT
  ?? path.resolve(REPO, '../../silkpage/main/silkpage/www');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.mjs':  'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.xml':  'application/xml; charset=utf-8',
  '.xsl':  'application/xslt+xml; charset=utf-8',
  '.xsd':  'application/xml; charset=utf-8',
  '.svg':  'image/svg+xml',
  '.png':  'image/png',
  '.jpg':  'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif':  'image/gif',
  '.webp': 'image/webp',
  '.ico':  'image/x-icon',
  '.pdf':  'application/pdf',
  '.ttf':  'font/ttf',
  '.woff': 'font/woff',
  '.woff2':'font/woff2',
};

// ── Request handler ─────────────────────────────────────────────────────────

function handler(req, res) {
  const url      = new URL(req.url, `http://localhost:${PORT}`);
  let   pathname = decodeURIComponent(url.pathname);

  // Directory → index.html
  if (pathname.endsWith('/')) pathname += 'index.html';

  // Resolve against webroot; reject path traversal
  const abs = path.resolve(WEBROOT, '.' + pathname);
  if (!abs.startsWith(WEBROOT)) {
    res.writeHead(403); res.end('403 Forbidden'); return;
  }

  fs.stat(abs, (err, stat) => {
    if (err || !stat.isFile()) {
      // Try appending index.html for bare directory paths without trailing slash
      const idx = path.join(abs, 'index.html');
      fs.stat(idx, (e2, s2) => {
        if (!e2 && s2.isFile()) return sendFile(idx, res);
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end(`404 Not Found: ${pathname}`);
      });
      return;
    }
    sendFile(abs, res);
  });
}

function sendFile(abs, res) {
  const ext  = path.extname(abs).toLowerCase();
  const mime = MIME[ext] ?? 'application/octet-stream';
  const stream = fs.createReadStream(abs);
  stream.on('error', () => { res.writeHead(500); res.end('500 Read error'); });
  res.writeHead(200, { 'Content-Type': mime });
  stream.pipe(res);
}

// ── Start ───────────────────────────────────────────────────────────────────

if (!fs.existsSync(WEBROOT)) {
  console.error(`singine-serve: webroot not found: ${WEBROOT}`);
  console.error(`  Set SINGINE_WEBROOT or pass as second argument.`);
  process.exit(1);
}

const server = http.createServer(handler);
server.listen(PORT, '127.0.0.1', () => {
  console.log(`singine-serve running`);
  console.log(`  webroot  ${WEBROOT}`);
  console.log(`  url      http://localhost:${PORT}/`);
  console.log(`  cv       http://localhost:${PORT}/cv/`);
  console.log();
  console.log(`  Ctrl+C to stop`);
});
