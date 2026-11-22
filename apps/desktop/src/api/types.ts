// Mirrors the backend contract (backend/docmaster). Keep in sync with schema.yaml field types
// and the RPC methods in backend/docmaster/rpc/methods.py; tests/test_contract.py checks the names.

export type ScalarFieldType = "text" | "multiline" | "email" | "url" | "date" | "number" | "select" | "checkbox";
export type FieldType = ScalarFieldType | "group_list" | "text_list";

export interface FieldValidation {
  max_length?: number;
  pattern?: string;
  min?: number;
  max?: number;
  min_items?: number;
  max_items?: number;
}

export interface SelectOption {
  value: string;
  label: string;
}

export interface FieldSchema {
  id: string;
  label: string;
  type: FieldType;
  required?: boolean;
  default?: unknown;
  help?: string;
  validation?: FieldValidation;
  options?: (SelectOption | string)[];
  /** group_list: the fields of each item */
  item_fields?: FieldSchema[];
  /** text_list: the schema of each item */
  item?: { type: ScalarFieldType; validation?: FieldValidation };
}

export interface GroupSchema {
  id: string;
  label: string;
  /** false = not printed into the document (e.g. the email draft group) */
  print?: boolean;
  fields: FieldSchema[];
}

export interface TemplateSummary {
  id: string;
  version: number;
  name: string;
  description: string;
  groups: GroupSchema[];
  source: "bundled" | "user";
  dir: string;
  status: "ok" | "error";
  problems: string[];
  has_examples: boolean;
}

export type Values = Record<string, unknown>;

export interface GenerateResult {
  job_id: string;
  template_id: string;
  template_version: number;
  docx_path: string;
  pdf_path: string;
  pages: number;
  docx_sha256: string;
  pdf_sha256: string;
  pdf_seconds: number;
  total_ms: number;
}

export interface JobRecord {
  job_id: string;
  template_id: string;
  template_version: number;
  created_at: string;
  docx_path: string;
  pdf_path: string | null;
  pages: number | null;
  status: "docx_done" | "pdf_done" | "pdf_failed";
  eml_path: string | null;
  drafts: { mode: "eml" | "imap"; created_at: string; status: string; path?: string; folder?: string; account?: string }[];
}

export interface JobFileState {
  docx_exists: boolean;
  docx_changed: boolean;
  pdf_exists: boolean;
  pdf_changed: boolean;
  /** true when the PDF must not be used: it was made from a different DOCX, or is missing/modified */
  pdf_stale: boolean;
}

export interface JobInfo {
  job: JobRecord;
  state: JobFileState;
}

export interface ConvertResult {
  job_id: string;
  pdf_path: string;
  pages: number;
  docx_sha256: string;
  pdf_sha256: string;
  pdf_seconds: number;
}

export type FileKind = "docx" | "pdf" | "eml";

export interface DraftMessage {
  to: string;
  cc?: string;
  bcc?: string;
  subject: string;
  body: string;
}

export interface ImapAccountInput {
  email: string;
  host: string;
  port: number;
  username?: string;
  drafts_folder?: string;
}

export type ImapAccountInfo =
  | { configured: false }
  | { configured: true; has_password: boolean; email: string; host: string; port: number; username: string; drafts_folder: string | null };

export interface EmlResult {
  job_id: string;
  job_ids?: string[];
  eml_path: string;
  bytes: number;
  attachment: string;
  attachments?: string[];
}

export interface ImapDraftResult {
  job_id: string;
  account: string;
  folder: string;
  uid: number | null;
  confirmed: boolean;
  attachment: string;
  attachments?: string[];
  job_ids?: string[];
}

export interface AppSettings {
  output_dir: string;
  offline_mode: boolean;
  keep_history: boolean;
  date_format: string;
  last_output_dir: string | null;
  date_format_example: string;
  date_format_presets: { format: string; example: string }[];
  defaults: { output_dir: string };
  settings_file: string;
}

export interface HistoryRow {
  kind?: "job" | "batch";
  batch_id?: string;
  batch_dir?: string | null;
  template_name?: string | null;
  documents?: HistoryRow[];
  job_id: string;
  template_id: string;
  template_version: number;
  created_at: string;
  status: "docx_done" | "pdf_done" | "pdf_failed";
  output_dir: string;
  docx_path: string | null;
  pdf_path: string | null;
  pages: number | null;
  error_code: string | null;
  drafts: number;
  docx_exists: boolean;
  pdf_exists: boolean;
}

export interface PrivacySummary {
  stored: { what: string; where: string; bytes: number | null; contains_personal_data: boolean; rows?: number; present?: boolean }[];
  never_stored: string[];
  outbound: { purpose: string; host: string; port: number; when: string }[];
  offline_mode: boolean;
  keep_history: boolean;
  telemetry: false;
  data_dir: string;
}

export interface ReachabilityResult {
  host: string; port: number; ok: boolean; ms: number | null;
  dns: { ok: boolean; addresses?: string[]; error?: string } | null;
  tcp: { ok: boolean; error?: string } | null;
  tls: { ok: boolean; protocol?: string; subject?: string; error?: string } | null;
}

export interface SelfCheck {
  ok: boolean;
  checks: { check: string; ok: boolean; detail: string; fix?: string }[];
  log_path: string | null;
  log_tail: string[];
}

export interface Diagnostics {
  templates_dir: string;
  user_templates_dir: string;
  templates: number;
  output_dir: string;
  output_dir_writable: boolean;
  libreoffice: { found: boolean; path: string | null; version: string | null };
  platform: string;
  python: string;
}

export interface PingResult {
  name: string;
  version: string;
  pid: number;
  python: string;
  frozen: boolean;
}

export type ErrorCode =
  | "VALIDATION_ERROR" | "TEMPLATE_NOT_FOUND" | "TEMPLATE_INVALID" | "DOCX_GENERATION_FAILED"
  | "LIBREOFFICE_NOT_FOUND" | "PDF_CONVERSION_FAILED" | "PDF_INVALID" | "OUTPUT_PATH_ERROR"
  | "BACKEND_UNAVAILABLE" | "METHOD_NOT_ALLOWED" | "INTERNAL_ERROR" | "JOB_NOT_FOUND"
  | "AUTH_REQUIRED" | "AUTH_FAILED" | "SETTING_INVALID"
  | "EMAIL_INVALID_ADDRESS" | "EMAIL_ACCOUNT_MISSING" | "EMAIL_AUTH_FAILED" | "EMAIL_NETWORK_ERROR" | "EMAIL_IMAP_ERROR"
  | "EMAIL_ATTACHMENT_TOO_LARGE" | "EMAIL_DRAFT_FAILED" | "CREDENTIAL_STORE_UNAVAILABLE" | "OFFLINE_MODE" | "PDF_STALE" | "FILE_NOT_FOUND" | "PATH_NOT_ALLOWED" | "OPEN_FAILED" | "SAVE_FAILED" | "INVALID_REQUEST";

export interface RpcError {
  code: number;
  message: string;
  data: { code: ErrorCode; errors?: string[]; docx_path?: string; pdf_path?: string; job_id?: string; [k: string]: unknown };
}

export type ProgressStage = "validating" | "rendering_docx" | "docx_done" | "converting_pdf" | "pdf_done" | "email_connecting" | "failed" | "batch_done";

export interface ProgressEvent {
  job_id: string;
  stage: ProgressStage;
  message: string;
  docx_path?: string;
  pdf_path?: string;
  // batch generation: which document this event belongs to
  batch_id?: string;
  document?: string;
  document_name?: string;
  index?: number;
  total?: number;
  doc_job_id?: string;
}

export interface BatchDocument {
  job_id: string;
  template_id: string;
  template_name: string;
  status: "pdf_done" | "failed";
  docx_path: string | null;
  pdf_path: string | null;
  pages: number | null;
  pdf_seconds?: number;
  error?: { code: string; message: string; data?: Record<string, unknown> };
  state?: JobFileState;
}

export interface BatchResult {
  batch_id: string;
  batch_dir: string;
  person: string;
  ok: boolean;
  documents: BatchDocument[];
  total_ms: number;
}

export type BackendStatus =
  | { state: "starting"; attempt: number }
  | { state: "ready"; version: string; pid: number; frozen: boolean }
  | { state: "restarting"; attempt: number; reason: string }
  | { state: "failed"; reason: string };

export function isRpcError(e: unknown): e is RpcError {
  return typeof e === "object" && e !== null && "message" in e && "data" in e && typeof (e as RpcError).data === "object";
}
