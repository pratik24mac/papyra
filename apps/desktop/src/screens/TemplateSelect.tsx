import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Checkbox, Col, Row, Skeleton, Space, Tag, Typography, message } from "antd";
import { FolderOpenOutlined, ReloadOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { TemplateSummary } from "../api/types";
import { countRequired, defaultValues } from "../lib/schema";
import { mergeTemplates } from "../lib/merge";
import { useStore } from "../store";

export function TemplateSelect() {
  const { dispatch } = useStore();
  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<string[]>([]);
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
  const toggle = (id: string, on: boolean) => setPicked((p) => (on ? [...p.filter((x) => x !== id), id] : p.filter((x) => x !== id)));
  const startBatch = () => {
    const chosen = templates.filter((t) => picked.includes(t.id) && t.status === "ok");
    if (chosen.length < 2) return;
    const merged = mergeTemplates(chosen);
    dispatch({ type: "selectTemplates", templates: chosen, values: defaultValues(merged.summary) });
  };
  const openFolder = async () => { try { const d = await (await backend()).openTemplatesDir(); message.info(`Templates folder: ${d}`); } catch (e) { message.error(String((e as Error)?.message ?? e)); } };
  return (
    <div>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 8 }} wrap>
        <Typography.Text type="secondary">Choose one template, or tick several to fill their shared details once and generate them together.</Typography.Text>
        <Space>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={openFolder}>My templates folder</Button>
          <Button size="small" icon={<ReloadOutlined />} loading={busy} onClick={() => load(true)}>Rescan templates</Button>
        </Space>
      </Space>
      <Row gutter={[12, 12]}>
        {templates.map((t) => {
          const fields = t.groups.flatMap((g) => g.fields);
          const required = fields.filter((f) => f.required);
          const broken = t.status === "error";
          return (
            <Col xs={24} md={12} lg={8} key={`${t.id}-${t.source}`}>
              <Card className="glass" size="small" styles={{ body: { padding: 12 } }} title={<Space>{!broken && <Checkbox checked={picked.includes(t.id)} onChange={(e) => toggle(t.id, e.target.checked)} aria-label={`Select ${t.name}`} />}{t.name}{t.source === "user" && <Tag color="purple">my template</Tag>}{broken && <Tag color="red">needs fixing</Tag>}</Space>} extra={<Tag>v{t.version}</Tag>}
                actions={[broken
                  ? <Button key="fix" onClick={openFolder} icon={<FolderOpenOutlined />}>Open folder to fix</Button>
                  : <Button key="use" type="primary" onClick={() => dispatch({ type: "selectTemplate", template: t, values: defaultValues(t) })}>Use this template</Button>]}>
                {broken ? (
                  <Alert type="error" showIcon message="This template cannot be used until these are fixed" description={
                    <ul style={{ margin: 0, paddingLeft: 18 }}>{t.problems.map((p, i) => <li key={i} style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{p}</li>)}</ul>} />
                ) : (
                  <>
                    <Typography.Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ marginBottom: 6, fontSize: 12 }}>{t.description}</Typography.Paragraph>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>{fields.length} inputs · {countRequired(t)} required · {required.slice(0, 4).map((f) => f.label).join(", ")}{required.length > 4 ? "…" : ""}</Typography.Text>
                  </>
                )}
                {broken && <Typography.Text type="secondary" style={{ display: "block", marginTop: 6, fontSize: 11 }}>{t.dir}</Typography.Text>}
              </Card>
            </Col>
          );
        })}
      </Row>
      {picked.length > 0 && (
        <div className="glass" style={{ position: "sticky", bottom: 12, marginTop: 16, padding: 12, borderRadius: 12, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <Space orientation="vertical" size={2}>
            <Typography.Text>{picked.length} selected: {templates.filter((t) => picked.includes(t.id)).map((t) => t.name).join(", ")}</Typography.Text>
            {(() => { const sel = templates.filter((t) => picked.includes(t.id) && t.status === "ok"); if (sel.length < 2) return null;
              const conflicts = mergeTemplates(sel).summary.groups.flatMap((g) => g.fields).filter((f) => f.id.includes("__")).map((f) => f.label);
              return conflicts.length ? <Typography.Text type="warning" style={{ fontSize: 12 }}>Asked separately because the templates define them differently: {conflicts.join(", ")}</Typography.Text> : null; })()}
          </Space>
          <Space>
            <Button size="small" onClick={() => setPicked([])}>Clear</Button>
            <Button type="primary" disabled={picked.length < 2} onClick={startBatch}>Generate {picked.length} documents together</Button>
          </Space>
        </div>
      )}
    </div>
  );
}
