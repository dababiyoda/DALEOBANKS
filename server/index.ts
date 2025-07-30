import express from "express";
import { createServer } from "http";
import { setupVite, serveStatic, log } from "./vite";
import { spawn } from "child_process";
import path from "path";
import { createProxyMiddleware } from "http-proxy-middleware";

const isProduction = process.env.NODE_ENV === "production";
const PORT = parseInt(process.env.PORT || "5000");
const BACKEND_PORT = 5001; // Python backend on different port

// Start the Python FastAPI server on a different port
const pythonPath = process.env.PYTHON_PATH || "python3";
const appPath = path.resolve(process.cwd(), "app.py");

const pythonProcess = spawn(pythonPath, [appPath], {
  stdio: "inherit",
  env: {
    ...process.env,
    PORT: BACKEND_PORT.toString()
  }
});

pythonProcess.on("error", (err) => {
  console.error("Failed to start Python server:", err);
  process.exit(1);
});

pythonProcess.on("exit", (code) => {
  console.log(`Python server exited with code ${code}`);
  process.exit(code || 0);
});

// Create Express app
const app = express();
const server = createServer(app);

// Proxy API and WebSocket requests to Python backend
app.use('/api', createProxyMiddleware({
  target: `http://localhost:${BACKEND_PORT}`,
  changeOrigin: true,
  ws: false,
  pathRewrite: {
    '^/api': '/api'  // Keep the /api prefix
  }
}));

app.use('/ws', createProxyMiddleware({
  target: `http://localhost:${BACKEND_PORT}`,
  changeOrigin: true,
  ws: true
}));

// Proxy other backend-specific routes
const backendRoutes = ['/health', '/toggle', '/mode', '/persona', '/notes', '/redirects', '/config', '/metrics', '/logs'];
backendRoutes.forEach(route => {
  app.use(route, createProxyMiddleware({
    target: `http://localhost:${BACKEND_PORT}`,
    changeOrigin: true
  }));
});

// Setup frontend
async function startServer() {
  if (isProduction) {
    log("Starting production server...");
    serveStatic(app);
  } else {
    log("Starting development server...");
    await setupVite(app, server);
  }

  server.listen(PORT, "0.0.0.0", () => {
    log(`Server running at http://0.0.0.0:${PORT}`);
  });
}

// Wait a bit for Python to start, then start Express
setTimeout(() => {
  startServer().catch(err => {
    console.error("Failed to start server:", err);
    process.exit(1);
  });
}, 2000);

// Handle graceful shutdown
process.on("SIGINT", () => {
  console.log("Shutting down...");
  pythonProcess.kill("SIGINT");
  server.close();
  process.exit(0);
});

process.on("SIGTERM", () => {
  console.log("Shutting down...");
  pythonProcess.kill("SIGTERM");
  server.close();
  process.exit(0);
});
