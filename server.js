"use strict";

const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const REPO_ROOT = path.resolve(__dirname);
const LOG_DIR = resolveLogDir();
const STATE_FILE = path.join(LOG_DIR, "scheduler_state.json");
const DEFAULT_TIMEZONE = "Asia/Tokyo";
const DEFAULT_POLL_MS = 30_000;
const DEFAULT_PORT = 8787;

loadEnvFile(path.join(REPO_ROOT, ".env"));

const TIME_ZONE = process.env.SCHEDULE_TIMEZONE || DEFAULT_TIMEZONE;
const POLL_INTERVAL_MS = parseInt(process.env.SCHEDULE_POLL_MS || "", 10) || DEFAULT_POLL_MS;
const PORT = parseInt(process.env.PORT || "", 10) || DEFAULT_PORT;
const PYTHON_BIN = resolvePythonBin();

const paperSchedule = parseTimeString(process.env.PAPER_TIME || "10:00");
const githubSchedule = parseTimeString(process.env.GITHUB_TIME || "11:00");
const paperMaxPapers = parsePositiveInt(process.env.PAPER_MAX_PAPERS);

const tasks = {
  paper: {
    label: "paper",
    script: "daily_paper_video.py",
    schedule: paperSchedule,
    args: ["--once"],
    env: {},
  },
  github: {
    label: "github",
    script: "daily_github_video.py",
    schedule: githubSchedule,
    args: ["--once", "--days", "1"],
    env: {
      SKIP_DIFFUSERS: process.env.GITHUB_SKIP_DIFFUSERS || process.env.SKIP_DIFFUSERS || "1",
    },
  },
  bsd_14: {
    label: "bsd_14",
    script: "daily_bsd_video.py",
    schedule: { hour: 14, minute: 0 },
    args: ["--once"],
    env: {},
  },
  bsd_17: {
    label: "bsd_17",
    script: "daily_bsd_video.py",
    schedule: { hour: 17, minute: 0 },
    args: ["--once"],
    env: {},
  },
};

if (process.env.PAPER_TEST_MODE === "1") {
  tasks.paper.args.push("--test");
}
if (paperMaxPapers) {
  tasks.paper.args.push("--papers", String(paperMaxPapers));
}
if (process.env.GITHUB_TEST_MODE === "1") {
  tasks.github.args.push("--test");
}
if (process.env.GITHUB_DAYS_BACK) {
  tasks.github.args = ["--once", "--days", process.env.GITHUB_DAYS_BACK];
}

const state = loadState();

Object.keys(tasks).forEach((name) => {
  if (!state[name]) {
    state[name] = {};
  }
});

safeAppendLog("boot.log", "Starting scheduler process.");

const server = http.createServer((req, res) => {
  if (!req.url) {
    respondJson(res, 400, { error: "missing url" });
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const method = req.method || "GET";

  if (method === "GET" && url.pathname === "/health") {
    respondJson(res, 200, buildStatus());
    return;
  }

  if ((method === "POST" || method === "GET") && url.pathname === "/run/github") {
    triggerTask("github", "manual");
    respondJson(res, 202, buildStatus());
    return;
  }

  if ((method === "POST" || method === "GET") && url.pathname === "/run/paper") {
    triggerTask("paper", "manual");
    respondJson(res, 202, buildStatus());
    return;
  }

  respondJson(res, 404, { error: "not found" });
});

server.listen(PORT, () => {
  logLine(`Scheduler server listening on port ${PORT} (TZ=${TIME_ZONE})`);
});
server.on("error", (err) => {
  logLine(`Server listen error: ${err.message || err}`);
});

const scheduleTimer = setInterval(scheduleTick, POLL_INTERVAL_MS);
scheduleTick();

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
process.on("uncaughtException", (err) => {
  logLine(`uncaughtException: ${err.stack || err.message || err}`);
});
process.on("unhandledRejection", (err) => {
  logLine(`unhandledRejection: ${err}`);
});

function scheduleTick() {
  const nowParts = getZonedParts(new Date(), TIME_ZONE);
  Object.keys(tasks).forEach((taskName) => {
    const task = tasks[taskName];
    if (shouldRun(taskName, task, nowParts)) {
      triggerTask(taskName, "schedule");
    }
  });
}

function shouldRun(taskName, task, nowParts) {
  const taskState = state[taskName] || {};
  if (taskState.running) {
    return false;
  }

  const today = nowParts.dateStr;
  const lastSuccess = taskState.last_success_date;
  if (lastSuccess === today) {
    return false;
  }

  const nowMinutes = nowParts.hour * 60 + nowParts.minute;
  const targetMinutes = task.schedule.hour * 60 + task.schedule.minute;
  return nowMinutes >= targetMinutes;
}

function triggerTask(taskName, reason) {
  const task = tasks[taskName];
  if (!task) {
    logLine(`Unknown task: ${taskName}`);
    return;
  }

  const taskState = state[taskName];
  if (taskState.running) {
    logLine(`Task ${taskName} is already running.`);
    return;
  }

  const nowParts = getZonedParts(new Date(), TIME_ZONE);
  taskState.running = true;
  taskState.last_attempt_date = nowParts.dateStr;
  taskState.last_attempt_time = nowParts.timeStr;
  taskState.last_reason = reason;
  saveState();

  const scriptPath = path.join(REPO_ROOT, task.script);
  const child = spawn(PYTHON_BIN, [scriptPath, ...task.args], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      ...task.env,
      PYTHONUNBUFFERED: "1",
      PATH: buildPathEnv(),
    },
  });

  logLine(`Task ${taskName} started (${reason}) using ${PYTHON_BIN}`);

  pipeWithPrefix(child.stdout, taskName);
  pipeWithPrefix(child.stderr, taskName);

  child.on("close", (code) => {
    const doneParts = getZonedParts(new Date(), TIME_ZONE);
    taskState.running = false;
    taskState.last_exit_code = code;
    taskState.last_finish_date = doneParts.dateStr;
    taskState.last_finish_time = doneParts.timeStr;
    if (code === 0) {
      taskState.last_success_date = doneParts.dateStr;
      taskState.last_success_time = doneParts.timeStr;
    }
    saveState();
    logLine(`Task ${taskName} finished with exit code ${code}`);
  });

  child.on("error", (err) => {
    taskState.running = false;
    taskState.last_exit_code = 1;
    taskState.last_error = String(err);
    saveState();
    logLine(`Task ${taskName} failed to start: ${err}`);
  });
}

function buildStatus() {
  const nowParts = getZonedParts(new Date(), TIME_ZONE);
  const status = {
    time_zone: TIME_ZONE,
    now: `${nowParts.dateStr} ${nowParts.timeStr}`,
    uptime_seconds: Math.round(process.uptime()),
    python_bin: PYTHON_BIN,
    tasks: {},
  };

  Object.keys(tasks).forEach((taskName) => {
    const task = tasks[taskName];
    const taskState = state[taskName] || {};
    status.tasks[taskName] = {
      schedule: `${pad2(task.schedule.hour)}:${pad2(task.schedule.minute)}`,
      running: Boolean(taskState.running),
      last_attempt_date: taskState.last_attempt_date || null,
      last_attempt_time: taskState.last_attempt_time || null,
      last_finish_date: taskState.last_finish_date || null,
      last_finish_time: taskState.last_finish_time || null,
      last_success_date: taskState.last_success_date || null,
      last_success_time: taskState.last_success_time || null,
      last_exit_code: typeof taskState.last_exit_code === "number" ? taskState.last_exit_code : null,
      last_reason: taskState.last_reason || null,
    };
  });

  return status;
}

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return;
  }
  const content = fs.readFileSync(filePath, "utf8");
  const lines = content.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }
    const eq = trimmed.indexOf("=");
    if (eq === -1) {
      continue;
    }
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }
    if (!(key in process.env)) {
      process.env[key] = value;
    }
  }
}

function resolvePythonBin() {
  const envBin = process.env.PYTHON_BIN;
  if (envBin && fs.existsSync(envBin)) {
    return envBin;
  }
  const preferred = "/Users/yasufumi/miniforge3/bin/python3.10";
  if (fs.existsSync(preferred)) {
    return preferred;
  }
  return "python3";
}

function parseTimeString(text) {
  const match = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!match) {
    return { hour: 10, minute: 0 };
  }
  const hour = Math.min(Math.max(parseInt(match[1], 10), 0), 23);
  const minute = Math.min(Math.max(parseInt(match[2], 10), 0), 59);
  return { hour, minute };
}

function parsePositiveInt(value) {
  if (!value) {
    return null;
  }
  const num = parseInt(value, 10);
  if (!Number.isFinite(num) || num <= 0) {
    return null;
  }
  return num;
}

function loadState() {
  try {
    ensureLogDir();
    if (!fs.existsSync(STATE_FILE)) {
      return {};
    }
    const raw = fs.readFileSync(STATE_FILE, "utf8");
    return JSON.parse(raw);
  } catch (err) {
    logLine(`Failed to load state: ${err}`);
    return {};
  }
}

function saveState() {
  try {
    ensureLogDir();
    const tempFile = `${STATE_FILE}.tmp`;
    fs.writeFileSync(tempFile, JSON.stringify(state, null, 2));
    fs.renameSync(tempFile, STATE_FILE);
  } catch (err) {
    logLine(`Failed to save state: ${err}`);
  }
}

function getZonedParts(date, timeZone) {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const parts = formatter.formatToParts(date);
  const map = {};
  for (const part of parts) {
    if (part.type !== "literal") {
      map[part.type] = part.value;
    }
  }
  const year = parseInt(map.year, 10);
  const month = parseInt(map.month, 10);
  const day = parseInt(map.day, 10);
  const hour = parseInt(map.hour, 10);
  const minute = parseInt(map.minute, 10);
  const second = parseInt(map.second, 10);
  return {
    year,
    month,
    day,
    hour,
    minute,
    second,
    dateStr: `${map.year}-${map.month}-${map.day}`,
    timeStr: `${map.hour}:${map.minute}:${map.second}`,
  };
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function buildPathEnv() {
  const parts = new Set();
  const existing = process.env.PATH || "";
  existing.split(path.delimiter).filter(Boolean).forEach((entry) => parts.add(entry));
  [
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
  ].forEach((entry) => parts.add(entry));
  return Array.from(parts).join(path.delimiter);
}

function respondJson(res, statusCode, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(statusCode, {
    "Content-Type": "application/json",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function pipeWithPrefix(stream, label) {
  if (!stream) {
    return;
  }
  let buffer = "";
  stream.on("data", (chunk) => {
    buffer += chunk.toString();
    let idx;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trimEnd();
      buffer = buffer.slice(idx + 1);
      if (line.length) {
        logLine(`[${label}] ${line}`);
      }
    }
  });
  stream.on("end", () => {
    if (buffer.trim().length) {
      logLine(`[${label}] ${buffer.trimEnd()}`);
    }
  });
}

function logLine(message) {
  const nowParts = getZonedParts(new Date(), TIME_ZONE);
  const timestamp = `${nowParts.dateStr} ${nowParts.timeStr}`;
  console.log(`[${timestamp}] ${message}`);
}

function resolveLogDir() {
  const homeEnv = process.env.HOME;
  let homeDir = homeEnv && homeEnv !== "/var/empty" ? homeEnv : os.homedir();
  if (!homeDir || homeDir === "/var/empty") {
    return path.join(os.tmpdir(), "auto-video-product");
  }
  return path.join(homeDir, "Library", "Logs", "auto-video-product");
}

function ensureLogDir() {
  if (!fs.existsSync(LOG_DIR)) {
    fs.mkdirSync(LOG_DIR, { recursive: true });
  }
}

function safeAppendLog(filename, message) {
  try {
    ensureLogDir();
    const fullPath = path.join(LOG_DIR, filename);
    const line = `${new Date().toISOString()} ${message}\n`;
    fs.appendFileSync(fullPath, line);
  } catch (err) {
    // Ignore logging failures to keep the scheduler alive.
  }
}

function shutdown() {
  clearInterval(scheduleTimer);
  server.close(() => {
    logLine("Scheduler server stopped.");
    process.exit(0);
  });
}
