import { useState } from "react";
import { Alert, Button, Form, Input, Typography } from "antd";
import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { backend } from "../api/backend";
import { describeError } from "../lib/errors";
import { useStore } from "../store";

export function Login() {
  const { dispatch } = useStore();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (v: { username: string; password: string }) => {
    setBusy(true); setError(null);
    try {
      const api = await backend();
      const user = await api.login(v.username, v.password);
      dispatch({ type: "signIn", user });
    } catch (e) {
      setError(describeError(e).detail);
    } finally { setBusy(false); }
  };
  return (
    <div className="login-wrap">
      <div className="glass login-card">
        <img src="/papyra-icon.png" alt="Papyra" width={76} height={76} style={{ borderRadius: 18, display: "block", margin: "0 auto 16px" }} />
        <Typography.Title level={3} style={{ margin: "0 0 4px", fontWeight: 700 }}>Papyra</Typography.Title>
        <Typography.Text type="secondary">Sign in to generate documents</Typography.Text>
        <Form layout="vertical" onFinish={submit} style={{ marginTop: 24, textAlign: "left" }} requiredMark={false}>
          <Form.Item name="username" rules={[{ required: true, message: "Enter your username" }]}>
            <Input size="large" prefix={<UserOutlined />} placeholder="Username" autoComplete="username" autoFocus />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "Enter your password" }]}>
            <Input.Password size="large" prefix={<LockOutlined />} placeholder="Password" autoComplete="current-password" />
          </Form.Item>
          {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
          <Button type="primary" size="large" htmlType="submit" block loading={busy}>Sign in</Button>
        </Form>
        <Typography.Text type="secondary" style={{ display: "block", marginTop: 18, fontSize: 12 }}>Everything runs on this computer. No account data is sent anywhere.</Typography.Text>
      </div>
    </div>
  );
}
