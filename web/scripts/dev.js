const net = require("net");
const path = require("path");
const { spawn } = require("child_process");

const MAX_TRIES = 10;

function withNodeOption(existing, option) {
  const options = (existing || "").split(/\s+/).filter(Boolean);
  return options.includes(option) ? options.join(" ") : [...options, option].join(" ");
}

function readRequestedPort() {
  const argPortIndex = process.argv.findIndex((arg) => arg === "--port");
  if (argPortIndex !== -1 && process.argv[argPortIndex + 1]) {
    const parsed = Number.parseInt(process.argv[argPortIndex + 1], 10);
    if (Number.isInteger(parsed) && parsed > 0) {
      return parsed;
    }
  }

  const envPort = Number.parseInt(process.env.PORT || "3000", 10);
  return Number.isInteger(envPort) && envPort > 0 ? envPort : 3000;
}

function canConnect(port, host) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ port, host });

    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });

    socket.once("error", () => resolve(false));
  });
}

async function isPortFree(port) {
  const ipv4Busy = await canConnect(port, "127.0.0.1");
  if (ipv4Busy) {
    return false;
  }

  const ipv6Busy = await canConnect(port, "::1");
  return !ipv6Busy;
}

async function findPort(startPort) {
  for (let port = startPort; port < startPort + MAX_TRIES; port += 1) {
    // eslint-disable-next-line no-await-in-loop
    if (await isPortFree(port)) {
      return port;
    }
  }
  return null;
}

async function main() {
  const requestedPort = readRequestedPort();
  const port = await findPort(requestedPort);

  if (port == null) {
    console.error(
      `[dev] No open port found in range ${requestedPort}-${requestedPort + MAX_TRIES - 1}.`
    );
    process.exit(1);
  }

  if (port !== requestedPort) {
    console.warn(`[dev] Port ${requestedPort} is busy, starting Next.js on ${port}.`);
  }

  const nextBin = path.join(__dirname, "..", "node_modules", "next", "dist", "bin", "next");
  const child = spawn(process.execPath, [nextBin, "dev", "--port", String(port)], {
    stdio: "inherit",
    env: {
      ...process.env,
      NODE_OPTIONS: withNodeOption(process.env.NODE_OPTIONS, "--no-deprecation"),
      PORT: String(port),
    },
  });

  child.on("exit", (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 0);
  });
}

main().catch((error) => {
  console.error("[dev] Failed to start Next.js:", error);
  process.exit(1);
});
