// Dependency-free regression checks against the client's actual score helpers.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../app/index.html'), 'utf8');
function extract(name) {
  const start = source.indexOf('function ' + name + '(');
  assert.ok(start >= 0, name);
  const ends = ['\nfunction ', '\nasync function ', '\n$(\''].map(s => source.indexOf(s, start + 1)).filter(n => n >= 0);
  return source.slice(start, Math.min(...ends));
}
const notes = [
  { n: 64, startQ: 3.5, durQ: 5, v: 96, tabString: 1, tabFret: 0 },
  { n: 69, startQ: 9, durQ: .5, v: 96, tabString: 2, tabFret: 10 },
];
const sandbox = {
  quantizedScore: notes, currentProject: { title: 'Regression fixture' }, TAB_MAX_FRET: 36,
  timeSignature: () => ({ top: 4, bottom: 4, measureQ: 4 }), tempo: () => 120,
  scoreXmlWithAudioOffset: xml => xml,
};
vm.createContext(sandbox);
for (const name of ['xmlPitch', 'musicXml', 'guitarPosition', 'tabOpenMidi', 'tabPositionForNote', 'scoreDisplayNotes', 'appendImportedNote']) vm.runInContext(extract(name), sandbox);
const segments = sandbox.scoreDisplayNotes();
assert.deepEqual(Array.from(segments, n => n.durQ), [.5, 4, .5, .5]);
assert.deepEqual(Array.from(segments, n => n.sourceIndex), [0, 0, 0, 1]);
for (const kind of ['piano', 'tab']) {
  const xml = sandbox.musicXml(kind);
  assert.equal((xml.match(/<tie type="start"/g) || []).length, 2);
  assert.equal((xml.match(/<tie type="stop"/g) || []).length, 2);
  assert.equal((xml.match(/<pitch>/g) || []).length, 4);
  if (kind === 'tab') {
    assert.equal((xml.match(/<string>1<\/string><fret>0<\/fret>/g) || []).length, 3);
    assert.ok(xml.includes('<string>2</string><fret>10</fret>'));
    assert.ok(xml.includes('<staff-tuning line="1"><tuning-step>E</tuning-step><tuning-octave>2'));
  }
}
function element(types) {
  return { querySelector(selector) {
    if (selector === 'voice') return { textContent: '1' };
    if (selector === 'staff') return null;
    return types.some(type => selector.includes(type)) ? {} : null;
  }};
}
const parsed = [], ties = new Map();
for (const [startQ, durQ, types] of [[3.5, .5, ['start']], [4, 4, ['start', 'stop']], [8, .5, ['stop']]]) {
  sandbox.appendImportedNote(parsed, ties, { ...notes[0], startQ, durQ }, element(types));
}
assert.equal(parsed.length, 1);
assert.equal(parsed[0].durQ, 5);
assert.equal(parsed[0].tabFret, 0);
assert.equal(ties.size, 0);
notes.push({ n: 72, startQ: 9, durQ: 1, v: 96 });
assert.ok(sandbox.musicXml().includes('<forward><duration>2</duration></forward>'));
notes.push({ n: 74, startQ: 9.5, durQ: 1, v: 96 });
assert.ok(sandbox.musicXml().includes('<backup><duration>2</duration></backup>'));
console.log('PASS: sustained display, shared piano/TAB export, ties, fingering, overlapping durations');
