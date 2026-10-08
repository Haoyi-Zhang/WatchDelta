#!/usr/bin/env node
/**
 * Versioned source-decision replay for Vite issue #16248.
 *
 * This is deliberately not labeled a full Vite reproduction. It executes the
 * relevant v5.2.4 and v5.2.10 path/configuration decisions on an alphabet for
 * which fast-glob's escapePath is the identity, then classifies whether the
 * target falls below an emitted absolute `outDir/**` rule.
 */
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import process from 'node:process';

const artifact = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const upstream = path.join(artifact, 'evidence', 'upstream', 'vite');
const oldSource = fs.readFileSync(path.join(upstream, 'watch-v5.2.4.ts'), 'utf8');
const fixedSource = fs.readFileSync(path.join(upstream, 'watch-v5.2.10.ts'), 'utf8');
const provenance = JSON.parse(fs.readFileSync(path.join(upstream, 'provenance.json'), 'utf8'));

function sha256(text) { return crypto.createHash('sha256').update(text).digest('hex'); }
function arraify(value) { return Array.isArray(value) ? value : [value]; }
function normalizePath(value) { return value.replaceAll('\\', '/'); }
function withTrailingSlash(value) { return value.endsWith('/') ? value : value + '/'; }
function escapePath(value) {
  if (!/^[A-Za-z0-9_./-]+$/.test(value)) throw new Error(`path alphabet needs escaping: ${value}`);
  return value;
}

function oldResolve(config, options = undefined) {
  const ignoredList = options?.ignored ?? [];
  const ignored = ['**/.git/**', '**/node_modules/**', '**/test-results/**',
    escapePath(config.cacheDir) + '/**', ...arraify(ignoredList || [])];
  if (config.build.outDir) {
    ignored.push(escapePath(path.resolve(config.root, config.build.outDir)) + '/**');
  }
  return ignored;
}

function getResolvedOutDirs(root, outDir, outputOptions) {
  const resolvedOutDir = path.resolve(root, outDir);
  if (!outputOptions) return new Set([resolvedOutDir]);
  return new Set(arraify(outputOptions).map(({dir}) => dir ? path.resolve(root, dir) : resolvedOutDir));
}
function resolveEmptyOutDir(emptyOutDir, root, outDirs) {
  if (emptyOutDir != null) return emptyOutDir;
  for (const outDir of outDirs) {
    if (!normalizePath(outDir).startsWith(withTrailingSlash(normalizePath(root)))) return false;
  }
  return true;
}
function fixedResolve(config, options = undefined) {
  const ignoredList = options?.ignored ?? [];
  const outDirs = getResolvedOutDirs(config.root, config.build.outDir, config.build.outputOptions);
  const empty = resolveEmptyOutDir(config.build.emptyOutDir, config.root, outDirs);
  const ignored = ['**/.git/**', '**/node_modules/**', '**/test-results/**',
    escapePath(config.cacheDir) + '/**', ...arraify(ignoredList || [])];
  if (empty) ignored.push(...[...outDirs].map(outDir => escapePath(outDir) + '/**'));
  return {ignored, resolvedOutDirs:[...outDirs], resolvedEmptyOutDir:empty};
}
function covered(target, patterns) {
  const normalized = normalizePath(path.resolve(target));
  return patterns.some(pattern => {
    if (!pattern.startsWith('/')) return false; // defaults/user globs are outside this replay's claim
    const prefix = normalizePath(pattern).replace(/\/\*\*$/, '');
    return normalized === prefix || normalized.startsWith(prefix + '/');
  });
}

if (!oldSource.includes('if (config.build.outDir)') ||
    !oldSource.includes('path.resolve(config.root, config.build.outDir)')) {
  throw new Error('v5.2.4 source snapshot does not contain the replayed decision');
}
if (!fixedSource.includes('if (emptyOutDir)') ||
    !fixedSource.includes('...[...resolvedOutDirs].map')) {
  throw new Error('v5.2.10 source snapshot does not contain the replayed decision');
}

const root = '/tmp/watchdelta-vite/project';
const configs = [
  {id:'issue-empty-false', outDir:'dist', emptyOutDir:false},
  {id:'inside-empty-true', outDir:'dist', emptyOutDir:true},
  {id:'inside-empty-auto', outDir:'dist', emptyOutDir:null},
  {id:'outside-empty-auto', outDir:'../external-dist', emptyOutDir:null},
  {id:'outside-empty-false', outDir:'../external-dist', emptyOutDir:false},
  {id:'outside-empty-true', outDir:'../external-dist', emptyOutDir:true},
  {id:'single-output-false', outDir:'dist', emptyOutDir:false, outputOptions:{dir:'bundle'}},
  {id:'single-output-true', outDir:'dist', emptyOutDir:true, outputOptions:{dir:'bundle'}},
  {id:'multi-output-false', outDir:'dist', emptyOutDir:false, outputOptions:[{dir:'bundle-a'},{dir:'bundle-b'}]},
  {id:'multi-output-true', outDir:'dist', emptyOutDir:true, outputOptions:[{dir:'bundle-a'},{dir:'bundle-b'}]},
  {id:'fallback-output-false', outDir:'dist', emptyOutDir:false, outputOptions:[{}, {dir:'bundle-b'}]},
  {id:'fallback-output-true', outDir:'dist', emptyOutDir:true, outputOptions:[{}, {dir:'bundle-b'}]},
];
const targets = [
  {id:'configured-outdir', make:c => path.resolve(root,c.outDir,'styles.scss')},
  {id:'root-source', make:() => path.resolve(root,'src','styles.scss')},
  {id:'first-rollup-output', make:c => path.resolve(root,arraify(c.outputOptions ?? {})[0]?.dir ?? c.outDir,'styles.scss')},
  {id:'unrelated', make:() => path.resolve(root,'assets','styles.scss')},
];
const records=[];
for (const c of configs) {
  const config={root,cacheDir:path.resolve(root,'node_modules/.vite'),build:{outDir:c.outDir,emptyOutDir:c.emptyOutDir,outputOptions:c.outputOptions}};
  const oldPatterns=oldResolve(config);
  const fixed=fixedResolve(config);
  for (const t of targets) {
    const target=t.make(c);
    const oldIgnored=covered(target,oldPatterns);
    const fixedIgnored=covered(target,fixed.ignored);
    records.push({case:`${c.id}/${t.id}`,config:c,target,oldIgnored,fixedIgnored,
      changed:oldIgnored!==fixedIgnored,oldPatterns:oldPatterns.filter(x=>x.startsWith('/')),
      fixedPatterns:fixed.ignored.filter(x=>x.startsWith('/')),
      resolvedOutDirs:fixed.resolvedOutDirs,resolvedEmptyOutDir:fixed.resolvedEmptyOutDir});
  }
}
const issueCase=records.find(r=>r.case==='issue-empty-false/configured-outdir');
if (!issueCase || issueCase.oldIgnored!==true || issueCase.fixedIgnored!==false) {
  throw new Error(`issue decision not reproduced: ${JSON.stringify(issueCase)}`);
}
const outIndex=process.argv.indexOf('--output');
if (outIndex<0 || !process.argv[outIndex+1]) throw new Error('usage: node scripts/vite_filter_replay.mjs --output DIR');
const output=path.resolve(process.argv[outIndex+1]);
if (fs.existsSync(output)) throw new Error(`refusing to overwrite ${output}`);
fs.mkdirSync(output,{recursive:true});
fs.writeFileSync(path.join(output,'records.jsonl'),records.map(r=>JSON.stringify(r)).join('\n')+'\n');
const summary={
  classification:'versioned source-decision replay, not full Vite runtime reproduction',
  cases:records.length,
  unchanged:records.filter(r=>!r.changed).length,
  changed:records.filter(r=>r.changed).length,
  old_ignored_fixed_not:records.filter(r=>r.oldIgnored&&!r.fixedIgnored).length,
  old_not_fixed_ignored:records.filter(r=>!r.oldIgnored&&r.fixedIgnored).length,
  issue_case:issueCase,
  source:{
    old:{...provenance.old_source,sha256:sha256(oldSource)},
    fixed:{...provenance.fixed_source,sha256:sha256(fixedSource)},
  },
  node:process.version,
};
fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2)+'\n');
fs.writeFileSync(path.join(output,'provenance.json'),JSON.stringify(provenance,null,2)+'\n');
console.log(JSON.stringify(summary,null,2));
