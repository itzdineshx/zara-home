import { spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const rootDir = process.cwd();
const pythonExecutable = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
const electronBuilderExecutable = path.join(rootDir, 'node_modules', '.bin', 'electron-builder.cmd');
const localAppData = process.env.LOCALAPPDATA;

if (!localAppData) {
  throw new Error('LOCALAPPDATA is not set.');
}

const buildRoot = path.join(localAppData, 'ZaraAI');
const backendOutputDir = path.join(buildRoot, 'build', 'backend');
const backendWorkDir = path.join(buildRoot, 'build', 'pyinstaller-work');
const backendLinkDir = path.join(rootDir, 'dist', 'backend');

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    stdio: 'inherit',
    env: process.env,
    shell: true,
    ...options,
  });

  if (result.status !== 0) {
    throw new Error(`Command failed: ${command} ${args.join(' ')}`);
  }
}

function removePath(targetPath) {
  if (fs.existsSync(targetPath)) {
    fs.rmSync(targetPath, { recursive: true, force: true });
  }
}

run('npm.cmd', ['run', 'build'], {
  cwd: rootDir,
  env: {
    ...process.env,
    VITE_BASE_PATH: './',
  },
});
run(pythonExecutable, [
  '-m',
  'PyInstaller',
  '--noconfirm',
  '--clean',
  '--onefile',
  '--name',
  'zara-backend',
  '--distpath',
  backendOutputDir,
  '--workpath',
  backendWorkDir,
  '--specpath',
  path.join(rootDir, 'backend', 'build'),
  '--paths',
  'backend',
  'backend/windows_backend_launcher.py',
], { cwd: rootDir });

removePath(backendLinkDir);
fs.mkdirSync(path.dirname(backendLinkDir), { recursive: true });
run('cmd.exe', ['/c', 'mklink', '/J', backendLinkDir, backendOutputDir], { cwd: rootDir });

try {
  run(electronBuilderExecutable, ['--win', 'nsis'], { cwd: rootDir });
} finally {
  removePath(backendLinkDir);
}
