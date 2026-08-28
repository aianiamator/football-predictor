# The app

Mobile-first PWA. Read-only, no accounts, no API keys — it fetches three static
JSON files and nothing else.

## Run it

```bash
npm install --prefix app
python -m tools.dev_seed      # dev data, since the live feed is empty off-season
npm run dev --prefix app      # http://localhost:5178
```

`tools/dev_seed.py` writes into `app/public/data/`, which is gitignored. It is
**development data only** — the forecasts are genuine model output but the
fixture list is constructed. Never serve it to users.

## Build and deploy

```bash
VITE_DATA_URL=https://your-cdn.example.com npm run build --prefix app
```

`VITE_DATA_URL` is the base URL of the published JSON. It defaults to `/data`,
which works when the app and the engine output are served from the same origin —
the simplest deployment, and the one I would pick.

Upload `app/dist/` and the engine's `output/` directory to Cloudflare.

## Why the app is this small

| | gzipped |
|---|---|
| JS | 17.1 KB |
| CSS | 3.0 KB |
| HTML | 0.5 KB |
| **Total shell** | **~20.6 KB** |
| Data on first load | ~6 KB |

Three decisions got it there, all of them because the audience pays for every
megabyte:

- **React is aliased to `preact/compat`** in `vite.config.ts`. Same JSX, same
  hooks, same imports — 40 KB smaller. Delete the alias and it runs on React
  unchanged.
- **No router, no icon library, no web fonts, no images.** Navigation is state
  plus the History API, icons are inline SVG, type is the system stack, and
  team badges are a coloured circle with a letter.
- **Cache-first loading.** Saved data renders on the first paint; the network
  only refreshes it. A reader on a dead connection still sees the last
  forecasts they downloaded, with an honest banner saying so.

## Structure

```
src/
  App.tsx              shell, navigation, data loading
  api.ts               fetch + localStorage cache, never throws
  i18n.ts              all interface text, five languages
  types.ts             mirrors what engine/store.py publishes
  components/
    ThreeWayBar.tsx    the one that matters - read the docstring first
    MatchCard.tsx      list row
    ...
  screens/
    Matches.tsx        home
    MatchDetail.tsx    one match, larger
    TrackRecord.tsx    hits and misses, never filtered
```

## Adding a language

Add the code to `Lang`, add an entry to `LANGS`, add one block to `STRINGS` in
`src/i18n.ts`. TypeScript will list anything you missed. Nothing else changes.

The engine publishes `summary_key` and `summary_args`, not an English sentence —
so translating a forecast is a template lookup, never parsing prose.

> The Yorùbá, Hausa, Igbo and Pidgin strings need a native speaker's review
> before launch. They are careful, not authoritative.

## Constraints this app is built to

Enforced, not aspirational — see `../CLAUDE.md` for the full list.

- Every screen readable with the text removed: colour, size, shape, position first
- Body text ≥18px, tap targets ≥56px (verified: 73 buttons, none smaller)
- No dropdowns, no modals, no hamburger, no horizontal page scrolling
- Two taps maximum to reach anything
- The words *bet, odds, tip, sure, guaranteed* and friends appear nowhere
- Never *probability*, *expected goals*, *model*, or *algorithm* in the interface
- The track record is never hidden or filtered; misses render as prominently as hits
- The permanent footer appears on every screen
