// Renders one schema field as an Ant Design form control. Template-specific knowledge lives in
// schema.yaml, never here.
import { Button, Card, Checkbox, DatePicker, Form, Input, InputNumber, Select, Space, Typography } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import type { FieldSchema } from "../api/types";
import { emptyItem, rulesFor, type NamePath } from "../lib/schema";

const { TextArea } = Input;

// Form.Item injects value/onChange/id into its direct child, so every prop must be forwarded.
function Control({ f, ...rest }: { f: FieldSchema } & Record<string, unknown>) {
  const v = f.validation ?? {};
  switch (f.type) {
    case "multiline": return <TextArea autoSize={{ minRows: 3, maxRows: 10 }} maxLength={v.max_length} showCount={!!v.max_length} {...rest} />;
    case "number": return <InputNumber style={{ width: "100%" }} min={v.min} max={v.max} {...rest} />;
    case "select": return <Select allowClear={!f.required} options={(f.options ?? []).map((o) => (typeof o === "string" ? { value: o, label: o } : o))} {...rest} />;
    case "checkbox": return <Checkbox {...rest}>{f.help ?? f.label}</Checkbox>;
    case "date": return <DatePicker style={{ width: "100%" }} format="YYYY-MM-DD" {...rest} />;
    case "email": return <Input type="email" maxLength={v.max_length} {...rest} />;
    case "url": return <Input placeholder="https://…" maxLength={v.max_length} {...rest} />;
    default: return <Input maxLength={v.max_length} {...rest} />;
  }
}

export function FieldRenderer({ f, prefix = [] }: { f: FieldSchema; prefix?: NamePath }) {
  const name = [...prefix, f.id];
  const rules = rulesFor(f);

  if (f.type === "group_list") {
    return (
      <Form.Item label={f.label} required={!!f.required} tooltip={f.help}>
        <Form.List name={name} rules={[{ validator: rules[0]?.validator ?? (async () => {}) }]}>
          {(items, { add, remove }, { errors }) => (
            <Space orientation="vertical" style={{ width: "100%" }} size="middle">
              {items.map((item, idx) => (
                <Card key={item.key} size="small" title={`${f.label.replace(/s$/, "")} ${idx + 1}`}
                  extra={<Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(item.name)} aria-label={`Remove ${f.label} ${idx + 1}`} />}>
                  {(f.item_fields ?? []).map((sf) => <FieldRenderer key={sf.id} f={sf} prefix={[item.name]} />)}
                </Card>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add(emptyItem(f))} block disabled={!!f.validation?.max_items && items.length >= f.validation.max_items}>
                Add {f.label.replace(/s$/, "").toLowerCase()}
              </Button>
              <Form.ErrorList errors={errors} />
            </Space>
          )}
        </Form.List>
      </Form.Item>
    );
  }

  if (f.type === "text_list") {
    const itemRules = rulesFor({ id: "item", label: f.label.replace(/s$/, ""), type: f.item?.type ?? "text", required: true, validation: f.item?.validation });
    return (
      <Form.Item label={f.label} required={!!f.required} tooltip={f.help}>
        <Form.List name={name} rules={[{ validator: rules[0]?.validator ?? (async () => {}) }]}>
          {(items, { add, remove }, { errors }) => (
            <Space orientation="vertical" style={{ width: "100%" }} size="small">
              {items.map((item, idx) => (
                <Space key={item.key} align="start" style={{ width: "100%", display: "flex" }}>
                  <Typography.Text type="secondary" style={{ paddingTop: 6, width: 24 }}>{idx + 1}.</Typography.Text>
                  <Form.Item name={item.name} rules={itemRules} style={{ flex: 1, marginBottom: 0, minWidth: 480 }}>
                    <TextArea autoSize={{ minRows: 1, maxRows: 6 }} maxLength={f.item?.validation?.max_length} />
                  </Form.Item>
                  <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(item.name)} aria-label={`Remove item ${idx + 1}`} />
                </Space>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add("")} disabled={!!f.validation?.max_items && items.length >= f.validation.max_items}>
                Add {f.label.replace(/s$/, "").toLowerCase()}
              </Button>
              <Form.ErrorList errors={errors} />
            </Space>
          )}
        </Form.List>
      </Form.Item>
    );
  }

  const extra: Record<string, unknown> = {};
  if (f.type === "checkbox") extra.valuePropName = "checked";
  if (f.type === "date") {
    extra.getValueProps = (v: unknown) => ({ value: v ? dayjs(String(v)) : null });
    extra.normalize = (v: dayjs.Dayjs | null) => (v ? v.format("YYYY-MM-DD") : undefined);
  }
  return (
    <Form.Item name={name} label={f.type === "checkbox" ? undefined : f.label} rules={rules} tooltip={f.type === "checkbox" ? undefined : f.help} validateFirst {...extra}>
      <Control f={f} />
    </Form.Item>
  );
}
