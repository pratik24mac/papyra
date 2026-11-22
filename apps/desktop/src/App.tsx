import { Avatar, ConfigProvider, Dropdown, Segmented, Steps, Typography, theme } from "antd";
import { LogoutOutlined } from "@ant-design/icons";
import { backend } from "./api/backend";
import { BackendStatusBadge } from "./components/BackendStatusBadge";
import { Dashboard } from "./screens/Dashboard";
import { DocumentForm } from "./screens/DocumentForm";
import { Email } from "./screens/Email";
import { Generate } from "./screens/Generate";
import { Login } from "./screens/Login";
import { SetupRequired } from "./screens/SetupRequired";
import { ErrorBoundary } from "./components/ErrorBoundary";
import type { SelfCheck } from "./api/types";
import { useCallback, useEffect, useState } from "react";
import { Preview } from "./screens/Preview";
import { Review } from "./screens/Review";
import { Settings } from "./screens/Settings";
import { TemplateSelect } from "./screens/TemplateSelect";
import { StoreProvider, useStore, type View } from "./store";

function Wizard() {
  const { state } = useStore();
  const steps = [{ title: "Template", content: state.template?.name }, { title: "Details" }, { title: "Review" }, { title: "Generate" }, { title: "Preview" }, { title: "Email" }];
  const screen = [<TemplateSelect />, <DocumentForm />, <Review />, <Generate />, <Preview />, <Email />][state.step];
  return (
    <div>
      <Typography.Title level={4} style={{ marginTop: 0, marginBottom: 10, fontWeight: 700 }}>New document</Typography.Title>
      <Steps current={state.step} items={steps} size="small" style={{ marginBottom: 16 }} />
      {state.step > 0 && !state.template ? <TemplateSelect /> : screen}
    </div>
  );
}

function Shell() {
  const { state, dispatch } = useStore();
  const [readiness, setReadiness] = useState<SelfCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const recheck = useCallback(async () => {
    setChecking(true);
    try { setReadiness(await (await backend()).selfCheck(false)); } catch { setReadiness(null); } finally { setChecking(false); }
  }, []);
  const engineReady = state.backend.state === "ready";
  useEffect(() => { if (state.user && engineReady) recheck(); }, [state.user, engineReady, recheck]);
  if (!state.user) return <Login />;
  const signOut = async () => { (await backend()).logout(); dispatch({ type: "signOut" }); };
  const engineFailure = state.backend.state === "failed" ? state.backend.reason : null;
  const blocked = engineFailure !== null || (readiness !== null && !readiness.ok);
  return (
    <div>
      <header className="glass topbar">
        <div className="brand" onClick={() => dispatch({ type: "navigate", view: "dashboard" })}><img src="/papyra-icon.png" alt="" width={26} height={26} style={{ borderRadius: 7 }} />Papyra</div>
        <Segmented value={state.view} onChange={(v) => dispatch({ type: "navigate", view: v as View })}
          options={[{ label: "Dashboard", value: "dashboard" }, { label: "New document", value: "wizard" }, { label: "Settings", value: "settings" }]} />
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <BackendStatusBadge status={state.backend} />
          <Dropdown menu={{ items: [{ key: "out", icon: <LogoutOutlined />, label: "Sign out", onClick: signOut }] }} trigger={["click"]}>
            <Avatar style={{ background: "linear-gradient(135deg,#0a84ff,#0040dd)", cursor: "pointer" }}>{state.user.charAt(0).toUpperCase()}</Avatar>
          </Dropdown>
        </div>
      </header>
      <main className="content">
        <ErrorBoundary key={state.view} onReset={() => dispatch({ type: "navigate", view: "dashboard" })}>
        {blocked && state.view !== "settings" ? <SetupRequired check={readiness} engineFailure={engineFailure} onRecheck={recheck} busy={checking} /> : null}
        {!(blocked && state.view !== "settings") && state.view === "dashboard" && <Dashboard />}
        {!(blocked && state.view !== "settings") && state.view === "wizard" && <Wizard />}
        {state.view === "settings" && <Settings />}
        </ErrorBoundary>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ConfigProvider theme={{
      algorithm: theme.darkAlgorithm,
      token: { colorPrimary: "#0a84ff", borderRadius: 10, fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Helvetica, Arial, sans-serif',
               colorBgBase: "#0a0a0c", colorBgContainer: "rgba(28,28,30,0.72)", colorBgElevated: "#2c2c2e", colorBorder: "rgba(255,255,255,0.10)", colorBorderSecondary: "rgba(255,255,255,0.08)",
               colorText: "#f5f5f7", colorTextSecondary: "#a1a1a6", controlHeight: 32, fontSize: 13, marginLG: 16, paddingLG: 16 },
      components: { Card: { headerBg: "transparent", bodyPadding: 14, headerPadding: 14, headerHeight: 42, headerFontSize: 14 },
                    Form: { itemMarginBottom: 10, verticalLabelPadding: "0 0 4px", labelFontSize: 12 },
                    Descriptions: { itemPaddingBottom: 6 },
                    Segmented: { itemSelectedBg: "rgba(255,255,255,0.14)", trackBg: "rgba(255,255,255,0.06)" } },
    }}>
      <StoreProvider>
        <Shell />
      </StoreProvider>
    </ConfigProvider>
  );
}
