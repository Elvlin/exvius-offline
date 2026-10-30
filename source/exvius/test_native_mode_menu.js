const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const source = fs.readFileSync(path.join(__dirname, 'summon_menu.js'), 'utf8')
    .replace(/^import .*;\r?$/gm, '');
  const {modeFields} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  const replies = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  let rows = 0;
  for (const reply of replies) {
    for (const group of Object.values(reply.native_groups)) {
      const parsed = [];
      for (const field of modeFields(group)) {
        // Frida's native integer/bool arguments reject JavaScript booleans.
        for (const value of [field.row, field.column, field.last]) assert.equal(typeof value, 'number');
        assert.ok([0, 1].includes(field.last));
        if (field.column === 0) parsed[field.row] = {};
        parsed[field.row][field.key] = field.value;
        assert.equal(field.last, field.column === Object.keys(group[field.row]).length - 1 ? 1 : 0);
      }
      assert.deepEqual(parsed, group.map(row => Object.fromEntries(Object.entries(row).map(([k,v]) => [k, String(v)]))));
      rows += group.length;
    }
  }
  assert.ok(rows > 0);
  const text = fs.readFileSync(path.join(__dirname, '../../data/text_decoded/F_TEXT_DUNGEON_NAME.ndjson'), 'utf8');
  const keys = new Set(text.trim().split('\n').map(line => JSON.parse(line).key));
  for (const reply of replies) assert.ok(keys.has('MST_DUNGEONS_NAME_' + reply.dungeon));
  console.log('Original mode response rows, native integer arguments and shipped dungeon text keys passed: ' + rows + ' rows.');
})().catch(error => {console.error(error); process.exitCode = 1;});
