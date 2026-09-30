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

Sustained MusicXML ties are merged into one model note. The editable renderers derive measure-local display segments without changing the source note identity. Both notation exports use one writer, include continuation ties and TAB fingering, and preserve overlapping durations using MusicXML backup/forward elements.

## Score playback and controls

All scores use the same playback controller. With backing enabled, the audio element's current time is the clock for piano note scheduling and both playheads, so seeking and playback-rate changes stay aligned. Without backing, a monotonic clock plays the score alone. Tempo and meter are locked during a score session. Starting a new recording clears the old playback session and captures its own audio start position.

The score's audio start position uses original-speed seconds and is saved in the MusicXML miscellaneous field `audio-offset-seconds`; files without it start at zero. There is no filename-specific playback behavior.

The score toolbar separates listening/mixing, quantization, editing, and export. Piano gain and backing volume are independent. Additional per-measure recording/pitch-input tools live in an expandable section.

Run `node scripts/check-score.js` for dependency-free score display, sustained-tie, export, fingering, and overlapping-duration regression checks.

## PDF generation

The browser builds a small PDF 1.4 document directly from `quantizedScore`. Piano and TAB use separate render paths and are saved independently through the score upload API. PDFs use A4 landscape pages with four measures per row and three rows per page.

## Security boundary

- The service listens on loopback only.
- Project identifiers and filenames are normalized before filesystem access.
- Upload sizes are bounded.
- No remote persistence or analytics are used.
- Score removal validates a direct child of the transcription folder and sends it to the Windows Recycle Bin. A failed recycle operation never falls back to permanent deletion.
