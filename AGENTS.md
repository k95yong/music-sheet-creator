# AGENTS.md

## Scope

These instructions apply to the entire repository.

## Product invariants

- Piano notation and guitar TAB must always derive from the same `quantizedScore` note model.
- Pitch edits must update both views. TAB-only string changes must preserve MIDI pitch.
- Imported TAB string/fret positions must survive export and re-import.
- Keep all project data local. Do not add telemetry, analytics, or remote uploads.
- The HTTP server must remain bound to `127.0.0.1` by default.
- Preserve undo support for every destructive score-editing operation.

## Code organization

- `app/index.html` contains the dependency-free client application.
- `app/workspace_server.pyw` contains the local API, file storage, and Windows MIDI bridge.
- `scripts/` contains launch or maintenance commands.
- `docs/` contains design and behavior documentation.
- Do not commit user workspaces, recordings, generated scores, downloads, caches, or machine-specific paths.

## Change workflow

1. Run `node --check` against the JavaScript extracted from `app/index.html`.
2. Run `python -m py_compile app/workspace_server.pyw` on Windows.
3. Exercise MusicXML import, linked pitch editing, TAB string movement, undo, and export after score-model changes.
4. For PDF changes, generate both variants, parse each PDF, render every page, and visually inspect the PNG output.
5. Confirm no absolute user path or personal project title is present before committing.

## Style

- Keep the app dependency-free unless a dependency materially improves notation correctness.
- Prefer small named functions over adding more behavior to existing one-line handlers.
- Use Korean for end-user interface text and clear English for repository documentation and code identifiers.
- Maintain keyboard accessibility alongside pointer interactions.

