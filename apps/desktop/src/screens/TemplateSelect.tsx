import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Col, Row, Skeleton, Space, Tag, Typography, message } from "antd";
import { FolderOpenOutlined, ReloadOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { TemplateSummary } from "../api/types";
import { countRequired, defaultValues } from "../lib/schema";
import { useStore } from "../store";

export function TemplateSelect() {
  const { dispatch } = useStore();
  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async (rescan = false) => {
    setBusy(true); setError(null);
    try { const api = await backend(); setTemplates(rescan ? await api.rescanTemplates() : await api.listTemplates()); }
    catch (e) { setError(String((e as Error)?.message ?? e)); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  // a folder dropped in while the app is open shows up when the window regains focus
  useEffect(() => { const h = () => load(); window.addEventListener("focus", h); return () => window.removeEventListener("focus", h); }, [load]);

  if (error) return <Alert type="error" showIcon message="Could not load templates" description={error} />;
  if (!templates) return <Skeleton active />;
  const openFolder = async () => { try { const d = await (await backend()).openTemplatesDir(); message.info(`Templates folder: ${d}`); } catch (e) { message.error(String((e as Error)?.message ?? e)); } };
  return (
    <div>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 8 }} wrap>
        <Typography.Text type="secondary">Choose the document you want to create. Each template defines its own set of inputs.</Typography.Text>
        <Space>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={openFolder}>My templates folder</Button>
          <Button size="small" icon={<ReloadOutlined />} loading={busy} onClick={() => load(true)}>Rescan templates</Button>
        </Space>
      </Space>
      <Row gutter={[16, 16]}>
        {templates.map((t) => {
          const fields = t.groups.flatMap((g) => g.fields);
          const required = fields.filter((f) => f.required);
          const broken = t.status === "error";
          return (
            <Col xs={24} md={12} key={`${t.id}-${t.source}`}>
              <Card className="glass" title={<Space>{t.name}{t.source === "user" && <Tag color="purple">my template</Tag>}{broken && <Tag color="red">needs fixing</Tag>}</Space>} extra={<Tag>v{t.version}</Tag>}
                actions={[broken
                  ? <Button key="fix" onClick={openFolder} icon={<FolderOpenOutlined />}>Open folder to fix</Button>
                  : <Button key="use" type="primary" onClick={() => dispatch({ type: "selectTemplate", template: t, values: defaultValues(t) })}>Use this template</Button>]}>
                {broken ? (
                  <Alert type="error" showIcon message="This template cannot be used until these are fixed" description={
                    <ul style={{ margin: 0, paddingLeft: 18 }}>{t.problems.map((p, i) => <li key={i} style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{p}</li>)}</ul>} />
                ) : (
                  <>
                    <Typography.Paragraph>{t.description}</Typography.Paragraph>
                    <Typography.Text type="secondary">{fields.length} inputs, {countRequired(t)} required:</Typography.Text>
                    <div style={{ marginTop: 8 }}>{required.map((f) => <Tag key={f.id} color="blue">{f.label}</Tag>)}</div>
                  </>
                )}
                <Typography.Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 11 }}>{t.dir}</Typography.Text>
              </Card>
            </Col>
          );
        })}
      </Row>
    </div>
  );
}
