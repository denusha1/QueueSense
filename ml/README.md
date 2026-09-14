# Waiting-time model

Run `python ml/src/train.py` from the repository root after generating the dataset and installing backend dependencies. Fixed random seed: 42. The pipeline replays arrivals, starts, completions and schedule intervals to construct only information available at each prediction time. Final service durations enter rolling features only after their completion event has occurred. Queue departures enter the replay at service start or cancellation/no-show end. No final timestamps are direct model features.

Features: department, waiting/called patients ahead, active scheduled staff, last 30 completed service durations, arrivals during the prior 30 minutes, local hour and weekday. Live inference uses present availability instead of historical schedules; this is a documented source of distribution shift. Historical training uses all-standard FIFO synthetic visits, not priority/clinical triage.

Splits use entire calendar dates: first 60% training, next 20% validation, last 20% test. Candidates are a queue-rate baseline, linear Ridge regression, Random Forest and Gradient Boosting. Selection uses validation MAE. Only the selected model refits the combined training/validation interval before final test evaluation. The final test set is not used to select models or hyperparameters.

`evaluation/results.json` contains split dates, row counts, validation comparisons, test MAE/RMSE/R², error by department/hour and actual/predicted samples. `artifacts/wait_model.joblib` is a repository-owned artifact; do not load joblib files from untrusted uploads. The API loads this artifact once per process. Re-train with a new version and restart API to adopt a replacement model; preserve prior artifacts when versioning deployed predictions.

Current synthetic test result: Random Forest MAE 7.1038 minutes, RMSE 14.0474, R² 0.8730. Operational baseline MAE 9.6164 minutes. These results describe this synthetic generator, not a real clinic or clinical outcome. No confidence interval or guaranteed service time is claimed. No-staff situations return an unavailable estimate rather than a fabricated wait.
