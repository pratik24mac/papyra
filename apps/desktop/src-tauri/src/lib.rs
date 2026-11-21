mod auth;
mod backend;
mod files;

use backend::{Backend, BackendStatus, RpcError, ALLOWED_METHODS};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, RunEvent, State};

#[tauri::command]
async fn backend_call(app: AppHandle, backend: State<'_, Backend>, method: String, params: Option<Value>) -> Result<Value, RpcError> {
    auth::require_auth(&app)?;
    if !ALLOWED_METHODS.contains(&method.as_str()) {
        return Err(RpcError { code: -32601, message: format!("method not allowed from the UI: {method}"), data: json!({ "code": "METHOD_NOT_ALLOWED" }) });
    }
    let timeout = if method.starts_with("docgen.") { Duration::from_secs(1200) } else if method.starts_with("email.") { Duration::from_secs(90) } else { Duration::from_secs(20) };
    backend.call(&method, params.unwrap_or_else(|| json!({})), timeout).await
}

#[tauri::command]
fn backend_status(backend: State<'_, Backend>) -> BackendStatus {
    backend.status()
}

/// Reveal the app data folder (settings, history, logs) in the file manager.
#[tauri::command]
async fn open_data_dir(app: AppHandle) -> Result<(), RpcError> {
    auth::require_auth(&app)?;
    use tauri_plugin_opener::OpenerExt;
    let data = std::env::var("DOCMASTER_DATA_DIR").map(PathBuf::from)
        .unwrap_or_else(|_| app.path().app_data_dir().unwrap_or_else(|_| std::env::temp_dir().join("papyra")));
    app.opener().open_path(data.to_string_lossy(), None::<&str>).map_err(|e| RpcError { code: -32040, message: e.to_string(), data: json!({ "code": "OPEN_FAILED" }) })
}

/// Native folder picker for the output folder (the choice is then saved through `settings.set`).
#[tauri::command]
async fn choose_output_dir(app: AppHandle) -> Result<Option<String>, RpcError> {
    auth::require_auth(&app)?;
    use tauri_plugin_dialog::DialogExt;
    let picked = app.dialog().file().set_title("Choose the folder for generated documents").blocking_pick_folder();
    Ok(picked.and_then(|p| p.into_path().ok()).map(|p| p.to_string_lossy().to_string()))
}

fn templates_dir(app: &AppHandle) -> PathBuf {
    if let Ok(p) = std::env::var("DOCMASTER_TEMPLATES_DIR") {
        return PathBuf::from(p);
    }
    if cfg!(debug_assertions) {
        if let Ok(p) = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../templates").canonicalize() {
            return p;
        }
    }
    app.path().resource_dir().map(|r| r.join("resources").join("templates")).unwrap_or_default()
}

/// User-added templates: a folder the user can edit, next to the generated documents.
pub(crate) fn user_templates_dir(app: &AppHandle) -> PathBuf {
    std::env::var("DOCMASTER_USER_TEMPLATES_DIR").map(PathBuf::from).unwrap_or_else(|_| output_dir(app).join("templates"))
}

/// Open the LibreOffice download page in the user's browser (explicit user action; the app
/// itself opens no connection).
#[tauri::command]
async fn open_libreoffice_download(app: AppHandle) -> Result<(), RpcError> {
    auth::require_auth(&app)?;
    use tauri_plugin_opener::OpenerExt;
    app.opener().open_url("https://www.libreoffice.org/download/download-libreoffice/", None::<&str>)
        .map_err(|e| RpcError { code: -32040, message: e.to_string(), data: json!({ "code": "OPEN_FAILED" }) })
}

/// Reveal the user templates folder in the file manager (created by the backend on start).
#[tauri::command]
async fn open_templates_dir(app: AppHandle) -> Result<String, RpcError> {
    auth::require_auth(&app)?;
    use tauri_plugin_opener::OpenerExt;
    let dir = user_templates_dir(&app);
    let _ = std::fs::create_dir_all(&dir);
    app.opener().open_path(dir.to_string_lossy(), None::<&str>).map_err(|e| RpcError { code: -32040, message: e.to_string(), data: json!({ "code": "OPEN_FAILED" }) })?;
    Ok(dir.to_string_lossy().to_string())
}

pub(crate) fn output_dir(app: &AppHandle) -> PathBuf {
    std::env::var("DOCMASTER_OUTPUT_DIR").map(PathBuf::from).unwrap_or_else(|_| {
        app.path().document_dir().unwrap_or_else(|_| std::env::temp_dir()).join("Papyra")
    })
}

fn selftest_out(line: &str) {
    println!("{line}");
    if let Ok(path) = std::env::var("DOCMASTER_SELFTEST_LOG") {
        use std::io::Write;
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
            let _ = writeln!(f, "{line}");
        }
    }
}

/// `DOCMASTER_SELFTEST=1`: exercise the whole link without a human and exit 0/1.
/// `DOCMASTER_SELFTEST_LOG=<file>` additionally appends every result line to that file.
async fn selftest(app: AppHandle, templates: PathBuf) -> i32 {
    let backend = app.state::<Backend>();
    let mut ok = true;
    fn step(ok: &mut bool, name: &str, started: Instant, res: &Result<Value, RpcError>, pass: bool) {
        selftest_out(&format!("SELFTEST {name:<14} {:>6} ms  {}  {}", started.elapsed().as_millis(), if pass { "PASS" } else { "FAIL" },
                 serde_json::to_string(res).unwrap_or_default().chars().take(220).collect::<String>()));
        *ok &= pass;
    }
    let t = Instant::now();
    let r = backend.call("system.ping", json!({}), Duration::from_secs(90)).await;
    step(&mut ok, "ping", t, &r, r.as_ref().map(|v| v["name"] == "docmaster-backend").unwrap_or(false));
    let t = Instant::now();
    let r = backend.call("system.diagnostics", json!({}), Duration::from_secs(30)).await;
    step(&mut ok, "diagnostics", t, &r, r.as_ref().map(|v| v["libreoffice"]["found"] == true).unwrap_or(false));
    let t = Instant::now();
    let r = backend.call("templates.list", json!({}), Duration::from_secs(20)).await;
    step(&mut ok, "templates", t, &r, r.as_ref().map(|v| v["templates"][0]["id"] == "resume-ats").unwrap_or(false));
    let t = Instant::now();
    let r = backend.call("docgen.generate", json!({ "template_id": "resume-ats", "values": { "full_name": "" } }), Duration::from_secs(20)).await;
    step(&mut ok, "invalid-values", t, &r, matches!(&r, Err(e) if e.data["code"] == "VALIDATION_ERROR"));
    let values: Value = std::fs::read_to_string(templates.join("resume-ats/v1/values.example.json")).ok()
        .and_then(|s| serde_json::from_str(&s).ok()).unwrap_or(Value::Null);
    let before = backend.notifications.load(std::sync::atomic::Ordering::Relaxed);
    let t = Instant::now();
    let r = backend.call("docgen.generate", json!({ "template_id": "resume-ats", "values": values, "job_id": "selftest" }), Duration::from_secs(300)).await;
    step(&mut ok, "generate", t, &r, r.as_ref().map(|v| v["pages"] == 2).unwrap_or(false));
    // staleness: edit the DOCX externally (append a byte to the zip comment area is enough to change its hash)
    let docx = r.as_ref().ok().and_then(|v| v["docx_path"].as_str().map(String::from)).unwrap_or_default();
    let t = Instant::now();
    let r2 = backend.call("jobs.get", json!({ "job_id": "selftest" }), Duration::from_secs(20)).await;
    step(&mut ok, "jobs.get", t, &r2, r2.as_ref().map(|v| v["state"]["pdf_stale"] == false).unwrap_or(false));
    if let Ok(mut f) = std::fs::OpenOptions::new().append(true).open(&docx) { use std::io::Write; let _ = f.write_all(b"\n"); }
    let t = Instant::now();
    let r2 = backend.call("jobs.get", json!({ "job_id": "selftest" }), Duration::from_secs(20)).await;
    step(&mut ok, "stale-detect", t, &r2, r2.as_ref().map(|v| v["state"]["pdf_stale"] == true && v["state"]["docx_changed"] == true).unwrap_or(false));
    let t = Instant::now();
    let r2 = backend.call("docgen.convert_pdf", json!({ "job_id": "selftest" }), Duration::from_secs(300)).await;
    step(&mut ok, "reconvert", t, &r2, r2.as_ref().map(|v| v["pages"] == 2).unwrap_or(false));
    let t = Instant::now();
    let r2 = backend.call("jobs.get", json!({ "job_id": "selftest" }), Duration::from_secs(20)).await;
    step(&mut ok, "fresh-again", t, &r2, r2.as_ref().map(|v| v["state"]["pdf_stale"] == false).unwrap_or(false));
    let t = Instant::now();
    let r2 = files::job_file(&app, &output_dir(&app), "selftest", "pdf").await.map(|p| json!(p.to_string_lossy()));
    step(&mut ok, "path-check", t, &r2, r2.is_ok());
    let t = Instant::now();
    let r2 = files::job_file(&app, &output_dir(&app), "../etc", "pdf").await.map(|p| json!(p.to_string_lossy()));
    step(&mut ok, "path-reject", t, &r2, r2.is_err());
    let t = Instant::now();
    let r2 = backend.call("email.prepare_eml", json!({ "job_id": "selftest", "message": { "to": "hr@example.com", "cc": "Zoë <zoe@example.com>", "subject": "Résumé — selftest", "body": "Hello" } }), Duration::from_secs(60)).await;
    let eml_ok = r2.as_ref().ok().and_then(|v| v["eml_path"].as_str().map(|p| std::path::Path::new(p).exists())).unwrap_or(false);
    step(&mut ok, "prepare-eml", t, &r2, eml_ok);
    let t = Instant::now();
    let r2 = backend.call("email.prepare_eml", json!({ "job_id": "selftest", "message": { "to": "not-an-address", "subject": "x", "body": "" } }), Duration::from_secs(60)).await;
    step(&mut ok, "eml-bad-addr", t, &r2, matches!(&r2, Err(e) if e.data["code"] == "EMAIL_INVALID_ADDRESS"));
    let t = Instant::now();
    let r2 = backend.call("email.imap_get_account", json!({}), Duration::from_secs(20)).await;
    step(&mut ok, "imap-account", t, &r2, r2.as_ref().map(|v| v["configured"].is_boolean()).unwrap_or(false));
    let t = Instant::now();
    let r2 = backend.call("email.create_imap_draft", json!({ "job_id": "selftest", "message": { "to": "hr@example.com", "subject": "x", "body": "" } }), Duration::from_secs(60)).await;
    step(&mut ok, "imap-no-acct", t, &r2, matches!(&r2, Err(e) if e.data["code"] == "EMAIL_ACCOUNT_MISSING" || e.data["code"] == "EMAIL_NETWORK_ERROR" || e.data["code"] == "EMAIL_AUTH_FAILED"));
    let t = Instant::now();
    let r2 = backend.call("history.list", json!({}), Duration::from_secs(20)).await;
    step(&mut ok, "history.list", t, &r2, r2.as_ref().map(|v| v["jobs"].as_array().map(|a| a.iter().any(|j| j["job_id"] == "selftest" && j["drafts"] == 1)).unwrap_or(false)).unwrap_or(false));
    let t = Instant::now();
    let r2 = backend.call("privacy.summary", json!({}), Duration::from_secs(20)).await;
    step(&mut ok, "privacy", t, &r2, r2.as_ref().map(|v| v["telemetry"] == false && v["stored"].as_array().map(|a| a.len() == 5).unwrap_or(false)).unwrap_or(false));
    let t = Instant::now();
    let r2 = backend.call("settings.set", json!({ "key": "offline_mode", "value": true }), Duration::from_secs(20)).await;
    step(&mut ok, "offline-on", t, &r2, r2.as_ref().map(|v| v["offline_mode"] == true).unwrap_or(false));
    let t = Instant::now();
    let r2 = backend.call("network.check", json!({}), Duration::from_secs(20)).await;
    step(&mut ok, "offline-blocks", t, &r2, matches!(&r2, Err(e) if e.data["code"] == "OFFLINE_MODE"));
    let _ = backend.call("settings.set", json!({ "key": "offline_mode", "value": false }), Duration::from_secs(20)).await;
    let sub = output_dir(&app).join("chosen-folder");
    let t = Instant::now();
    let r2 = backend.call("settings.set", json!({ "key": "output_dir", "value": sub.to_string_lossy() }), Duration::from_secs(20)).await;
    step(&mut ok, "settings.set", t, &r2, r2.as_ref().map(|v| v["output_dir"].as_str().map(|s| s.ends_with("chosen-folder")).unwrap_or(false)).unwrap_or(false));
    let t = Instant::now();
    let r2 = backend.call("docgen.generate", json!({ "template_id": "resume-ats", "values": values, "job_id": "selftest2" }), Duration::from_secs(300)).await;
    step(&mut ok, "gen-in-chosen", t, &r2, r2.as_ref().map(|v| v["docx_path"].as_str().map(|s| s.contains("chosen-folder")).unwrap_or(false)).unwrap_or(false));
    let t = Instant::now();
    let r2 = backend.call("settings.set", json!({ "key": "output_dir", "value": null }), Duration::from_secs(20)).await;
    step(&mut ok, "settings.reset", t, &r2, r2.as_ref().map(|v| v["output_dir"] == v["defaults"]["output_dir"]).unwrap_or(false));
    let notes = backend.notifications.load(std::sync::atomic::Ordering::Relaxed) - before;
    selftest_out(&format!("SELFTEST notifications  {notes} progress events received  {}", if notes >= 12 { "PASS" } else { "FAIL" }));
    ok &= notes >= 12;
    let t = Instant::now();
    let r2 = backend.call("history.delete", json!({ "job_id": "selftest2", "delete_files": true }), Duration::from_secs(20)).await;
    step(&mut ok, "history.delete", t, &r2, r2.as_ref().map(|v| v["removed_row"] == true && v["removed_files"] == true).unwrap_or(false));
    let t = Instant::now();
    let r = backend.call("system.ping", json!({}), Duration::from_secs(10)).await;
    step(&mut ok, "ping-after", t, &r, r.is_ok());
    selftest_out(&format!("SELFTEST RESULT {}", if ok { "PASS" } else { "FAIL" }));
    if ok { 0 } else { 1 }
}

pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(Backend::new())
        .manage(auth::Auth::new())
        .invoke_handler(tauri::generate_handler![backend_call, backend_status, choose_output_dir, open_data_dir, open_templates_dir, open_libreoffice_download, auth::login, auth::logout, auth::auth_status, files::read_job_pdf, files::open_job_file, files::reveal_job_folder, files::save_job_copy, files::open_job_in_browser])
        .setup(|app| {
            let handle = app.handle().clone();
            let templates = templates_dir(&handle);
            let output = output_dir(&handle);
            let data = std::env::var("DOCMASTER_DATA_DIR").map(PathBuf::from)
                .unwrap_or_else(|_| handle.path().app_data_dir().unwrap_or_else(|_| std::env::temp_dir().join("papyra")));
            eprintln!("[app] templates: {} | default output: {} | data: {}", templates.display(), output.display(), data.display());
            let user_templates = user_templates_dir(&handle);
            app.state::<Backend>().start(&handle, &templates, &output, &data, &user_templates)?;
            if std::env::var("DOCMASTER_SELFTEST").is_ok() {
                tauri::async_runtime::spawn(async move {
                    let code = selftest(handle.clone(), templates).await;
                    handle.state::<Backend>().shutdown();
                    handle.exit(code);
                });
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            app.state::<Backend>().shutdown();
        }
    });
}
