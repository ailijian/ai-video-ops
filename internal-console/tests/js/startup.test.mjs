import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

// Behavior modules alone do not parse app.js. Check every shipped entry and
// module, including unreachable imports, so integration syntax errors fail CI.
test('all shipped JavaScript parses as browser modules, including the application entry', () => {
  const assets = new URL('../../static/assets/', import.meta.url);
  const files = readdirSync(assets).filter(name => /\.(?:mjs|js)$/.test(name));
  assert.ok(files.includes('app.js') && files.includes('startup.js'));
  for (const file of files) {
    const result = spawnSync(process.execPath, ['--input-type=module', '--check'], {
      input: readFileSync(new URL(file, assets)), encoding: 'utf8', timeout: 5000,
    });
    assert.equal(result.status, 0, `${file}: ${result.stderr || result.error}`);
  }
});
