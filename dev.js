import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const isWin = process.platform === 'win32';
const root = process.cwd();

// Detect Python binary (prioritize project .venv)
let pythonCmd = 'python';
const venvWin = join(root, '.venv', 'Scripts', 'python.exe');
const venvUnix = join(root, '.venv', 'bin', 'python');

if (existsSync(venvWin)) {
  pythonCmd = venvWin;
} else if (existsSync(venvUnix)) {
  pythonCmd = venvUnix;
}

console.log('\x1b[36m[Athena Shield]\x1b[0m Starting Backend API and Frontend UI...');
console.log(`\x1b[32m[Backend]\x1b[0m  FastAPI: http://127.0.0.1:8000 (runtime: ${pythonCmd})`);
console.log(`\x1b[35m[Frontend]\x1b[0m Vite console: http://127.0.0.1:5173\n`);

// Spawn backend (FastAPI)
const backend = spawn(pythonCmd, ['server.py'], {
  cwd: root,
  stdio: 'inherit'
});

// Spawn frontend (Vite)
const frontend = isWin
  ? spawn('cmd.exe', ['/d', '/s', '/c', 'npm run dev'], { cwd: join(root, 'frontend'), stdio: 'inherit' })
  : spawn('npm', ['run', 'dev'], { cwd: join(root, 'frontend'), stdio: 'inherit' });

function cleanup() {
  console.log('\n\x1b[33m[Athena Shield]\x1b[0m Shutting down servers...');
  try {
    if (isWin) {
      if (backend.pid) spawn('taskkill', ['/pid', backend.pid.toString(), '/f', '/t'], { stdio: 'ignore' });
      if (frontend.pid) spawn('taskkill', ['/pid', frontend.pid.toString(), '/f', '/t'], { stdio: 'ignore' });
    } else {
      backend.kill('SIGTERM');
      frontend.kill('SIGTERM');
    }
  } catch {}
  process.exit(0);
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);

backend.on('close', (code) => {
  if (code && code !== 0) console.log(`\x1b[31m[Backend]\x1b[0m Exited with code ${code}`);
});

frontend.on('close', (code) => {
  if (code && code !== 0) console.log(`\x1b[31m[Frontend]\x1b[0m Exited with code ${code}`);
});
