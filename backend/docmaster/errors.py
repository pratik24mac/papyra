"""Central error taxonomy. Every error the backend reports carries a stable code, a user-facing
message and optional structured data. The UI maps codes to actions ("install LibreOffice", …)."""
from __future__ import annotations


class DocMasterError(Exception):
    code = "INTERNAL_ERROR"
    rpc_code = -32000
    user_message = "An unexpected error occurred."

    def __init__(self, message: str | None = None, data: dict | None = None):
        super().__init__(message or self.user_message)
        self.data = data or {}

    def to_rpc(self) -> dict:
        return {"code": self.rpc_code, "message": str(self), "data": {"code": self.code, **self.data}}


class ValidationError(DocMasterError):
    code, rpc_code, user_message = "VALIDATION_ERROR", -32001, "Some values are missing or invalid."

class TemplateNotFound(DocMasterError):
    code, rpc_code, user_message = "TEMPLATE_NOT_FOUND", -32002, "The selected template is not available."

class TemplateInvalid(DocMasterError):
    code, rpc_code, user_message = "TEMPLATE_INVALID", -32003, "The bundled template is damaged or inconsistent with its schema."

class DocxGenerationFailed(DocMasterError):
    code, rpc_code, user_message = "DOCX_GENERATION_FAILED", -32004, "The Word document could not be generated."

class LibreOfficeNotFound(DocMasterError):
    code, rpc_code, user_message = "LIBREOFFICE_NOT_FOUND", -32010, "LibreOffice was not found. Install it or set its location in Settings."

class PdfConversionFailed(DocMasterError):
    code, rpc_code, user_message = "PDF_CONVERSION_FAILED", -32011, "The PDF could not be created. The Word document has been kept."

class PdfInvalid(DocMasterError):
    code, rpc_code, user_message = "PDF_INVALID", -32012, "The PDF was created but failed validation. The Word document has been kept."

class PdfStale(DocMasterError):
    code, rpc_code, user_message = "PDF_STALE", -32013, "The PDF is out of date. Regenerate it before preparing the email."

class OutputPathError(DocMasterError):
    code, rpc_code, user_message = "OUTPUT_PATH_ERROR", -32020, "The output folder is not writable."


class EmailInvalidAddress(DocMasterError):
    code, rpc_code, user_message = "EMAIL_INVALID_ADDRESS", -32070, "One of the email addresses is not valid."

class EmailAccountMissing(DocMasterError):
    code, rpc_code, user_message = "EMAIL_ACCOUNT_MISSING", -32071, "No mailbox is connected. Add your email account in Settings."

class EmailAuthFailed(DocMasterError):
    code, rpc_code, user_message = "EMAIL_AUTH_FAILED", -32072, "The mail server rejected the username or password."

class EmailNetworkError(DocMasterError):
    code, rpc_code, user_message = "EMAIL_NETWORK_ERROR", -32073, "Could not reach the mail server. Check your internet connection."

class EmailImapError(DocMasterError):
    code, rpc_code, user_message = "EMAIL_IMAP_ERROR", -32074, "The mail server returned an error while saving the draft."

class EmailAttachmentTooLarge(DocMasterError):
    code, rpc_code, user_message = "EMAIL_ATTACHMENT_TOO_LARGE", -32075, "The PDF is too large to attach."

class EmailDraftFailed(DocMasterError):
    code, rpc_code, user_message = "EMAIL_DRAFT_FAILED", -32076, "The email draft could not be created."
