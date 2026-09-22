# Contributing

## Before opening a pull request

Run the relevant checks locally:

```bash
python -m compileall -q backend/app
PYTHONPATH=backend pytest -q backend/tests
cd frontend && npm install && npm run build
```

Keep tax/reference data separate from application logic. Changes to risk rules should include tests and clearly state whether the change is a documentation flag or a legal/tax determination. The latter is intentionally outside this application's automated scope.

Never add real taxpayer data, credentials, production exports or confidential documents to the repository.
