# Navigator web UI

Vite + React + TypeScript, Tailwind v4, shadcn/ui (Base UI), @assistant-ui/react.

## Run

Backend (from the repo root; fake mode spends no Gemini quota):

    COPILOT_FAKE=1 python3 -m uvicorn server:app --port 8000

For real answers, set `GEMINI_API_KEY` (env or `.env`) and omit `COPILOT_FAKE`.

Frontend (from `web/`):

    npm install
    npm run dev      # http://localhost:5173, proxies /api to localhost:8000
    npm run build    # type-check and production build

Review decisions are written by the backend to `outputs/audit_log.csv` and `outputs/e_drafts.json`.
