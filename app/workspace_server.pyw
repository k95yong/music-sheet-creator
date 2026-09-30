import base64
import ctypes
import json
import mimetypes
import os
import subprocess
import queue
import re
import sys
import threading
import time
import webbrowser
from ctypes import wintypes
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import urlopen

PROGRAM_ROOT = Path(__file__).resolve().parent
WORKSPACE = Path(os.environ.get(
    "MUSIC_SHEET_WORKSPACE",
    Path.home() / "Documents" / "Music Sheet Creator",
)).expanduser().resolve()
CONFIG_ROOT = WORKSPACE / "config"
PROJECTS_ROOT = WORKSPACE / "01_Projects"
STATE_FILE = CONFIG_ROOT / "app_state.json"
PORT = int(os.environ.get("MUSIC_SHEET_PORT", "8765"))

winmm = ctypes.WinDLL("winmm")
DWORD_PTR = ctypes.c_size_t
HMIDIIN = wintypes.HANDLE
HMIDIOUT = wintypes.HANDLE
CALLBACK_FUNCTION = 0x00030000
MIM_DATA = 0x3C3

winmm.midiInOpen.argtypes = [ctypes.POINTER(HMIDIIN), wintypes.UINT, DWORD_PTR, DWORD_PTR, wintypes.DWORD]
winmm.midiInOpen.restype = wintypes.UINT
winmm.midiInStart.argtypes = [HMIDIIN]
winmm.midiInStart.restype = wintypes.UINT
winmm.midiInStop.argtypes = [HMIDIIN]
winmm.midiInReset.argtypes = [HMIDIIN]
winmm.midiInClose.argtypes = [HMIDIIN]
winmm.midiOutOpen.argtypes = [ctypes.POINTER(HMIDIOUT), wintypes.UINT, DWORD_PTR, DWORD_PTR, wintypes.DWORD]
winmm.midiOutOpen.restype = wintypes.UINT
winmm.midiOutShortMsg.argtypes = [HMIDIOUT, wintypes.DWORD]
winmm.midiOutClose.argtypes = [HMIDIOUT]


class MIDIINCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.UINT), ("szPname", wintypes.WCHAR * 32),
                ("dwSupport", wintypes.DWORD)]


class MIDIOUTCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD),
                ("vDriverVersion", wintypes.UINT), ("szPname", wintypes.WCHAR * 32),
                ("wTechnology", wintypes.WORD), ("wVoices", wintypes.WORD),
                ("wNotes", wintypes.WORD), ("wChannelMask", wintypes.WORD),
                ("dwSupport", wintypes.DWORD)]


class MidiBridge:
    def __init__(self):
        self.hins, self.hout = [], HMIDIOUT()
        self.device, self.output, self.error = "", "", ""
        self.event_count, self.last_event, self.last_packed, self.last_packed_at = 0, {}, None, 0.0
        self.lock, self.subscribers = threading.Lock(), []
        self.CALLBACK = ctypes.WINFUNCTYPE(None, HMIDIIN, wintypes.UINT, DWORD_PTR, DWORD_PTR, DWORD_PTR)
        self.callback = self.CALLBACK(self._callback)
        self.connect()
        threading.Thread(target=self._retry_loop, daemon=True).start()

    def _devices(self, direction):
        result = []
        count = winmm.midiInGetNumDevs() if direction == "in" else winmm.midiOutGetNumDevs()
        struct_type = MIDIINCAPSW if direction == "in" else MIDIOUTCAPSW
        getter = winmm.midiInGetDevCapsW if direction == "in" else winmm.midiOutGetDevCapsW
        for index in range(count):
            caps = struct_type()
            if getter(index, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                result.append((index, caps.szPname))
        return result

    def connect(self):
        with self.lock:
            self._close_unlocked()
            inputs = self._devices("in")
            if not inputs:
                self.error = "MIDI 입력 장치를 찾지 못했습니다."
                return False
            selected_inputs = [(i, n) for i, n in inputs if "Keystation" in n] or [inputs[0]]
            opened_names = []
            for in_id, in_name in selected_inputs:
                handle = HMIDIIN()
                callback_address = ctypes.cast(self.callback, ctypes.c_void_p).value
                code = winmm.midiInOpen(ctypes.byref(handle), in_id, callback_address, 0, CALLBACK_FUNCTION)
                if code == 0:
                    winmm.midiInStart(handle)
                    self.hins.append(handle)
                    opened_names.append(in_name)
            if not self.hins:
                self.error = "다른 MIDI 앱/탭이 Keystation을 사용 중입니다. 기존 창을 닫으면 자동 재연결됩니다."
                return False
            self.device, self.error = " + ".join(opened_names), ""
            return True

    def _retry_loop(self):
        while True:
            time.sleep(3)
            if not self.connected:
                try: self.connect()
                except Exception: pass

    def _callback(self, _handle, message, _instance, param1, _param2):
        if message != MIM_DATA:
            return
        packed = int(param1) & 0xFFFFFF
        now = time.perf_counter()
        if packed == self.last_packed and now - self.last_packed_at < 0.006:
            return
        self.last_packed, self.last_packed_at = packed, now
        payload = {"status": packed & 0xFF, "note": (packed >> 8) & 0x7F,
                   "velocity": (packed >> 16) & 0x7F, "nativeAudio": bool(self.hout)}
        self.event_count += 1
        self.last_event = payload
        with self.lock:
            subscribers = list(self.subscribers)
        for target in subscribers:
            try: target.put_nowait(payload)
            except queue.Full: pass

    def subscribe(self):
        target = queue.Queue(maxsize=256)
        with self.lock: self.subscribers.append(target)
        return target

    def unsubscribe(self, target):
        with self.lock:
            if target in self.subscribers: self.subscribers.remove(target)

    def _close_unlocked(self):
        for handle in self.hins:
            winmm.midiInStop(handle); winmm.midiInReset(handle); winmm.midiInClose(handle)
        self.hins = []
        if self.hout:
            winmm.midiOutReset(self.hout); winmm.midiOutClose(self.hout); self.hout = HMIDIOUT()
        self.device, self.output = "", ""

    def close(self):
        with self.lock: self._close_unlocked()

    @property
    def connected(self):
        return bool(self.hins)


bridge = MidiBridge()


def safe_id(value):
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", " ", str(value)).strip().rstrip(".")
    value = re.sub(r"\s+", " ", value)[:80]
    return value or f"새 곡 {time.strftime('%Y%m%d-%H%M%S')}"


def project_path(project_id):
    path = (PROJECTS_ROOT / unquote(project_id)).resolve()
    if PROJECTS_ROOT.resolve() not in path.parents:
        raise ValueError("잘못된 프로젝트 경로")
    return path


def recycle_score_file(path, filename):
    if not isinstance(filename, str) or not filename or filename in {".", ".."} or any(c in filename for c in '/\\:\x00'):
        raise ValueError("잘못된 악보 파일명")
    folder = path / "02_Transcription"
    target = folder / filename
    if folder.resolve().parent != path.resolve() or target.is_symlink() or target.resolve().parent != folder.resolve():
        raise ValueError("악보 폴더 밖의 파일은 삭제할 수 없습니다.")
    if not target.is_file():
        raise FileNotFoundError("악보 파일을 찾지 못했습니다.")
    # Keep filenames out of executable PowerShell text, including quotes and Unicode.
    environment = os.environ.copy()
    environment["MUSIC_SHEET_RECYCLE_PATH"] = str(target.resolve())
    script = """$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName Microsoft.VisualBasic
if (-not [Environment]::UserInteractive) { throw 'Recycle Bin requires an interactive Windows session' }
[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(
    $env:MUSIC_SHEET_RECYCLE_PATH,
    [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
    [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin,
    [Microsoft.VisualBasic.FileIO.UICancelOption]::ThrowException
)"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode or target.exists():
        raise OSError("휴지통으로 이동하지 못했습니다. 파일 사용 여부와 휴지통을 확인하세요.")


def ensure_project(path, title=None):
    for folder in ("01_Reference", "02_Transcription", "03_Recordings", "04_Edits", "05_Mixes", "06_Masters", "07_Artwork", "08_Deliverables", "Notes"):
        (path / folder).mkdir(parents=True, exist_ok=True)
    meta_path = path / "project.json"
    if not meta_path.exists():
        meta = {"title": title or path.name, "key": "", "scale": "", "tempo": "", "timeSignature": "4/4", "activeAudio": "", "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path


def load_project(project_id):
    path = project_path(project_id)
    if not path.is_dir():
        raise FileNotFoundError(project_id)
    meta_path = ensure_project(path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    audio = []
    for folder in (path / "01_Reference", path / "04_Edits"):
        if folder.exists():
            audio.extend([str(p.relative_to(path)).replace("\\", "/") for p in folder.iterdir() if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".wma"}])
    scores = []
    score_dir = path / "02_Transcription"
    if score_dir.exists():
        scores = [p.name for p in score_dir.iterdir() if p.is_file()]
    memo_path = path / "Notes" / "작업메모.json"
    memo = json.loads(memo_path.read_text(encoding="utf-8")).get("text", "") if memo_path.exists() else ""
    return {"id": path.name, **meta, "audio": sorted(audio), "scores": sorted(scores), "memo": memo}


def list_projects():
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted((p for p in PROJECTS_ROOT.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        try:
            meta = json.loads(ensure_project(path).read_text(encoding="utf-8"))
            result.append({"id": path.name, "title": meta.get("title", path.name)})
        except Exception: pass
    return result


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *_args): pass

    def json_response(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(data)

    def body_json(self, max_size=2_000_000):
        size = int(self.headers.get("Content-Length", "0"))
        if size > max_size: raise ValueError("요청이 너무 큽니다.")
        return json.loads(self.rfile.read(size).decode("utf-8") or "{}")

    def send_path(self, path):
        if not path.is_file(): return self.send_error(404)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size = path.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            spec = range_header[6:].split(",", 1)[0]
            left, right = spec.split("-", 1)
            if left: start = int(left)
            if right: end = min(int(right), end)
            self.send_response(206); self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else: self.send_response(200)
        self.send_header("Content-Type", content_type); self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1)); self.end_headers()
        with path.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = source.read(min(1024 * 256, remaining))
                if not chunk: break
                self.wfile.write(chunk); remaining -= len(chunk)

    def do_GET(self):
        parsed = urlparse(self.path); parts = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
        try:
            if parsed.path == "/api/health": return self.json_response(200, {"ok": True})
            if parsed.path == "/api/midi-status": return self.json_response(200, {"connected": bridge.connected, "device": bridge.device, "output": bridge.output, "error": bridge.error, "eventCount": bridge.event_count, "lastEvent": bridge.last_event})
            if parsed.path == "/api/midi-stream": return self.stream_midi()
            if parsed.path == "/api/state":
                state = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
                return self.json_response(200, state)
            if parsed.path == "/api/projects": return self.json_response(200, {"projects": list_projects()})
            if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
                project_id = parts[2]
                if len(parts) == 3: return self.json_response(200, load_project(project_id))
                path = project_path(project_id)
                if parts[3] == "file" and len(parts) >= 5:
                    relative = "/".join(parts[4:])
                    target = (path / relative).resolve()
                    if path.resolve() not in target.parents: raise ValueError("잘못된 파일 경로")
                    return self.send_path(target)
            return super().do_GET()
        except FileNotFoundError: return self.json_response(404, {"error": "프로젝트를 찾지 못했습니다."})
        except Exception as exc: return self.json_response(400, {"error": str(exc)})

    def stream_midi(self):
        target = bridge.subscribe()
        try:
            self.send_response(200); self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "keep-alive"); self.end_headers()
            while True:
                try: line = f"data: {json.dumps(target.get(timeout=12), ensure_ascii=False)}\n\n".encode("utf-8")
                except queue.Empty: line = b": keepalive\n\n"
                self.wfile.write(line); self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError): pass
        finally: bridge.unsubscribe(target)

    def do_POST(self):
        parsed = urlparse(self.path); parts = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
        try:
            if parsed.path == "/api/midi-reconnect":
                bridge.connect(); return self.json_response(200, {"connected": bridge.connected, "device": bridge.device, "output": bridge.output, "error": bridge.error, "eventCount": bridge.event_count})
            if parsed.path == "/api/state":
                data = self.body_json(); CONFIG_ROOT.mkdir(parents=True, exist_ok=True); STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                return self.json_response(200, {"ok": True})
            if parsed.path == "/api/projects":
                data = self.body_json(); title = safe_id(data.get("title", "")); path = PROJECTS_ROOT / title
                base, counter = path, 2
                while path.exists(): path = Path(f"{base} ({counter})"); counter += 1
                path.mkdir(parents=True); ensure_project(path, title)
                return self.json_response(200, load_project(path.name))
            if len(parts) >= 4 and parts[:2] == ["api", "projects"]:
                project_id, action = parts[2], parts[3]; path = project_path(project_id); ensure_project(path)
                if action == "recycle-score":
                    if self.headers.get("Sec-Fetch-Site") == "cross-site" or self.headers.get("Origin") not in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
                        return self.json_response(403, {"error": "로컬 작업실에서만 삭제할 수 있습니다."})
                    if self.headers.get_content_type() != "application/json":
                        return self.json_response(415, {"error": "JSON 요청이 필요합니다."})
                    filename = self.body_json().get("filename")
                    recycle_score_file(path, filename)
                    return self.json_response(200, {"ok": True, "file": filename, "scores": load_project(project_id)["scores"]})
                if action == "meta":
                    data = self.body_json(); meta_path = path / "project.json"; meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    for key in ("title", "key", "scale", "tempo", "timeSignature", "activeAudio"): meta[key] = str(data.get(key, meta.get(key, "")))[:500]
                    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                    return self.json_response(200, {"ok": True})
                if action == "memo":
                    text = str(self.body_json().get("text", ""))[:2_000_000]; target = path / "Notes" / "작업메모.json"; tmp = target.with_suffix(".tmp")
                    tmp.write_text(json.dumps({"text": text, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False, indent=2), encoding="utf-8"); tmp.replace(target)
                    return self.json_response(200, {"ok": True})
                if action == "midi":
                    data = self.body_json(max_size=20_000_000); raw = base64.b64decode(data["base64"]); name = safe_id(data.get("name", "take.mid"))
                    if not name.lower().endswith(".mid"): name += ".mid"
                    target = path / "03_Recordings" / name; target.write_bytes(raw)
                    return self.json_response(200, {"ok": True, "file": target.name})
                if action == "recording-audio":
                    query = parse_qs(parsed.query); name = safe_id(query.get("filename", ["take-mix.webm"])[0])
                    if not name.lower().endswith((".webm", ".wav")): name += ".webm"
                    size = int(self.headers.get("Content-Length", "0"))
                    if size > 500_000_000: raise ValueError("오디오 녹음 파일이 너무 큽니다.")
                    target = path / "03_Recordings" / name; target.write_bytes(self.rfile.read(size))
                    return self.json_response(200, {"ok": True, "file": target.name})
                if action == "upload":
                    query = parse_qs(parsed.query); category = query.get("category", ["scores"])[0]; name = safe_id(query.get("filename", ["file"])[0])
                    folder = path / ("01_Reference" if category == "audio" else "02_Transcription")
                    size = int(self.headers.get("Content-Length", "0"))
                    if size > 500_000_000: raise ValueError("파일이 너무 큽니다.")
                    (folder / name).write_bytes(self.rfile.read(size))
                    return self.json_response(200, {"ok": True, "file": name})
            return self.json_response(404, {"error": "없는 API입니다."})
        except Exception as exc: return self.json_response(400, {"error": str(exc)})


def main():
    try:
        with urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=0.6) as response:
            running = response.status == 200
    except Exception:
        running = False
    if running:
        if "--no-browser" not in sys.argv: webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return
    CONFIG_ROOT.mkdir(parents=True, exist_ok=True); PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=str(PROGRAM_ROOT)))
    if "--no-browser" not in sys.argv: threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}/")).start()
    try: server.serve_forever()
    finally: bridge.close()


if __name__ == "__main__": main()
