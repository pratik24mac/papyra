// Settings → Dates: one format for every printed date (a template or a field may still override it).
import { useEffect, useState } from "react";
import { Card, Input, Select, Space, Typography, message } from "antd";
import { backend } from "../api/backend";
import type { AppSettings } from "../api/types";
import { describeError } from "../lib/errors";

export function DateFormatCard() {
  const [s, setS] = useState<AppSettings | null>(null);
  const [custom, setCustom] = useState("");
  const load = async () => setS(await (await backend()).settingsGet());
  useEffect(() => { load(); }, []);
  const apply = async (fmt: string) => {
    try { setS(await (await backend()).settingsSet("date_format", fmt)); message.success("Date format saved"); }
    catch (e) { const d = describeError(e); message.error(`${d.title}: ${d.detail}`); }
  };
  if (!s) return null;
  const presets = s.date_format_presets ?? [];
  const isPreset = presets.some((p) => p.format === s.date_format);
  return (
    <Card className="glass" title="Dates in documents">
      <Space orientation="vertical" style={{ width: "100%" }}>
        <Typography.Text type="secondary">Dates are entered with a date picker and printed in this format in every document. A template can set its own format, and a single field can override both.</Typography.Text>
        <Space wrap>
          <Select style={{ minWidth: 320 }} value={isPreset ? s.date_format : "custom"} onChange={(v) => v !== "custom" && apply(v)}
            options={[...presets.map((p) => ({ value: p.format, label: `${p.example}  ·  ${p.format}` })), { value: "custom", label: "Custom…" }]} />
          <Input placeholder="Custom, e.g. Do MMM YYYY" style={{ width: 220 }} value={custom || (isPreset ? "" : s.date_format)} onChange={(e) => setCustom(e.target.value)} onPressEnter={() => custom && apply(custom)} />
        </Space>
        <Typography.Text>Example: <strong>{s.date_format_example}</strong></Typography.Text>
        <Typography.Text type="secondary">Tokens: D or DD day, Do ordinal, M MM MMM MMMM month, YY YYYY year, ddd dddd weekday.</Typography.Text>
      </Space>
    </Card>
  );
}
