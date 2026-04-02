const path = require("path");

const rootDir = __dirname;
const runDir = path.join(rootDir, "run");
const logDir = path.join(runDir, "logs");

const wsHost = process.env.WSOCR_WS_HOST || "0.0.0.0";
const wsPort = process.env.WSOCR_WS_PORT || "8765";
const ocrBackend = process.env.WSOCR_OCR_BACKEND || "paddleocr";
const paddleDevice = process.env.WSOCR_PADDLE_DEVICE || "auto";
const logLevel = process.env.WSOCR_LOG_LEVEL || "INFO";

module.exports = {
  apps: [
    {
      name: "wechat-stream-ocr",
      cwd: rootDir,
      script: path.join(rootDir, ".venv", "bin", "python"),
      args: [
        "-u",
        "-m",
        "wechat_stream_ocr.main",
        "--ws-host",
        wsHost,
        "--ws-port",
        wsPort,
        "--ocr-backend",
        ocrBackend,
        "--log-level",
        logLevel,
      ],
      interpreter: "none",
      env: {
        PYTHONPATH: path.join(rootDir, "src"),
        PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK:
          process.env.PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK || "True",
        WSOCR_WS_HOST: wsHost,
        WSOCR_WS_PORT: wsPort,
        WSOCR_OCR_BACKEND: ocrBackend,
        WSOCR_PADDLE_DEVICE: paddleDevice,
        WSOCR_LOG_LEVEL: logLevel,
      },
      out_file: path.join(logDir, "wechat_stream_ocr-out.log"),
      error_file: path.join(logDir, "wechat_stream_ocr-error.log"),
      merge_logs: true,
      time: true,
      autorestart: true,
      restart_delay: 2000,
      min_uptime: "10s",
      max_restarts: 10,
    },
  ],
};
