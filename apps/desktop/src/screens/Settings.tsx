import { useEffect, useState } from "react";
import { Alert, Button, Card, Descriptions, Space, Tag, Typography, message } from "antd";
import { FolderOpenOutlined, ReloadOutlined, UndoOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { AppSettings, Diagnostics, PingResult } from "../api/types";
import { describeError } from "../lib/errors";
import { useStore } from "../store";
import { EmailAccountCard } from "../components/EmailAccountCard";
import { PrivacyCard } from "../components/PrivacyCard";
import { SelfCheckCard } from "../components/SelfCheckCard";
import { DateFormatCard } from "../components/DateFormatCard";

export function Settings() {
  const { state } = useStore();
  const [diag, setDiag] = useState<Diagnostics | null>(null);
  const [ping, setPing] = useState<PingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [folderBusy, setFolderBusy] = useState(false);
  const [tplBusy, setTplBusy] = useState(false);
  const changeTemplatesFolder = async (value?: string | null) => {
    setTplBusy(true);
    try {
      const api = await backend();
      let target = value;
      if (target === undefined) { target = await api.chooseTemplatesDir(); if (!target) return; }
      const s = await api.settingsSet("user_templates_dir", target);
      setSettings(s); setDiag(await api.diagnostics());
      message.success(target ? `Templates are now read from ${s.user_templates_dir}` : "Templates folder reset to default");
    } catch (e) { const d = describeError(e); message.error(`${d.title}: ${d.detail}`); }
    finally { setTplBusy(false); }
  };
  const refresh = async () => {
    setLoading(true); setError(null);
    try { const api = await backend(); setPing(await api.ping()); setDiag(await api.diagnostics()); setSettings(await api.settingsGet()); }
    catch (e) { setError(String((e as Error)?.message ?? e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (state.backend.state === "ready") refresh(); }, [state.backend.state]);
  const changeFolder = async (value?: string | null) => {
    setFolderBusy(true);
    try {
      const api = await backend();
      let target = value;
      if (target === undefined) { target = await api.chooseOutputDir(); if (!target) return; }
      const s = await api.settingsSet("output_dir", target);
      setSettings(s); setDiag(await api.diagnostics());
      message.success(target ? `Documents will be saved to ${s.output_dir}` : "Output folder reset to default");
    } catch (e) { const d = describeError(e); message.error(`${d.title}: ${d.detail}`); }
    finally { setFolderBusy(false); }
  };
  const ok = (b: boolean, yes = "OK", no = "Problem") => <Tag color={b ? "green" : "red"}>{b ? yes : no}</Tag>;
  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ marginTop: 0 }}>Settings</Typography.Title>
      <Card className="glass" title="Diagnostics" extra={<Button icon={<ReloadOutlined />} loading={loading} onClick={refresh}>Re-check</Button>}>
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="Document engine">{ping ? <>{ok(true, "Running")} {ping.name} {ping.version} · Python {ping.python} · pid {ping.pid}</> : <Tag>unknown</Tag>}</Descriptions.Item>
          <Descriptions.Item label="LibreOffice">{diag ? <>{ok(diag.libreoffice.found, "Found", "Not found")} {diag.libreoffice.version ?? "Install LibreOffice to enable PDF conversion"} <br /><Typography.Text type="secondary">{diag.libreoffice.path}</Typography.Text></> : "—"}</Descriptions.Item>
          <Descriptions.Item label="Templates">{diag ? <>{ok(diag.templates > 0)} {diag.templates} usable · bundled: {diag.templates_dir}</> : "—"}</Descriptions.Item>
          <Descriptions.Item label="My templates folder">{diag ? diag.user_templates_dir : "—"}</Descriptions.Item>
          <Descriptions.Item label="Output folder">{diag ? <>{ok(diag.output_dir_writable, "Writable", "Not writable")} {diag.output_dir}</> : "—"}</Descriptions.Item>
          <Descriptions.Item label="Platform">{diag?.platform ?? "—"}</Descriptions.Item>
        </Descriptions>
        <div style={{ marginTop: 16 }}><SelfCheckCard /></div>
      </Card>
      <Card className="glass" title="My templates folder" extra={<Space>
          <Button icon={<FolderOpenOutlined />} loading={tplBusy} onClick={() => changeTemplatesFolder()}>Choose folder…</Button>
          <Button icon={<UndoOutlined />} disabled={!settings || !settings.defaults.user_templates_dir || settings.user_templates_dir === settings.defaults.user_templates_dir} onClick={() => changeTemplatesFolder(null)}>Reset to default</Button>
          <Button onClick={async () => (await backend()).openTemplatesDir()}>Open</Button>
        </Space>}>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="Templates are read from">{settings?.user_templates_dir ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="Default">{settings?.defaults.user_templates_dir ?? "—"}</Descriptions.Item>
        </Descriptions>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>Each template is a folder named by its id with a v1 sub-folder; a shared _assets folder holds watermarks. The list rescans as soon as the folder changes. Bundled templates are always available.</Typography.Paragraph>
      </Card>
      <Card className="glass" title="Output folder" extra={<Space>
          <Button icon={<FolderOpenOutlined />} loading={folderBusy} onClick={() => changeFolder()}>Choose folder…</Button>
          <Button icon={<UndoOutlined />} disabled={!settings || settings.output_dir === settings.defaults.output_dir} onClick={() => changeFolder(null)}>Reset to default</Button>
        </Space>}>
        <Descriptions column={1} bordered size="small">
          <Descriptions.Item label="Generated documents go to">{settings?.output_dir ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="Default">{settings?.defaults.output_dir ?? "—"}</Descriptions.Item>
        </Descriptions>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>Each generated document gets its own sub-folder here. Documents already generated stay where they are.</Typography.Paragraph>
      </Card>
      <DateFormatCard />
      <EmailAccountCard />
      <PrivacyCard />
    </Space>
  );
}
