import { Badge, Tooltip } from "antd";
import type { BackendStatus } from "../api/types";

export function BackendStatusBadge({ status }: { status: BackendStatus }) {
  const map = {
    starting: { badge: "processing" as const, text: status.state === "starting" && status.attempt > 0 ? "Engine restarting…" : "Engine starting…", tip: "The document engine is starting. First launch after installation can take up to 30 seconds." },
    ready: { badge: "success" as const, text: "Engine ready", tip: status.state === "ready" ? `Backend ${status.version} (pid ${status.pid})` : "" },
    restarting: { badge: "warning" as const, text: "Engine restarting…", tip: status.state === "restarting" ? `Attempt ${status.attempt}: ${status.reason}` : "" },
    failed: { badge: "error" as const, text: "Engine unavailable", tip: status.state === "failed" ? status.reason : "" },
  }[status.state];
  return (
    <Tooltip title={map.tip}>
      <Badge status={map.badge} text={map.text} />
    </Tooltip>
  );
}
