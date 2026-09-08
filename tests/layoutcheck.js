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
  marX:0.965, marY:0.875,
  W:14.33, D:13.25, H:3, SW:32, SH:40, BW:32, BH:40, shW:32, shH:40,
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
  SIZ, hw, hd, spanW, spanD, cellWd, cellDd, mgX, mgY, marX, marY, gridProblem,
  isoPrims, isoCellDepth, ISO, ISOKZ, tileW, tileD, elevIn, colX, rowY, hw, hd,
  sheetOf, sheetDims, CUSTOM, SHEETS,
};`)(VALS);

let fails = 0;
const check = (c,m)=>{ if(!c){ console.log("  FAIL "+m); fails++; } };
const near = (a,b,t,m)=>check(Math.abs(a-b)<=t, `${m}: ${a} vs ${b}`);

console.log("checking the layout model\n");

/* ---- grid geometry ---- */
A.LAY.layout = 4; A.LAY.rows = 3;
check(A.HC() === 8 && A.HR() === 6, `4-col 3-row should be 8x6 half-modules, got ${A.HC()}x${A.HR()}`);
near(A.spanW(2), 14.33, 1e-4, "two half-modules make one cell");
near(A.spanD(1), 6.50, 1e-4, "one half-row");
near(A.gridW(), 58.07, 0.01, "full 4-col grid width");
near(A.gridD(), 40.25, 0.01, "full 3-row grid depth");
check(A.gridW() < VALS.tblW && A.gridD() < VALS.tblD, "grid must fit inside the table");
A.LAY.layout = 3;
check(A.HC() === 6, "3-col should be 6 half-modules");
near(A.gridW(), 58.07, 0.05, "3-col grid still spans the fitted width");
A.LAY.layout = 4;
near(A.cellWd(), 14.33, 1e-3, "fit mode should derive the 14.33in cell");
near(A.cellDd(), 13.25, 1e-3, "fit mode should derive the 13.25in row");
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


/* ---- gap and margin: both directions of the relationship ---- */
{
  A.LAY.layout = 4; A.LAY.rows = 3;

  // fit mode: margin is the input, the cell is derived
  A.SIZ.mode = "fit";
  VALS.marX = 0.965; VALS.marY = 0.875; VALS.gutter = 0.25;
  near(A.mgX(), 0.965, 1e-9, "fit mode should honour the side margin exactly");
  near(A.cellWd(), 14.33, 1e-3, "fit: 0.965in margin gives a 14.33in cell");
  // the grid plus both margins must exactly reconstruct the table
  near(A.gridW() + 2 * A.mgX(), VALS.tblW, 1e-9, "grid + margins must equal the table width");
  near(A.gridD() + 2 * A.mgY(), VALS.tblD, 1e-9, "grid + margins must equal the table depth");

  // a bigger margin must shrink the mats, not overflow the table
  VALS.marX = 4;
  const narrower = A.cellWd();
  check(narrower < 14.33, "raising the margin should shrink the cell");
  near(A.gridW() + 2 * A.mgX(), VALS.tblW, 1e-9, "grid + margins still equal the table width");

  // a bigger gap must also shrink the mats, keeping the total fixed
  VALS.marX = 0.965; VALS.gutter = 1.5;
  check(A.cellWd() < 14.33, "widening the gap should shrink the cell");
  near(A.gridW() + 2 * A.mgX(), VALS.tblW, 1e-9, "grid + margins still equal the table width");
  // and the gap must actually appear between adjacent half-modules
  near(A.colX(1) - (A.colX(0) + A.hw()), 1.5, 1e-9, "the gap between mats must equal the gap setting");
  VALS.gutter = 0.25;

  // fixed mode: the cell is the input, the margin is derived and centred
  A.SIZ.mode = "fixed";
  VALS.cellW = 14.33; VALS.cellD = 13.25;
  near(A.cellWd(), 14.33, 1e-9, "fixed mode should use the given cell");
  near(A.mgX(), 0.965, 1e-3, "fixed mode should centre the leftover as margin");
  near(A.gridW() + 2 * A.mgX(), VALS.tblW, 1e-9, "fixed mode grid + margins equal the table");

  // impossible settings must be reported, not drawn
  A.SIZ.mode = "fit"; VALS.marX = 29;
  check(A.gridProblem() !== null, "an impossible margin should be reported");
  VALS.marX = 0.965;
  check(A.gridProblem() === null, "a workable margin should not be flagged");
  A.SIZ.mode = "fixed"; VALS.cellW = 40;
  check(A.gridProblem() !== null, "a cell too big for the table should be reported");
  VALS.cellW = 14.33; A.SIZ.mode = "fit";
  check(A.gridProblem() === null, "back to a workable grid");
  console.log("  ok  gap and margin drive the grid in both directions, and overflow is caught");
}

/* ---- the sheet comes from the two fields, custom or preset ---- */
{
  VALS.shW = 32; VALS.shH = 40; VALS.BW = 32; VALS.BH = 40;
  let [w,h] = A.sheetDims();
  check(w === 32 && h === 40, `sheet fields should read 32x40, got ${w}x${h}`);

  // a custom size must actually reach the packer
  VALS.shW = 27.5; VALS.shH = 19.25; VALS.BW = 27.5; VALS.BH = 19.25;
  const sh = A.sheetOf();
  near(sh[0] / 25.4, 27.5, 1e-9, "a custom width must reach the packer");
  near(sh[1] / 25.4, 19.25, 1e-9, "a custom height must reach the packer");

  // the bed clamp still wins when it is smaller than the stock
  VALS.shW = 40; VALS.shH = 60; VALS.BW = 32; VALS.BH = 20;
  const cl = A.sheetOf();
  near(cl[0] / 25.4, 32, 1e-9, "the bed clamp must cap a bigger sheet");
  near(cl[1] / 25.4, 20, 1e-9, "the bed clamp must cap a bigger sheet");

  // an emptied or nonsense field must fall back, never produce NaN
  for (const bad of ["", "abc", null, undefined, NaN]){
    VALS.shW = bad; VALS.shH = bad;
    const [bw, bh] = A.sheetDims();
    check(Number.isFinite(bw) && Number.isFinite(bh) && bw >= 2 && bh >= 2,
          `an empty sheet field gave ${bw}x${bh}`);
    const s2 = A.sheetOf();
    check(Number.isFinite(s2[0]) && Number.isFinite(s2[1]),
          "sheetOf must never return NaN");
  }
  // Custom must be an offered option with no fixed dimensions of its own
  check(A.CUSTOM in A.SHEETS, "Custom should be one of the sheet options");
  check(A.SHEETS[A.CUSTOM] === null, "Custom must not carry fixed dimensions");
  const presets = Object.entries(A.SHEETS).filter(([,v]) => v);
  check(presets.length >= 8, `expected the preset list to survive, got ${presets.length}`);
  presets.forEach(([k,v]) => check(v.length === 2 && v[0] > 0 && v[1] > 0, `preset ${k} is malformed`));

  VALS.shW = 32; VALS.shH = 40; VALS.BW = 32; VALS.BH = 40;
  console.log(`  ok  sheet reads from its fields, custom sizes reach the packer, `
    + `the bed clamp still caps, and ${presets.length} presets remain`);
}

/* ---- isometric painter order, checked by ray-casting the real faces ----

   For a screen point, the world points that project to it form a line. From
   sx = (x-y)*C and sy = (x+y)*S - z*ZS, parametrising by z:
       x - y = sx/C ,  x + y = (sy + z*ZS)/S
   so both x and y grow with z: larger z is nearer the camera. The visible
   surface at that point is therefore the one with the LARGEST z along the
   ray. Painter order is correct only if the last tile drawn at each point is
   that same surface. ------------------------------------------------------ */
{
  A.LAY.layout = 4; A.LAY.rows = 3; A.SIZ.mode = "fit";
  VALS.marX = 0.965; VALS.marY = 0.875; VALS.gutter = 0.25;
  const {C, S, ZS} = A.ISO;

  const boxOf = t => {
    const x1 = A.colX(t.x), y1 = A.rowY(t.y);
    return {x1, y1, x2: x1 + A.tileW(t), y2: y1 + A.tileD(t), h: A.elevIn(t.elev), t};
  };
  // world point on the ray through (sx,sy) at height z
  const at = (sx, sy, z) => {
    const d = sx / C, m = (sy + z * ZS) / S;
    return [(m + d) / 2, (m - d) / 2];
  };
  // largest z at which this box's surface meets the ray, or null for a miss
  const hit = (b, sx, sy) => {
    const IN = (v,a,c) => v >= a - 1e-9 && v <= c + 1e-9;
    let best = null;
    // top face, z = h
    const [tx,ty] = at(sx, sy, b.h);
    if (IN(tx,b.x1,b.x2) && IN(ty,b.y1,b.y2)) best = b.h;
    // right face, x = x2  ->  solve for z
    // x(z) = (sx/C + (sy+z*ZS)/S)/2 = x2
    let z = ((2*b.x2 - sx/C) * S - sy) / ZS;
    if (z >= -1e-9 && z <= b.h + 1e-9){
      const [, yy] = at(sx, sy, z);
      if (IN(yy,b.y1,b.y2) && (best === null || z > best)) best = z;
    }
    // front face, y = y2
    z = ((2*b.y2 + sx/C) * S - sy) / ZS;
    if (z >= -1e-9 && z <= b.h + 1e-9){
      const [xx] = at(sx, sy, z);
      if (IN(xx,b.x1,b.x2) && (best === null || z > best)) best = z;
    }
    return best;
  };

  const LAYOUTS = {
    "bento preset": A.presetBento(),
    "filled grid":  A.presetFill(),
    "wide slab with mats behind it": [
      {x:0,y:0,w:2,h:2,elev:0},{x:2,y:0,w:2,h:2,elev:0},{x:4,y:0,w:2,h:2,elev:0},
      {x:6,y:0,w:2,h:2,elev:0},{x:0,y:2,w:8,h:1,elev:2},
      {x:0,y:3,w:2,h:1,elev:0},{x:2,y:3,w:2,h:3,elev:3},{x:4,y:3,w:2,h:2,elev:1}],
    "tall behind flat, and flat behind tall": [
      {x:0,y:0,w:2,h:2,elev:3},{x:0,y:2,w:2,h:2,elev:0},
      {x:2,y:0,w:2,h:2,elev:0},{x:2,y:2,w:2,h:2,elev:3},
      {x:4,y:0,w:4,h:1,elev:1},{x:4,y:1,w:2,h:5,elev:0},{x:6,y:1,w:2,h:2,elev:2}],
  };

  const audit = (tiles, prims) => {
    // every drawn primitive is its own little box, in draw order
    const boxes = prims.map((c,i) => ({
      x1:c.x1, y1:c.y1, x2:c.x2, y2:c.y2, h:c.z, t:c.t, rank:i,
    }));
    const rank = new Map(boxes.map(b => [b, b.rank]));
    // sample the screen over the drawing's extent
    const pts = [];
    boxes.forEach(b => { for (const [x,y] of [[b.x1,b.y1],[b.x2,b.y1],[b.x2,b.y2],[b.x1,b.y2]])
      for (const z of [0,b.h]) pts.push(A.isoP(x,y,z)); });
    const xs = pts.map(p=>p[0]), ys = pts.map(p=>p[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const y0 = Math.min(...ys), y1 = Math.max(...ys);
    const N = 150;
    let bad = 0, covered = 0;
    for (let i=0;i<N;i++) for (let j=0;j<N;j++){
      const sx = x0 + (x1-x0)*(i+0.5)/N, sy = y0 + (y1-y0)*(j+0.5)/N;
      let painter = null, painterRank = -1, truth = null, truthZ = -Infinity;
      for (const b of boxes){
        const z = hit(b, sx, sy);
        if (z === null) continue;
        if (b.rank > painterRank){ painterRank = b.rank; painter = b.t; }
        if (z > truthZ + 1e-9){ truthZ = z; truth = b.t; }
      }
      if (!painter) continue;
      covered++;
      if (painter !== truth) bad++;
    }
    return {bad, covered};
  };

  let totalBad = 0, totalCov = 0;
  for (const [name, tiles] of Object.entries(LAYOUTS)){
    A.TILES = tiles;
    const now = audit(tiles, A.isoPrims(tiles));
    totalBad += now.bad; totalCov += now.covered;
    if (now.bad) console.log(`  FAIL ${name}: ${now.bad} of ${now.covered} covered pixels show the wrong tile`);
  }
  check(totalBad === 0, `${totalBad} of ${totalCov} sampled pixels painted the wrong tile`);
  console.log(`  ok  ${totalCov} sampled pixels across 4 layouts, every one shows the frontmost surface`);

  // the test must catch the whole-tile orderings this replaced, or it proves
  // nothing. Both of them: sorting by grid origin, and by nearest corner.
  const wholeTile = keyFn => tiles => tiles.slice().sort((a,b)=>keyFn(a)-keyFn(b))
    .map(t => ({t, z: A.elevIn(t.elev),
                x1: A.colX(t.x), y1: A.rowY(t.y),
                x2: A.colX(t.x) + A.tileW(t), y2: A.rowY(t.y) + A.tileD(t)}));
  const byOrigin = wholeTile(t => t.x + t.y);
  const byNear   = wholeTile(t => (A.colX(t.x) + A.tileW(t)) + (A.rowY(t.y) + A.tileD(t))
                                  + A.ISOKZ * A.elevIn(t.elev));
  let oldBad = 0, nearBad = 0;
  for (const tiles of Object.values(LAYOUTS)){
    A.TILES = tiles;
    oldBad  += audit(tiles, byOrigin(tiles)).bad;
    nearBad += audit(tiles, byNear(tiles)).bad;
  }
  check(oldBad > 0,  "the ray-cast test does not reproduce the grid-origin bug");
  check(nearBad > 0, "the ray-cast test does not reproduce the nearest-corner bug");
  console.log(`  ok  reproduces both whole-tile orderings it replaced: `
    + `grid-origin mispainted ${oldBad} px, nearest-corner ${nearBad} px`);

  // a tile split into cells must still cover exactly its own footprint
  for (const tiles of Object.values(LAYOUTS)){
    A.TILES = tiles;
    const prims = A.isoPrims(tiles);
    tiles.forEach((t, ti) => {
      const mine = prims.filter(c => c.ti === ti);
      check(mine.length === t.w * t.h, `tile ${ti} split into ${mine.length}, want ${t.w*t.h}`);
      const x1 = Math.min(...mine.map(c=>c.x1)), x2 = Math.max(...mine.map(c=>c.x2));
      const y1 = Math.min(...mine.map(c=>c.y1)), y2 = Math.max(...mine.map(c=>c.y2));
      check(Math.abs((x2-x1) - A.tileW(t)) < 1e-9, `tile ${ti} cells span the wrong width`);
      check(Math.abs((y2-y1) - A.tileD(t)) < 1e-9, `tile ${ti} cells span the wrong depth`);
      // exactly one wall along each boundary run, and one badge anchor
      check(mine.filter(c=>c.wallR).length === t.h, `tile ${ti} wrong right-wall count`);
      check(mine.filter(c=>c.wallF).length === t.w, `tile ${ti} wrong front-wall count`);
      check(mine.filter(c=>c.anchor).length === 1, `tile ${ti} should have one badge anchor`);
    });
  }
  console.log("  ok  cell subdivision covers each tile exactly, with walls only on its boundary");
}

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
