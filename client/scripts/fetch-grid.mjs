// Puts the city grid (card 15) into public/grid/, where the site serves it
// itself, so the score map and gap finder work even while the API sleeps.
// Runs before `npm run dev` and `npm run build` (see package.json).
//
// The grid files are part of the map data release named in
// server/data-release.json (see server/scripts/get_data.py). For each
// borough's file, this uses the copy in server/data/ when it matches the
// release's fingerprint, and downloads it from the release otherwise. Each
// file is saved under a name that includes its fingerprint, so browsers can
// keep it for good; public/grid/index.json says which name each borough has.

import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const CLIENT = join(dirname(fileURLToPath(import.meta.url)), "..");
const RELEASE_FILE = join(CLIENT, "..", "server", "data-release.json");
const SERVER_DATA = join(CLIENT, "..", "server", "data");
const OUT = join(CLIENT, "public", "grid");
const FILES = join(OUT, "files");
const REPO = process.env.GITHUB_REPOSITORY || "Shen-42/nyc-15min";

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

async function download(url) {
  for (let attempt = 0; ; attempt++) {
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return Buffer.from(await res.arrayBuffer());
    } catch (err) {
      if (attempt === 3) throw err;
      const wait = 5 * 2 ** attempt;
      console.log(`  ${err.message}. Trying again in ${wait} s`);
      await new Promise((r) => setTimeout(r, wait * 1000));
    }
  }
}

async function main() {
  mkdirSync(FILES, { recursive: true });
  if (!existsSync(RELEASE_FILE)) {
    console.log("No server/data-release.json, so no grid for the score map.");
    writeFileSync(join(OUT, "index.json"), JSON.stringify({ files: {} }));
    return;
  }
  const release = JSON.parse(readFileSync(RELEASE_FILE, "utf8"));
  const grids = Object.entries(release.files).filter(([name]) => /^grid-[a-z-]+\.json$/.test(name));
  if (!grids.length) {
    console.log(`Release ${release.tag} has no grid files yet, so no grid for the score map.`);
    writeFileSync(join(OUT, "index.json"), JSON.stringify({ tag: release.tag, files: {} }));
    return;
  }

  const index = { tag: release.tag, files: {} };
  for (const [name, { sha256: want }] of grids) {
    const slug = name.slice("grid-".length, -".json".length);
    const saved = `grid-${slug}.${want.slice(0, 12)}.json`;
    index.files[slug] = `files/${saved}`;
    if (existsSync(join(FILES, saved))) continue; // same name, same contents

    const local = join(SERVER_DATA, name);
    let bytes = existsSync(local) ? readFileSync(local) : null;
    if (!bytes || sha256(bytes) !== want) {
      console.log(`Downloading ${name} from release ${release.tag}`);
      bytes = await download(`https://github.com/${REPO}/releases/download/${release.tag}/${name}`);
    }
    if (sha256(bytes) !== want) throw new Error(`${name} doesn't match its fingerprint in data-release.json.`);
    writeFileSync(join(FILES, saved), bytes);
  }

  // Remove grid files from older releases.
  const keep = new Set(Object.values(index.files).map((p) => p.slice("files/".length)));
  for (const old of readdirSync(FILES)) if (!keep.has(old)) unlinkSync(join(FILES, old));

  writeFileSync(join(OUT, "index.json"), JSON.stringify(index));
  console.log(`Grid for the score map: ${Object.keys(index.files).length} boroughs from release ${release.tag}`);
}

main().catch((err) => {
  console.error(`Couldn't get the grid: ${err.message}`);
  process.exit(1);
});
