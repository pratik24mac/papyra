// Settings → Diagnostics → "Run full check": the engine checks its own packaging, LibreOffice,
// leftover processes and a real test conversion, and shows the recent log. "Copy report" puts
// everything on the clipboard so a problem can be reported without hunting for files.
import { useState } from "react";
import { Alert, Button, Space, Table, Tag, Typography, message } from "antd";
import { CopyOutlined, ExperimentOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import type { SelfCheck } from "../api/types";
import { describeError } from "../lib/errors";

export function SelfCheckCard() {
  const [result, setResult] = useState<SelfCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setBusy(true); setError(null);
    try { setResult(await (await backend()).selfCheck()); }
    catch (e) { const d = describeError(e); setError(`${d.title}: ${d.detail}`); }
    finally { setBusy(false); }
  };
  const copy = async () => {
    if (!result) return;
    const text = ["Papyra diagnostics report", `overall: ${result.ok ? "OK" : "PROBLEMS"}`, "",
      ...result.checks.map((c) => `${c.ok ? "PASS" : "FAIL"}  ${c.check}: ${c.detail}${c.fix ? `\n      fix: ${c.fix}` : ""}`),
      "", `log: ${result.log_path ?? "-"}`, ...result.log_tail].join("\n");
    try { await navigator.clipboard.writeText(text); message.success("Report copied to the clipboard"); } catch { message.error("Could not copy"); }
  };
  return (
    <Space orientation="vertical" style={{ width: "100%" }} size="middle">
      <Space wrap>
        <Button type="primary" icon={<ExperimentOutlined />} loading={busy} onClick={run}>Run full check (includes a test PDF conversion)</Button>
        {result && <Button icon={<CopyOutlined />} onClick={copy}>Copy report</Button>}
        {result && (result.ok ? <Tag color="green">Everything works</Tag> : <Tag color="red">Problems found</Tag>)}
      </Space>
      {error && <Alert type="error" showIcon message={error} />}
      {result && (
        <>
          <Table size="small" pagination={false} rowKey="check" dataSource={result.checks} columns={[
            { title: "", dataIndex: "ok", width: 70, render: (ok: boolean) => <Tag color={ok ? "green" : "red"}>{ok ? "PASS" : "FAIL"}</Tag> },
            { title: "Check", dataIndex: "check", width: 240 },
            { title: "Detail", key: "d", render: (_: unknown, c) => <><span style={{ wordBreak: "break-all" }}>{c.detail}</span>{c.fix && <div><Typography.Text type="warning">{c.fix}</Typography.Text></div>}</> },
          ]} />
          <div>
            <Typography.Text type="secondary">Recent engine log ({result.log_path ?? "no log file"}), personal data redacted:</Typography.Text>
            <pre style={{ maxHeight: 220, overflow: "auto", background: "#101012", padding: 12, borderRadius: 10, fontSize: 11, margin: "6px 0 0" }}>{result.log_tail.join("\n") || "(empty)"}</pre>
          </div>
        </>
      )}
    </Space>
  );
}
