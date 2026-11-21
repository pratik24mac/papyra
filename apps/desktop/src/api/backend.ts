// The only way the UI reaches the backend. Inside Tauri it goes WebView → Rust `backend_call` →
// Python; in a plain browser (vite dev without Tauri) a mock serves static data so screens can be
// developed and screenshot-tested without the sidecar.
import type { AppSettings, BackendStatus, SelfCheck, HistoryRow, PrivacySummary, ReachabilityResult, ConvertResult, DraftMessage, EmlResult, ImapAccountInfo, ImapAccountInput, ImapDraftResult, Diagnostics, FileKind, GenerateResult, JobInfo, PingResult, ProgressEvent, RpcError, TemplateSummary, Values } from "./types";

type Unlisten = () => void;

export interface BackendApi {
  login(username: string, password: string): Promise<string>;
  logout(): Promise<void>;
  authStatus(): Promise<string | null>;
  ping(): Promise<PingResult>;
  diagnostics(): Promise<Diagnostics>;
  selfCheck(convert?: boolean): Promise<SelfCheck>;
  openLibreOfficeDownload(): Promise<void>;
  listTemplates(): Promise<TemplateSummary[]>;
  rescanTemplates(): Promise<TemplateSummary[]>;
  openTemplatesDir(): Promise<string>;
  generate(templateId: string, values: Values, jobId: string): Promise<GenerateResult>;
  exampleValues(templateId: string): Promise<Values>;
  status(): Promise<BackendStatus>;
  prepareEml(jobId: string, message: DraftMessage): Promise<EmlResult>;
  createImapDraft(jobId: string, message: DraftMessage): Promise<ImapDraftResult>;
  imapGetAccount(): Promise<ImapAccountInfo>;
  imapTest(account: ImapAccountInput, password: string): Promise<{ ok: boolean; drafts_folder: string; email: string }>;
  imapSaveAccount(account: ImapAccountInput, password: string): Promise<ImapAccountInfo>;
  imapRemoveAccount(): Promise<ImapAccountInfo>;
  settingsGet(): Promise<AppSettings>;
  settingsSet(key: "output_dir" | "offline_mode" | "keep_history", value: string | boolean | null): Promise<AppSettings>;
  historyList(limit?: number): Promise<{ jobs: HistoryRow[]; total: number }>;
  historyDelete(jobId: string, deleteFiles: boolean): Promise<{ removed_row: boolean; removed_files: boolean }>;
  historyClear(deleteFiles: boolean): Promise<{ removed_rows: number; removed_job_folders: number }>;
  privacySummary(): Promise<PrivacySummary>;
  privacyClearLogs(): Promise<{ cleared: number }>;
  privacyCleanup(): Promise<{ removed_temp_dirs: number; removed_partial_files: number }>;
  networkCheck(): Promise<ReachabilityResult>;
  openDataDir(): Promise<void>;
  chooseOutputDir(): Promise<string | null>;
  jobInfo(jobId: string): Promise<JobInfo>;
  convertPdf(jobId: string): Promise<ConvertResult>;
  readPdf(jobId: string): Promise<ArrayBuffer>;
  openFile(jobId: string, kind: FileKind): Promise<void>;
  openInBrowser(jobId: string, kind: FileKind): Promise<string>;
  revealFolder(jobId: string): Promise<void>;
  saveCopy(jobId: string, kind: FileKind): Promise<string | null>;
  onProgress(cb: (e: ProgressEvent) => void): Promise<Unlisten>;
  onStatus(cb: (s: BackendStatus) => void): Promise<Unlisten>;
}

export const inTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

async function tauriApi(): Promise<BackendApi> {
  const { invoke } = await import("@tauri-apps/api/core");
  const { listen } = await import("@tauri-apps/api/event");
  const call = <T>(method: string, params: Values = {}) => invoke<T>("backend_call", { method, params });
  return {
    login: (username, password) => invoke<string>("login", { username, password }),
    logout: () => invoke<void>("logout"),
    authStatus: () => invoke<string | null>("auth_status"),
    ping: () => call<PingResult>("system.ping"),
    diagnostics: () => call<Diagnostics>("system.diagnostics"),
    selfCheck: (convert = true) => call<SelfCheck>("system.selfcheck", { convert }),
    openLibreOfficeDownload: () => invoke<void>("open_libreoffice_download"),
    listTemplates: async () => (await call<{ templates: TemplateSummary[] }>("templates.list")).templates,
    generate: (template_id, values, job_id) => call<GenerateResult>("docgen.generate", { template_id, values, job_id }),
    rescanTemplates: async () => (await call<{ templates: TemplateSummary[] }>("templates.rescan")).templates,
    openTemplatesDir: () => invoke<string>("open_templates_dir"),
    exampleValues: async (template_id) => (await call<{ values: Values }>("templates.example_values", { template_id })).values,
    status: () => invoke<BackendStatus>("backend_status"),
    prepareEml: (job_id, message) => call<EmlResult>("email.prepare_eml", { job_id, message }),
    createImapDraft: (job_id, message) => call<ImapDraftResult>("email.create_imap_draft", { job_id, message }),
    imapGetAccount: () => call<ImapAccountInfo>("email.imap_get_account"),
    imapTest: (account, password) => call<{ ok: boolean; drafts_folder: string; email: string }>("email.imap_test", { account, password }),
    imapSaveAccount: (account, password) => call<ImapAccountInfo>("email.imap_save_account", { account, password }),
    imapRemoveAccount: () => call<ImapAccountInfo>("email.imap_remove_account"),
    historyList: (limit = 50) => call<{ jobs: HistoryRow[]; total: number }>("history.list", { limit }),
    historyDelete: (job_id, delete_files) => call<{ removed_row: boolean; removed_files: boolean }>("history.delete", { job_id, delete_files }),
    historyClear: (delete_files) => call<{ removed_rows: number; removed_job_folders: number }>("history.clear", { delete_files }),
    privacySummary: () => call<PrivacySummary>("privacy.summary"),
    privacyClearLogs: () => call<{ cleared: number }>("privacy.clear_logs"),
    privacyCleanup: () => call<{ removed_temp_dirs: number; removed_partial_files: number }>("privacy.cleanup"),
    networkCheck: () => call<ReachabilityResult>("network.check"),
    openDataDir: () => invoke<void>("open_data_dir"),
    settingsGet: () => call<AppSettings>("settings.get"),
    settingsSet: (key, value) => call<AppSettings>("settings.set", { key, value }),
    chooseOutputDir: () => invoke<string | null>("choose_output_dir"),
    jobInfo: (job_id) => call<JobInfo>("jobs.get", { job_id }),
    convertPdf: (job_id) => call<ConvertResult>("docgen.convert_pdf", { job_id }),
    readPdf: (jobId) => invoke<ArrayBuffer>("read_job_pdf", { jobId }),
    openFile: (jobId, kind) => invoke<void>("open_job_file", { jobId, kind }),
    openInBrowser: (jobId, kind) => invoke<string>("open_job_in_browser", { jobId, kind }),
    revealFolder: (jobId) => invoke<void>("reveal_job_folder", { jobId }),
    saveCopy: (jobId, kind) => invoke<string | null>("save_job_copy", { jobId, kind }),
    onProgress: (cb) => listen<{ method: string; params: ProgressEvent }>("backend://notification", (e) => {
      if (e.payload.method === "job.progress") cb(e.payload.params);
    }),
    onStatus: (cb) => listen<BackendStatus>("backend://status", (e) => cb(e.payload)),
  };
}

async function mockApi(): Promise<BackendApi> {
  const templates: TemplateSummary[] = await (await fetch("/mock/templates.json")).json();
  const example: Values = await (await fetch("/mock/values.example.json")).json();
  const progressListeners = new Set<(e: ProgressEvent) => void>();
  const statusListeners = new Set<(s: BackendStatus) => void>();
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
  const rpcError = (code: RpcError["data"]["code"], message: string, extra: Record<string, unknown> = {}): RpcError => ({ code: -32001, message, data: { code, ...extra } });
  let user: string | null = null;
  let outputDir = "/Users/you/Documents/Papyra";
  let imapAccount: ImapAccountInput | null = null;
  let offline = true, keepHistory = true;   // offline by default, like the real backend
  const settingsObj = (): AppSettings => ({ output_dir: outputDir, offline_mode: offline, keep_history: keepHistory, defaults: { output_dir: "/Users/you/Documents/Papyra" }, settings_file: "/mock/settings.json" });
  const historyRows: HistoryRow[] = [];
  let stale = false;   // the mock toggles staleness: window.__mockStale = true simulates an external edit
  return {
    login: async (u, p) => { await sleep(300); if (u === "admin" && p === "DocMaster!2026") { user = "admin"; return user; } throw rpcError("AUTH_FAILED", "Incorrect username or password."); },
    logout: async () => { user = null; },
    authStatus: async () => user,
    prepareEml: async (job_id, message) => { await sleep(300); if (!message.to.includes("@")) throw rpcError("EMAIL_INVALID_ADDRESS", "One of the email addresses is not valid.", { field: "to" }); return { job_id, eml_path: `/mock/out/${job_id}/Resume.eml`, bytes: 140_000, attachment: "Resume.pdf" }; },
    createImapDraft: async (job_id, message) => { await sleep(900); if (!imapAccount) throw rpcError("EMAIL_ACCOUNT_MISSING", "No mailbox is connected. Add your email account in Settings."); if (!message.to.includes("@")) throw rpcError("EMAIL_INVALID_ADDRESS", "One of the email addresses is not valid.", { field: "to" }); return { job_id, account: imapAccount.email, folder: "Drafts", uid: 57, confirmed: true, attachment: "Resume.pdf" }; },
    imapGetAccount: async () => imapAccount ? { configured: true, has_password: true, email: imapAccount.email, host: imapAccount.host, port: imapAccount.port, username: imapAccount.email, drafts_folder: "Drafts" } : { configured: false },
    imapTest: async (account, password) => { await sleep(600); if (password !== "secret-pw") throw rpcError("EMAIL_AUTH_FAILED", "The mail server rejected the username or password."); return { ok: true, drafts_folder: "Drafts", email: account.email }; },
    imapSaveAccount: async (account, password) => { await sleep(600); if (password !== "secret-pw") throw rpcError("EMAIL_AUTH_FAILED", "The mail server rejected the username or password."); imapAccount = account; return { configured: true, has_password: true, email: account.email, host: account.host, port: account.port, username: account.email, drafts_folder: "Drafts" }; },
    imapRemoveAccount: async () => { imapAccount = null; return { configured: false }; },
    settingsGet: async () => settingsObj(),
    settingsSet: async (k, v) => { if (k === "output_dir") outputDir = (v as string | null) ?? "/Users/you/Documents/Papyra"; if (k === "offline_mode") offline = Boolean(v); if (k === "keep_history") keepHistory = Boolean(v); return settingsObj(); },
    historyList: async () => ({ jobs: [...historyRows].reverse(), total: historyRows.length }),
    historyDelete: async (job_id, delete_files) => { const i = historyRows.findIndex((r) => r.job_id === job_id); if (i >= 0) historyRows.splice(i, 1); return { removed_row: i >= 0, removed_files: delete_files }; },
    historyClear: async (delete_files) => { const n = historyRows.length; historyRows.length = 0; return { removed_rows: n, removed_job_folders: delete_files ? n : 0 }; },
    privacySummary: async () => ({ stored: [
        { what: "Generated documents (Word, PDF, .eml) and job records", where: outputDir, bytes: 2_400_000, contains_personal_data: true },
        { what: "Document history (metadata only: template, time, paths, page count)", where: "/mock/history.db", bytes: 24_576, contains_personal_data: false, rows: historyRows.length },
        { what: "Settings (output folder, mail server, preferences)", where: "/mock/settings.json", bytes: 310, contains_personal_data: !!imapAccount },
        { what: "Mailbox password", where: "System keychain (macOS Keychain / Windows Credential Manager)", bytes: null, contains_personal_data: true, present: !!imapAccount },
        { what: "Logs (redacted: no values, no addresses, no secrets)", where: "/mock/logs", bytes: 12_000, contains_personal_data: false } ],
      never_stored: ["form values you type (unless they are printed in the generated document itself)", "email bodies outside the .eml file you choose to save", "any data on a server: there is no Papyra server"],
      outbound: imapAccount ? [{ purpose: "Save email drafts to your mailbox (IMAP over TLS)", host: imapAccount.host, port: imapAccount.port, when: "only when you click Create draft" }] : [],
      offline_mode: offline, keep_history: keepHistory, telemetry: false, data_dir: "/mock/data" }),
    privacyClearLogs: async () => ({ cleared: 1 }),
    privacyCleanup: async () => ({ removed_temp_dirs: 0, removed_partial_files: 0 }),
    networkCheck: async () => { await sleep(700); if (offline) throw rpcError("OFFLINE_MODE", "Offline mode is on: the app will not connect to any server."); if (!imapAccount) throw rpcError("EMAIL_ACCOUNT_MISSING", "No mailbox is connected."); return { host: imapAccount.host, port: imapAccount.port, ok: true, ms: 142, dns: { ok: true, addresses: ["203.0.113.5"] }, tcp: { ok: true }, tls: { ok: true, protocol: "TLSv1.3", subject: imapAccount.host } }; },
    openDataDir: async () => alert("(mock) would open the data folder"),
    chooseOutputDir: async () => "/Users/you/Desktop/Generated documents",
    jobInfo: async (job_id) => {
      stale = Boolean((window as unknown as { __mockStale?: boolean }).__mockStale);
      return { job: { job_id, template_id: "resume-ats", template_version: 1, created_at: new Date().toISOString(), docx_path: `/mock/out/${job_id}/Resume.docx`, pdf_path: `/mock/out/${job_id}/Resume.pdf`, pages: 2, status: "pdf_done", eml_path: null, drafts: [] },
               state: { docx_exists: true, docx_changed: stale, pdf_exists: true, pdf_changed: false, pdf_stale: stale } };
    },
    convertPdf: async (job_id) => { await sleep(800); (window as unknown as { __mockStale?: boolean }).__mockStale = false; return { job_id, pdf_path: `/mock/out/${job_id}/Resume.pdf`, pages: 2, docx_sha256: "x", pdf_sha256: "y", pdf_seconds: 0.8 }; },
    readPdf: async () => (await fetch("/mock/example-output.pdf")).arrayBuffer(),
    openFile: async (_j, kind) => alert(`(mock) would open the ${kind} in its default application`),
    openInBrowser: async (_j, kind) => { window.open(kind === "pdf" ? "/mock/example-output.pdf" : "#", "_blank"); return "browser"; },
    revealFolder: async () => alert("(mock) would reveal the output folder"),
    saveCopy: async (_j, kind) => `/Users/you/Desktop/copy.${kind}`,
    ping: async () => ({ name: "docmaster-backend (mock)", version: "0.0.0", pid: 0, python: "n/a", frozen: false }),
    openLibreOfficeDownload: async () => alert("(mock) would open the LibreOffice download page"),
    selfCheck: async (convert = true) => {
      const missing = Boolean((window as unknown as { __mockSetupMissing?: boolean }).__mockSetupMissing);
      if (!convert) return { ok: !missing, checks: [
        { check: "module docx", ok: true, detail: "1.2.0" }, { check: "module psutil", ok: true, detail: "7.2.2" },
        { check: "LibreOffice installed", ok: !missing, detail: missing ? "soffice not found in the standard locations" : "/Applications/LibreOffice.app (mock) · LibreOffice 26.8", fix: missing ? "Install LibreOffice to its default folder, or set DOCMASTER_SOFFICE." : undefined },
        { check: "LibreOffice profile", ok: true, detail: "/mock/lo-profile · warm" } ], log_path: "/mock/logs/backend.log", log_tail: [] };
      await sleep(900); return { ok: false, checks: [
        { check: "module docx", ok: true, detail: "1.2.0" }, { check: "module psutil", ok: false, detail: "ModuleNotFoundError: No module named 'psutil'", fix: "The engine was packaged without this dependency. Rebuild it after pip install -r tools/requirements.txt." },
        { check: "LibreOffice installed", ok: true, detail: "/Applications/LibreOffice.app (mock) · LibreOffice 26.8" }, { check: "LibreOffice profile", ok: true, detail: "/mock/lo-profile · warm" },
        { check: "No leftover LibreOffice processes", ok: true, detail: "0 running with the Papyra profile" }, { check: "Test PDF conversion", ok: true, detail: "0.7 s, 1 page, total 0.9 s" } ],
      log_path: "/mock/logs/backend.log", log_tail: ["2026-11-21 23:13:39,824 INFO docmaster.rpc: rpc server ready", "2026-11-21 23:14:45,018 ERROR docmaster.rpc: docgen.generate crashed", "ModuleNotFoundError: No module named 'psutil'"] }; },
    diagnostics: async () => ({ templates_dir: "/mock/templates", user_templates_dir: "/Users/you/Documents/Papyra/templates", templates: templates.length, output_dir: "~/Documents/Papyra", output_dir_writable: true,
      libreoffice: { found: true, path: "/Applications/LibreOffice.app (mock)", version: "LibreOffice (mock)" }, platform: navigator.platform, python: "mock" }),
    listTemplates: async () => templates,
    rescanTemplates: async () => templates,
    openTemplatesDir: async () => "/Users/you/Documents/Papyra/templates",
    exampleValues: async () => example,
    status: async () => ({ state: "ready", version: "mock", pid: 0, frozen: false }),
    onProgress: async (cb) => { progressListeners.add(cb); return () => progressListeners.delete(cb); },
    onStatus: async (cb) => { statusListeners.add(cb); return () => statusListeners.delete(cb); },
    generate: async (template_id, values, job_id) => {
      const emit = (stage: ProgressEvent["stage"], message: string) => progressListeners.forEach((cb) => cb({ job_id, stage, message }));
      emit("validating", "Checking values"); await sleep(300);
      if (!values.full_name) throw rpcError("VALIDATION_ERROR", "Some values are missing or invalid.", { errors: ["full_name: required"] });
      emit("rendering_docx", "Generating Word document"); await sleep(600);
      emit("docx_done", "Word document created"); emit("converting_pdf", "Converting to PDF"); await sleep(1200);
      if (values.full_name === "FAIL PDF") throw rpcError("PDF_CONVERSION_FAILED", "The PDF could not be created. The Word document has been kept.", { docx_path: "/mock/out/doc.docx" });
      emit("pdf_done", "PDF created (2 pages)");
      if (keepHistory) historyRows.push({ job_id, template_id, template_version: 1, created_at: new Date().toISOString(), status: "pdf_done", output_dir: outputDir, docx_path: `/mock/out/${job_id}/Resume.docx`, pdf_path: `/mock/out/${job_id}/Resume.pdf`, pages: 2, error_code: null, drafts: 0, docx_exists: true, pdf_exists: true });
      return { job_id, template_id, template_version: 1, docx_path: `/mock/out/${job_id}/Resume.docx`, pdf_path: `/mock/out/${job_id}/Resume.pdf`, pages: 2, docx_sha256: "mock", pdf_sha256: "mock", pdf_seconds: 1.1, total_ms: 2100 };
    },
  };
}

let instance: Promise<BackendApi> | null = null;
export function backend(): Promise<BackendApi> {
  if (!instance) instance = inTauri ? tauriApi() : mockApi();
  return instance;
}
