/* Coverage dome: shared by the phone capture page and the PC page.
 *
 * The object sits in the middle. Each cell is one direction to shoot from:
 * 18 sectors around (20 degrees each) x 3 rings (low, middle, high camera angle).
 * Outer ring = low camera, inner ring = high camera looking down.
 * The photographer starts at the bottom and walks to the left (clockwise from above).
 */
(function (root) {
  "use strict";
  const RINGS = 3, SECTORS = 18;
  const RING_LABELS = ["low", "middle", "high"];
  const D2R = Math.PI / 180;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  /* Direction the back camera points in (x east, y north, z up) from the
   * W3C deviceorientation angles. Works for portrait and landscape. */
  function viewFromOrientation(alpha, beta, gamma) {
    const a = alpha * D2R, b = beta * D2R, g = gamma * D2R;
    const ca = Math.cos(a), sa = Math.sin(a), cb = Math.cos(b), sb = Math.sin(b), cg = Math.cos(g), sg = Math.sin(g);
    return {
      x: -ca * sg - sa * sb * cg,
      y: -sa * sg + ca * sb * cg,
      z: -cb * cg
    };
  }
  const headingOf = f => ((Math.atan2(f.x, f.y) / D2R) % 360 + 360) % 360;
  /* Camera height angle above the object, assuming it looks at the object. */
  const elevationOfCamera = f => -Math.asin(clamp(f.z, -1, 1)) / D2R;

  function ringOf(elevation) { return elevation >= 50 ? 2 : elevation >= 25 ? 1 : 0; }
  function sectorOf(azimuth) {
    const a = ((azimuth % 360) + 360) % 360;
    return Math.floor(a / (360 / SECTORS)) % SECTORS;
  }
  const cellOf = (azimuth, elevation) => [ringOf(elevation), sectorOf(azimuth)];

  const emptyCells = () => Array.from({ length: RINGS }, () => Array(SECTORS).fill(0));
  function coverage(cells) {
    let done = 0;
    cells.forEach(r => r.forEach(c => { if (c > 0) done++; }));
    return { done, total: RINGS * SECTORS };
  }

  /* Signed azimuth difference in degrees, -180..180. Positive = step left around the object. */
  const angleDiff = (to, from) => ((to - from + 540) % 360) - 180;

  /* Nearest cell that still needs a photo, searching the current ring first. */
  function nextNeeded(cells, ring, azimuth) {
    let best = null;
    for (let r = 0; r < RINGS; r++) {
      for (let s = 0; s < SECTORS; s++) {
        if (cells[r][s] > 0) continue;
        const centre = (s + 0.5) * (360 / SECTORS);
        const d = angleDiff(centre, azimuth);
        const score = Math.abs(d) + Math.abs(r - ring) * 1000;
        if (!best || score < best.score) best = { ring: r, sector: s, delta: d, score };
      }
    }
    return best;
  }

  /* Plain-language hint for the photographer. */
  function guideText(cells, ring, azimuth) {
    const n = nextNeeded(cells, ring, azimuth);
    if (!n) return "Everything is covered. Tap Finish.";
    if (n.ring !== ring) {
      return n.ring > ring ? "This height is done. Raise the phone and aim down more." : "This height is done. Lower the phone.";
    }
    const deg = Math.round(Math.abs(n.delta));
    if (deg <= 10) return "Hold steady.";
    return (n.delta > 0 ? "Step left around the object" : "Step right around the object") + " (" + deg + "\u00b0 to the next red area)";
  }

  /* ---------- drawing ---------- */
  const RADII = [[0.97, 0.69], [0.69, 0.43], [0.43, 0.17]];   // outer..inner per ring
  const COLORS = { need: "#D64541", done: "#2EA06E", edge: "#F6F6F2" };

  function pointFor(cx, cy, R, azimuth, elevation) {
    const rad = R * (0.97 - clamp(elevation, 0, 85) / 85 * 0.8);
    const phi = (90 + azimuth) * D2R;
    return { x: cx + rad * Math.cos(phi), y: cy + rad * Math.sin(phi) };
  }

  function drawDome(canvas, cells, opts) {
    opts = opts || {};
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    const cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 3;
    ctx.clearRect(0, 0, W, H);
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(246,246,242,0.92)"; ctx.fill();
    const step = 2 * Math.PI / SECTORS;
    for (let r = 0; r < RINGS; r++) {
      const ro = R * RADII[r][0], ri = R * RADII[r][1];
      for (let s = 0; s < SECTORS; s++) {
        const a0 = Math.PI / 2 + s * step + 0.012, a1 = Math.PI / 2 + (s + 1) * step - 0.012;
        const done = cells[r][s] > 0;
        ctx.beginPath(); ctx.arc(cx, cy, ro - 1, a0, a1); ctx.arc(cx, cy, ri + 1, a1, a0, true); ctx.closePath();
        ctx.fillStyle = done ? COLORS.done : COLORS.need; ctx.fill();
        const mid = (a0 + a1) / 2, rm = (ro + ri) / 2;
        if (done) {                      // check mark, so color is not the only signal
          const x = cx + rm * Math.cos(mid), y = cy + rm * Math.sin(mid), u = Math.max(2, (ro - ri) * 0.16);
          ctx.beginPath(); ctx.moveTo(x - u * 1.2, y); ctx.lineTo(x - u * 0.3, y + u * 0.9); ctx.lineTo(x + u * 1.3, y - u * 0.9);
          ctx.strokeStyle = "#fff"; ctx.lineWidth = Math.max(1.5, u * 0.45); ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.stroke();
        }
        if (opts.current && opts.current[0] === r && opts.current[1] === s) {
          ctx.beginPath(); ctx.arc(cx, cy, ro - 1, a0, a1); ctx.arc(cx, cy, ri + 1, a1, a0, true); ctx.closePath();
          ctx.lineWidth = Math.max(2, R * 0.03); ctx.strokeStyle = "#22302B"; ctx.stroke();
        }
      }
    }
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.1, 0, Math.PI * 2); ctx.fillStyle = "#22302B"; ctx.fill();
    if (opts.pointer) {
      const p = pointFor(cx, cy, R, opts.pointer.az, opts.pointer.el);
      ctx.beginPath(); ctx.arc(p.x, p.y, Math.max(4, R * 0.055), 0, Math.PI * 2);
      ctx.fillStyle = "#F2C230"; ctx.fill(); ctx.lineWidth = 2; ctx.strokeStyle = "#22302B"; ctx.stroke();
    }
    if (opts.start) {                    // where the walk begins
      ctx.fillStyle = "#22302B"; ctx.font = "600 " + Math.max(10, R * 0.09) + "px sans-serif";
      ctx.textAlign = "center"; ctx.fillText("start", cx, cy + R * 0.99 - 2);
    }
  }

  const api = {
    RINGS, SECTORS, RING_LABELS, viewFromOrientation, headingOf, elevationOfCamera, ringOf, sectorOf, cellOf,
    emptyCells, coverage, angleDiff, nextNeeded, guideText, drawDome, pointFor
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.Dome = api;
})(typeof window !== "undefined" ? window : globalThis);
