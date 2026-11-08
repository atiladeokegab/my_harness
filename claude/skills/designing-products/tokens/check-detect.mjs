#!/usr/bin/env node
// The G2 gate over `impeccable detect --json` output. No dependencies.
//   node check-detect.mjs detect.json      (or the JSON on stdin)
// Impeccable marks design-system-* findings (a colour, radius or font size outside DESIGN.md) as
// advisory, so its own exit code stays 0 on them. We fail on them: drift from the guide is the point.
// Exit 0 clean, 2 findings, 1 when the input is not the detector's JSON array (it could not scan).
import fs from 'node:fs';

let findings;
try {
  findings = JSON.parse(fs.readFileSync(process.argv[2] ?? 0, 'utf8'));
  if (!Array.isArray(findings)) throw new Error('not an array');
} catch (e) {
  console.error(`check-detect: no detector JSON to read (${e.message}); the scan did not run`);
  process.exit(1);
}
const failing = findings.filter((f) => !f.advisory || String(f.antipattern).startsWith('design-system-'));
for (const f of failing) console.error(`${f.file}:${f.line} ${f.antipattern}: ${f.snippet}`);
const notes = findings.length - failing.length;
if (notes) console.error(`${notes} advisory note(s) not counted; see the JSON`);
process.exit(failing.length ? 2 : 0);
