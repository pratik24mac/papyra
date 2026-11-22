import { useEffect, useState } from "react";
import { Alert, Button, Card, Form, Modal, Space, Typography, message } from "antd";
import { ExperimentOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import { FieldGrid } from "../lib/layout";
import { describeError } from "../lib/errors";
import { defaultValues, expandDefault, parseServerError } from "../lib/schema";
import { mergeExamples, mergeTemplates } from "../lib/merge";
import type { Values } from "../api/types";
import { useStore } from "../store";

export function DocumentForm() {
  const { state, dispatch } = useStore();
  const [form] = Form.useForm();
  const t = state.template!;
  const serverErrors = state.job?.error ? describeError(state.job.error).fieldErrors : undefined;

  useEffect(() => {
    form.setFieldsValue(state.values);
    if (serverErrors?.length) {
      form.setFields(serverErrors.map((line) => { const { name, message } = parseServerError(line); return { name, errors: [message] }; }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t.id]);

  const persist = () => dispatch({ type: "setValues", values: form.getFieldsValue(true) });

  const next = async () => {
    try {
      await form.validateFields();
    } catch {
      form.scrollToField((form.getFieldsError().find((f) => f.errors.length) ?? { name: [] }).name, { block: "center" });
      return;
    }
    const values = form.getFieldsValue(true);
    // expand defaults like "Resume — {full_name}" that still contain placeholders
    for (const g of t.groups) for (const f of g.fields) {
      if (typeof f.default === "string" && typeof values[f.id] === "string" && values[f.id] === f.default) values[f.id] = expandDefault(f.default, values);
    }
    dispatch({ type: "setValues", values });
    dispatch({ type: "step", step: 2 });
  };

  const [prefilling, setPrefilling] = useState(false);
  // "own input" = anything that differs from the untouched form (defaults, empty lists, unchecked boxes)
  const hasOwnInput = () => {
    const blank = defaultValues(t), current = form.getFieldsValue(true);
    return Object.keys(current).some((id) => JSON.stringify(current[id] ?? null) !== JSON.stringify(blank[id] ?? null));
  };
  const prefill = async () => {
    setPrefilling(true);
    try {
      const api = await backend();
      let v: Values;
      if (state.templates.length > 1) {
        const merged = mergeTemplates(state.templates);
        const examples: Record<string, Values> = {};
        for (const tpl of state.templates) if (tpl.has_examples) examples[tpl.id] = await api.exampleValues(tpl.id);
        v = mergeExamples(merged, examples);
      } else {
        v = await api.exampleValues(t.id);
      }
      form.setFieldsValue(v); dispatch({ type: "setValues", values: v });
      message.success("Form pre-filled with the template's example values");
    } catch (e) { message.error(describeError(e).detail); } finally { setPrefilling(false); }
  };
  const prefillButton = t.has_examples ? (
    <Button icon={<ExperimentOutlined />} loading={prefilling} onClick={() => hasOwnInput()
      ? Modal.confirm({ title: "Replace what you typed?", content: "Pre-filling overwrites every field with the template's example values.", okText: "Pre-fill", onOk: prefill })
      : prefill()}>Pre-fill with example values</Button>
  ) : null;

  return (
    <Form form={form} layout="vertical" initialValues={state.values} onValuesChange={persist} scrollToFirstError requiredMark autoComplete="off">
      {serverErrors?.length ? <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="The document engine rejected some values" description="The fields are marked below." /> : null}
      <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
        {prefillButton && <Space style={{ width: "100%", justifyContent: "space-between" }} wrap>
          <Typography.Text type="secondary">Fill in the details below, or start from the template's example values and edit them.</Typography.Text>
          {prefillButton}
        </Space>}
        {t.groups.map((g) => (
          <Card className="glass" key={g.id} title={g.label} id={`group-${g.id}`} extra={g.print === false ? <Typography.Text type="secondary">Used for the email draft, not printed</Typography.Text> : null}>
            <FieldGrid fields={g.fields} />
          </Card>
        ))}
        <Space>
          <Button onClick={() => { persist(); dispatch({ type: "step", step: 0 }); }}>Back</Button>
          <Button type="primary" onClick={next}>Review details</Button>
          {prefillButton}
        </Space>
      </Space>
    </Form>
  );
}
