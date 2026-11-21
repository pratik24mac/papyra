// A render crash anywhere below shows this panel instead of a blank window.
import React from "react";
import { Alert, Button, Space, Typography, message } from "antd";

type State = { error: Error | null; info: string };

export class ErrorBoundary extends React.Component<{ children: React.ReactNode; onReset?: () => void }, State> {
  state: State = { error: null, info: "" };
  static getDerivedStateFromError(error: Error): Partial<State> { return { error }; }
  componentDidCatch(error: Error, info: React.ErrorInfo) { this.setState({ info: info.componentStack ?? "" }); console.error("UI crash:", error, info); }
  render() {
    if (!this.state.error) return this.props.children;
    const details = `${this.state.error.name}: ${this.state.error.message}\n${this.state.error.stack ?? ""}\n--- component stack ---${this.state.info}`;
    return (
      <div style={{ maxWidth: 820, margin: "40px auto", padding: 16 }}>
        <Alert type="error" showIcon message="Something went wrong on this screen" description={
          <Space orientation="vertical" style={{ width: "100%" }}>
            <Typography.Text code style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{this.state.error.message}</Typography.Text>
            <Space wrap>
              <Button type="primary" onClick={() => { this.setState({ error: null, info: "" }); this.props.onReset?.(); }}>Back to dashboard</Button>
              <Button onClick={async () => { try { await navigator.clipboard.writeText(details); message.success("Details copied"); } catch { message.error("Could not copy"); } }}>Copy details</Button>
            </Space>
            <Typography.Text type="secondary">Your typed values are kept. Please copy the details and report them.</Typography.Text>
          </Space>} />
      </div>
    );
  }
}
