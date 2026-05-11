import { app, BrowserWindow } from 'electron';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '..');
const isDevelopment = !app.isPackaged;
const devServerUrl = process.env.ELECTRON_START_URL || 'http://127.0.0.1:8080';
const backendUrl = process.env.ZARA_BACKEND_URL || 'http://127.0.0.1:8000';
const backendHealthUrl = `${backendUrl.replace(/\/$/, '')}/health`;

let backendProcess = null;

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function getUserBackendEnvPath() {
  return path.join(app.getPath('userData'), 'backend.env');
}

function ensureUserBackendEnv() {
  const targetPath = getUserBackendEnvPath();
  if (fs.existsSync(targetPath)) {
    return targetPath;
  }

  const templatePath = path.join(app.getAppPath(), 'backend', '.env.example');
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.copyFileSync(templatePath, targetPath);
  return targetPath;
}

function getBackendExecutablePath() {
  return path.join(process.resourcesPath, 'backend', 'zara-backend.exe');
}

function startBackendProcess() {
  if (backendProcess) {
    return backendProcess;
  }

  const env = {
    ...process.env,
    ZARA_ENV_PATH: ensureUserBackendEnv(),
  };

  if (isDevelopment) {
    const pythonExecutable = path.join(projectRoot, '.venv', 'Scripts', 'python.exe');
    const executable = fs.existsSync(pythonExecutable) ? pythonExecutable : 'py';
    const args = fs.existsSync(pythonExecutable)
      ? ['-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000']
      : ['-3', '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--host', '127.0.0.1', '--port', '8000'];

    backendProcess = spawn(executable, args, {
      cwd: projectRoot,
      env,
      windowsHide: true,
      stdio: 'ignore',
    });
    return backendProcess;
  }

  backendProcess = spawn(getBackendExecutablePath(), [], {
    cwd: path.dirname(getBackendExecutablePath()),
    env,
    windowsHide: true,
    stdio: 'ignore',
  });

  return backendProcess;
}

async function waitForBackend(timeoutMs = 30000) {
  const startedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(backendHealthUrl);
      if (response.ok) {
        return;
      }
    } catch {
      // Retry until the backend is ready.
    }

    await delay(500);
  }

  throw new Error(`Backend did not become ready at ${backendHealthUrl}`);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 720,
    backgroundColor: '#0b1020',
    autoHideMenuBar: true,
    title: 'Zara AI',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      devTools: isDevelopment,
    },
  });

  if (isDevelopment) {
    win.loadURL(devServerUrl);
    win.webContents.openDevTools({ mode: 'detach' });
    return;
  }

  win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
}

async function bootstrap() {
  startBackendProcess();
  await waitForBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
}

app.whenReady().then(bootstrap);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
});
