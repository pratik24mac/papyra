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

  const del = (row: HistoryRow) => Modal.confirm({
    title: "Delete this document?",
    content: <Space orientation="vertical"><span>Remove it from the history list. You can also delete the generated files (Word, PDF, .eml) from disk.</span><Typography.Text type="secondary">{row.output_dir}/{row.job_id}</Typography.Text></Space>,
    okText: "Delete files too", okButtonProps: { danger: true }, cancelText: "Cancel",
    footer: (_, { OkBtn, CancelBtn }) => <Space><CancelBtn /><Button onClick={async () => { await (await backend()).historyDelete(row.job_id, false); Modal.destroyAll(); message.success("Removed from history"); load(); }}>Remove from list only</Button><OkBtn /></Space>,
    onOk: async () => { try { const r = await (await backend()).historyDelete(row.job_id, true); message.success(r.removed_files ? "Files and history entry deleted" : "History entry deleted"); } catch (e) { message.error(describeError(e).detail); } load(); },
  });

  return (
    <Card className="glass" style={{ marginTop: 24 }} title="Recent documents" extra={<Button icon={<ReloadOutlined />} size="small" loading={loading} onClick={load}>Refresh</Button>}>
      {rows.length === 0 ? <Empty description={<Typography.Text type="secondary">No documents yet.</Typography.Text>} /> : (
        <Table size="small" rowKey="job_id" pagination={false} dataSource={rows} columns={[
          { title: "Created", dataIndex: "created_at", render: (v: string) => new Date(v).toLocaleString() },
          { title: "Template", dataIndex: "template_id", render: (v: string, r) => `${v} v${r.template_version}` },
          { title: "Pages", dataIndex: "pages", render: (v: number | null) => v ?? "—" },
          { title: "Status", dataIndex: "status", render: (v: string, r) => r.status === "pdf_done" && r.pdf_exists ? <Tag color="green">PDF ready</Tag> : r.status === "pdf_failed" ? <Tag color="red">PDF failed</Tag> : !r.pdf_exists ? <Tag>files missing</Tag> : <Tag color="blue">{v}</Tag> },
          { title: "Drafts", dataIndex: "drafts", render: (v: number) => v || "—" },
          { title: "", key: "actions", render: (_: unknown, r) => <Space>
              <Button size="small" icon={<EyeOutlined />} disabled={!r.pdf_exists} onClick={() => dispatch({ type: "openJob", jobId: r.job_id })}>Open</Button>
              <Button size="small" icon={<FolderOpenOutlined />} disabled={!r.docx_exists && !r.pdf_exists} onClick={async () => { try { await (await backend()).revealFolder(r.job_id); } catch (e) { message.error(describeError(e).detail); } }} />
              <Button size="small" danger icon={<DeleteOutlined />} onClick={() => del(r)} />
            </Space> },
        ]} />
      )}
    </Card>
  );
}
