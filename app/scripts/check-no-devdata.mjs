/**
 * Refuse to build while development data is present.
 *
 * tools/dev_seed.py writes into app/public/data/, and Vite copies everything
 * in public/ into the bundle. Without this guard a build made on a developer
 * machine would ship invented fixtures and a retroactive track record as
 * though they were real forecasts. That is the single worst thing this
 * project could publish, so it is a hard failure rather than a warning.
 */
import { existsSync, readdirSync } from "node:fs"
import { resolve, dirname } from "node:path"
import { fileURLToPath } from "node:url"

const dir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "public", "data")

if (existsSync(dir) && readdirSync(dir).length > 0) {
  console.error(`
BUILD REFUSED: development data is present.

  ${dir}
  contains: ${readdirSync(dir).join(", ")}

This directory is written by tools/dev_seed.py. Its forecasts are real model
output, but the fixture list is invented and the track record is retroactive.
Shipping it would present made-up matches as genuine forecasts.

Delete it and build again:

  rm -rf app/public/data
`)
  process.exit(1)
}
