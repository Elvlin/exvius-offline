const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
const source = fs.readFileSync(require('node:path').join(__dirname, 'mission_repeat.js'), 'utf8');
const { repeatRunMark } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
// The first run of an autoplay sequence starts from cleared totals and is never marked.
assert.equal(repeatRunMark(true, 0), 0);
assert.equal(repeatRunMark(true, 1), 2);
assert.equal(repeatRunMark(true, 2), 3);
assert.equal(repeatRunMark(false, 4), 0);
console.log('Autoplay continuation marks passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
