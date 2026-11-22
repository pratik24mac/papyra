// Step 6: prepare the email draft. Two independent workflows: an offline .eml file, or a draft
// appended to the connected mailbox over IMAP. The app never sends; the user confirms first.
import { useEffect, useState } from "react";
import { Alert, Button, Card, Descriptions, Form, Input, Modal, Radio, Space, Tag, Typography, message as toast } from "antd";
import { MailOutlined, FileOutlined, FolderOpenOutlined, CloudUploadOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { DraftMessage, EmlResult, ImapAccountInfo, ImapDraftResult, JobInfo } from "../api/types";
import { describeError } from "../lib/errors";
import { readyJobIds, useStore } from "../store";

type Mode = "eml" | "imap";

export function Email() {
  const { state, dispatch } = useStore();
  const jobIds = readyJobIds(state.job);
  const jobId = jobIds[0];
  const [form] = Form.useForm<DraftMessage>();
  const [mode, setMode] = useState<Mode>("eml");
  const [account, setAccount] = useState<ImapAccountInfo | null>(null);
  const [offline, setOffline] = useState(true);
  const [infos, setInfos] = useState<JobInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ mode: Mode; eml?: EmlResult; imap?: ImapDraftResult } | null>(null);
  const [error, setError] = useState<ReturnType<typeof describeError> | null>(null);

  useEffect(() => {
    if (!jobId) return;
    backend().then(async (api) => {
      const a = await api.imapGetAccount(); setAccount(a);
      const st = await api.settingsGet(); setOffline(st.offline_mode);
      if (a.configured && !st.offline_mode) setMode("imap");
      setInfos(await Promise.all(jobIds.map((id) => api.jobInfo(id))));
    });
    const v = state.values;
    form.setFieldsValue({ to: String(v.recipient_email ?? ""), subject: String(v.email_subject ?? ""), body: String(v.email_body ?? "") });
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!jobId) return null;
  const stale = infos.some((i) => i.state.pdf_stale);
  const attachments = infos.map((i) => i.job.pdf_path?.split("/").pop() ?? "document.pdf");
  const attachment = attachments.length > 1 ? `${attachments.length} PDFs` : attachments[0];
  const pages = infos.reduce((n, i) => n + (i.job.pages ?? 0), 0);

  const create = async () => {
    const msg = await form.validateFields().catch(() => null);
    if (!msg) return;
    const target = mode === "imap" && account?.configured ? `a draft in the Drafts folder of ${account.email}` : "a .eml file next to the generated document";
    Modal.confirm({
      title: "Create the email draft?",
      content: <>This will create {target} with <strong>{attachments.join(", ")}</strong> attached. Nothing will be sent.</>,
      okText: "Create draft", onOk: async () => {
        setBusy(true); setError(null); setResult(null);
        try {
          const api = await backend();
          if (mode === "imap") setResult({ mode, imap: await api.createImapDraft(jobIds, msg) });
          else setResult({ mode, eml: await api.prepareEml(jobIds, msg) });
          setInfos(await Promise.all(jobIds.map((id) => api.jobInfo(id))));
        } catch (e) { setError(describeError(e)); } finally { setBusy(false); }
      },
    });
  };
  const open = async (kind: "eml" | "folder") => {
    try { const api = await backend(); if (kind === "eml") await api.openFile(jobId, "eml"); else await api.revealFolder(jobId); }
    catch (e) { toast.error(describeError(e).detail); }
  };

  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      {stale && <Alert type="warning" showIcon message="The PDF is out of date" description="Go back to Preview and regenerate the PDF before preparing the email." />}
      <Card className="glass" title={attachments.length > 1 ? `Attachments (${attachments.length})` : "Attachment"}>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label={attachments.length > 1 ? "Files" : "File"}>{attachments.length ? attachments.join(", ") : "—"}</Descriptions.Item>
          <Descriptions.Item label="Pages">{infos.length ? pages : "—"}</Descriptions.Item>
          <Descriptions.Item label="Status">{stale ? <Tag color="orange">out of date</Tag> : <Tag color="green">current</Tag>}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Card className="glass" title="Message">
        <Form form={form} layout="vertical" requiredMark autoComplete="off">
          <Form.Item name="to" label="To" rules={[{ required: true, message: "At least one recipient is required" }]} help="Separate several addresses with commas">
            <Input placeholder="name@example.com" />
          </Form.Item>
          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="cc" label="CC" style={{ minWidth: 320 }}><Input /></Form.Item>
            <Form.Item name="bcc" label="BCC" style={{ minWidth: 320 }}><Input /></Form.Item>
          </Space>
          <Form.Item name="subject" label="Subject" rules={[{ required: true, message: "A subject is required" }]}><Input /></Form.Item>
          <Form.Item name="body" label="Body" rules={[{ required: true, message: "Write a short message" }]}><Input.TextArea autoSize={{ minRows: 5, maxRows: 14 }} /></Form.Item>
        </Form>
      </Card>
      <Card className="glass" title="How to create the draft">
        <Radio.Group value={mode} onChange={(e) => setMode(e.target.value)}>
          <Space orientation="vertical">
            <Radio value="imap" disabled={!account?.configured || offline}>
              <CloudUploadOutlined /> Save a draft in my mailbox {offline ? <Typography.Text type="secondary">— offline mode is on (Settings → Privacy); the app will not connect to any server</Typography.Text> : account?.configured ? <Typography.Text type="secondary">({account.email}, via IMAP)</Typography.Text> : <Typography.Text type="secondary">— connect your email account in Settings first</Typography.Text>}
            </Radio>
            <Radio value="eml"><FileOutlined /> Save a .eml file <Typography.Text type="secondary">(offline; open it in your mail app. Outlook opens it as an editable draft; Apple Mail and Thunderbird show it as a message you can forward)</Typography.Text></Radio>
          </Space>
        </Radio.Group>
      </Card>
      {error && <Alert type="error" showIcon message={error.title} description={<>{error.detail}{error.action && <><br /><strong>{error.action}</strong></>}</>} />}
      {result?.eml && (
        <Alert type="success" showIcon message="Email file saved" description={<Space orientation="vertical">
          <span>{result.eml.eml_path} ({Math.round(result.eml.bytes / 1024)} KB, {(result.eml.attachments ?? [result.eml.attachment]).length > 1 ? `${(result.eml.attachments ?? []).length} attachments` : `attachment ${result.eml.attachment}`})</span>
          <Space><Button icon={<MailOutlined />} onClick={() => open("eml")}>Open in mail app</Button><Button icon={<FolderOpenOutlined />} onClick={() => open("folder")}>Show in folder</Button></Space>
        </Space>} />
      )}
      {result?.imap && (
        <Alert type="success" showIcon message={`Draft saved in "${result.imap.folder}" of ${result.imap.account}`} description="Open your mail app or webmail, review the draft, and send it when you are ready. Nothing has been sent." />
      )}
      <Space>
        <Button onClick={() => dispatch({ type: "step", step: 4 })}>Back to preview</Button>
        <Button type="primary" icon={<MailOutlined />} disabled={stale || busy} loading={busy} onClick={create}>Create draft…</Button>
        <Button onClick={() => dispatch({ type: "reset" })}>New document</Button>
      </Space>
    </Space>
  );
}
