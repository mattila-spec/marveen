# Update startup health budget

Both updater health paths allow 120 HTTP probes, one second apart; each request
has a three-second timeout. This accommodates startup inventory of a large
store. HTTP success remains mandatory; an exhausted budget still rolls back.

A finalizer failure is reported in `store/update.last-result`. Its application
verdict does not trigger the systemd launch fallback and a second finalizer.

Regression: `python3 scripts/__tests__/update-startup-budget.test.py`.
