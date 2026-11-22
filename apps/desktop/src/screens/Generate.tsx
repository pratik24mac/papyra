import { Alert, Button, Card, Descriptions, Space, Steps } from "antd";
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

  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Card className="glass" title="Generation progress">
        <Steps orientation="vertical" size="small" items={items} />
      </Card>
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
