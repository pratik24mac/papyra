// Step 5: show the PDF, let the user open/save the files, and refuse a stale PDF (spec §8).
import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Space, Tabs, Tag, Typography, message } from "antd";
import { FileWordOutlined, FilePdfOutlined, FolderOpenOutlined, GlobalOutlined, ReloadOutlined, SaveOutlined, MailOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { JobInfo } from "../api/types";
import { PdfViewer } from "../components/PdfViewer";
import { describeError } from "../lib/errors";
import { readyJobIds, useStore } from "../store";

/** One document's preview and actions. `onStale` reports whether its PDF is usable. */
export function DocumentPreview({ jobId, onStale }: { jobId: string; onStale?: (stale: boolean) => void }) {
  const [info, setInfo] = useState<JobInfo | null>(null);
  const [pdf, setPdf] = useState<ArrayBuffer | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<ReturnType<typeof describeError> | null>(null);

  const refresh = useCallback(async () => {
    if (!jobId) return;
    setError(null);
    try {
      const api = await backend();
      const i = await api.jobInfo(jobId);
      setInfo(i); onStale?.(i.state.pdf_stale);
      setPdf(i.state.pdf_stale ? null : await api.readPdf(jobId));
    } catch (e) { setError(describeError(e)); }
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { refresh(); }, [refresh]);
  // re-check when the window regains focus: the user may have edited the Word file meanwhile
  useEffect(() => { const h = () => refresh(); window.addEventListener("focus", h); return () => window.removeEventListener("focus", h); }, [refresh]);

  const run = async (label: string, fn: () => Promise<unknown>, after?: () => void) => {
    setBusy(label); setError(null);
    try { await fn(); after?.(); } catch (e) { setError(describeError(e)); } finally { setBusy(null); }
  };
  const api = () => backend();
  if (!jobId) return null;
  const stale = info?.state.pdf_stale ?? false;

  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      {stale && (
        <Alert type="warning" showIcon message="The Word document was changed after this PDF was created"
          description="To avoid attaching an outdated PDF, regenerate it from the current Word document before continuing."
          action={<Button type="primary" icon={<ReloadOutlined />} loading={busy === "convert"} onClick={() => run("convert", async () => (await api()).convertPdf(jobId), refresh)}>Regenerate PDF</Button>} />
      )}
      {info && !info.state.docx_exists && <Alert type="error" showIcon message="The Word document no longer exists" description="Generate the document again." />}
      {error && <Alert type="error" showIcon message={error.title} description={<>{error.detail}{error.action && <><br /><strong>{error.action}</strong></>}</>} />}
      <Card className="glass" title="PDF preview" extra={
        <Space wrap>
          <Button icon={<FilePdfOutlined />} disabled={stale} loading={busy === "openpdf"} onClick={() => run("openpdf", async () => (await api()).openFile(jobId, "pdf"))}>Open PDF</Button>
          <Button icon={<GlobalOutlined />} disabled={stale} loading={busy === "browser"} onClick={() => run("browser", async () => { const b = await (await api()).openInBrowser(jobId, "pdf"); message.success(`Opened in ${b}`); })}>Open PDF in browser</Button>
          <Button icon={<FileWordOutlined />} loading={busy === "opendocx"} onClick={() => run("opendocx", async () => (await api()).openFile(jobId, "docx"))}>Open in Word</Button>
          <Button icon={<SaveOutlined />} disabled={stale} loading={busy === "save"} onClick={() => run("save", async () => { const p = await (await api()).saveCopy(jobId, "pdf"); if (p) message.success(`Saved a copy to ${p}`); })}>Save a copy…</Button>
          <Button icon={<FolderOpenOutlined />} onClick={() => run("reveal", async () => (await api()).revealFolder(jobId))}>Show in folder</Button>
        </Space>}>
        {stale ? <Typography.Text type="secondary">Preview hidden: the PDF is out of date.</Typography.Text> : <PdfViewer data={pdf} />}
      </Card>
    </Space>
  );
}

export function Preview() {
  const { state, dispatch } = useStore();
  const ready = readyJobIds(state.job);
  const [staleById, setStaleById] = useState<Record<string, boolean>>({});
  const [active, setActive] = useState<string | null>(null);
  if (!ready.length) return null;
  const batch = state.job?.batch ?? null;
  const current = active && ready.includes(active) ? active : ready[0];
  const anyStale = ready.some((id) => staleById[id]);
  const markStale = (id: string) => (v: boolean) => setStaleById((m) => (m[id] === v ? m : { ...m, [id]: v }));
  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      {batch ? (
        <Tabs activeKey={current} onChange={setActive} items={batch.documents.map((d) => ({
          key: d.job_id, disabled: d.status !== "pdf_done",
          label: <Space size={6}>{d.template_name}{d.status !== "pdf_done" ? <Tag color="red">failed</Tag> : staleById[d.job_id] ? <Tag color="orange">out of date</Tag> : null}</Space>,
          children: d.status === "pdf_done" ? <DocumentPreview jobId={d.job_id} onStale={markStale(d.job_id)} />
                   : <Alert type="error" showIcon message={`${d.template_name} was not generated`} description={d.error?.message} />,
        }))} />
      ) : <DocumentPreview jobId={ready[0]} onStale={markStale(ready[0])} />}
      <Space>
        <Button onClick={() => dispatch({ type: "step", step: 1 })}>Correct details</Button>
        <Button type="primary" icon={<MailOutlined />} disabled={anyStale} onClick={() => dispatch({ type: "step", step: 5 })}>Continue to email</Button>
        <Button onClick={() => dispatch({ type: "reset" })}>New document</Button>
      </Space>
    </Space>
  );
}
