# Rintel Scoring API (private backend)

The proprietary scoring engine runs here and only here. Never commit this repo
public; never ship the engine to the frontend or to a Supabase function.

## Endpoints
- `GET  /health`
- `POST /api/score`         body `{"transactions":[...]}` or `{"demo":true,"profile":"merchant|salaried|stressed|hidden"}`
- `POST /api/score/upload`  multipart `file=<pdf>` (501 until the Task-2 parser lands)

All `/api/*` calls require header `X-API-Key: <RINTEL_API_KEY>`.

## Run locally
    pip install -r requirements.txt
    RINTEL_API_KEY=testkey python app.py
    curl -s localhost:8000/api/score -H "X-API-Key: testkey" \
         -H "Content-Type: application/json" -d '{"demo":true,"profile":"hidden"}'

## Deploy to Railway
1. Push this folder to a PRIVATE GitHub repo.
2. Railway -> New Project -> Deploy from repo.
3. Variables: `RINTEL_API_KEY` (long random string), `ALLOWED_ORIGIN` (your Lovable URL).
4. Railway uses the Procfile (gunicorn). Copy the public URL -> that's your API base.

## Files
- `app.py`                  API + presentation (consumer-safe output)
- `rintel_scoring_engine.py`THE IP — scoring engine (server-side only)
- `normalize.py`            raw data -> engine schema; `parse_pdf` is the Task-2 seam
- `demo_profiles.py`        synthetic borrowers for demo mode
