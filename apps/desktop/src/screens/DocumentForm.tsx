import { useEffect } from "react";
import { Alert, Button, Card, Form, Space, Typography } from "antd";
import { backend, inTauri } from "../api/backend";
import { FieldRenderer } from "../components/FieldRenderer";
import { describeError } from "../lib/errors";
import { expandDefault, parseServerError } from "../lib/schema";
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

  const loadExample = async () => {
    const api = await backend();
    const v = await api.exampleValues(t.id);
    form.setFieldsValue(v); dispatch({ type: "setValues", values: v });
  };

  return (
    <Form form={form} layout="vertical" initialValues={state.values} onValuesChange={persist} scrollToFirstError requiredMark>
      {serverErrors?.length ? <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="The document engine rejected some values" description="The fields are marked below." /> : null}
      <Space orientation="vertical" size="large" style={{ width: "100%" }}>
        {t.groups.map((g) => (
          <Card className="glass" key={g.id} title={g.label} id={`group-${g.id}`} extra={g.print === false ? <Typography.Text type="secondary">Used for the email draft, not printed</Typography.Text> : null}>
            {g.fields.map((f) => <FieldRenderer key={f.id} f={f} />)}
          </Card>
        ))}
        <Space>
          <Button onClick={() => { persist(); dispatch({ type: "step", step: 0 }); }}>Back</Button>
          <Button type="primary" onClick={next}>Review details</Button>
          {(!inTauri || import.meta.env.DEV) && <Button onClick={loadExample}>Load example values</Button>}
        </Space>
      </Space>
    </Form>
  );
}
