//! Supervises the Python backend process and speaks JSON-RPC 2.0 over its stdin/stdout.
//!
//! * the WebView never touches the process: it only calls `backend_call`, which is allow-listed
//! * requests get a numeric id and a oneshot channel; responses are matched by id
//! * notifications (`job.progress`) are re-emitted as Tauri events `backend://notification`
//! * lifecycle: Starting → Ready (after a successful ping) → Restarting (crash, up to 3 times)
//!   → Failed; every change is emitted as `backend://status`; every call has a timeout

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use tokio::sync::oneshot;

pub const MAX_RESTARTS: u32 = 3;

/// Where the backend executable lives, in order of preference:
/// 1. `DOCMASTER_BACKEND` (explicit path, tests)
/// 2. the one-dir bundle shipped as a resource (`resources/backend/docmaster-backend[.exe]`)
/// 3. the same folder inside the source tree (dev builds)
/// 4. the legacy one-file sidecar (`externalBin`), kept as a fallback
fn backend_command(app: &AppHandle) -> Result<tauri_plugin_shell::process::Command, String> {
    let exe = if cfg!(windows) { "docmaster-backend.exe" } else { "docmaster-backend" };
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(p) = std::env::var("DOCMASTER_BACKEND") { candidates.push(PathBuf::from(p)); }
    if let Ok(res) = app.path().resource_dir() { candidates.push(res.join("resources").join("backend").join(exe)); }
    candidates.push(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources").join("backend").join(exe));
    if let Some(path) = candidates.iter().find(|p| p.is_file()) {
        eprintln!("[app] backend: {}", path.display());
        return Ok(app.shell().command(path));
    }
    eprintln!("[app] backend: one-file sidecar (fallback)");
    app.shell().sidecar("docmaster-backend").map_err(|e| format!("backend executable not found: {e}"))
}
const STARTUP_TIMEOUT: Duration = Duration::from_secs(90);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RpcError {
    pub code: i64,
    pub message: String,
    #[serde(default)]
    pub data: Value,
}

impl RpcError {
    fn local(code: i64, message: impl Into<String>) -> Self {
        Self { code, message: message.into(), data: json!({ "code": "BACKEND_UNAVAILABLE" }) }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "state", rename_all = "snake_case")]
pub enum BackendStatus {
    Starting { attempt: u32 },
    Ready { version: String, pid: u64, frozen: bool },
    Restarting { attempt: u32, reason: String },
    Failed { reason: String },
}

type Pending = HashMap<u64, oneshot::Sender<Result<Value, RpcError>>>;

pub struct Backend {
    child: Mutex<Option<CommandChild>>,
    pending: Mutex<Pending>,
    next_id: AtomicU64,
    status: Mutex<BackendStatus>,
    spawn_args: Mutex<Option<(PathBuf, PathBuf, PathBuf, PathBuf)>>,
    restarts: AtomicU32,
    shutting_down: AtomicBool,
    pub notifications: AtomicU64,
}

/// Methods the WebView is allowed to invoke. `system.shutdown` is deliberately absent.
pub const ALLOWED_METHODS: &[&str] = &["system.ping", "system.diagnostics", "templates.list", "templates.rescan", "templates.example_values", "docgen.generate", "docgen.convert_pdf", "jobs.get", "settings.get", "settings.set",
    "email.prepare_eml", "email.imap_get_account", "email.imap_test", "email.imap_save_account", "email.imap_remove_account", "email.create_imap_draft",
    "history.list", "history.delete", "history.clear", "privacy.summary", "privacy.clear_logs", "privacy.cleanup", "network.check"];

impl Backend {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            pending: Mutex::new(HashMap::new()),
            next_id: AtomicU64::new(1),
            status: Mutex::new(BackendStatus::Starting { attempt: 0 }),
            spawn_args: Mutex::new(None),
            restarts: AtomicU32::new(0),
            shutting_down: AtomicBool::new(false),
            notifications: AtomicU64::new(0),
        }
    }

    pub fn status(&self) -> BackendStatus {
        self.status.lock().unwrap().clone()
    }

    fn set_status(&self, app: &AppHandle, status: BackendStatus) {
        eprintln!("[app] backend status: {}", serde_json::to_string(&status).unwrap_or_default());
        *self.status.lock().unwrap() = status.clone();
        let _ = app.emit("backend://status", status);
    }

    /// Start (or restart) the backend process and verify it answers a ping.
    pub fn start(&self, app: &AppHandle, templates_dir: &Path, output_dir: &Path, data_dir: &Path, user_templates_dir: &Path) -> Result<(), String> {
        *self.spawn_args.lock().unwrap() = Some((templates_dir.to_path_buf(), output_dir.to_path_buf(), data_dir.to_path_buf(), user_templates_dir.to_path_buf()));
        self.spawn(app)
    }

    fn spawn(&self, app: &AppHandle) -> Result<(), String> {
        let (templates_dir, output_dir, data_dir, user_templates_dir) = self.spawn_args.lock().unwrap().clone().ok_or("backend not configured")?;
        let attempt = self.restarts.load(Ordering::SeqCst);
        self.set_status(app, BackendStatus::Starting { attempt });
        let (mut rx, child) = backend_command(app)?
            .args(["--templates-dir", &templates_dir.to_string_lossy(), "--output-dir", &output_dir.to_string_lossy(), "--data-dir", &data_dir.to_string_lossy(), "--user-templates-dir", &user_templates_dir.to_string_lossy()])
            .spawn()
            .map_err(|e| format!("failed to start backend: {e}"))?;
        *self.child.lock().unwrap() = Some(child);

        // reader task: responses, notifications, termination
        let reader_app = app.clone();
        tauri::async_runtime::spawn(async move {
            while let Some(event) = rx.recv().await {
                let backend = reader_app.state::<Backend>();
                match event {
                    CommandEvent::Stdout(bytes) => backend.handle_line(&reader_app, String::from_utf8_lossy(&bytes).trim()),
                    CommandEvent::Stderr(bytes) => eprintln!("[backend] {}", String::from_utf8_lossy(&bytes).trim_end()),
                    CommandEvent::Terminated(payload) => {
                        backend.on_terminated(&reader_app, payload.code);
                        break;
                    }
                    _ => {}
                }
            }
        });

        // health task: the process is only "ready" once it answers
        let health_app = app.clone();
        tauri::async_runtime::spawn(async move {
            let backend = health_app.state::<Backend>();
            match backend.call("system.ping", json!({}), STARTUP_TIMEOUT).await {
                Ok(v) => backend.set_status(&health_app, BackendStatus::Ready {
                    version: v["version"].as_str().unwrap_or("?").to_string(),
                    pid: v["pid"].as_u64().unwrap_or(0),
                    frozen: v["frozen"].as_bool().unwrap_or(false),
                }),
                Err(e) => {
                    eprintln!("[app] backend did not become ready: {}", e.message);
                    backend.shutdown_child();
                }
            }
        });
        Ok(())
    }

    fn on_terminated(&self, app: &AppHandle, code: Option<i32>) {
        *self.child.lock().unwrap() = None;
        self.fail_all("backend process terminated");
        let _ = app.emit("backend://terminated", code);
        if self.shutting_down.load(Ordering::SeqCst) {
            return;
        }
        let attempt = self.restarts.fetch_add(1, Ordering::SeqCst) + 1;
        if attempt > MAX_RESTARTS {
            self.set_status(app, BackendStatus::Failed { reason: format!("backend crashed {MAX_RESTARTS} times (last exit code {code:?})") });
            return;
        }
        self.set_status(app, BackendStatus::Restarting { attempt, reason: format!("exit code {code:?}") });
        let app = app.clone();
        tauri::async_runtime::spawn(async move {
            tokio::time::sleep(Duration::from_millis(500 * attempt as u64)).await;
            if let Err(e) = app.state::<Backend>().spawn(&app) {
                app.state::<Backend>().set_status(&app, BackendStatus::Failed { reason: e });
            }
        });
    }

    fn handle_line(&self, app: &AppHandle, line: &str) {
        if line.is_empty() {
            return;
        }
        let msg: Value = match serde_json::from_str(line) {
            Ok(v) => v,
            Err(_) => {
                eprintln!("[backend] non-JSON on stdout: {line}");
                return;
            }
        };
        match msg.get("id").and_then(Value::as_u64) {
            Some(id) => {
                if let Some(tx) = self.pending.lock().unwrap().remove(&id) {
                    let result = match msg.get("error") {
                        Some(err) => Err(serde_json::from_value(err.clone())
                            .unwrap_or_else(|_| RpcError::local(-32000, "malformed error from backend"))),
                        None => Ok(msg.get("result").cloned().unwrap_or(Value::Null)),
                    };
                    let _ = tx.send(result);
                }
            }
            None => {
                if let Some(method) = msg.get("method").and_then(Value::as_str) {
                    self.notifications.fetch_add(1, Ordering::Relaxed);
                    let _ = app.emit("backend://notification", json!({ "method": method, "params": msg.get("params").cloned().unwrap_or(Value::Null) }));
                }
            }
        }
    }

    fn fail_all(&self, reason: &str) {
        for (_, tx) in self.pending.lock().unwrap().drain() {
            let _ = tx.send(Err(RpcError::local(-1, reason)));
        }
    }

    pub async fn call(&self, method: &str, params: Value, timeout: Duration) -> Result<Value, RpcError> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let (tx, rx) = oneshot::channel();
        self.pending.lock().unwrap().insert(id, tx);
        let line = serde_json::to_string(&json!({ "jsonrpc": "2.0", "id": id, "method": method, "params": params })).unwrap() + "\n";
        {
            let mut guard = self.child.lock().unwrap();
            let Some(child) = guard.as_mut() else {
                self.pending.lock().unwrap().remove(&id);
                return Err(RpcError::local(-1, "backend is not running"));
            };
            if let Err(e) = child.write(line.as_bytes()) {
                self.pending.lock().unwrap().remove(&id);
                return Err(RpcError::local(-1, format!("cannot write to backend: {e}")));
            }
        }
        match tokio::time::timeout(timeout, rx).await {
            Ok(Ok(result)) => result,
            Ok(Err(_)) => Err(RpcError::local(-2, "backend dropped the request")),
            Err(_) => {
                self.pending.lock().unwrap().remove(&id);
                Err(RpcError::local(-3, format!("backend did not answer {method} within {} s", timeout.as_secs())))
            }
        }
    }

    fn shutdown_child(&self) {
        let child = self.child.lock().unwrap().take();
        if let Some(mut child) = child {
            let _ = child.write(b"{\"jsonrpc\":\"2.0\",\"id\":0,\"method\":\"system.shutdown\",\"params\":{}}\n");
            std::thread::sleep(Duration::from_millis(500));
            let _ = child.kill();
        }
    }

    /// Final shutdown on app exit: no restart afterwards.
    pub fn shutdown(&self) {
        self.shutting_down.store(true, Ordering::SeqCst);
        self.shutdown_child();
    }
}
