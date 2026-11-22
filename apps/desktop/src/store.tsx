// Wizard + backend state shared across screens. Values survive navigation between steps
// (spec §5.7) because they live here, not in the form.
import { createContext, useContext, useEffect, useReducer, type ReactNode } from "react";
import { backend } from "./api/backend";
import type { BackendStatus, BatchResult, GenerateResult, ProgressEvent, TemplateSummary, Values } from "./api/types";
import { mergeTemplates } from "./lib/merge";

export type View = "dashboard" | "wizard" | "settings";
export type Step = 0 | 1 | 2 | 3 | 4 | 5; // template, details, review, generate, preview, email

export interface Job {
  jobId: string;                   // single document job id, or the batch id
  stages: ProgressEvent[];
  result: GenerateResult | null;
  batch: BatchResult | null;       // set when several templates were generated together
  error: unknown | null;
  inFlight: boolean;
}

/** Job ids of the generated documents that have a usable PDF (single or batch). */
export function readyJobIds(job: Job | null): string[] {
  if (!job) return [];
  if (job.batch) return job.batch.documents.filter((d) => d.status === "pdf_done").map((d) => d.job_id);
  return job.result || !job.inFlight ? [job.jobId] : [];
}

export interface State {
  user: string | null;
  view: View;
  step: Step;
  template: TemplateSummary | null;        // the (possibly merged) template driving the form
  templates: TemplateSummary[];            // the selected templates (1..N)
  values: Values;
  job: Job | null;
  backend: BackendStatus;
  outputDir: string | null;      // per-document "Save to" folder; null = Settings default
}

type Action =
  | { type: "navigate"; view: View }
  | { type: "step"; step: Step }
  | { type: "selectTemplate"; template: TemplateSummary; values: Values }
  | { type: "selectTemplates"; templates: TemplateSummary[]; values: Values }
  | { type: "batchDone"; result: BatchResult }
  | { type: "openBatch"; batch: BatchResult }
  | { type: "setValues"; values: Values }
  | { type: "setOutputDir"; dir: string | null }
  | { type: "jobStart"; jobId: string }
  | { type: "openJob"; jobId: string }
  | { type: "jobProgress"; event: ProgressEvent }
  | { type: "jobDone"; result: GenerateResult }
  | { type: "jobFailed"; error: unknown }
  | { type: "backend"; status: BackendStatus }
  | { type: "signIn"; user: string }
  | { type: "signOut" }
  | { type: "reset" };

const initial: State = { outputDir: null, user: null, view: "dashboard", step: 0, template: null, templates: [], values: {}, job: null, backend: { state: "starting", attempt: 0 } };

function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "navigate": return { ...s, view: a.view };
    case "step": return { ...s, step: a.step };
    case "selectTemplate": return { ...s, template: a.template, templates: [a.template], values: a.values, job: null, step: 1 };
    case "selectTemplates": return { ...s, template: mergeTemplates(a.templates).summary, templates: a.templates, values: a.values, job: null, step: 1 };
    case "batchDone": return s.job ? { ...s, job: { ...s.job, batch: a.result, inFlight: false } } : s;
    case "openBatch": return { ...s, view: "wizard", step: 4, job: { jobId: a.batch.batch_id, stages: [], result: null, batch: a.batch, error: null, inFlight: false } };
    case "setValues": return { ...s, values: a.values };
    case "setOutputDir": return { ...s, outputDir: a.dir };
    case "jobStart": return { ...s, step: 3, job: { jobId: a.jobId, stages: [], result: null, batch: null, error: null, inFlight: true } };
    case "openJob": return { ...s, view: "wizard", step: 4, template: s.template, values: s.values, job: { jobId: a.jobId, stages: [], result: null, batch: null, error: null, inFlight: false } };
    case "jobProgress":
      if (!s.job || (a.event.job_id !== s.job.jobId && a.event.batch_id !== s.job.jobId)) return s;
      return { ...s, job: { ...s.job, stages: [...s.job.stages, a.event] } };
    case "jobDone": return s.job ? { ...s, job: { ...s.job, result: a.result, inFlight: false } } : s;
    case "jobFailed": return s.job ? { ...s, job: { ...s.job, error: a.error, inFlight: false } } : s;
    case "backend": return { ...s, backend: a.status };
    case "signIn": return { ...s, user: a.user, view: "dashboard" };
    case "signOut": return { ...initial, backend: s.backend };
    case "reset": return { ...initial, user: s.user, view: "wizard", backend: s.backend, outputDir: s.outputDir };
  }
}

const Ctx = createContext<{ state: State; dispatch: (a: Action) => void } | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);
  useEffect(() => {
    let un1: (() => void) | undefined, un2: (() => void) | undefined;
    backend().then(async (api) => {
      const user = await api.authStatus();
      if (user) dispatch({ type: "signIn", user });
      dispatch({ type: "backend", status: await api.status() });
      un1 = await api.onStatus((status) => dispatch({ type: "backend", status }));
      un2 = await api.onProgress((event) => dispatch({ type: "jobProgress", event }));
    });
    return () => { un1?.(); un2?.(); };
  }, []);
  return <Ctx.Provider value={{ state, dispatch }}>{children}</Ctx.Provider>;
}

export function useStore() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("StoreProvider missing");
  return ctx;
}

/** Start generation exactly once per click; duplicate requests are impossible while one is in flight. */
export async function startGeneration(state: State, dispatch: (a: Action) => void) {
  if (!state.template || state.job?.inFlight) return;
  const jobId = crypto.randomUUID();
  dispatch({ type: "jobStart", jobId });
  try {
    const api = await backend();
    if (state.templates.length > 1) {
      const merged = mergeTemplates(state.templates); const { values, byTemplate } = merged.split(state.values);
      const result = await api.generateBatch(state.templates.map((t) => t.id), values, byTemplate, jobId, state.outputDir);
      dispatch({ type: "batchDone", result });
    } else {
      const result = await api.generate(state.template.id, state.values, jobId, state.outputDir);
      dispatch({ type: "jobDone", result });
    }
  } catch (error) {
    dispatch({ type: "jobFailed", error });
  }
}
