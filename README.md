# Music Sheet Creator

Windows MIDI keyboard performances can be recorded, quantized, edited as piano notation and guitar TAB, and exported as MusicXML or PDF in a local browser workspace.

## Highlights

- Native Windows MIDI input bridge with browser MIDI fallback
- Backing-track playback, mixed audio recording, pause, seek, and metronome
- Quantization to quarter, eighth, or sixteenth notes
- Linked piano notation and guitar TAB editing
- Note drag, delete, duplicate, octave shift, measure recording, and undo
- TAB controls: `Left/Right` changes pitch by a semitone; `Up/Down` moves across strings while preserving pitch
- MusicXML import/export, including saved TAB string and fret positions
- Separate piano-score and guitar-TAB PDF export
- Project-based local storage for audio, notes, recordings, scores, and deliverables

## Requirements

- Windows 10 or later
- Python 3.10 or later
- A Chromium-based browser is recommended
- Optional: a MIDI keyboard such as the M-Audio Keystation series

No third-party Python packages are required.

## Run

From PowerShell:

```powershell
./scripts/start.ps1
```

The app opens at `http://127.0.0.1:8765/`.

Choose a different workspace or port when needed:

```powershell
./scripts/start.ps1 -Workspace "D:\Music\Sheet Workspace" -Port 9000
```

The default workspace is `%USERPROFILE%\Documents\Music Sheet Creator`. You can also set `MUSIC_SHEET_WORKSPACE` and `MUSIC_SHEET_PORT` directly.

## Keyboard controls

| Context | Key | Action |
| --- | --- | --- |
| Score | `Delete` | Delete selected note or measure |
| Score | `Ctrl+Z` | Undo the last score edit |
| Score | `Space` | Stop score playback |
| Score | `Shift+Up/Down` | Move the selected note, measure, or full score by an octave |
| Guitar TAB | `Left/Right` | Lower or raise the selected note by one semitone |
| Guitar TAB | `Up/Down` | Move the selected note by one guitar string, preserving pitch |

Piano and TAB views share one note model. A pitch edit in either view immediately updates the other view.

## Project data

Each song is stored below `01_Projects/<song name>/`:

```text
01_Reference/       backing tracks
02_Transcription/   MusicXML, PDF, MIDI, and score assets
03_Recordings/      MIDI and mixed audio takes
04_Edits/
05_Mixes/
06_Masters/
07_Artwork/
08_Deliverables/
Notes/              auto-saved memo data
project.json        song metadata
```

The server binds only to `127.0.0.1`. It does not upload project data to an external service.

## Repository layout

```text
app/
  index.html             single-page score editor
  workspace_server.pyw   local HTTP API and Windows MIDI bridge
docs/
  ARCHITECTURE.md        data flow and implementation notes
scripts/
  start.ps1              Windows launcher
AGENTS.md                 contributor and agent guidance
README.md
```

## Notes

- Standard guitar tuning is `E2 A2 D3 G3 B3 E4` (strings 6 through 1).
- TAB supports frets 0-36 so high transposed passages can remain representable. Notes beyond a typical 24-fret guitar should be reviewed for playability.
- Generated PDFs are lightweight local exports intended for rehearsal and review. MusicXML remains the best interchange format for further engraving in MuseScore or another notation editor.
