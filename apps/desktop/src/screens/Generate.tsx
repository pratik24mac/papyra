import { Alert, Button, Card, Descriptions, Space, Steps, Table, Tag } from "antd";
import type { ProgressStage } from "../api/types";
import { describeError } from "../lib/errors";
import { startGeneration, useStore } from "../store";

// each stage is complete once the backend reports the event that follows it
const STAGES: { key: ProgressStage; title: string; completes: ProgressStage }[] = [
  { key: "validating", title: "Validate values", completes: "rendering_docx" },
  { key: "rendering_docx", title: "Generate Word document", completes: "docx_done" },
  { key: "converting_pdf", title: "Convert to PDF", completes: "pdf_done" },
];

export function Generate() {
  const { state, dispatch } = useStore();
  const job = state.job;
  if (!job) return null;
  const seen = new Set(job.stages.map((s) => s.stage));
  const failed = job.error ? describeError(job.error) : null;
  const current = STAGES.findIndex((s) => !seen.has(s.completes));
  const items = STAGES.map((s, i) => {
    const complete = seen.has(s.completes) || !!job.result;
    const active = !complete && i === current;
    const status = complete ? "finish" : failed && active ? "error" : active && job.inFlight ? "process" : "wait";
    const msg = job.stages.filter((e) => e.stage === s.key || e.stage === s.completes).at(-1)?.message;
    return { title: s.title, status: status as "finish" | "error" | "process" | "wait", content: msg };
  });

  const isBatch = state.templates.length > 1 || !!job.batch;
  const docRows = isBatch ? state.templates.map((t, i) => {
    const ev = job.stages.filter((e) => e.index === i);
    const last = ev.at(-1);
    const done = job.batch?.documents[i];
    const status = done ? done.status : last?.stage === "failed" ? "failed" : ev.length ? "working" : "waiting";
    return { key: t.id, name: t.name, status, message: done?.status === "failed" ? done.error?.message : last?.message ?? "", pages: done?.pages ?? null, pdf: done?.pdf_path ?? null };
  }) : [];
  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Card className="glass" title="Generation progress">
        {isBatch ? (
          <Table size="small" pagination={false} dataSource={docRows} columns={[
            { title: "Document", dataIndex: "name", width: 240 },
            { title: "", dataIndex: "status", width: 110, render: (s: string) => <Tag color={s === "pdf_done" ? "green" : s === "failed" ? "red" : s === "working" ? "blue" : undefined}>{s === "pdf_done" ? "ready" : s}</Tag> },
            { title: "Progress", dataIndex: "message" },
            { title: "Pages", dataIndex: "pages", width: 70, render: (v: number | null) => v ?? "—" },
          ]} />
        ) : <Steps orientation="vertical" size="small" items={items} />}
      </Card>
      {job.batch && (
        <Card className="glass" title={job.batch.ok ? "All documents generated" : "Some documents failed"}>
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="Folder">{job.batch.batch_dir}</Descriptions.Item>
            <Descriptions.Item label="Documents">{job.batch.documents.filter((d) => d.status === "pdf_done").length} of {job.batch.documents.length} ready</Descriptions.Item>
            <Descriptions.Item label="Time">{(job.batch.total_ms / 1000).toFixed(1)} s</Descriptions.Item>
          </Descriptions>
          {job.batch.documents.some((d) => d.status === "pdf_done") && <Button type="primary" style={{ marginTop: 16 }} onClick={() => dispatch({ type: "step", step: 4 })}>Preview PDFs</Button>}
        </Card>
      )}
      {job.result && (
        <Card className="glass" title="Document generated">
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="Word document">{job.result.docx_path}</Descriptions.Item>
            <Descriptions.Item label="PDF">{job.result.pdf_path}</Descriptions.Item>
            <Descriptions.Item label="Pages">{job.result.pages}</Descriptions.Item>
            <Descriptions.Item label="Time">{(job.result.total_ms / 1000).toFixed(1)} s (PDF conversion {job.result.pdf_seconds.toFixed(1)} s)</Descriptions.Item>
          </Descriptions>
          <Button type="primary" style={{ marginTop: 16 }} onClick={() => dispatch({ type: "step", step: 4 })}>Preview PDF</Button>
        </Card>
      )}
      {failed && (
        <Alert type="error" showIcon message={failed.title} description={
          <Space orientation="vertical">
            <span>{failed.detail}</span>
            {failed.action && <strong>{failed.action}</strong>}
            {failed.keptDocx && <span>Word document kept at: {failed.keptDocx}</span>}
            {failed.fieldErrors && <ul style={{ margin: 0 }}>{failed.fieldErrors.map((e) => <li key={e}>{e}</li>)}</ul>}
          </Space>} />
      )}
      <Space>
        {failed?.fieldErrors ? <Button type="primary" onClick={() => dispatch({ type: "step", step: 1 })}>Fix details</Button> : null}
        {!job.inFlight && <Button onClick={() => dispatch({ type: "step", step: 1 })}>Edit details</Button>}
        {!job.inFlight && <Button onClick={() => startGeneration(state, dispatch)}>Generate again</Button>}
        {!job.inFlight && <Button onClick={() => dispatch({ type: "reset" })}>New document</Button>}
      </Space>
    </Space>
  );
}
