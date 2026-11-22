import { Button, Card, Descriptions, Space, Typography } from "antd";
import type { FieldSchema, Values } from "../api/types";
import { formatValue, isEmpty } from "../lib/schema";
import { effectiveDateFormat, formatDate } from "../lib/dates";
import { useEffect, useState } from "react";
import { backend } from "../api/backend";
import { startGeneration, useStore } from "../store";
import { SaveToRow } from "../components/SaveToRow";

function Value({ f, v }: { f: FieldSchema; v: unknown }) {
  if (f.type === "group_list") {
    const items = (v as Values[]) ?? [];
    if (!items.length) return <Typography.Text type="secondary">—</Typography.Text>;
    return (
      <Space orientation="vertical" style={{ width: "100%" }}>
        {items.map((item, i) => (
          <Descriptions key={i} size="small" column={1} bordered title={`${f.label.replace(/s$/, "")} ${i + 1}`}>
            {(f.item_fields ?? []).map((sf) => <Descriptions.Item key={sf.id} label={sf.label}><Value f={sf} v={item[sf.id]} /></Descriptions.Item>)}
          </Descriptions>
        ))}
      </Space>
    );
  }
  if (f.type === "text_list") {
    const items = (v as string[]) ?? [];
    return items.length ? <ol style={{ margin: 0, paddingLeft: 20 }}>{items.map((x, i) => <li key={i} style={{ whiteSpace: "pre-wrap" }}>{x}</li>)}</ol> : <Typography.Text type="secondary">—</Typography.Text>;
  }
  const shown = f.type === "date" && typeof v === "string" && v ? `${formatDate(v, dateFormat(f))}` : formatValue(f, v);
  return <Typography.Text style={{ whiteSpace: "pre-wrap" }} type={isEmpty(v) ? "secondary" : undefined}>{shown}</Typography.Text>;
}

let appDateFormat: string | null = null;        // the user's explicit Settings choice, loaded once per review
let templateDateFormat: string | undefined;
function dateFormat(f: FieldSchema): string { return effectiveDateFormat(f.format, appDateFormat, templateDateFormat); }

export function Review() {
  const { state, dispatch } = useStore();
  const t = state.template!;
  const [, bump] = useState(0);
  useEffect(() => { backend().then(async (api) => { const s = await api.settingsGet(); appDateFormat = s.date_format_explicit ?? null; templateDateFormat = state.templates.length === 1 ? state.templates[0].date_format ?? undefined : undefined; bump((n) => n + 1); }); }, [state.templates]);
  const ready = state.backend.state === "ready";
  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Typography.Paragraph type="secondary">Check the details below. Nothing has been generated yet.</Typography.Paragraph>
      {t.groups.map((g) => (
        <Card className="glass" key={g.id} title={g.label} extra={<Button size="small" onClick={() => dispatch({ type: "step", step: 1 })}>Edit</Button>}>
          <Descriptions column={1} bordered size="small">
            {g.fields.map((f) => <Descriptions.Item key={f.id} label={f.label}><Value f={f} v={state.values[f.id]} /></Descriptions.Item>)}
          </Descriptions>
        </Card>
      ))}
      <SaveToRow />
      <Space>
        <Button onClick={() => dispatch({ type: "step", step: 1 })}>Back</Button>
        <Button type="primary" disabled={!ready || state.job?.inFlight} loading={state.job?.inFlight} onClick={() => startGeneration(state, dispatch)}>
          Generate document
        </Button>
        {!ready && <Typography.Text type="secondary">Waiting for the document engine…</Typography.Text>}
      </Space>
    </Space>
  );
}
