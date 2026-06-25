# Development Checklist

## 1. Before Starting a Change

- [ ] Define the exact goal in one or two sentences.
- [ ] Identify affected layers: backend, API, Web UI, extraction, storage,
  export, configuration, tests or docs.
- [ ] Check `git status --short` before editing.
- [ ] Keep unrelated existing changes separate from the current change.
- [ ] Confirm whether the change is MVP scope, UI polish or post-MVP work.
- [ ] Stop before introducing new dependencies, runtime services, public
  behavior or architecture decisions without explicit approval.
- [ ] Do not treat reports or old planning notes as source of truth.

## 2. Before Creating a Codex Task

- [ ] Make the task narrow and outcome-based.
- [ ] Define in-scope files, layers and expected behavior.
- [ ] Define non-goals and forbidden areas.
- [ ] State validation commands expected for the change.
- [ ] State manual checks when UI, provider, storage, export, preview/delete or
  retention behavior is affected.
- [ ] Call out whether real-provider smoke is allowed or forbidden.
- [ ] Forbid broad scope creep and unrelated cleanup.

## 3. Backend/API Changes

- [ ] Preserve application facade boundaries.
- [ ] Keep FastAPI routes thin: parse HTTP input, call the facade, map response.
- [ ] Do not put DB, storage, provider or export ownership directly in HTTP
  routes unless the design is explicitly changed.
- [ ] Update API tests for endpoint behavior, status codes and response shape.
- [ ] Check error mapping for safe, user-facing messages.
- [ ] Do not leak secrets, provider internals, local paths or raw debug payloads.
- [ ] Keep backend validation as the gate for external/model/provider output.

## 4. Web UI Changes

- [ ] Verify the Web UI still works under `/app`.
- [ ] Do not hardcode `localhost`; use relative backend endpoints.
- [ ] Keep user-facing UI copy in Russian.
- [ ] Preserve upload, polling, history and selected-file state.
- [ ] Preserve preview, delete, Markdown and PDF flows.
- [ ] Avoid presenting raw/sanitized JSON as a user-facing UI surface.
- [ ] Run a manual browser check for visible UI changes when browser tools are
  available.
- [ ] Do not claim full PDF input support unless backend behavior is explicitly
  implemented and tested.

## 5. Extraction / Provider Changes

- [ ] Justify prompt, schema or model-policy changes narrowly.
- [ ] Preserve the structured output contract expected by backend validation.
- [ ] Treat provider output as untrusted until backend validation succeeds.
- [ ] Do not run casual external provider calls during routine development.
- [ ] Keep real-provider smoke explicit, manual and env-gated.
- [ ] Remember that provider classification and field grouping may vary.
- [ ] Preserve Stage 21 table-derived values behavior when changing field/table
  extraction or result shaping.
- [ ] Do not add hidden fallback from a failed real provider to the fake provider.

## 6. Export Changes

- [ ] Treat Markdown and PDF as user-facing outputs.
- [ ] Keep default exports readable: summary, warnings, values, tables and text.
- [ ] Do not expose `Extraction Metadata` in default user-facing exports.
- [ ] Do not expose provider/model/job/attempt debug metadata.
- [ ] Do not expose raw provider response, sanitized provider response, secrets
  or local paths.
- [ ] Update Markdown/PDF export tests when export shape changes.
- [ ] Manually check downloaded Markdown/PDF files when export behavior changes.

## 7. Storage / Preview / Delete / Retention Changes

- [ ] Keep preview behind the backend safe endpoint.
- [ ] Do not expose raw/sanitized/debug artifacts as user-facing UI downloads.
- [ ] Guard against path traversal, absolute paths, drive prefixes and unsafe
  storage roots.
- [ ] Ensure delete cannot remove files outside configured upload/result roots.
- [ ] Preserve safe cleanup behavior for upload and result directories.
- [ ] Keep retention wording accurate: default is 7 days through callable cleanup,
  not scheduled cron/background cleanup.
- [ ] Update storage, application and API tests when storage, preview, delete or
  retention behavior changes.

## 8. Configuration and Secrets

- [ ] Use local `.env` for local settings.
- [ ] Never commit `.env`, API keys, tokens, local credentials or generated
  runtime artifacts.
- [ ] Update `.env.example` when adding or renaming config variables.
- [ ] Treat OpenRouter and ImgBB keys as sensitive.
- [ ] Do not put secret values in reports, docs, tests, fixtures or screenshots.
- [ ] Do not put local absolute paths in user-facing responses or exports.
- [ ] Keep runtime configuration in settings/environment, not hidden constants.

## 9. Validation Commands

Run the relevant subset for the change. For code, tests, config or behavior
changes, use the full set:

```powershell
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

- [ ] Confirm default pytest does not call real external providers.
- [ ] Skip broad code validation only for docs-only changes, and state why.
- [ ] Always check `git status --short` before handoff.

## 10. Manual Smoke Checklist

For UI/API/export/storage changes, run a local smoke check:

- [ ] Start the app.
- [ ] Open `/app`.
- [ ] Upload an image.
- [ ] Wait for the result.
- [ ] Check preview.
- [ ] Check values, tables and text.
- [ ] Copy or download Markdown.
- [ ] Download PDF.
- [ ] Delete the job.
- [ ] Confirm the job disappears from the list.
- [ ] Check for obvious console-visible UI errors when browser tools are
  available.

## 11. Before Commit

- [ ] Review `git status --short`.
- [ ] Review the staged diff, not only the working tree diff.
- [ ] Commit one coherent change at a time.
- [ ] Do not commit ignored local reports, plans or tasks unless intentionally
  tracking them.
- [ ] Do not commit `data/`, `.env`, provider artifacts, generated outputs or
  temporary files unless the task explicitly requires them.
- [ ] Do not include unrelated refactors or formatting churn.
- [ ] Do not commit secrets or local credentials.

## 12. Documentation Updates

- [ ] Update `README.md` for run commands, configuration or user-facing behavior
  changes.
- [ ] Update `docs/PROJECT_CONTEXT.md` for accepted architecture, scope or MVP
  baseline decisions.
- [ ] Update `docs/LLM_MODEL_POLICY.md` for provider, model, prompt, schema or
  media staging policy changes.
- [ ] Update `docs/PROJECT_MAP.md` when public files, layers, ownership
  boundaries or major surfaces are added, removed or renamed.
- [ ] Keep docs aligned with current code and accepted project decisions.
- [ ] Remove or rewrite stale claims when behavior changes.
- [ ] Avoid documenting production deployment, auth, scheduled cleanup, generic
  artifact explorer, raw/sanitized JSON UI or full PDF extraction input unless
  those capabilities are explicitly implemented and accepted.
