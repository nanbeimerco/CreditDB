/**
 * CreditDB Electron Main Process
 * Completely isolated from AnimeLatentPredict (com.creditdb.desktop).
 * Serves the static dashboard locally with zero external runtime dependencies.
 */

const { app, BrowserWindow } = require("electron");
const path = require("path");
const http = require("http");
const fs = require("fs");

let mainWindow = null;
let server = null;

// Determine docs root
function getDocsDir() {
  return path.join(app.getAppPath(), "docs");
}

// MIME types
const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

// Start embedded micro HTTP server to serve static docs cleanly
function startLocalServer(callback) {
  const docsDir = getDocsDir();

  server = http.createServer((req, res) => {
    let reqPath = decodeURIComponent(req.url.split("?")[0]);
    if (reqPath === "/" || reqPath === "") {
      reqPath = "/index.html";
    }

    const filePath = path.join(docsDir, reqPath);

    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.writeHead(404, { "Content-Type": "text/plain" });
        res.end("Not Found");
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      const contentType = MIME_TYPES[ext] || "application/octet-stream";
      res.writeHead(200, {
        "Content-Type": contentType,
        "Cache-Control": "no-cache",
      });
      res.end(data);
    });
  });

  // Listen on random available port on localhost
  server.listen(0, "127.0.0.1", () => {
    const port = server.address().port;
    callback(port);
  });
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1024,
    minHeight: 700,
    title: "CreditDB - アニメ作品・偏差値・制作陣能力評価 Web図鑑",
    backgroundColor: "#000000",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      backgroundThrottling: false,
    },
    autoHideMenuBar: true,
    show: false,
  });

  mainWindow.loadURL(`http://127.0.0.1:${port}`);

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// Single instance lock
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    startLocalServer((port) => {
      createWindow(port);
    });

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        startLocalServer((port) => {
          createWindow(port);
        });
      }
    });
  });

  app.on("window-all-closed", () => {
    if (server) {
      server.close();
    }
    if (process.platform !== "darwin") {
      app.quit();
    }
  });
}
