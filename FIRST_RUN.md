# FIRST RUN — exact laptop steps

Prerequisites: Docker Desktop (or Docker Engine + Compose v2) and Node 20+ if
you want to run the frontend tests outside Docker.

## 1. Put the files in your repo
```bash
# from the unzipped folder
cp -R aureus-mvp/. /path/to/your/repo/    # or unzip directly into the repo
cd /path/to/your/repo
```

## 2. Create your env file
```bash
cp .env.example .env
# optionally edit ADMIN_PASSWORD, SECRET_KEY
```

## 3. Bring up the stack (migrations + seed run automatically)
```bash
docker compose up -d --build
```
Wait ~30s on first build. Then:
- API health:  http://localhost:8000/api/health  -> {"trading_mode":"paper"}
- API docs:    http://localhost:8000/api/docs
- Frontend:    http://localhost:5173  (login: admin@local / admin)

## 4. Frontend deps (only if running tests/build locally, outside Docker)
```bash
cd frontend
npm install
npm run test     # ARM LIVE + kill switch tests
npm run build    # type-check + production bundle
cd ..
```

## 5. Run full verification
```bash
make verify-phase15
```
This runs the backend safety gate, the full backend suite, the frontend tests
and build, smoke checks, and the env-level hard-stop proof. It prints
`PHASE 15 PASS` only if everything actually passes.

## 6. Commit and push
```bash
git add .
git commit -m "Add AUREUS MVP: paper-safe gold trading platform with verification"
git push
```

## Troubleshooting
- Port already in use: change BACKEND_PORT / FRONTEND_PORT / POSTGRES_PORT in .env.
- `make verify-phase15` step 1 hangs: first Docker build can be slow; the script
  waits up to 60s for backend health. Re-run if your image pull was slow.
- Frontend test step: if `npm install` is slow in the script, run it once
  manually in `frontend/` first.
