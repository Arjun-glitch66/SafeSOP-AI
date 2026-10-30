# SafeSOP-AI frontend

React 19 + Vite single-page app for the SafeSOP-AI revision workflow: upload an SOP PDF,
describe a change, generate a draft with Gemini (via the FastAPI backend), inspect the
automated safety-regression checks, compare the draft with the original, and record a
human review decision.

## Run

```bash
npm ci
npm run dev      # http://localhost:5173
npm run build    # production build into dist/
npm run lint     # oxlint
```

The backend must be running (see the repository README). By default the app calls
`http://127.0.0.1:8000`; set `VITE_API_BASE` in `frontend/.env.local` to point elsewhere.
The backend only accepts requests from origins listed in its `ALLOWED_ORIGINS` setting.

## Layout

| Path | Purpose |
|------|---------|
| `src/App.jsx` | Shell, navigation and all shared state, passed to pages as one `app` object |
| `src/api.js` | Every backend call |
| `src/pages/` | One component per view: Overview, Documents, Revision Studio, Safety & Quality, Version History |
| `src/components/` | Diff view, evaluation report, small UI pieces, status labels |
| `src/index.css` | All styles (plain CSS with design tokens on `:root`) |

## Wording rules

The UI never calls a draft "safe". A draft with no findings is shown as "No rule fired", and
every draft is labelled as not approved until a named reviewer approves it.
