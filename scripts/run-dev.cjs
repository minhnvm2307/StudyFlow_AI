const path = require('node:path');
const { spawnSync } = require('node:child_process');

function getLauncher(platform = process.platform) {
  if (platform === 'win32') {
    return {
      command: 'powershell.exe',
      args: [
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        path.join(__dirname, 'run-dev.ps1'),
      ],
    };
  }

  return {
    command: 'bash',
    args: [path.join(__dirname, 'run-dev.sh')],
  };
}

function main(argv = process.argv.slice(2), platform = process.platform) {
  if (argv[0] === '--print-launcher') {
    const requestedPlatform = argv[1] || platform;
    process.stdout.write(`${JSON.stringify(getLauncher(requestedPlatform))}\n`);
    return 0;
  }

  const launcher = getLauncher(platform);
  const result = spawnSync(launcher.command, [...launcher.args, ...argv], {
    cwd: path.resolve(__dirname, '..'),
    stdio: 'inherit',
  });

  if (result.error) {
    throw result.error;
  }

  if (typeof result.status === 'number') {
    return result.status;
  }

  return 1;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  getLauncher,
  main,
};
