import { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Row, Skeleton, Tag, Typography } from "antd";
import { backend } from "../api/backend";
import type { TemplateSummary } from "../api/types";
import { countRequired, defaultValues } from "../lib/schema";
import { useStore } from "../store";

export function TemplateSelect() {
  const { dispatch } = useStore();
  const [templates, setTemplates] = useState<TemplateSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    backend().then((api) => api.listTemplates()).then(setTemplates).catch((e) => setError(String(e?.message ?? e)));
  }, []);
  if (error) return <Alert type="error" showIcon message="Could not load templates" description={error} />;
  if (!templates) return <Skeleton active />;
  return (
    <div>
      <Typography.Paragraph type="secondary">Choose the document you want to create. Each template defines its own set of inputs.</Typography.Paragraph>
      <Row gutter={[16, 16]}>
        {templates.map((t) => {
          const fields = t.groups.flatMap((g) => g.fields);
          const required = fields.filter((f) => f.required);
          return (
            <Col xs={24} md={12} key={t.id}>
              <Card className="glass" title={t.name} extra={<Tag>v{t.version}</Tag>}
                actions={[<Button key="use" type="primary" onClick={() => dispatch({ type: "selectTemplate", template: t, values: defaultValues(t) })}>Use this template</Button>]}>
                <Typography.Paragraph>{t.description}</Typography.Paragraph>
                <Typography.Text type="secondary">{fields.length} inputs, {countRequired(t)} required:</Typography.Text>
                <div style={{ marginTop: 8 }}>{required.map((f) => <Tag key={f.id} color="blue">{f.label}</Tag>)}</div>
              </Card>
            </Col>
          );
        })}
      </Row>
    </div>
  );
}
