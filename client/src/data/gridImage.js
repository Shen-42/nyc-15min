// Turns the city grid (cards 12 and 15) into one smooth image for the map.
//
// Each grid cell is a point with a value (a score, or 1/0 for a gap). The
// value at any spot on the image is a weighted average of the nearby points,
// with weights that fall off smoothly with distance (a Gaussian, sigma in
// grid cells). Dividing by the summed weights ("normalized convolution")
// keeps edges and small holes from fading toward zero: a small park is filled
// in by its neighbors. The image is then cut to the shoreline so nothing
// spills into the rivers, and any "blank" outlines (lakes, and for the gap
// finder, parks) are cut out of it.
//
// Only the part of the city in view is drawn (card 15): the whole city at
// full detail would be a canvas of tens of millions of pixels. Zoomed out,
// each grid square gets fewer pixels, which can't be told apart at that zoom.
//
// With fill on (the score map), cells with no value, the parks, are colored
// from the blocks around them: where the normal smoothing has no data, a much
// wider one takes over, so even the middle of Central Park gets a color that
// blends with its edges instead of a hole.

// Image pixels per grid square, at most. The browser smooths it further when zooming in.
const MAX_PIXELS_PER_CELL = 6;
// The most pixels an image may have, so drawing stays quick zoomed out.
const MAX_PIXELS = 2_500_000;
// The wide smoothing that fills parks on the score map, in grid cells. Five
// cells (500 m) reaches the middle of Central Park, 800 m across.
const FILL_SIGMA = 5;

// Leaflet stretches an image evenly in Web Mercator, not in latitude, so
// image rows are placed by Mercator y.
const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const latFromMercY = (y) => ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI;

export function smoothstep(edge0, edge1, x) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

function gaussianKernel(sigma) {
  const radius = Math.ceil(3 * sigma);
  const weights = [];
  for (let i = -radius; i <= radius; i++) weights.push(Math.exp(-(i * i) / (2 * sigma * sigma)));
  const sum = weights.reduce((a, b) => a + b, 0);
  return { radius, weights: weights.map((w) => w / sum) };
}

// A Gaussian blur, done as two 1-D passes (across, then down).
function blur(source, cols, rows, { radius, weights }) {
  const across = new Float32Array(source.length);
  const out = new Float32Array(source.length);
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      let sum = 0;
      for (let i = -radius; i <= radius; i++) {
        const xx = x + i;
        if (xx >= 0 && xx < cols) sum += source[y * cols + xx] * weights[i + radius];
      }
      across[y * cols + x] = sum;
    }
  }
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      let sum = 0;
      for (let i = -radius; i <= radius; i++) {
        const yy = y + i;
        if (yy >= 0 && yy < rows) sum += across[yy * cols + x] * weights[i + radius];
      }
      out[y * cols + x] = sum;
    }
  }
  return out;
}

// Bilinear lookup in a cols x rows array at fractional (gx, gy).
function sample(field, cols, rows, gx, gy) {
  const x0 = Math.max(0, Math.min(cols - 2, Math.floor(gx)));
  const y0 = Math.max(0, Math.min(rows - 2, Math.floor(gy)));
  const tx = Math.min(1, Math.max(0, gx - x0));
  const ty = Math.min(1, Math.max(0, gy - y0));
  const i = y0 * cols + x0;
  const top = field[i] * (1 - tx) + field[i + 1] * tx;
  const bottom = field[i + cols] * (1 - tx) + field[i + cols + 1] * tx;
  return top * (1 - ty) + bottom * ty;
}

// Returns { url, bounds } for L.imageOverlay, or null if no squares are in view.
//   cells: [lat, lng, scores, flags, col, row] (see grid.js); meta: the grid's meta.
//   view: { south, west, north, east }, the part of the map to draw.
//   valueFor(cell): a number, or null for "no data here" (parks).
//   colorFor(value): [r, g, b, alpha 0-1], or null to leave the spot clear.
//   sigma: how far the smoothing reaches, in grid squares.
//   land: outlines to keep, as [[lat, lng], ...]; blank: outlines to cut out.
//   fill: color squares with no value from their surroundings (see above).
export function gridImage({ cells, meta, view, valueFor, colorFor, sigma, land, blank = [], fill = false }) {
  const [originLat, originLng] = meta.origin;
  const [stepLat, stepLng] = meta.step;

  // The squares in view, plus a margin so the fade at the edges isn't cut off.
  const kernel = gaussianKernel(sigma);
  const wide = gaussianKernel(FILL_SIGMA);
  const pad = (fill ? wide : kernel).radius + 1;
  const c0 = Math.floor((view.west - originLng) / stepLng) - pad;
  const c1 = Math.ceil((view.east - originLng) / stepLng) + pad;
  const r0 = Math.floor((view.south - originLat) / stepLat) - pad;
  const r1 = Math.ceil((view.north - originLat) / stepLat) + pad;
  const cols = c1 - c0 + 1;
  const rows = r1 - r0 + 1;
  const inView = cells.filter((cell) => cell[4] >= c0 && cell[4] <= c1 && cell[5] >= r0 && cell[5] <= r1);
  if (!inView.length) return null;
  // The center of square (c0, r0), where the arrays below start.
  const lat0 = originLat + (r0 + 0.5) * stepLat;
  const lng0 = originLng + (c0 + 0.5) * stepLng;
  const pixelsPerCell = Math.max(1, Math.min(MAX_PIXELS_PER_CELL, Math.floor(Math.sqrt(MAX_PIXELS / (cols * rows)))));

  // Row 0 is the south edge here. isLand marks every grid cell; hasData
  // only those with a value, so parks (no value) can be told from water.
  const values = new Float32Array(cols * rows);
  const hasData = new Float32Array(cols * rows);
  const isLand = new Float32Array(cols * rows);
  for (const cell of inView) {
    const x = cell[4] - c0;
    const y = cell[5] - r0;
    isLand[y * cols + x] = 1;
    const value = valueFor(cell);
    if (value === null) continue;
    values[y * cols + x] = value;
    hasData[y * cols + x] = 1;
  }
  const valueSum = blur(values, cols, rows, kernel);
  const weightSum = blur(hasData, cols, rows, kernel);
  const landSum = blur(isLand, cols, rows, kernel);
  const wideValueSum = fill ? blur(values, cols, rows, wide) : null;
  const wideWeightSum = fill ? blur(hasData, cols, rows, wide) : null;

  const south = lat0, north = lat0 + (rows - 1) * stepLat;
  const west = lng0, east = lng0 + (cols - 1) * stepLng;
  const width = (cols - 1) * pixelsPerCell;
  const height = (rows - 1) * pixelsPerCell;
  const yNorth = mercY(north), ySouth = mercY(south);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(width, height);
  for (let py = 0; py < height; py++) {
    const lat = latFromMercY(yNorth - ((py + 0.5) / height) * (yNorth - ySouth));
    const gy = (lat - lat0) / stepLat;
    for (let px = 0; px < width; px++) {
      const gx = (px + 0.5) / pixelsPerCell;
      const weight = sample(weightSum, cols, rows, gx, gy);
      let value, alpha;
      if (fill) {
        // Blend from the normal smoothing to the wide one as data runs out.
        const wideWeight = sample(wideWeightSum, cols, rows, gx, gy);
        if (wideWeight < 1e-4) continue;
        const wideValue = sample(wideValueSum, cols, rows, gx, gy) / wideWeight;
        const t = smoothstep(0.05, 0.3, weight);
        value = t > 0 ? t * (sample(valueSum, cols, rows, gx, gy) / Math.max(weight, 1e-6)) + (1 - t) * wideValue : wideValue;
        alpha = 1;
      } else {
        if (weight < 0.05) continue;
        value = sample(valueSum, cols, rows, gx, gy) / weight;
        // Full color everywhere people live, right up to the shoreline (the
        // image is cut to it below). Only where most nearby land is park
        // (cells with no value), such as a highway strip running through a
        // park, does the color drop out.
        const land = sample(landSum, cols, rows, gx, gy);
        alpha = smoothstep(0.25, 0.4, weight / land);
      }
      const color = colorFor(value);
      if (!color) continue;
      alpha *= color[3];
      const i = (py * width + px) * 4;
      image.data[i] = color[0];
      image.data[i + 1] = color[1];
      image.data[i + 2] = color[2];
      image.data[i + 3] = Math.round(alpha * 255);
    }
  }
  ctx.putImageData(image, 0, 0);

  // Cut to the shoreline: draw the land outlines as a clipping path, then
  // the image through it. Then erase the parks and lakes.
  const clipped = document.createElement("canvas");
  clipped.width = width;
  clipped.height = height;
  const clipCtx = clipped.getContext("2d");
  // Only outlines whose bounding box overlaps the image; the city has
  // thousands. (Checking for a corner inside the image isn't enough: zoomed
  // into the middle of Queens, none of its outline's corners are in view.)
  const near = (ring) => {
    let s = Infinity, n = -Infinity, w = Infinity, e = -Infinity;
    for (const [lat, lng] of ring) {
      if (lat < s) s = lat;
      if (lat > n) n = lat;
      if (lng < w) w = lng;
      if (lng > e) e = lng;
    }
    return s <= north && n >= south && w <= east && e >= west;
  };
  const trace = (rings) => {
    clipCtx.beginPath();
    for (const ring of rings.filter(near)) {
      ring.forEach(([lat, lng], k) => {
        const x = ((lng - west) / (east - west)) * width;
        const y = ((yNorth - mercY(lat)) / (yNorth - ySouth)) * height;
        if (k === 0) clipCtx.moveTo(x, y);
        else clipCtx.lineTo(x, y);
      });
      clipCtx.closePath();
    }
  };
  trace(land);
  clipCtx.clip();
  clipCtx.drawImage(canvas, 0, 0);
  if (blank.length) {
    clipCtx.globalCompositeOperation = "destination-out"; // drawing erases
    trace(blank);
    clipCtx.fill("nonzero");
  }

  return {
    url: clipped.toDataURL(),
    bounds: [
      [south, west],
      [north, east],
    ],
  };
}
