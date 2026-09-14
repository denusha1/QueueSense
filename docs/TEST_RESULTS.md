# Local verification results

- Native PostgreSQL 17.10: all five migrations applied; unchanged migration re-run passed; full synthetic seed loaded.
- Database integrity: 11 invalid writes rejected; valid queue lifecycle and rollback verified.
- API/model suite: 20 passed. Two dependency deprecation warnings in the test client; no failing tests.
- Generator suite: seven tests covering reproducibility, seed sensitivity, FIFO/lunch behavior, non-overlap/schedules, references/timestamps, summary parity and bounds.
- Browser suite: all 15 product views loaded without application/runtime errors; real UI check-in → call → start → complete; private patient page reflected completion; simulator, import validation and CSV/PDF downloads passed; viewport widths 375/768/1440 had no horizontal document overflow.
- Frontend: optimized Next.js production build and TypeScript checks passed.
- Dependency audit during frontend tooling installation: zero reported vulnerabilities.
- Model test set: MAE 7.1038 minutes; RMSE 14.0474; R² 0.8730. Operational baseline MAE 9.6164. Synthetic holdout only.

Not executed here: Docker build/Compose, hosted CI run, cloud deployment or real-clinic evaluation. No claim of those checks passing is made.
