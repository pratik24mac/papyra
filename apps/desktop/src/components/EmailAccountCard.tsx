// Settings → Email account: IMAP details + password. The password goes straight to the backend,
// which keeps it in the OS keychain; it is never shown again or written to a settings file.
import { useEffect, useState } from "react";
import { Alert, Button, Card, Descriptions, Form, Input, InputNumber, Space, Tag, Typography, message } from "antd";
import { ApiOutlined, DisconnectOutlined, SaveOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { ImapAccountInfo, ImapAccountInput } from "../api/types";
import { describeError } from "../lib/errors";

type FormValues = ImapAccountInput & { password: string };

export function EmailAccountCard() {
  const [form] = Form.useForm<FormValues>();
  const [account, setAccount] = useState<ImapAccountInfo | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const load = async () => setAccount(await (await backend()).imapGetAccount());
  useEffect(() => { load(); }, []);

  const run = async (label: string, fn: (v: FormValues) => Promise<string>) => {
    const v = await form.validateFields().catch(() => null);
    if (!v) return;
    setBusy(label); setNote(null);
    try { setNote({ type: "success", text: await fn(v) }); await load(); }
    catch (e) { const d = describeError(e); setNote({ type: "error", text: `${d.title}: ${d.detail}${d.action ? ` ${d.action}` : ""}` }); }
    finally { setBusy(null); }
  };
  const toInput = (v: FormValues): ImapAccountInput => ({ email: v.email.trim(), host: v.host.trim(), port: Number(v.port) || 993, username: v.username?.trim() || undefined, drafts_folder: v.drafts_folder?.trim() || undefined });

  return (
    <Card className="glass" title="Email account (IMAP drafts)">
      {account?.configured ? (
        <Space orientation="vertical" style={{ width: "100%" }} size="middle">
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="Status"><Tag color="green">Connected</Tag> {account.email}</Descriptions.Item>
            <Descriptions.Item label="IMAP server">{account.host}:{account.port}</Descriptions.Item>
            <Descriptions.Item label="Drafts folder">{account.drafts_folder ?? "detected automatically"}</Descriptions.Item>
            <Descriptions.Item label="Password">{account.has_password ? "stored in the system keychain" : <Tag color="red">missing — reconnect</Tag>}</Descriptions.Item>
          </Descriptions>
          <Space>
            <Button icon={<ApiOutlined />} loading={busy === "test"} onClick={async () => { setBusy("test"); setNote(null); try { const r = await (await backend()).imapTest({ email: account.email, host: account.host, port: account.port, username: account.username, drafts_folder: account.drafts_folder ?? undefined }, undefined as unknown as string); setNote({ type: "success", text: `Connection OK, Drafts folder "${r.drafts_folder}"` }); } catch (e) { const d = describeError(e); setNote({ type: "error", text: `${d.title}: ${d.detail}` }); } finally { setBusy(null); } }}>Test connection</Button>
            <Button danger icon={<DisconnectOutlined />} loading={busy === "remove"} onClick={async () => { setBusy("remove"); try { await (await backend()).imapRemoveAccount(); message.success("Mailbox disconnected and password removed from the keychain"); await load(); } finally { setBusy(null); } }}>Disconnect</Button>
          </Space>
          {note && <Alert type={note.type} showIcon message={note.text} />}
        </Space>
      ) : (
        <Form form={form} layout="vertical" initialValues={{ host: "imap.porkbun.com", port: 993 }} requiredMark>
          <Typography.Paragraph type="secondary">Drafts are saved to your mailbox over IMAP; the app never sends mail. For Porkbun the server is <code>imap.porkbun.com</code>, port 993, and the username is your full email address.</Typography.Paragraph>
          <Form.Item name="email" label="Email address" rules={[{ required: true, type: "email", message: "Enter your email address" }]}><Input placeholder="you@yourdomain.com" /></Form.Item>
          <Space size="large">
            <Form.Item name="host" label="IMAP server" rules={[{ required: true }]} style={{ minWidth: 300 }}><Input /></Form.Item>
            <Form.Item name="port" label="Port" rules={[{ required: true }]}><InputNumber min={1} max={65535} /></Form.Item>
          </Space>
          <Form.Item name="username" label="Username (if different from the email address)"><Input autoComplete="off" /></Form.Item>
          <Form.Item name="password" label="Password" rules={[{ required: true, message: "Enter the mailbox password" }]}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item name="drafts_folder" label="Drafts folder (leave empty to detect)"><Input placeholder="Drafts" /></Form.Item>
          <Space>
            <Button icon={<ApiOutlined />} loading={busy === "test"} onClick={() => run("test", async (v) => { const r = await (await backend()).imapTest(toInput(v), v.password); return `Connection OK, Drafts folder "${r.drafts_folder}"`; })}>Test connection</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={busy === "save"} onClick={() => run("save", async (v) => { await (await backend()).imapSaveAccount(toInput(v), v.password); form.resetFields(["password"]); return "Mailbox connected. The password is stored in the system keychain."; })}>Connect</Button>
          </Space>
          {note && <Alert type={note.type} showIcon message={note.text} style={{ marginTop: 16 }} />}
        </Form>
      )}
    </Card>
  );
}
