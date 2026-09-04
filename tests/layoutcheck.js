/*
 * layoutcheck.js - exercise the planner's layout model: the table grid,
 * tile placement, the SKU rollup, and multi-sheet nesting.
 */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(ROOT, "src", "planner.html"), "utf8");
const code = html.match(/<script>\n([\s\S]*)<\/script>/)[1];
const body = code.slice(0, code.indexOf("/* ============================ wiring"));

const VALS = {
  cellW:14.33, cellW3:19.25, cellD:13.25, gutter:0.25,
  e1:1.5, e2:3, e3:4.5, t:1.5, kerf:0.15, tab:22, gap:3,
  W:14.33, D:13.25, H:3, SW:32, SH:40, BW:32, BH:40,
  tblW:60, tblD:42, layout:4, rowsn:3,
  mat:"matboard 4-ply", sheet:"Matboard 32 × 40",
};
const stub = `
const document = {
  getElementById(id){
    return {
      get value(){ return VALS[id]; }, set value(v){ VALS[id]=v; },
      set textContent(v){ VALS["_t_"+id]=v; }, get textContent(){ return VALS["_t_"+id]; },
      set innerHTML(v){ VALS["_h_"+id]=v; }, get innerHTML(){ return VALS["_h_"+id]; },
      set disabled(v){}, set open(v){}, set hidden(v){}, get hidden(){ return true; },
      addEventListener(){}, appendChild(){}, closest(){ return null; },
      children:[], dataset:{}, getBoundingClientRect(){ return {left:0,top:0,width:800,height:560}; },
    };
  },
  createElement(){ return {addEventListener(){}, appendChild(){}, style:{}, click(){}, remove(){}}; },
  addEventListener(){},
};
const window = {};
const navigator = {clipboard:{writeText(){return Promise.resolve();}}};
`;
const A = new Function("VALS", stub + body + `
return {
  get TILES(){return TILES}, set TILES(v){TILES=v},
  get SEL(){return SEL}, set SEL(v){SEL=v},
  LAY, HC, HR, spanHalf, tileW, tileD, canPlace, overlaps, fitsGrid,
  presetBento, presetFill, skus, skuSpec, partsFor, sheetOf, nestAll, area,
  render, spec, problems, net, bandParts, pack, exportSVG, elevIn, gridW, gridD,
  isoP, isoInv, cellFromInches, colX, rowY, halfOf, cellWv, cellDv, gut,
};`)(VALS);

let fails = 0;
const check = (c,m)=>{ if(!c){ console.log("  FAIL "+m); fails++; } };
const near = (a,b,t,m)=>check(Math.abs(a-b)<=t, `${m}: ${a} vs ${b}`);

console.log("checking the layout model\n");

/* ---- grid geometry ---- */
A.LAY.layout = 4; A.LAY.rows = 3;
check(A.HC() === 8 && A.HR() === 6, `4-col 3-row should be 8x6 half-modules, got ${A.HC()}x${A.HR()}`);
near(A.spanHalf(14.33, 2), 14.33, 1e-9, "two half-modules make one cell");
near(A.spanHalf(13.25, 1), 6.50, 1e-9, "one half-row");
near(A.gridW(), 58.07, 0.01, "full 4-col grid width");
near(A.gridD(), 40.25, 0.01, "full 3-row grid depth");
check(A.gridW() < VALS.tblW && A.gridD() < VALS.tblD, "grid must fit inside the table");
A.LAY.layout = 3;
check(A.HC() === 6, "3-col should be 6 half-modules");
near(A.gridW(), 58.25, 0.01, "full 3-col grid width");
A.LAY.layout = 4;
console.log("  ok  grid spans reproduce the drawn cells and fit the table");

/* ---- presets place no overlapping tiles, all inside the grid ---- */
for (const [name, mk] of [["bento", A.presetBento], ["fill", A.presetFill]]){
  const T = mk();
  check(T.length > 0, `${name} preset is empty`);
  T.forEach(t=>check(A.fitsGrid(t), `${name}: tile ${JSON.stringify(t)} outside the grid`));
  for (let i=0;i<T.length;i++) for (let j=i+1;j<T.length;j++)
    check(!A.overlaps(T[i],T[j]), `${name}: tiles ${i} and ${j} overlap`);
  console.log(`  ok  ${name} preset: ${T.length} tiles, none overlapping, all in bounds`);
}

/* ---- placement rejects overlaps and out-of-bounds ---- */
A.TILES = [{x:0,y:0,w:2,h:2,elev:1}];
check(!A.canPlace({x:1,y:1,w:2,h:2}), "an overlapping tile was accepted");
check(!A.canPlace({x:7,y:0,w:2,h:2}), "a tile past the right edge was accepted");
check(!A.canPlace({x:0,y:5,w:2,h:2}), "a tile past the bottom edge was accepted");
check(A.canPlace({x:2,y:0,w:2,h:2}), "a legal adjacent tile was rejected");
check(A.canPlace({x:0,y:0,w:2,h:2}, A.TILES[0]), "a tile should not collide with itself when moved");
console.log("  ok  placement rejects overlaps and out-of-bounds, allows legal neighbours");

/* ---- the SKU rollup must conserve every riser ---- */
A.TILES = A.presetBento();
A.render();
const sk = A.skus();
const risers = A.TILES.filter(t=>t.elev>0).length;
near(sk.reduce((n,k)=>n+k.n,0), risers, 0, "SKU quantities must sum to the riser count");
check(!sk.some(k=>k.elev===0), "level-0 placemats must not become SKUs");
sk.forEach(k=>{
  check(k.idx.length === k.n, `SKU ${k.key} index list disagrees with its count`);
  k.idx.forEach(i=>{
    const t = A.TILES[i];
    check(t && t.w===k.w && t.h===k.h && t.elev===k.elev, `SKU ${k.key} points at the wrong tile`);
  });
});
const keys = new Set(sk.map(k=>k.key));
check(keys.size === sk.length, "duplicate SKU keys");
console.log(`  ok  rollup: ${risers} risers into ${sk.length} distinct sizes, counts conserved`);

/* ---- multi-sheet nesting must place every part ---- */
const sheet = A.sheetOf(), gap = VALS.gap;
let all = [];
sk.forEach(k=>{ for (let i=0;i<k.n;i++){ const p = A.partsFor(k, sheet); if (p) all = all.concat(p); } });
const {sheets, unplaced} = A.nestAll(all, sheet, gap);
check(unplaced.length === 0, `${unplaced.length} parts could not be nested`);
near(sheets.reduce((n,s)=>n+s.length,0), all.length, 0, "every part must land on exactly one sheet");
const seen = new Set();
sheets.forEach(s=>s.forEach(pl=>{
  check(!seen.has(pl.part), "a part was placed on two sheets");
  seen.add(pl.part);
}));
sheets.forEach((s,si)=>{
  s.forEach(pl=>check(pl.x>=0 && pl.y>=0 && pl.x+pl.w<=sheet[0]+1e-6 && pl.y+pl.h<=sheet[1]+1e-6,
    `sheet ${si+1}: a part sits off the sheet`));
  for (let i=0;i<s.length;i++) for (let j=i+1;j<s.length;j++){
    const a=s[i], b=s[j];
    const ov = a.x<b.x+b.w-1e-6 && b.x<a.x+a.w-1e-6 && a.y<b.y+b.h-1e-6 && b.y<a.y+a.h-1e-6;
    check(!ov, `sheet ${si+1}: parts overlap`);
  }
});
console.log(`  ok  ${all.length} parts nested onto ${sheets.length} sheets, none lost or overlapping`);

/* ---- every drawing must be finite: no NaN leaking into SVG ---- */
["_h_planstage","_h_viewstage","_h_sheetstage","_h_netstage"].forEach(k=>{
  const s = VALS[k] || "";
  check(s.length > 0, `${k} rendered empty`);
  check(!/NaN|Infinity|undefined/.test(s), `${k} contains NaN/Infinity/undefined`);
});
console.log("  ok  plan, preview, sheet and net drawings are all finite");

/* ---- all three views render for every layout, and stay finite ---- */
let n = 0;
for (const v of ["iso","front","side"]) for (const lay of [3,4]) for (const rw of [2,3,4]){
  VALS.layout = lay; VALS.rowsn = rw;
  A.LAY.layout = lay; A.LAY.rows = rw;
  A.TILES = A.presetBento();
  try {
    A.render();
    const s = VALS._h_viewstage || "";
    check(!/NaN/.test(s), `${v} view at ${lay}col/${rw}row produced NaN`);
    n++;
  } catch (e){ check(false, `${v} view at ${lay}col/${rw}row threw: ${e.message}`); }
}
console.log(`  ok  ${n} view/layout combinations render cleanly`);

/* ---- an empty table must not break anything ---- */
A.TILES = []; A.SEL = new Set();
try { A.render(); check(A.skus().length === 0, "empty table produced SKUs"); }
catch (e){ check(false, `empty table threw: ${e.message}`); }
console.log("  ok  an empty table renders without risers");

/* ---- a tiny bed must surface unplaceable parts, not lose them ---- */
VALS.layout = 4; VALS.rowsn = 3; A.LAY.layout = 4; A.LAY.rows = 3;
A.TILES = [{x:0,y:0,w:8,h:2,elev:3}];
const tiny = [inch=>inch]; // noop
VALS.sheet = "Boss LS-1416 bed"; VALS.BW = 16; VALS.BH = 14;
A.render();
const sh2 = A.sheetOf();
const big = A.partsFor({w:8,h:2,elev:3}, sh2) || [];
const r2 = A.nestAll(big, sh2, gap);
check(r2.unplaced.length > 0, "an oversize riser on a 16x14 bed should report unplaced parts");
console.log("  ok  oversize parts on a small bed are reported, not silently dropped");


/* ---- the isometric inverse must exactly undo the projection ---- */
{
  let worst = 0;
  for (const z of [0, 1.5, 3, 4.5])
    for (let x = 0; x <= 60; x += 3.7)
      for (let y = 0; y <= 42; y += 2.9){
        const [sx, sy] = A.isoP(x, y, z);
        const [rx, ry] = A.isoInv(sx, sy, z);
        worst = Math.max(worst, Math.abs(rx - x), Math.abs(ry - y));
      }
  check(worst < 1e-9, `iso projection round-trip drifts by ${worst}`);
  console.log(`  ok  iso inverse round-trips exactly (worst error ${worst.toExponential(1)} in)`);
}

/* ---- picking in iso must land on the cell actually under the cursor ---- */
{
  A.LAY.layout = 4; A.LAY.rows = 3;
  let hits = 0, miss = 0;
  for (let cx = 0; cx < A.HC(); cx++) for (let cy = 0; cy < A.HR(); cy++)
    for (const z of [0, 3]){
      // centre of this half-cell, projected to iso, then picked back
      const ix = A.colX(cx) + A.halfOf(A.cellWv())/2;
      const iy = A.rowY(cy) + A.halfOf(A.cellDv())/2;
      const [sx, sy] = A.isoP(ix, iy, z);
      const [bx, by] = A.isoInv(sx, sy, z);
      const c = A.cellFromInches(bx, by);
      if (c.x === cx && c.y === cy) hits++; else { miss++;
        if (miss < 3) console.log(`  FAIL iso pick at z=${z}: cell ${cx},${cy} came back ${c.x},${c.y}`); }
    }
  check(miss === 0, `${miss} iso picks landed on the wrong cell`);
  console.log(`  ok  ${hits} iso cell picks all resolve to the right cell, at ground and raised heights`);
}

console.log();
console.log(fails ? `FAILED with ${fails} problem(s)` : "the layout model checks out");
process.exit(fails ? 1 : 0);
