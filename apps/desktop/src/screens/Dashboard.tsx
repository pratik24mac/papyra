import { Alert } from "antd";
import { RecentDocuments } from "../components/RecentDocuments";
import { FileAddOutlined, FolderOpenOutlined, SettingOutlined, AppstoreOutlined } from "@ant-design/icons";
import { useStore } from "../store";

function Tile({ icon, color, title, text, onClick, disabled }: { icon: React.ReactNode; color: string; title: string; text: string; onClick: () => void; disabled?: boolean }) {
  return (
    <div className="glass tile" role="button" tabIndex={0} aria-disabled={disabled} onClick={() => !disabled && onClick()} onKeyDown={(e) => e.key === "Enter" && !disabled && onClick()}>
      <div className="tile-icon" style={{ background: color }}>{icon}</div>
      <div><h3>{title}</h3><p>{text}</p></div>
    </div>
  );
}

export function Dashboard() {
  const { state, dispatch } = useStore();
  const ready = state.backend.state === "ready";
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  return (
    <div>
      <div className="hello">{greet}, {state.user ?? "there"}.</div>
      {state.backend.state === "failed" && <Alert type="error" showIcon style={{ marginBottom: 16 }} message="The document engine could not be started" description={state.backend.reason} />}
      <div className="tiles">
        <Tile icon={<FileAddOutlined />} color="linear-gradient(135deg,#0a84ff,#0040dd)" title="New document" text="Pick a template, fill in the details, review, generate Word and PDF." disabled={!ready} onClick={() => dispatch({ type: "reset" })} />
        <Tile icon={<AppstoreOutlined />} color="linear-gradient(135deg,#30d158,#0f8a3c)" title="Templates" text="Bundled, versioned templates. Users cannot change or replace them." disabled={!ready} onClick={() => dispatch({ type: "reset" })} />
        <Tile icon={<FolderOpenOutlined />} color="linear-gradient(135deg,#ff9f0a,#c75e00)" title="Recent documents" text="Generated documents on this computer. Open, reveal or delete them below." onClick={() => document.querySelector(".ant-table")?.scrollIntoView({ behavior: "smooth" })} />
        <Tile icon={<SettingOutlined />} color="linear-gradient(135deg,#8e8e93,#48484a)" title="Settings" text="Output folder, email preferences, engine and LibreOffice diagnostics." onClick={() => dispatch({ type: "navigate", view: "settings" })} />
      </div>
      <RecentDocuments />
    </div>
  );
}
