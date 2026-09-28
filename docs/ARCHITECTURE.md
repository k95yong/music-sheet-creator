# Architecture

## Overview

Music Sheet Creator is a local-first two-process application:

```text
MIDI device -> Windows MIDI bridge -> Server-Sent Events -> browser note model
                                                       |-> piano score
                                                       |-> guitar TAB
                                                       |-> MusicXML / PDF
Backing audio -> Web Audio mix bus -> local recording API
```

The Python process serves static files and a small JSON/file API. The browser owns timing, synthesis, score editing, rendering, MusicXML conversion, and PDF generation.

## Shared score model

`quantizedScore` is the authoritative in-memory score. Each note contains:

- `n`: MIDI pitch
- `v`: velocity
- `startQ`: start position in quarter-note units
- `durQ`: duration in quarter-note units
- `tabString` and `tabFret`: optional player-selected TAB position

The piano and TAB renderers consume the same array. Changing pitch therefore updates both views. Moving a TAB note between strings changes only `tabString`/`tabFret` and verifies that the resulting fret represents the same MIDI pitch.

## Persistence

The workspace root is configured by `MUSIC_SHEET_WORKSPACE`. The server creates `config/` and `01_Projects/` below it. Project metadata and memo content are JSON; binary and notation assets remain regular files in their project folders.

MusicXML TAB exports include `<technical><string>` and `<fret>` elements. The importer restores those values so manual fingering survives a save/load cycle.

## PDF generation

The browser builds a small PDF 1.4 document directly from `quantizedScore`. Piano and TAB use separate render paths and are saved independently through the score upload API. PDFs use A4 landscape pages with four measures per row and three rows per page.

## Security boundary

- The service listens on loopback only.
- Project identifiers and filenames are normalized before filesystem access.
- Upload sizes are bounded.
- No remote persistence or analytics are used.

