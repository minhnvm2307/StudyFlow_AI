const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const repoRoot = path.resolve(__dirname, '..', '..');
const packageJsonPath = path.join(repoRoot, 'package.json');
const launcherPath = path.join(repoRoot, 'scripts', 'run-dev.cjs');
const bashLauncherPath = path.join(repoRoot, 'scripts', 'run-dev.sh');
const gitattributesPath = path.join(repoRoot, '.gitattributes');

test('npm run dev uses the cross-platform node launcher', () => {
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'));
  assert.equal(packageJson.scripts.dev, 'node scripts/run-dev.cjs');
});

test('windows launcher resolves to the PowerShell script', () => {
  const result = spawnSync(process.execPath, [launcherPath, '--print-launcher', 'win32'], {
    cwd: repoRoot,
    encoding: 'utf8',
  });

  assert.equal(result.status, 0, result.stderr);

  const launcher = JSON.parse(result.stdout);
  assert.equal(path.normalize(launcher.command), 'powershell.exe');
  assert.deepEqual(launcher.args.slice(0, 3), [
    '-ExecutionPolicy',
    'Bypass',
    '-File',
  ]);
  assert.equal(
    path.normalize(launcher.args[3]),
    path.normalize(path.join(repoRoot, 'scripts', 'run-dev.ps1')),
  );
});

test('bash dev launcher is stored with LF line endings', () => {
  const content = fs.readFileSync(bashLauncherPath, 'utf8');
  assert.equal(content.includes('\r\n'), false);
});

test('git enforces LF line endings for shell scripts', () => {
  const content = fs.readFileSync(gitattributesPath, 'utf8');
  assert.match(content, /^\*\.sh text eol=lf$/m);
});
