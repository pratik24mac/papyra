// Settings → Privacy & network: what is stored where, what the app can ever connect to,
// offline mode, history opt-out, deletion and cleanup, and a VPN-friendly reachability check.
import { useEffect, useState } from "react";
import { Alert, Button, Card, Descriptions, Modal, Space, Switch, Tag, Typography, message } from "antd";
import { ApiOutlined, ClearOutlined, DeleteOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { PrivacySummary, ReachabilityResult } from "../api/types";
import { describeError } from "../lib/errors";

const kb = (b: number | null) => (b === null ? "—" : b < 1024 ? `${b} B` : b < 1048576 ? `${Math.round(b / 1024)} KB` : `${(b / 1048576).toFixed(1)} MB`);

export function PrivacyCard() {
  const [s, setS] = useState<PrivacySummary | null>(null);
  const [net, setNet] = useState<ReachabilityResult | null>(null);
  const [netErr, setNetErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = async () => setS(await (await backend()).privacySummary());
  useEffect(() => { load(); }, []);
  const act = async (label: string, fn: () => Promise<string>) => { setBusy(label); try { message.success(await fn()); await load(); } catch (e) { message.error(describeError(e).detail); } finally { setBusy(null); } };
  const toggle = (key: "offline_mode" | "keep_history") => async (v: boolean) => { await (await backend()).settingsSet(key, v); await load(); };
  if (!s) return null;
  return (
    <Card className="glass" title="Privacy & network">
      <Space orientation="vertical" size="large" style={{ width: "100%" }}>
        <Descriptions column={1} bordered size="small" title="What is stored on this computer">
          {s.stored.map((x) => <Descriptions.Item key={x.what} label={<>{x.what} {x.contains_personal_data ? <Tag color="orange">personal data</Tag> : <Tag>metadata</Tag>}</>}>{x.where}{x.bytes !== null && <Typography.Text type="secondary"> · {kb(x.bytes)}</Typography.Text>}{x.rows !== undefined && <Typography.Text type="secondary"> · {x.rows} entries</Typography.Text>}{x.present === false && <Typography.Text type="secondary"> · none</Typography.Text>}</Descriptions.Item>)}
        </Descriptions>
        <div>
          <Typography.Text strong>Never stored:</Typography.Text>
          <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>{s.never_stored.map((x) => <li key={x}><Typography.Text type="secondary">{x}</Typography.Text></li>)}</ul>
        </div>
        <Descriptions column={1} bordered size="small" title="Network">
          <Descriptions.Item label="Telemetry / analytics">None. The app has no server.</Descriptions.Item>
          <Descriptions.Item label="Outbound connections">{s.outbound.length === 0 ? "None configured." : s.outbound.map((o) => <div key={o.host}>{o.purpose}: <code>{o.host}:{o.port}</code> — {o.when}</div>)}</Descriptions.Item>
          <Descriptions.Item label="Offline mode"><Space><Switch checked={s.offline_mode} onChange={toggle("offline_mode")} /><Typography.Text type="secondary"><strong>On by default.</strong> Blocks every connection at the socket level, including mailbox drafts. Document generation never needs the network. Turn it off only while saving a draft to your mailbox.</Typography.Text></Space></Descriptions.Item>
          <Descriptions.Item label="Keep document history"><Space><Switch checked={s.keep_history} onChange={toggle("keep_history")} /><Typography.Text type="secondary">Off: nothing is listed under Recent documents (files are still saved).</Typography.Text></Space></Descriptions.Item>
        </Descriptions>
        <Space wrap>
          <Button icon={<ApiOutlined />} loading={busy === "net"} disabled={s.offline_mode || s.outbound.length === 0} onClick={async () => { setBusy("net"); setNet(null); setNetErr(null); try { setNet(await (await backend()).networkCheck()); } catch (e) { setNetErr(describeError(e).detail); } finally { setBusy(null); } }}>Check mail server reachability (VPN test)</Button>
          <Button icon={<DeleteOutlined />} danger loading={busy === "clear"} onClick={() => Modal.confirm({ title: "Delete all generated documents and history?", content: "Every job folder in the output folder listed above and all history entries will be removed. The mailbox password is not affected.", okText: "Delete everything", okButtonProps: { danger: true }, onOk: () => act("clear", async () => { const r = await (await backend()).historyClear(true); return `Deleted ${r.removed_job_folders} document folders and ${r.removed_rows} history entries`; }) })}>Delete all documents & history</Button>
          <Button icon={<ClearOutlined />} loading={busy === "logs"} onClick={() => act("logs", async () => { await (await backend()).privacyClearLogs(); const c = await (await backend()).privacyCleanup(); return `Logs cleared; removed ${c.removed_temp_dirs} temp folders and ${c.removed_partial_files} partial files`; })}>Clear logs & temp files</Button>
          <Button icon={<FolderOpenOutlined />} onClick={async () => (await backend()).openDataDir()}>Open data folder</Button>
        </Space>
        {netErr && <Alert type="warning" showIcon message={netErr} />}
        {net && (
          <Alert type={net.ok ? "success" : "error"} showIcon message={net.ok ? `Mail server reachable through your current network (${net.ms} ms)` : "Mail server not reachable"} description={
            <Descriptions column={1} size="small">
              <Descriptions.Item label="DNS">{net.dns ? (net.dns.ok ? `OK → ${net.dns.addresses?.join(", ")}` : net.dns.error) : "—"}</Descriptions.Item>
              <Descriptions.Item label="TCP connect">{net.tcp ? (net.tcp.ok ? "OK" : net.tcp.error) : "not attempted"}</Descriptions.Item>
              <Descriptions.Item label="TLS">{net.tls ? (net.tls.ok ? `OK (${net.tls.protocol}, certificate for ${net.tls.subject})` : net.tls.error) : "not attempted"}</Descriptions.Item>
            </Descriptions>} />
        )}
        <Typography.Text type="secondary">Using a VPN: all traffic, including the IMAP connection, goes through the VPN as your system routes it. If the check fails only while the VPN is on, the VPN or its DNS is blocking port {s.outbound[0]?.port ?? 993}; ask the VPN provider to allow it, or save a .eml file instead.</Typography.Text>
      </Space>
    </Card>
  );
}
