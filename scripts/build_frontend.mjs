/**
 * scripts/build_frontend.mjs — BookTale frontend build (esbuild)
 *
 * Minifies every script in static/js/ and the stylesheet static/css/booktale.css
 * into static/dist/ using content-hash filenames (cache busting), then writes
 * static/dist/manifest.json mapping logical paths (js/utils.js, css/booktale.css)
 * to their hashed URLs. Flask's `asset()` Jinja helper (web_app.py) reads that
 * manifest at request time and falls back to the un-hashed path when the build
 * has not been run (dev/tests).
 *
 * Usage:  npm run build        (one-shot)
 *         npm run watch        (rebuild on change)
 */
import { build, context } from 'esbuild';
import { mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const JS_DIR = join(ROOT, 'app', 'static', 'js');
const CSS_FILE = join(ROOT, 'app', 'static', 'css', 'booktale.css');
const OUT_DIR = join(ROOT, 'app', 'static', 'dist');
const MANIFEST = join(OUT_DIR, 'manifest.json');

const watch = process.argv.includes('--watch');

async function buildOnce() {
  mkdirSync(OUT_DIR, { recursive: true });

  const jsFiles = readdirSync(JS_DIR).filter((f) => f.endsWith('.js'));

  // ── JS: minify each file in isolation (they are classic scripts that share
  //    the global scope via load order — bundling would break globals like
  //    showToast/toggleTheme referenced by inline handlers).
  const jsResult = await build({
    entryPoints: jsFiles.map((f) => join(JS_DIR, f)),
    outdir: OUT_DIR,
    entryNames: 'js/[name]-[hash].min',
    format: 'iife',
    bundle: false,
    minify: true,
    charset: 'utf8',
    sourcemap: false,
    logLevel: 'silent',
    metafile: true,
  });

  // ── CSS: minify (bundle:false keeps url('../fonts/...') paths intact;
  //    dist css lives at static/dist/ so ../fonts resolves to static/fonts).
  const cssResult = await build({
    entryPoints: [CSS_FILE],
    outdir: OUT_DIR,
    entryNames: '[name]-[hash].min',
    bundle: false,
    minify: true,
    charset: 'utf8',
    sourcemap: false,
    logLevel: 'silent',
    metafile: true,
  });

  // ── Manifest: use esbuild's metafile for an exact entry -> output mapping.
  //    (A naive split('-') truncates hyphenated names like ai-companion.js.)
  //    Metafile output keys are CWD-relative (e.g. static/dist/js/x.min.js),
  //    so strip any leading path and rebuild the URL from the dist root.
  const toUrl = (outPath) => {
    const parts = outPath.replace(/\\/g, '/').split('/');
    const file = parts[parts.length - 1];
    const sub = parts.includes('js') && file.endsWith('.js') ? 'js/' : '';
    return `/static/dist/${sub}${file}`;
  };
  const manifest = {};
  for (const [out, info] of Object.entries(jsResult.metafile.outputs)) {
    const entry = info.entryPoint; // absolute path to the source entry
    if (!entry) continue;
    const logical = `js/${basename(entry)}`;
    manifest[logical] = toUrl(out);
  }
  for (const [out, info] of Object.entries(cssResult.metafile.outputs)) {
    if (!info.entryPoint) continue;
    manifest['css/booktale.css'] = toUrl(out);
  }

  // Fallback safety: any source file that somehow produced no output keeps
  // its un-hashed URL so templates never 404.
  for (const f of jsFiles) {
    const logical = `js/${f}`;
    if (!manifest[logical]) manifest[logical] = `/static/js/${f}`;
  }
  if (!manifest['css/booktale.css']) manifest['css/booktale.css'] = '/static/css/booktale.css';

  writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2) + '\n');
  console.log(`[build] ${Object.keys(manifest).length} assets -> static/dist/manifest.json`);
  for (const [k, v] of Object.entries(manifest)) console.log(`  ${k} -> ${v}`);
}

if (watch) {
  // ── Watch mode ──
  const ctx = await context({
    entryPoints: readdirSync(JS_DIR).filter((f) => f.endsWith('.js')).map((f) => join(JS_DIR, f)),
    outdir: OUT_DIR,
    entryNames: 'js/[name]-[hash].min',
    format: 'iife',
    bundle: false,
    minify: true,
    charset: 'utf8',
    sourcemap: false,
    logLevel: 'silent',
    metafile: true,
  });
  // Regenerate the manifest on every rebuild so the running app always
  // resolves fresh content hashes (the asset() helper caches the manifest).
  await ctx.watch({ onRebuild: () => { buildOnce(); } });
  console.log('[build] watching static/js + static/css... (Ctrl+C to stop)');
} else {
  await buildOnce();
}
