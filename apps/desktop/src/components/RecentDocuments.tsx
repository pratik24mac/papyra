// Dashboard: local history (metadata only). Open resumes the preview/email steps for a job;
// Delete removes the history row and, optionally, the files.
import { useEffect, useState } from "react";
import { Button, Card, Empty, Modal, Space, Table, Tag, Typography, message } from "antd";
import { DeleteOutlined, EyeOutlined, FolderOpenOutlined, ReloadOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { HistoryRow } from "../api/types";
import { describeError } from "../lib/errors";
import { useStore } from "../store";

export function RecentDocuments() {
  const { state, dispatch } = useStore();
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const load = async () => { setLoading(true); try { setRows((await (await backend()).historyList(50)).jobs); } finally { setLoading(false); } };
  useEffect(() => { if (state.backend.state === "ready") load(); }, [state.backend.state]);

  const openRow = async (r: HistoryRow) => {
    if (r.kind === "batch" && r.batch_id) {
      try { dispatch({ type: "openBatch", batch: await (await backend()).batchInfo(r.batch_id) }); } catch (e) { message.error(describeError(e).detail); }
    } else dispatch({ type: "openJob", jobId: r.job_id });
  };
  const delBatch = (row: HistoryRow) => Modal.confirm({
    title: `Delete this batch of ${row.documents?.length ?? 0} documents?`,
    content: <Space orientation="vertical"><span>Remove the batch from the history. You can also delete its folder with every Word, PDF and email file.</span><Typography.Text type="secondary">{row.batch_dir}</Typography.Text></Space>,
    okText: "Delete files too", okButtonProps: { danger: true }, cancelText: "Cancel",
    footer: (_, { OkBtn, CancelBtn }) => <Space><CancelBtn /><Button onClick={async () => { await (await backend()).historyDeleteBatch(row.batch_id!, false); Modal.destroyAll(); message.success("Removed from history"); load(); }}>Remove from list only</Button><OkBtn /></Space>,
    onOk: async () => { try { const r = await (await backend()).historyDeleteBatch(row.batch_id!, true); message.success(r.removed_files ? "Folder and history entries deleted" : "History entries deleted"); } catch (e) { message.error(describeError(e).detail); } load(); },
  });
  const del = (row: HistoryRow) => row.kind === "batch" ? delBatch(row) : Modal.confirm({
    title: "Delete this document?",
    content: <Space orientation="vertical"><span>Remove it from the history list. You can also delete the generated files (Word, PDF, .eml) from disk.</span><Typography.Text type="secondary">{row.output_dir}/{row.job_id}</Typography.Text></Space>,
    okText: "Delete files too", okButtonProps: { danger: true }, cancelText: "Cancel",
    footer: (_, { OkBtn, CancelBtn }) => <Space><CancelBtn /><Button onClick={async () => { await (await backend()).historyDelete(row.job_id, false); Modal.destroyAll(); message.success("Removed from history"); load(); }}>Remove from list only</Button><OkBtn /></Space>,
    onOk: async () => { try { const r = await (await backend()).historyDelete(row.job_id, true); message.success(r.removed_files ? "Files and history entry deleted" : "History entry deleted"); } catch (e) { message.error(describeError(e).detail); } load(); },
  });

  return (
    <Card className="glass" style={{ marginTop: 24 }} title="Recent documents" extra={<Button icon={<ReloadOutlined />} size="small" loading={loading} onClick={load}>Refresh</Button>}>
      {rows.length === 0 ? <Empty description={<Typography.Text type="secondary">No documents yet.</Typography.Text>} /> : (
        <Table size="small" rowKey="job_id" pagination={false} dataSource={rows}
          expandable={{ rowExpandable: (r) => r.kind === "batch", expandedRowRender: (r) => (
            <Table size="small" pagination={false} rowKey="job_id" dataSource={r.documents ?? []} showHeader={false} columns={[
              { dataIndex: "template_name", render: (v: string, d) => v ?? d.template_id },
              { dataIndex: "pages", width: 80, render: (v: number | null) => (v ? `${v} pages` : "—") },
              { dataIndex: "status", width: 110, render: (v: string, d) => d.status === "pdf_done" && d.pdf_exists ? <Tag color="green">PDF ready</Tag> : <Tag color="red">{v}</Tag> },
              { key: "a", width: 120, render: (_: unknown, d) => <Button size="small" icon={<EyeOutlined />} disabled={!d.pdf_exists} onClick={() => dispatch({ type: "openJob", jobId: d.job_id })}>Open</Button> },
            ]} />) }}
          columns={[
          { title: "Created", dataIndex: "created_at", render: (v: string) => new Date(v).toLocaleString() },
          { title: "Template", dataIndex: "template_id", render: (v: string, r) => r.kind === "batch" ? <Space size={6}><Tag color="geekblue">{r.documents?.length ?? 0} documents</Tag><span>{v}</span></Space> : `${v} v${r.template_version}` },
          { title: "Pages", dataIndex: "pages", render: (v: number | null) => v ?? "—" },
          { title: "Status", dataIndex: "status", render: (v: string, r) => r.status === "pdf_done" && r.pdf_exists ? <Tag color="green">PDF ready</Tag> : r.status === "pdf_failed" ? <Tag color="red">PDF failed</Tag> : !r.pdf_exists ? <Tag>files missing</Tag> : <Tag color="blue">{v}</Tag> },
          { title: "Drafts", dataIndex: "drafts", render: (v: number) => v || "—" },
          { title: "", key: "actions", render: (_: unknown, r) => <Space>
              <Button size="small" icon={<EyeOutlined />} disabled={!r.pdf_exists} onClick={() => openRow(r)}>Open</Button>
              <Button size="small" icon={<FolderOpenOutlined />} disabled={!r.docx_exists && !r.pdf_exists} onClick={async () => { try { await (await backend()).revealFolder(r.kind === "batch" ? (r.documents?.[0]?.job_id ?? r.job_id) : r.job_id); } catch (e) { message.error(describeError(e).detail); } }} />
              <Button size="small" danger icon={<DeleteOutlined />} onClick={() => del(r)} />
            </Space> },
        ]} />
      )}
    </Card>
  );
}
