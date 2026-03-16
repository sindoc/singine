#!/usr/bin/env node
/**
 * bin/singine.js — npm shim for the singine Python CLI
 *
 * Locates Python 3, sets PYTHONPATH to the package root so that
 * `singine.*` modules resolve, then delegates to `singine.command`.
 *
 * Works whether installed globally (`npm install -g @sindoc/singine`),
 * locally (`npm install @sindoc/singine`), or run from the source tree.
 */

'use strict';

const { spawnSync } = require('child_process');
const path = require('path');

// ── Locate Python 3 ───────────────────────────────────────────────────────────

function findPython() {
  for (const candidate of ['python3', 'python']) {
    const probe = spawnSync(candidate, ['--version'], { encoding: 'utf8' });
    if (probe.status === 0) {
      const ver = (probe.stdout || probe.stderr || '').trim();
      // Require Python 3.10+
      const m = ver.match(/Python (\d+)\.(\d+)/);
      if (m && (parseInt(m[1]) > 3 || (parseInt(m[1]) === 3 && parseInt(m[2]) >= 10))) {
        return candidate;
      }
    }
  }
  return null;
}

// ── Run ───────────────────────────────────────────────────────────────────────

const python = findPython();

if (!python) {
  process.stderr.write(
    'singine: Python 3.10+ not found on PATH.\n' +
    'Install Python 3 and ensure it is available as `python3` or `python`.\n'
  );
  process.exit(1);
}

// Package root is one level up from bin/
const pkgRoot = path.resolve(__dirname, '..');

const env = Object.assign({}, process.env, {
  PYTHONPATH: process.env.PYTHONPATH
    ? `${pkgRoot}${path.delimiter}${process.env.PYTHONPATH}`
    : pkgRoot
});

const result = spawnSync(
  python,
  ['-m', 'singine.command', ...process.argv.slice(2)],
  { env, stdio: 'inherit' }
);

process.exit(result.status ?? 1);
