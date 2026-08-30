/**
 * Fold the engine's published JSON into the built site.
 *
 * Written in Node rather than a shell loop because npm runs scripts through
 * cmd.exe on Windows, where `for f in ...; do` is a syntax error. The build
 * has to work on a developer's laptop and on Cloudflare's Linux builders.
 *
 * When output/ is absent - which is the normal case on a fresh clone, since it
 * is generated, not committed - each file is written as a valid EMPTY document
 * of the right shape. An empty array where the app expects an object would
 * crash it, so the shapes matter.
 */
import { mkdirSync, copyFileSync, writeFileSync, existsSync } from "node:fs"
import { resolve, dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const here = dirname(fileURLToPath(import.meta.url))
const src = resolve(here, "..", "..", "output")
const dest = resolve(here, "..", "dist", "data")

const EMPTY = {
  "predictions.json": [],
  "track-record.json": { overall: { matches_settled: 0, accuracy_pct: null }, by_league: [], recent: [], awaiting: [], awaiting_total: 0 },
  "meta.json": { published_at: null, upcoming: 0, settled: 0, awaiting: 0, leagues: [] },
}

mkdirSync(dest, { recursive: true })

for (const name of Object.keys(EMPTY)) {
  const from = join(src, name)
  if (existsSync(from)) {
    copyFileSync(from, join(dest, name))
    console.log(`  ${name}: copied from output/`)
  } else {
    writeFileSync(join(dest, name), JSON.stringify(EMPTY[name]), "utf8")
    console.log(`  ${name}: not generated yet, wrote empty placeholder`)
  }
}
