import type { RpcError } from "../api/types";
import { isRpcError } from "../api/types";

export interface ErrorView {
  title: string;
  detail: string;
  action?: string;
  fieldErrors?: string[];
  keptDocx?: string;
}

/** Map backend error codes to what the user should read and do next. */
export function describeError(e: unknown): ErrorView {
  if (!isRpcError(e)) return { title: "Unexpected error", detail: String((e as Error)?.message ?? e) };
  const { message, data } = e as RpcError;
  switch (data.code) {
    case "VALIDATION_ERROR":
      return { title: "Some details need attention", detail: message, action: "Go back to the form to correct the highlighted fields.", fieldErrors: data.errors };
    case "LIBREOFFICE_NOT_FOUND":
      return { title: "LibreOffice is not installed", detail: message, action: "Install LibreOffice, or set its location in Settings, then generate again. The Word document can still be generated." };
    case "PDF_CONVERSION_FAILED":
      return { title: "PDF conversion failed", detail: message, action: "The Word document was kept. Try again, or open the Word file to check it.", keptDocx: data.docx_path };
    case "PDF_INVALID":
      return { title: "The PDF did not pass validation", detail: message, action: "The Word document was kept. Check it and generate again.", keptDocx: data.docx_path };
    case "OUTPUT_PATH_ERROR":
      return { title: "Cannot write to the output folder", detail: message, action: "Choose a different output folder in Settings." };
    case "EMAIL_INVALID_ADDRESS":
      return { title: "Check the email addresses", detail: message, action: `Correct the ${String(data.field ?? "recipient")} field.` };
    case "EMAIL_ACCOUNT_MISSING":
      return { title: "No mailbox connected", detail: message, action: "Connect your email account in Settings, or save a .eml file instead." };
    case "EMAIL_AUTH_FAILED":
      return { title: "Mailbox sign-in failed", detail: message, action: "Check the email address and password in Settings → Email account." };
    case "EMAIL_NETWORK_ERROR":
      return { title: "Mail server unreachable", detail: message, action: "Check your internet connection and the IMAP host, then try again. You can still save a .eml file offline." };
    case "EMAIL_IMAP_ERROR":
      return { title: "Mail server error", detail: message, action: "Try again. If it persists, set the Drafts folder name explicitly in Settings." };
    case "EMAIL_ATTACHMENT_TOO_LARGE":
      return { title: "Attachment too large", detail: message, action: "The PDF exceeds 25 MB. Reduce the document size." };
    case "EMAIL_DRAFT_FAILED":
      return { title: "Draft not created", detail: message, action: "Try again." };
    case "CREDENTIAL_STORE_UNAVAILABLE":
      return { title: "Keychain unavailable", detail: message, action: "The system credential store could not be used. Try again after unlocking your keychain." };
    case "OFFLINE_MODE":
      return { title: "Offline mode is on", detail: message, action: "Turn off offline mode in Settings → Privacy to use your mailbox." };
    case "SETTING_INVALID":
      return { title: "Setting not accepted", detail: message, action: "Choose a different value." };
    case "TEMPLATE_NOT_FOUND":
    case "TEMPLATE_INVALID":
      return { title: "Template problem", detail: message, action: "This bundled template is unavailable. Please reinstall the application." };
    case "AUTH_REQUIRED":
    case "AUTH_FAILED":
      return { title: "Sign-in required", detail: message, action: "Sign in to continue." };
    case "PDF_STALE":
      return { title: "The PDF is out of date", detail: message, action: "The Word document was changed after the PDF was created. Regenerate the PDF before previewing or attaching it." };
    case "JOB_NOT_FOUND":
    case "FILE_NOT_FOUND":
      return { title: "File not available", detail: message, action: "The generated files were moved or deleted. Generate the document again." };
    case "BACKEND_UNAVAILABLE":
      return { title: "The document engine is not running", detail: message, action: "Wait for it to restart, or restart the application." };
    case "INTERNAL_ERROR":
      return { title: "The document engine hit an internal error", detail: String(data.detail ?? message), action: "Open Settings → Diagnostics → Run full check and use Copy report." };
    default:
      return { title: "Generation failed", detail: message, action: "Try again. If it keeps failing, run the full check in Settings → Diagnostics." };
  }
}
