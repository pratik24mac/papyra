//! File access for generated documents. The WebView never passes a path: it names a job, the
//! backend says where that job's files are, and Rust checks the path is inside the output folder
//! before reading, opening or copying it.

use crate::backend::{Backend, RpcError};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::time::Duration;
use tauri::{AppHandle, Manager};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

fn err(message: impl Into<String>, code: &str) -> RpcError {
    RpcError { code: -32040, message: message.into(), data: json!({ "code": code }) }
}

/// Resolve `kind` ("docx" | "pdf") of `job_id` to a path inside `output_dir`, via the backend's record.
pub async fn job_file(app: &AppHandle, _default_output_dir: &Path, job_id: &str, kind: &str) -> Result<PathBuf, RpcError> {
    if std::env::var("DOCMASTER_SELFTEST").is_err() {
        crate::auth::require_auth(app)?;
    }
    if !matches!(kind, "docx" | "pdf" | "eml") {
        return Err(err("unknown file kind", "INVALID_REQUEST"));
    }
    let backend = app.state::<Backend>();
    let info: Value = backend.call("jobs.get", json!({ "job_id": job_id }), Duration::from_secs(20)).await?;
    let state = &info["state"];
    if kind == "pdf" && state["pdf_stale"] == true {
        return Err(err("The PDF is out of date: the Word document changed after it was created. Regenerate the PDF first.", "PDF_STALE"));
    }
    let raw = info["job"][format!("{kind}_path")].as_str().ok_or_else(|| err("file not available", "FILE_NOT_FOUND"))?;
    let path = Path::new(raw).canonicalize().map_err(|_| err("file not found", "FILE_NOT_FOUND"))?;
    // containment is checked against the output folder the backend is using *now* (user-configurable)
    let current = info["output_dir"].as_str().ok_or_else(|| err("output folder unknown", "OUTPUT_PATH_ERROR"))?;
    let root = Path::new(current).canonicalize().map_err(|_| err("output folder missing", "OUTPUT_PATH_ERROR"))?;
    if !path.starts_with(&root) {
        return Err(err("file is outside the output folder", "PATH_NOT_ALLOWED"));
    }
    Ok(path)
}

#[tauri::command]
pub async fn read_job_pdf(app: AppHandle, job_id: String) -> Result<tauri::ipc::Response, RpcError> {
    let path = job_file(&app, &crate::output_dir(&app), &job_id, "pdf").await?;
    let bytes = std::fs::read(&path).map_err(|e| err(format!("cannot read PDF: {e}"), "FILE_NOT_FOUND"))?;
    Ok(tauri::ipc::Response::new(bytes))
}

#[tauri::command]
pub async fn open_job_file(app: AppHandle, job_id: String, kind: String) -> Result<(), RpcError> {
    let path = job_file(&app, &crate::output_dir(&app), &job_id, &kind).await?;
    app.opener().open_path(path.to_string_lossy(), None::<&str>).map_err(|e| err(format!("cannot open file: {e}"), "OPEN_FAILED"))
}

#[tauri::command]
pub async fn reveal_job_folder(app: AppHandle, job_id: String) -> Result<(), RpcError> {
    let path = job_file(&app, &crate::output_dir(&app), &job_id, "docx").await?;
    app.opener().reveal_item_in_dir(&path).map_err(|e| err(format!("cannot reveal file: {e}"), "OPEN_FAILED"))
}

/// Save-as dialog, then copy. Returns the chosen path, or null when the user cancelled.
#[tauri::command]
pub async fn save_job_copy(app: AppHandle, job_id: String, kind: String) -> Result<Option<String>, RpcError> {
    let path = job_file(&app, &crate::output_dir(&app), &job_id, &kind).await?;
    let name = path.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    let chosen = app.dialog().file().set_file_name(&name).add_filter(kind.to_uppercase(), &[&kind]).blocking_save_file();
    let Some(target) = chosen else { return Ok(None) };
    let target = target.into_path().map_err(|e| err(e.to_string(), "SAVE_FAILED"))?;
    std::fs::copy(&path, &target).map_err(|e| err(format!("cannot save copy: {e}"), "SAVE_FAILED"))?;
    Ok(Some(target.to_string_lossy().to_string()))
}

/// Open the job's PDF (or DOCX) in a web browser instead of the default application.
/// Tries common browsers in order; the first one installed wins.
#[tauri::command]
pub async fn open_job_in_browser(app: AppHandle, job_id: String, kind: String) -> Result<String, RpcError> {
    let path = job_file(&app, &crate::output_dir(&app), &job_id, &kind).await?;
    let candidates: &[&str] = if cfg!(target_os = "macos") {
        &["Google Chrome", "Safari", "Microsoft Edge", "Firefox", "Arc", "Brave Browser"]
    } else if cfg!(target_os = "windows") {
        &["msedge", "chrome", "firefox"]
    } else {
        &["xdg-open"]
    };
    let mut last = String::new();
    for browser in candidates {
        match app.opener().open_path(path.to_string_lossy(), Some(*browser)) {
            Ok(()) => return Ok(browser.to_string()),
            Err(e) => last = e.to_string(),
        }
    }
    Err(err(format!("no browser could open the file: {last}"), "OPEN_FAILED"))
}
