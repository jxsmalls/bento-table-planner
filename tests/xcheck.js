/*
 * xcheck.js - run the planner's real geometry functions (extracted from
 * planner.html, not a copy) against reference numbers produced by the
 * verified Python, so a transcription slip can't ship.
 *
 *   node xcheck.js ref.json
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..");

const html = fs.readFileSync(path.join(ROOT, "src", "planner.html"), "utf8");
const m = html.match(/<script>\n([\s\S]*)<\/script>/);
if (!m) { console.error("no <script> block found"); process.exit(1); }

// keep everything up to the wiring section; that part needs a real DOM
let code = m[1];
const cut = code.indexOf("/* ============================ wiring");
if (cut < 0) { console.error("wiring marker missing"); process.exit(1); }
code = code.slice(0, cut);

// minimal DOM stub: only the inputs the geometry actually reads
const VALS = {};
// the page does its own `const $ = id => document.getElementById(id)`, so
// stub the document and let the page's own accessor run against it
const stub = `
const document = {
  getElementById(id){
    return {
      get value(){ return VALS[id]; }, set value(v){ VALS[id] = v; },
      set textContent(v){}, set innerHTML(v){},
      set hidden(v){}, get hidden(){ return true; },
      addEventListener(){}, appendChild(){}, className: "",
    };
  },
  createElement(){ return { addEventListener(){}, appendChild(){}, style:{} }; },
};
`;
const fn = new Function("VALS",
  stub + code +
  "\nreturn {spec, problems, net, bandParts, scheme, ribs, pack, perSheet, area, exportSVG};");

const api = fn(VALS);

const ref = JSON.parse(fs.readFileSync(path.join(__dirname, "ref.json"), "utf8"));
const MM = 25.4;
let fails = 0;
const near = (a, b, tol, what) => {
  if (Math.abs(a - b) > tol) { console.log(`  FAIL ${what}: js ${a} vs py ${b}`); fails++; return false; }
  return true;
};

console.log("cross-checking JS geometry against the Python reference\n");

for (const c of ref.cases) {
  Object.assign(VALS, {W: c.w, D: c.d, H: c.h, t: c.t, kerf: c.kerf, tab: c.tab,
                       SW: 32, SH: 40, BW: 32, BH: 40, gap: 3});
  const s = api.spec();
  const tag = `${c.w}x${c.d}x${c.h} t=${c.t}`;

  near(s.wp, c.wp, 1e-6, `${tag} panel width`);
  near(s.dp, c.dp, 1e-6, `${tag} panel depth`);
  near(s.hf, c.hf, 1e-6, `${tag} wall flat height`);
  near(s.tab, c.tab_eff, 1e-6, `${tag} effective tab`);

  const n = api.net(s);
  near(n.size[0], c.net_w, 1e-6, `${tag} net width`);
  near(n.size[1], c.net_h, 1e-6, `${tag} net height`);
  near(api.area(n), c.net_area, 1e-3, `${tag} net cut area`);
  near(n.cut[0].length, c.net_points, 0, `${tag} outline point count`);
  near(n.score.length, c.net_scores, 0, `${tag} score line count`);

  const sheet = [32 * MM, 40 * MM];
  const bp = api.bandParts(s, sheet);
  if (api.scheme(s, sheet) !== c.scheme) {
    console.log(`  FAIL ${tag} scheme: js ${api.scheme(s, sheet)} vs py ${c.scheme}`);
    fails++;
  }
  near(bp.length, c.band_parts, 0, `${tag} band part count`);
  near(bp.reduce((t, p) => t + api.area(p), 0), c.band_area, 1e-3, `${tag} band cut area`);

  const rb = api.ribs(s);
  near(rb[0].size[0], c.ribA_len, 1e-6, `${tag} rib A length`);
  near(rb[0].size[1], c.rib_h, 1e-6, `${tag} rib height`);

  const n1 = api.perSheet(() => [api.net(s)], sheet, 3, 24);
  const nb = api.perSheet(() => api.bandParts(s, sheet), sheet, 3, 24);
  near(n1, c.per_sheet_one, 0, `${tag} one-piece per sheet`);
  near(nb, c.per_sheet_band, 0, `${tag} band per sheet`);

  if (!fails) console.log(`  ok  ${tag}`);
}

// the exported SVG must be true 1:1 mm with all three layers
Object.assign(VALS, {W: 14.33, D: 13.25, H: 3, t: 1.5, kerf: 0.15, tab: 22,
                     SW: 32, SH: 40, BW: 32, BH: 40, gap: 3});
const s = api.spec();
const sheet = [32 * MM, 40 * MM];
const { placed } = api.pack([api.net(s), api.net(s)], sheet[0], sheet[1], 6, 3);
const svg = api.exportSVG(placed, sheet[0], sheet[1]);
for (const need of ['width="812.800mm"', 'id="CUT"', 'id="SCORE"', 'id="LABEL"',
                    'stroke="#FF0000"', 'stroke="#0000FF"']) {
  if (!svg.includes(need)) { console.log(`  FAIL export svg missing ${need}`); fails++; }
}
if (placed.length !== 2) { console.log(`  FAIL export placed ${placed.length} of 2`); fails++; }
console.log(fails ? "" : "  ok  exported SVG is 1:1 mm and fully layered");

console.log();
console.log(fails ? `FAILED with ${fails} mismatch(es)` : "JS matches the Python reference exactly");
process.exit(fails ? 1 : 0);
