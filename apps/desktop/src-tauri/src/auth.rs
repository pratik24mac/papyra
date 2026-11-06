//! Fixed-credential sign-in. The password is never stored: only a salted SHA-256 digest lives
//! in the binary, verification is constant-time, and failed attempts are slowed down.
//! Every command that reaches the backend or the generated files requires `require_auth`.
//! Change the credentials with `tools/set_password.py`.

use crate::backend::RpcError;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::time::Duration;
use subtle::ConstantTimeEq;
use tauri::{AppHandle, Manager, State};

pub const USERNAME: &str = "admin";
const SALT: &str = "docmaster-v1";
// sha256("docmaster-v1:" + password), hex
const PASSWORD_SHA256: &str = "cfe0f3931cb1b3069b71d229eae42df51ee6243a90ee82bfb287ad32126b20c9";

pub struct Auth {
    authenticated: AtomicBool,
    failures: AtomicU32,
}

impl Auth {
    pub fn new() -> Self {
        Self { authenticated: AtomicBool::new(false), failures: AtomicU32::new(0) }
    }
    pub fn is_authenticated(&self) -> bool {
        self.authenticated.load(Ordering::SeqCst)
    }
}

pub fn verify(username: &str, password: &str) -> bool {
    let digest = hex::encode(Sha256::digest(format!("{SALT}:{password}").as_bytes()));
    let user_ok = username.as_bytes().ct_eq(USERNAME.as_bytes());
    let pass_ok = digest.as_bytes().ct_eq(PASSWORD_SHA256.as_bytes());
    bool::from(user_ok & pass_ok)
}

pub fn require_auth(app: &AppHandle) -> Result<(), RpcError> {
    if app.state::<Auth>().is_authenticated() {
        Ok(())
    } else {
        Err(RpcError { code: -32050, message: "Please sign in first.".into(), data: json!({ "code": "AUTH_REQUIRED" }) })
    }
}

#[tauri::command]
pub async fn login(auth: State<'_, Auth>, username: String, password: String) -> Result<String, RpcError> {
    let failures = auth.failures.load(Ordering::SeqCst);
    if failures > 0 {
        tokio::time::sleep(Duration::from_millis((500 * failures as u64).min(5000))).await;
    }
    if verify(username.trim(), &password) {
        auth.failures.store(0, Ordering::SeqCst);
        auth.authenticated.store(true, Ordering::SeqCst);
        Ok(USERNAME.to_string())
    } else {
        auth.failures.fetch_add(1, Ordering::SeqCst);
        Err(RpcError { code: -32051, message: "Incorrect username or password.".into(), data: json!({ "code": "AUTH_FAILED" }) })
    }
}

#[tauri::command]
pub fn logout(auth: State<'_, Auth>) {
    auth.authenticated.store(false, Ordering::SeqCst);
}

#[tauri::command]
pub fn auth_status(auth: State<'_, Auth>) -> Option<String> {
    auth.is_authenticated().then(|| USERNAME.to_string())
}

#[cfg(test)]
mod tests {
    use super::verify;
    #[test]
    fn accepts_the_fixed_credentials_only() {
        assert!(verify("admin", "DocMaster!2026"));
        assert!(!verify("admin", "docmaster!2026"));
        assert!(!verify("root", "DocMaster!2026"));
        assert!(!verify("", ""));
    }
}
