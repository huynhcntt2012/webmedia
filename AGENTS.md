# Suni AI Cinema

User requires sequential delivery across the 12 stages in `docs/ROADMAP.md`.
Read the current acceptance record before changing scope. Do not claim a stage
accepted while required integration tests have not run. Do not start the next
stage until the preceding acceptance gate passes, except the user's explicit
2026-10-10 instruction to implement stages 11 and 12 before returning to stage 10.

- Current stage: 12 local code/tests complete, accepted 2026-10-11; external production acceptance deferred. User explicitly deferred deployment on 2026-10-11: do not connect SSH or deploy; complete local code and tests. Stage 11 accepted 2026-10-11 based on completed integration/E2E evidence. Stage 10 local implementation/tests complete; full acceptance pending real SePay sandbox E2E. Stages 04–09 accepted on 2026-10-10; stages 01–03 on 2026-10-09.
  User keeps VIP/Premium draft; sample prices only in isolated tests. Real SePay sandbox acceptance awaits credentials/endpoint. Do not mark stage 10 accepted by this exception.
- Every stage needs a migration decision (including an explicit no-op when appropriate),
  unit/integration tests, security checks and an acceptance record.
- Keep secrets out of source and logs. `.env` is local and must never be committed.
- Run migrations/rollback tests only against the isolated Compose test project.
- Do not use SQLite/mocks as evidence that PostgreSQL/Redis/Celery integration passed.
- Treat Compose development configuration as local-only. Production needs stage 12 review.
- Run relevant tests after changes. Frontend E2E uses the built standalone server.
- Record environment blockers honestly; Docker runtime tests cannot pass on YAML parsing alone.
