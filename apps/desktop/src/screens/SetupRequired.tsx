// Shown instead of the app until every dependency is in place: the engine's runtime modules,
// LibreOffice, and a usable template. Nothing can be generated before this passes.
import { Alert, Button, Card, Space, Table, Tag, Typography } from "antd";
import { DownloadOutlined, ReloadOutlined, SettingOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { SelfCheck } from "../api/types";
import { useStore } from "../store";

export function SetupRequired({ check, engineFailure, onRecheck, busy }: { check: SelfCheck | null; engineFailure: string | null; onRecheck: () => void; busy: boolean }) {
  const { dispatch } = useStore();
  const failing = check?.checks.filter((c) => !c.ok) ?? [];
  const needsLibreOffice = failing.some((c) => c.check === "LibreOffice installed");
  return (
    <div style={{ maxWidth: 820, margin: "0 auto" }}>
      <Card className="glass" title={<Space><Tag color="red">Setup required</Tag><span>Papyra cannot start until these are fixed</span></Space>}
        extra={<Button icon={<ReloadOutlined />} loading={busy} onClick={onRecheck}>Check again</Button>}>
        {engineFailure && <Alert type="error" showIcon message="The document engine refused to start" description={engineFailure} style={{ marginBottom: 16 }} />}
        {failing.length > 0 && (
          <Table size="small" pagination={false} rowKey="check" dataSource={failing} columns={[
            { title: "Missing", dataIndex: "check", width: 240 },
            { title: "Detail", key: "d", render: (_: unknown, c) => <><span>{c.detail}</span>{c.fix && <div><Typography.Text type="warning">{c.fix}</Typography.Text></div>}</> },
          ]} />
        )}
        <Space wrap style={{ marginTop: 16 }}>
          {needsLibreOffice && <Button type="primary" icon={<DownloadOutlined />} onClick={async () => (await backend()).openLibreOfficeDownload()}>Get LibreOffice (free)</Button>}
          <Button icon={<SettingOutlined />} onClick={() => dispatch({ type: "navigate", view: "settings" })}>Open diagnostics</Button>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>
          Papyra checks its own packaging, LibreOffice and the templates every time it starts. Install what is missing, then click Check again; no restart is needed.
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
