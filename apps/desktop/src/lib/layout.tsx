// Compact form layout: short controls sit two per row, long ones take the full width.
import { Col, Row } from "antd";
import type { FieldSchema } from "../api/types";
import { FieldRenderer } from "../components/FieldRenderer";
import type { NamePath } from "./schema";

export const SHORT_TYPES = new Set(["text", "email", "url", "date", "number", "select", "checkbox"]);

export function FieldGrid({ fields, prefix }: { fields: FieldSchema[]; prefix?: NamePath }) {
  return (
    <Row gutter={[12, 0]}>
      {fields.map((f) => (
        <Col key={f.id} xs={24} md={SHORT_TYPES.has(f.type) ? 12 : 24} lg={SHORT_TYPES.has(f.type) ? 8 : 24}>
          <FieldRenderer f={f} prefix={prefix} />
        </Col>
      ))}
    </Row>
  );
}
