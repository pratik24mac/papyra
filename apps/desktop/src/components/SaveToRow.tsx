// "Save to": where this document's folder goes. Defaults to the Settings folder; a chosen folder
// is remembered for the next document in this session and as the engine's last choice.
import { useEffect, useState } from "react";
import { Button, Card, Space, Typography, message } from "antd";
import { FolderOpenOutlined, UndoOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import { describeError } from "../lib/errors";
import { useStore } from "../store";

export function SaveToRow() {
  const { state, dispatch } = useStore();
  const [defaultDir, setDefaultDir] = useState<string>("");
  useEffect(() => { backend().then(async (api) => { const s = await api.settingsGet(); setDefaultDir(s.output_dir); if (!state.outputDir && s.last_output_dir) dispatch({ type: "setOutputDir", dir: s.last_output_dir }); }); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const choose = async () => {
    try { const d = await (await backend()).chooseOutputDir(); if (d) dispatch({ type: "setOutputDir", dir: d }); }
    catch (e) { message.error(describeError(e).detail); }
  };
  const current = state.outputDir ?? defaultDir;
  return (
    <Card className="glass" size="small" title="Save to">
      <Space wrap style={{ width: "100%", justifyContent: "space-between" }}>
        <Typography.Text style={{ wordBreak: "break-all" }}>{current || "…"}{!state.outputDir && <Typography.Text type="secondary"> (default from Settings)</Typography.Text>}</Typography.Text>
        <Space>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={choose}>Change…</Button>
          <Button size="small" icon={<UndoOutlined />} disabled={!state.outputDir} onClick={() => dispatch({ type: "setOutputDir", dir: null })}>Use default</Button>
        </Space>
      </Space>
      <Typography.Text type="secondary" style={{ display: "block", marginTop: 6, fontSize: 12 }}>A sub-folder is created there for this document's Word, PDF and email files.</Typography.Text>
    </Card>
  );
}
