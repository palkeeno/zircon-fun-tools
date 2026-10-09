# Community tools improvement audit

Base: latest `origin/main` at `435a375` (including the target-guild synchronization fix). Uncommitted changes in the user's original checkout are excluded.

| Requested requirement | Implementation | Evidence |
|---|---|---|
| Required quote fields | quote_records.normalize; atomic rejection of invalid bulk imports | QuoteValidationTests; test_invalid_bulk_update_preserves_memory_and_disk |
| Working /help | cogs/help.py builds paginated help from loaded commands | test_help_lists_every_loaded_command_and_can_page (real command schema serialization) |
| Quote pagination | cogs/pagination.py; all list/search records accessible | test_id_and_character_search_and_pagination |
| Quote ID / character ID search | all four fields in Quotes._handle_search | test_id_and_character_search_and_pagination |
| Preserve quote IDs and creation history | merge_records matches explicit ID, then unique content; preserves creation metadata | test_identity_and_creation_history_survive_import_and_edit; legacy migration tests |
| Validate records on load | quote/birthday validators; rejected-row reports; preserve malformed source | quote read-validation tests; birthday invalid-read test |
| Individual add/edit/delete | quote_add/edit/delete and birthday_add/edit/delete; explicit delete confirmation | CRUD tests and actual application-command schema |
| Birthday today/month/upcoming | birthday mode choices; Japan time; year rollover and leap-year handling | test_today_month_upcoming_year_boundary_and_leap_day; actual command test |
| Text-only birthday fallback | image errors fall back to Embed without file; success flag follows Discord send | test_image_failure_sends_text_and_marks_reported_only_after_send; existing failed-send tests |
| Exclude lottery invoker | already present in main (#3), preserved in this PR | test_lottery_excludes_invoker_and_bots |
| /remove-role without deletion | authoritative member enumeration, permission/hierarchy checks, owner confirmation, per-member atomic removal, partial-failure counts | RoleTests; no role.delete calls |
| Bounded poster queue/concurrency | FIFO queue, configurable workers, duplicate request coalescing, bounded wait, shutdown waits for threads | PosterQueueTests |
| Character info/completed image cache | TTL disk caches, corruption recovery, bounded disk count, layout/assets/fonts key | CacheFeatureTests; actual 1600×2100 PNG composition in existing tests |
| Prepare Japanese fonts | explicit setup_fonts.py --prepare; generation only loads local validated fonts | test_prepared_font_is_loaded_without_network; installer calls preparation |
| Correct Python version docs | Python 3.10+ / recommended 3.12 | README, EC2_SETUP, requirements; 3.10/3.12 CI matrix |
| Meaningful regression tests | actual data writes/reloads, failure recovery, commands/buttons, concurrency and cache reuse | test_features.py, test_monitoring.py and existing regression suite |
| Isolate tests from settings/data | bootstrap overrides env file and storage before application imports; temporary-copy runner | runner and direct unittest both pass; env-file subprocess tests |
| Common slash-command errors | command_errors.send_error; Bot tree handler; component errors reuse handler | test_error_initial_deferred_and_permission_responses |
| Unified supervision | systemd only; old supervisors disabled; CLI wrappers delegate; rendered-unit installer | MonitoringTests with fake system commands; Bash syntax checks |

## Verification

- Windows / Python 3.11: 106 tests pass through `python test/run_tests.py`.
- Direct `python -m unittest discover test`: same suite, disposable configuration and data.
- Bash syntax checks for scripts; installer exercised with fake sudo/systemctl/crontab, including a path containing spaces and `%` and a legacy-PID refusal.
- CI: Windows/Ubuntu and Python 3.10/3.12 (results must be checked on the PR head).

No production service was changed. Real Discord delivery, live role changes and the current official character site are outside the local test evidence. systemd migration requires stopping old supervisors before the documented installer is run.

## Review fixes

- Block quote CRUD after rejected rows are detected, until a validated explicit full replacement succeeds; failed replacement preserves the guard.
- Include dynamically selected country-flag assets in the completed-poster cache fingerprint (additions, replacement, deletion).
- Finish shutdown even if an in-flight poster thread fails during cancellation.

Each path has an executable regression test in test_features.py.

- Enforce birthday character-ID uniqueness for additions and bulk replacements. Retain legacy same-day duplicates on load and collapse them during individual edits; reject conflicting dates on load.
- Recheck pending birthdays even after today was marked complete, retaining sent flags through bulk replacement to avoid duplicate celebrations.

- Check metadata TTL before accepting completed PNGs and include metadata content in the image key; a near-expiry asset change cannot extend stale fields beyond their TTL.
- Explicitly restart the service after reinstalling its unit; the fake-command installer test covers repeated installation.

- Route default image assets and dynamic country flags through the isolated data directory, so direct unittest execution cannot read the original checkout assets.

- Render WorkingDirectory as an unquoted literal absolute path, escaping unit specifiers separately from ExecStart arguments. Linux CI now validates the rendered service with systemd-analyze verify.

- Permit birthday CRUD when multiple legacy duplicate groups exist: normalize preserved same-date groups on mutation, retain any successful notification flag, and still reject newly introduced duplicates. Original rows are kept in the atomic-write backup.

- Key loaded font objects by resolved path, requested size, mtime and file size, matching poster fingerprints. A replacement-font regression checks fresh rendering and reuse after restart.
