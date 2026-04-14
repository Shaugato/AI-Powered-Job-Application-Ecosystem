import { startTransition, useEffect, useRef, useState } from "react";
import type { Dispatch, FormEvent, ReactNode, SetStateAction } from "react";
import {
  artifactUrl,
  cancelIntegrationBrowserCapture,
  clearAuthToken,
  connectIntegrationConnection,
  createApplicationPlan,
  createGenerationRequest,
  createLearningOutcome,
  deleteBaseProfile,
  deleteIntegrationConnection,
  deleteJob,
  deletePrompt,
  deleteSearchProfile,
  deleteTemplate,
  fetchApplicationPlans,
  fetchApplicationRuns,
  fetchArtifactBundle,
  fetchAuthStatus,
  fetchBaseProfiles,
  fetchCandidateMemory,
  fetchCorpusLibrary,
  fetchCorpusWorkflow,
  fetchDashboardOverview,
  fetchDrafts,
  fetchGenerationWorkflow,
  fetchIngestionConfigs,
  fetchIngestionRuns,
  fetchIntegrationBrowserCapture,
  fetchIntegrationConnections,
  fetchIntegrationProviders,
  fetchJobs,
  fetchLearningOutcomes,
  fetchNotificationEvents,
  fetchNotificationPreferences,
  fetchPlatformHealth,
  fetchPromptPerformance,
  fetchPrompts,
  fetchResumeScores,
  fetchSearchProfiles,
  fetchTemplates,
  finalizeIntegrationBrowserCapture,
  googleAuthStartUrl,
  logoutCurrentSession,
  readAuthToken,
  saveBaseProfile,
  saveIngestionConfig,
  saveIntegrationConnection,
  syncCandidateMemory,
  saveJob,
  saveNotificationPreference,
  savePrompt,
  saveSearchProfile,
  saveTemplate,
  sendTestNotification,
  startApplicationRun,
  startJobPipeline,
  storeAuthToken,
  triggerIngestion,
  uploadCorpusFiles,
  uploadTemplate,
} from "./api";
import type {
  ApplicationOutcome,
  IntegrationBrowserCapture,
  ApplicationPlan,
  ApplicationRun,
  AuthStatus,
  BaseProfile,
  CandidateMemory,
  CorpusDocumentSummary,
  CorpusLibraryFile,
  CorpusLibrarySection,
  DashboardOverview,
  GenerationArtifactBundle,
  GenerationResult,
  IngestionRun,
  IngestionSourceConfig,
  IntegrationConnection,
  IntegrationProvider,
  JobPosting,
  NotificationEvent,
  NotificationPreference,
  PromptPerformance,
  PromptVersion,
  ResumeVariantScore,
  SearchProfile,
  TemplateVariant,
  WorkflowSubmission,
} from "./types";

type ViewKey = "landing" | "overview" | "knowledge" | "library" | "integrations" | "studio" | "monitoring" | "applications" | "insights";
type BannerTone = "neutral" | "success" | "error";
type BannerState = { tone: BannerTone; message: string } | null;
type BusyState = { title: string; detail: string } | null;

type BaseForm = { fullName: string; email: string; phone: string; location: string; website: string; summary: string; skills: string; certifications: string; experience: string; projects: string; education: string };
type UploadForm = { documentType: "resume" | "cover_letter" | "prompt"; roleHints: string; files: File[] };
type PromptForm = { name: string; roleTags: string; promptText: string; temperature: string; successRate: string };
type TemplateForm = { name: string; documentKind: string; templatePath: string; file: File | null };
type SearchForm = { name: string; roles: string; keywords: string; locations: string; sources: string; dailyCap: string; remotePolicy: string };
type MonitorForm = { name: string; source: string; searchProfileId: string; connectionId: string; queryText: string; cadenceMinutes: string; maxResults: string; searchUrl: string; enabled: boolean };
type JobForm = { source: string; connectionId: string; company: string; title: string; url: string; externalId: string; location: string; workMode: string; description: string; labels: string; riskFlags: string };
type DraftForm = { jobId: string; resumeTemplate: string; coverTemplate: string; generationResultId: string; planJobId: string };
type OutcomeForm = { applicationPlanId: string; applicationRunId: string; responseType: string; interview: boolean; responseTimeDays: string; notes: string };
type NotificationForm = { emailEnabled: boolean; emailTarget: string; slackEnabled: boolean; slackTarget: string; testChannel: string; testSubject: string; testBody: string };
type ConnectionForm = { name: string; providerKey: string; loginHint: string; settings: Record<string, string> };

const viewPaths: Record<ViewKey, string> = {
  landing: "/",
  overview: "/app/command-center",
  knowledge: "/app/profile-memory",
  library: "/app/tailoring-lab",
  integrations: "/app/integrations",
  studio: "/app/playbooks",
  monitoring: "/app/opportunity-radar",
  applications: "/app/apply-queue",
  insights: "/app/learning-loop",
};

const nav = [
  { key: "overview", label: "Command Center", desc: "Live mission status", glyph: "CC" },
  { key: "knowledge", label: "Profile Memory", desc: "Uploads, assets, learned signals", glyph: "PM" },
  { key: "monitoring", label: "Opportunity Radar", desc: "Searches, monitors, live matches", glyph: "OR" },
  { key: "library", label: "Tailoring Lab", desc: "Resume strategy and AI reasoning", glyph: "TL" },
  { key: "applications", label: "Apply Queue", desc: "Reviews, submissions, queue flow", glyph: "AQ" },
  { key: "insights", label: "Learning Loop", desc: "Outcomes, performance, feedback", glyph: "LL" },
  { key: "studio", label: "Playbooks", desc: "Prompts, templates, rules", glyph: "PB" },
  { key: "integrations", label: "Integrations", desc: "Sign-in, boards, notifications", glyph: "IG" },
] as const;

const emptyOverview: DashboardOverview = { totals: { jobs: 0, drafts: 0, applications: 0, pending_approvals: 0, ingestion_runs: 0, outcomes: 0 }, jobs: [], drafts: [], applications: [], pending_approvals: [], recent_runs: [], recent_ingestion_runs: [], recent_outcomes: [], source_health: [] };
const emptyAuth: AuthStatus = { authenticated: false, google_ready: false, auth_mode: "google", session_expires_at: null, user: null };
const emptyMemory: CandidateMemory = { source_profile_id: null, summary: null, skills: [], certifications: [], experience: [], projects: [], education: [], approved_documents: 0, pending_documents: 0, source_documents: [] };
const emptyBase: BaseForm = { fullName: "", email: "", phone: "", location: "", website: "", summary: "", skills: "", certifications: "", experience: "", projects: "", education: "" };
const emptyUpload: UploadForm = { documentType: "resume", roleHints: "", files: [] };
const emptyPrompt: PromptForm = { name: "", roleTags: "", promptText: "", temperature: "0.2", successRate: "0" };
const emptyTemplate: TemplateForm = { name: "", documentKind: "resume", templatePath: "", file: null };
const emptySearch: SearchForm = { name: "", roles: "", keywords: "", locations: "", sources: "seek, linkedin, indeed, company_portal", dailyCap: "12", remotePolicy: "hybrid" };
const emptyMonitor: MonitorForm = { name: "", source: "seek", searchProfileId: "", connectionId: "", queryText: "", cadenceMinutes: "45", maxResults: "25", searchUrl: "", enabled: true };
const emptyJob: JobForm = { source: "company_portal", connectionId: "", company: "", title: "", url: "", externalId: "", location: "Melbourne, VIC", workMode: "hybrid", description: "", labels: "", riskFlags: "" };
const emptyDraft: DraftForm = { jobId: "", resumeTemplate: "", coverTemplate: "", generationResultId: "", planJobId: "" };
const emptyOutcome: OutcomeForm = { applicationPlanId: "", applicationRunId: "", responseType: "no_response", interview: false, responseTimeDays: "", notes: "" };
const emptyNotify: NotificationForm = { emailEnabled: true, emailTarget: "", slackEnabled: false, slackTarget: "", testChannel: "dashboard", testSubject: "JobOps test notification", testBody: "This is a test notification from your AI job application platform." };

function resolveView(pathname: string): ViewKey {
  if (pathname === "/app" || pathname === "/app/" || pathname.startsWith("/app/command-center")) return "overview";
  if (pathname.startsWith("/app/profile-memory") || pathname.startsWith("/app/upload")) return "knowledge";
  if (pathname.startsWith("/app/tailoring-lab") || pathname.startsWith("/app/library")) return "library";
  if (pathname.startsWith("/app/integrations") || pathname.startsWith("/app/connections")) return "integrations";
  if (pathname.startsWith("/app/playbooks") || pathname.startsWith("/app/studio")) return "studio";
  if (pathname.startsWith("/app/opportunity-radar") || pathname.startsWith("/app/monitoring")) return "monitoring";
  if (pathname.startsWith("/app/apply-queue") || pathname.startsWith("/app/applications")) return "applications";
  if (pathname.startsWith("/app/learning-loop") || pathname.startsWith("/app/insights")) return "insights";
  return "landing";
}
function list(value: string): string[] { return value.split(",").map((v) => v.trim()).filter(Boolean); }
function join(value?: string[] | null): string { return (value ?? []).join(", "); }
function patch<T>(setter: Dispatch<SetStateAction<T>>, next: Partial<T>): void { setter((prev) => ({ ...prev, ...next })); }
function num(value: string): number | null { if (!value.trim()) return null; const parsed = Number(value); return Number.isFinite(parsed) ? parsed : null; }
function fmtDate(value?: string | null): string { if (!value) return "Not yet"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("en-AU", { dateStyle: "medium", timeStyle: "short" }).format(date); }
function tone(status: string): string { const s = status.toLowerCase(); if (["connected", "configured", "completed", "approved", "ready", "authenticated", "delivered"].some((t) => s.includes(t))) return "pill pill-ok"; if (["pending", "review", "running", "action", "queued"].some((t) => s.includes(t))) return "pill pill-warn"; return "pill pill-muted"; }
function kind(kindValue: string): string { return ({ resume: "Resume", cover_letter: "Cover letter", prompt: "Prompt", document: "Document" } as Record<string, string>)[kindValue] ?? kindValue; }
function msg(error: unknown): string { return error instanceof Error ? error.message : String(error); }
function defaultSettings(provider: IntegrationProvider | null): Record<string, string> { const settings: Record<string, string> = {}; provider?.fields.forEach((field) => { if ((field.key === "redirect_uri" || field.key === "port") && field.placeholder) settings[field.key] = field.placeholder; }); return settings; }
function makeConnectionForm(provider: IntegrationProvider | null, connection?: IntegrationConnection | null): ConnectionForm { const settings = defaultSettings(provider); provider?.fields.forEach((field) => { const value = connection?.settings_json?.[field.key]; if (value !== undefined && value !== null) settings[field.key] = String(value); }); return { name: connection?.name ?? provider?.name ?? "", providerKey: provider?.key ?? "", loginHint: connection?.login_hint ?? "", settings }; }

function lines(value: string): string[] { return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean); }
function encodeEntries(value: string): Record<string, unknown>[] { return value.split(/\r?\n\s*\r?\n/).map((block) => lines(block)).filter((block) => block.length > 0).map((block) => { const [headline, ...bulletLines] = block; const [title, subtitle] = headline.split("|").map((part) => part.trim()); return { title: title || headline, subtitle: subtitle || null, bullets: bulletLines }; }); }
function decodeEntries(entries: Record<string, unknown>[] | null | undefined): string { return (entries ?? []).map((entry) => { const title = String(entry.title ?? "").trim(); const subtitle = String(entry.subtitle ?? "").trim(); const header = subtitle ? `${title} | ${subtitle}` : title; const bullets = Array.isArray(entry.bullets) ? entry.bullets.map((item) => String(item)) : []; return [header, ...bullets].filter(Boolean).join("\n"); }).filter(Boolean).join("\n\n"); }
function encodeEducation(value: string): Record<string, unknown>[] { return lines(value).map((line) => ({ line })); }
function decodeEducation(entries: Record<string, unknown>[] | null | undefined): string { return (entries ?? []).map((entry) => String(entry.line ?? entry.degree ?? entry.title ?? "").trim()).filter(Boolean).join("\n"); }
const REQUIRED_GOOGLE_REDIRECT_URI = "http://localhost:8013/api/v1/auth/google/callback";
type DisplayLibraryFile = {
  key: string;
  title: string;
  subtitle?: string | null;
  lines: string[];
  preview?: string | null;
  chips?: string[];
};
function cleanCopy(value?: string | null): string {
  return String(value ?? "")
    .replace(/\uFFFD/g, " ")
    .replace(/\/(?=(linkedin|github|email|phone|mobile))/gi, " / ")
    .replace(/\s+/g, " ")
    .trim();
}
function cleanLine(value?: string | null): string {
  return cleanCopy(value).replace(/^[\-\u2022]+\s*/, "").trim();
}
function isInternalNoise(value?: string | null): boolean {
  const cleaned = cleanLine(value);
  const lowered = cleaned.toLowerCase();
  if (!cleaned) return true;
  if (lowered.startsWith("private-data/") || lowered.startsWith("source: private-data/")) return true;
  if (cleaned.includes("\\private-data\\") || cleaned.endsWith(".txt")) return true;
  if (/invalid schema|badrequesterror|invalid_json_schema|text\/json_schema|required to be supplied|private-data\/library|fallback to local/i.test(cleaned)) return true;
  return ["experience", "projects", "education", "certifications", "technical skills", "skills", "summary", "identity", "personal information", "source text"].includes(lowered);
}
function dedupeText(values: string[]): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  values.map((value) => cleanLine(value)).forEach((value) => {
    const key = value.toLowerCase();
    if (!value || isInternalNoise(value) || seen.has(key)) return;
    seen.add(key);
    result.push(value);
  });
  return result;
}
function titleCaseWords(value: string): string {
  return value.split(/\s+/).map((token) => token ? `${token[0].toUpperCase()}${token.slice(1)}` : token).join(" ");
}
function prettyFileName(name: string): string {
  const base = cleanCopy(name.replace(/\.[^.]+$/, "").replace(/^\d+_/, "").replace(/[-_]+/g, " "));
  return titleCaseWords(base || "Entry");
}
function collectLibraryLines(file: CorpusLibraryFile): string[] {
  const explicit = dedupeText(file.lines ?? []);
  if (explicit.length) return explicit;
  const preview = cleanLine(file.preview_excerpt);
  return preview && !isInternalNoise(preview) ? [preview] : [];
}
function normalizeReasoning(value?: string | null, fallback = "The system will explain how it selected evidence, balanced sections, and kept the resume within one page."): string {
  const raw = String(value ?? "").trim();
  if (!raw) return fallback;
  const cleaned = cleanCopy(raw);
  const candidate = cleaned.split(/(?:BadRequestError|invalid schema|Error code:|fallback to local heuristic)/i)[0].trim() || cleaned;
  if (!candidate || /invalid schema|badrequesterror|private-data\/library|text\/json_schema|required to be supplied/i.test(candidate)) return fallback;
  return candidate;
}
function displayLibraryFiles(section: CorpusLibrarySection): DisplayLibraryFile[] {
  const sectionKey = section.key.toLowerCase();
  if (["technical_skills", "skills", "certifications"].includes(sectionKey)) {
    const chips = dedupeText(section.files.flatMap((file) => {
      const groupedLines = collectLibraryLines(file);
      return groupedLines.length ? groupedLines : [cleanLine(file.title ?? file.name)];
    }));
    return chips.length ? [{ key: sectionKey, title: cleanCopy(section.title), lines: [], chips }] : [];
  }
  if (sectionKey === "education") {
    const groupedLines = dedupeText(section.files.flatMap((file) => collectLibraryLines(file)));
    return groupedLines.length ? [{ key: sectionKey, title: cleanCopy(section.title), lines: groupedLines }] : [];
  }
  return section.files.map((file, index) => {
    const title = cleanLine(file.title ?? prettyFileName(file.name));
    const subtitle = cleanLine(file.subtitle);
    const groupedLines = dedupeText(
      collectLibraryLines(file).filter((line) => line.toLowerCase() !== title.toLowerCase() && (!subtitle || line.toLowerCase() !== subtitle.toLowerCase()))
    );
    return {
      key: `${section.key}-${index}-${file.name}`,
      title: title || prettyFileName(file.name),
      subtitle: subtitle && !isInternalNoise(subtitle) ? subtitle : null,
      lines: groupedLines,
      preview: cleanLine(file.preview_excerpt) || null,
    };
  }).filter((file) => file.title || file.lines.length || file.preview);
}
function copyText(value: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) return navigator.clipboard.writeText(value);
  return Promise.resolve();
}

function uploadProgressMessages(kindValue: UploadForm["documentType"]): string[] {
  if (kindValue === "cover_letter") {
    return [
      "Analyzing the uploaded cover letter.",
      "Restoring the original tone and sentence flow.",
      "Extracting company-facing language blocks.",
      "Saving the letter into its reusable library folder.",
      "Refreshing profile memory for future tailoring.",
    ];
  }
  if (kindValue === "prompt") {
    return [
      "Analyzing the uploaded prompt file.",
      "Extracting the trusted decision logic.",
      "Separating reusable prompt instructions.",
      "Saving the prompt into the internal library.",
      "Refreshing the platform memory map.",
    ];
  }
  return [
    "Analyzing the uploaded resume.",
    "Extracting personal information and contact details.",
    "Extracting technical skills and certifications.",
    "Extracting experience and project sections.",
    "Extracting education and role signals.",
    "Building the resume folder inside Profile Memory.",
    "Refreshing the platform memory for future tailoring.",
  ];
}


function ResumePreview({ draft, bundle }: { draft: GenerationResult | null; bundle: GenerationArtifactBundle | null }): JSX.Element {
  if (!draft) return <div className="resume-preview-empty">Generate a draft to inspect the one-page output the system is using.</div>;
  const previewArtifact = bundle?.artifacts.find((artifact) => artifact.kind === "resume_preview" && artifact.available && artifact.url);
  const pdfArtifact = bundle?.artifacts.find((artifact) => artifact.kind === "resume_pdf" && artifact.available && artifact.url);
  const texArtifact = bundle?.artifacts.find((artifact) => artifact.kind === "resume_tex" && artifact.available && artifact.url);
  const resume = (draft.resume_json ?? {}) as Record<string, unknown>;
  const pagePlan = (resume.page_plan ?? {}) as Record<string, unknown>;
  return <div className="resume-preview-card"><div className="resume-preview-head"><div><strong>Draft {draft.id.slice(0, 8)}</strong><p>{normalizeReasoning(draft.grounding_notes, "Grounded from your uploaded resumes, cover letters, prompts, and profile memory.")}</p></div><span className={tone(draft.compile_status)}>{draft.compile_status}</span></div><div className="artifact-row top-gap">{previewArtifact ? <a className="artifact-link" href={artifactUrl(String(previewArtifact.url))} target="_blank" rel="noreferrer">Open preview</a> : null}{pdfArtifact ? <a className="artifact-link" href={artifactUrl(String(pdfArtifact.url))} target="_blank" rel="noreferrer">Open PDF</a> : null}{texArtifact ? <a className="artifact-link" href={artifactUrl(String(texArtifact.url))} target="_blank" rel="noreferrer">Open TeX</a> : null}</div><div className="resume-section-grid top-gap"><div className="status-row-card"><div><strong>Page plan</strong><p>{String(pagePlan.strategy ?? "The composer is balancing sections to keep the output tight.")}</p></div><span className="pill pill-ok">{String(pagePlan.line_budget ?? "1 page")}</span></div><div className="status-row-card"><div><strong>Section balance</strong><p>Summary {String(pagePlan.summary_lines ?? "-")} | Experience {String(pagePlan.experience_lines ?? "-")} | Projects {String(pagePlan.project_lines ?? "-")}</p></div><span className="pill pill-muted">AI composed</span></div></div>{previewArtifact ? <iframe className="resume-preview-frame top-gap" src={artifactUrl(String(previewArtifact.url))} title="Generated resume preview" /> : null}</div>;
}
function Panel({ eyebrow, title, children }: { eyebrow?: string; title: string; children: ReactNode }): JSX.Element {
  return <section className="panel"><div className="panel-header">{eyebrow ? <p className="panel-eyebrow">{eyebrow}</p> : null}<h3>{title}</h3></div><div className="panel-body">{children}</div></section>;
}
function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }): JSX.Element {
  return <label className="field-block"><span>{label}</span>{children}{hint ? <small className="inline-note">{hint}</small> : null}</label>;
}

export default function App(): JSX.Element {
  const [view, setView] = useState<ViewKey>(() => resolveView(window.location.pathname));
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<BusyState>(null);
  const [apiOnline, setApiOnline] = useState(true);
  const [banner, setBanner] = useState<BannerState>(null);
  const [connectNotice, setConnectNotice] = useState<{ title: string; lines: string[]; url?: string | null } | null>(null);
  const [browserCapture, setBrowserCapture] = useState<IntegrationBrowserCapture | null>(null);

  const [auth, setAuth] = useState<AuthStatus>(emptyAuth);
  const [overview, setOverview] = useState<DashboardOverview>(emptyOverview);
  const [memory, setMemory] = useState<CandidateMemory>(emptyMemory);
  const [baseProfiles, setBaseProfiles] = useState<BaseProfile[]>([]);
  const [docs, setDocs] = useState<CorpusDocumentSummary[]>([]);
  const [prompts, setPrompts] = useState<PromptVersion[]>([]);
  const [templates, setTemplates] = useState<TemplateVariant[]>([]);
  const [jobs, setJobs] = useState<JobPosting[]>([]);
  const [drafts, setDrafts] = useState<GenerationResult[]>([]);
  const [artifacts, setArtifacts] = useState<Record<string, GenerationArtifactBundle>>({});
  const [plans, setPlans] = useState<ApplicationPlan[]>([]);
  const [runs, setRuns] = useState<ApplicationRun[]>([]);
  const [providers, setProviders] = useState<IntegrationProvider[]>([]);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [searchProfiles, setSearchProfiles] = useState<SearchProfile[]>([]);
  const [monitors, setMonitors] = useState<IngestionSourceConfig[]>([]);
  const [ingestionRuns, setIngestionRuns] = useState<IngestionRun[]>([]);
  const [outcomes, setOutcomes] = useState<ApplicationOutcome[]>([]);
  const [promptPerf, setPromptPerf] = useState<PromptPerformance[]>([]);
  const [resumeScores, setResumeScores] = useState<ResumeVariantScore[]>([]);
  const [notifyPrefs, setNotifyPrefs] = useState<NotificationPreference[]>([]);
  const [notifyEvents, setNotifyEvents] = useState<NotificationEvent[]>([]);

  const [activeBaseId, setActiveBaseId] = useState<string | null>(null);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [activeTemplateId, setActiveTemplateId] = useState<string | null>(null);
  const [activeSearchId, setActiveSearchId] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeMonitorId, setActiveMonitorId] = useState<string | null>(null);
  const [selectedProviderKey, setSelectedProviderKey] = useState<string>("google_oauth");
  const [activeConnectionId, setActiveConnectionId] = useState<string | null>(null);
  const [previewDraftId, setPreviewDraftId] = useState<string | null>(null);
  const [showProfileEditor, setShowProfileEditor] = useState(false);
  const [libraryFilter, setLibraryFilter] = useState<"resume" | "cover_letter" | "prompt">("resume");
  const [selectedLibraryKey, setSelectedLibraryKey] = useState<string | null>(null);
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const busyTimerRef = useRef<number | null>(null);

  const [baseForm, setBaseForm] = useState<BaseForm>(emptyBase);
  const [uploadForm, setUploadForm] = useState<UploadForm>(emptyUpload);
  const [promptForm, setPromptForm] = useState<PromptForm>(emptyPrompt);
  const [templateForm, setTemplateForm] = useState<TemplateForm>(emptyTemplate);
  const [searchForm, setSearchForm] = useState<SearchForm>(emptySearch);
  const [monitorForm, setMonitorForm] = useState<MonitorForm>(emptyMonitor);
  const [jobForm, setJobForm] = useState<JobForm>(emptyJob);
  const [draftForm, setDraftForm] = useState<DraftForm>(emptyDraft);
  const [outcomeForm, setOutcomeForm] = useState<OutcomeForm>(emptyOutcome);
  const [notifyForm, setNotifyForm] = useState<NotificationForm>(emptyNotify);
  const [connectionForm, setConnectionForm] = useState<ConnectionForm>({ name: "Google", providerKey: "google_oauth", loginHint: "", settings: { redirect_uri: "http://localhost:8013/api/v1/auth/google/callback" } });

  const selectedProvider = providers.find((p) => p.key === selectedProviderKey) ?? null;
  const selectedConnection = connections.find((c) => c.id === activeConnectionId) ?? null;
  const googleConnection = connections.find((c) => c.provider_key === "google_oauth") ?? null;
  const sourceProviders = providers.filter((p) => p.category === "source");
  const accountProviders = providers.filter((p) => p.category === "account");
  const workspaceProviders = accountProviders.filter((p) => ["google_oauth", "microsoft_oauth"].includes(p.key));
  const jobBoardAccountProviders = accountProviders.filter((p) => !["google_oauth", "microsoft_oauth"].includes(p.key));
  const notificationProviders = providers.filter((p) => p.category === "notification");
  const resumeTemplates = templates.filter((t) => t.document_kind === "resume");
  const coverTemplates = templates.filter((t) => t.document_kind === "cover_letter");

  useEffect(() => {
    const onPop = (): void => setView(resolveView(window.location.pathname));
    window.addEventListener("popstate", onPop);
    const url = new URL(window.location.href);
    const authToken = url.searchParams.get("auth_token");
    if (authToken) {
      storeAuthToken(authToken);
      url.searchParams.delete("auth_token");
      window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
      setBanner({ tone: "success", message: "Google sign-in completed." });
    }
    void refreshAll();
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    return () => {
      if (busyTimerRef.current !== null) {
        window.clearInterval(busyTimerRef.current);
        busyTimerRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    const provider = providers.find((p) => p.key === selectedProviderKey) ?? null;
    const connection = activeConnectionId ? connections.find((c) => c.id === activeConnectionId) ?? null : connections.find((c) => c.provider_key === selectedProviderKey) ?? null;
    setActiveConnectionId(connection?.id ?? null);
    setConnectionForm(makeConnectionForm(provider, connection));
  }, [selectedProviderKey, activeConnectionId, providers, connections]);

  useEffect(() => {
    if (!providers.length) return;
    if (!providers.some((provider) => provider.key === selectedProviderKey)) {
      setSelectedProviderKey(providers[0].key);
    }
  }, [providers, selectedProviderKey]);

  useEffect(() => {
    const filteredDocs = docs.filter((doc) => doc.document_kind === libraryFilter);
    if (!filteredDocs.length) {
      setSelectedLibraryKey(null);
      return;
    }
    const currentVisible = filteredDocs.some((doc) => (doc.library_key ?? doc.source_document) === selectedLibraryKey);
    if (!currentVisible) {
      setSelectedLibraryKey(filteredDocs[0].library_key ?? filteredDocs[0].source_document);
    }
  }, [docs, libraryFilter, selectedLibraryKey]);

  useEffect(() => {
    const provider = providers.find((p) => p.key === selectedProviderKey) ?? null;
    const connection = activeConnectionId ? connections.find((c) => c.id === activeConnectionId) ?? null : null;
    if (!provider || provider.auth_type !== "browser_session" || !connection?.id) {
      setBrowserCapture(null);
      return;
    }
    void fetchIntegrationBrowserCapture(connection.id)
      .then((capture) => setBrowserCapture(capture))
      .catch(() => setBrowserCapture(null));
  }, [selectedProviderKey, activeConnectionId, providers, connections]);

  useEffect(() => {
    const email = notifyPrefs.find((p) => p.channel === "email");
    const slack = notifyPrefs.find((p) => p.channel === "slack");
    setNotifyForm((prev) => ({ ...prev, emailEnabled: email?.enabled ?? prev.emailEnabled, emailTarget: email?.target ?? prev.emailTarget, slackEnabled: slack?.enabled ?? prev.slackEnabled, slackTarget: slack?.target ?? prev.slackTarget }));
  }, [notifyPrefs]);
  useEffect(() => {
    const selected = baseProfiles.find((profile) => profile.id === activeBaseId) ?? baseProfiles[0] ?? null;
    if (!selected) return;
    if (!activeBaseId || !baseProfiles.some((profile) => profile.id === activeBaseId)) {
      editBase(selected);
    }
  }, [baseProfiles, activeBaseId]);

  async function refreshAll(): Promise<void> {
    setLoading(true);
    try {
      await fetchPlatformHealth();
      setApiOnline(true);
    } catch {
      setApiOnline(false);
      setBanner({ tone: "error", message: "The backend API on localhost:8013 is offline. Restart the platform services, then refresh this page." });
      setLoading(false);
      return;
    }

    try {
      const [authData, overviewData, baseData, docData, promptData, templateData, jobData, draftData, planData, runData, providerData, connectionData, searchData, monitorData, ingestData, outcomeData, promptPerfData, resumeScoreData, prefData, eventData] = await Promise.all([
        fetchAuthStatus(), fetchDashboardOverview(), fetchBaseProfiles(), fetchCorpusLibrary(), fetchPrompts(), fetchTemplates(), fetchJobs(), fetchDrafts(), fetchApplicationPlans(), fetchApplicationRuns(), fetchIntegrationProviders(), fetchIntegrationConnections(), fetchSearchProfiles(), fetchIngestionConfigs(), fetchIngestionRuns(), fetchLearningOutcomes(), fetchPromptPerformance(), fetchResumeScores(), fetchNotificationPreferences(), fetchNotificationEvents(),
      ]);
      const memoryData = await fetchCandidateMemory(activeBaseId ?? baseData[0]?.id);
      const bundles = await Promise.all(draftData.map(async (draft) => { try { return [draft.id, await fetchArtifactBundle(draft.id)] as const; } catch { return [draft.id, { generation_result_id: draft.id, artifacts: [] } as GenerationArtifactBundle] as const; } }));
      const artifactMap: Record<string, GenerationArtifactBundle> = {};
      bundles.forEach(([id, bundle]) => { artifactMap[id] = bundle; });
      startTransition(() => {
        setAuth(authData); setOverview(overviewData); setMemory(memoryData); setBaseProfiles(baseData); setDocs(docData); setPrompts(promptData); setTemplates(templateData); setJobs(jobData); setDrafts(draftData); setArtifacts(artifactMap); setPlans(planData); setRuns(runData); setProviders(providerData); setConnections(connectionData); setSearchProfiles(searchData); setMonitors(monitorData); setIngestionRuns(ingestData); setOutcomes(outcomeData); setPromptPerf(promptPerfData); setResumeScores(resumeScoreData); setNotifyPrefs(prefData); setNotifyEvents(eventData);
        setDraftForm((prev) => ({ ...prev, jobId: prev.jobId || jobData[0]?.id || "", planJobId: prev.planJobId || jobData[0]?.id || "", resumeTemplate: prev.resumeTemplate || templateData.find((t) => t.document_kind === "resume")?.name || "", coverTemplate: prev.coverTemplate || templateData.find((t) => t.document_kind === "cover_letter")?.name || "", generationResultId: prev.generationResultId || draftData[0]?.id || "" }));
        if (!previewDraftId && draftData[0]) setPreviewDraftId(draftData[0].id);
        setOutcomeForm((prev) => ({ ...prev, applicationPlanId: prev.applicationPlanId || planData[0]?.id || "", applicationRunId: prev.applicationRunId || runData[0]?.id || "" }));
      });
    } catch (error) {
      setBanner({ tone: "error", message: `Unable to refresh the platform: ${msg(error)}` });
    } finally {
      setLoading(false);
    }
  }

  function clearBusySequence(): void {
    if (busyTimerRef.current !== null) {
      window.clearInterval(busyTimerRef.current);
      busyTimerRef.current = null;
    }
  }

  function startBusySequence(title: string, details?: string[]): void {
    clearBusySequence();
    const messages = (details ?? []).filter(Boolean);
    const fallback = "The agents are working in the background. This surface will refresh when the current step completes.";
    setBusy({ title, detail: messages[0] ?? fallback });
    if (messages.length <= 1) return;
    let index = 0;
    busyTimerRef.current = window.setInterval(() => {
      index = Math.min(index + 1, messages.length - 1);
      setBusy({ title, detail: messages[index] ?? fallback });
      if (index >= messages.length - 1 && busyTimerRef.current !== null) {
        window.clearInterval(busyTimerRef.current);
        busyTimerRef.current = null;
      }
    }, 1350);
  }

  function stopBusySequence(): void {
    clearBusySequence();
    setBusy(null);
  }

  function navigate(next: ViewKey): void { if (window.location.pathname !== viewPaths[next]) window.history.pushState({}, "", viewPaths[next]); startTransition(() => setView(next)); }
  async function act<T>(label: string, work: () => Promise<T>, success?: string | ((value: T) => string), after?: (value: T) => void | Promise<void>, progressDetails?: string[]): Promise<T | null> {
    startBusySequence(label, progressDetails);
    try {
      const result = await work();
      if (after) await after(result);
      await refreshAll();
      if (success) setBanner({ tone: "success", message: typeof success === "function" ? success(result) : success });
      return result;
    } catch (error) {
      setBanner({ tone: "error", message: `${label} failed: ${msg(error)}` });
      return null;
    } finally {
      stopBusySequence();
    }
  }

  async function actWorkflow<T>(
    label: string,
    submit: () => Promise<WorkflowSubmission<T>>,
    poll: (workflowId: string) => Promise<WorkflowSubmission<T>>,
    success?: string | ((value: T) => string),
    after?: (value: T) => void | Promise<void>,
    progressDetails?: string[],
  ): Promise<T | null> {
    startBusySequence(label, progressDetails);
    const fallback = progressDetails?.[progressDetails.length - 1] ?? "The workflow is still running in the background.";
    try {
      let snapshot = await submit();
      if (!snapshot.result) clearBusySequence();
      let attempts = 0;
      while (!snapshot.result) {
        const workflowStatus = String(snapshot.workflow_status || "running");
        if (["failed", "terminated", "canceled", "timed_out"].includes(workflowStatus)) {
          throw new Error(snapshot.error || `Workflow ${workflowStatus}.`);
        }
        if (!snapshot.workflow_id) {
          throw new Error("Workflow submission did not return a workflow id.");
        }
        setBusy({ title: label, detail: `${fallback} Current workflow status: ${workflowStatus.replace(/_/g, " ")}.` });
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        snapshot = await poll(snapshot.workflow_id);
        attempts += 1;
        if (attempts >= 180) {
          throw new Error("Workflow did not complete within the expected time.");
        }
      }
      const result = snapshot.result;
      if (after) await after(result);
      await refreshAll();
      if (success) setBanner({ tone: "success", message: typeof success === "function" ? success(result) : success });
      return result;
    } catch (error) {
      setBanner({ tone: "error", message: `${label} failed: ${msg(error)}` });
      return null;
    } finally {
      stopBusySequence();
    }
  }

  function editBase(profile?: BaseProfile): void { if (!profile) { setActiveBaseId(null); setBaseForm(emptyBase); setShowProfileEditor(true); return; } setActiveBaseId(profile.id); setShowProfileEditor(false); setBaseForm({ fullName: profile.full_name, email: profile.email ?? "", phone: profile.phone ?? "", location: profile.location ?? "", website: profile.website ?? "", summary: profile.summary ?? "", skills: join(profile.skills_json ?? []), certifications: join(profile.certifications_json ?? []), experience: decodeEntries(profile.experience_json ?? []), projects: decodeEntries(profile.projects_json ?? []), education: decodeEducation(profile.education_json ?? []) }); }
  function editPrompt(prompt?: PromptVersion): void { if (!prompt) { setActivePromptId(null); setPromptForm(emptyPrompt); return; } setActivePromptId(prompt.id); setPromptForm({ name: prompt.name, roleTags: join(prompt.role_tags_json), promptText: prompt.prompt_text, temperature: String(prompt.temperature), successRate: String(prompt.success_rate_metric) }); }
  function editTemplate(template?: TemplateVariant): void { if (!template) { setActiveTemplateId(null); setTemplateForm(emptyTemplate); return; } setActiveTemplateId(template.id); setTemplateForm({ name: template.name, documentKind: template.document_kind, templatePath: template.template_path, file: null }); }
  function editSearch(profile?: SearchProfile): void { if (!profile) { setActiveSearchId(null); setSearchForm(emptySearch); return; } setActiveSearchId(profile.id); setSearchForm({ name: profile.name, roles: join(profile.roles), keywords: join(profile.keywords), locations: join(profile.locations), sources: join(profile.source_allowlist), dailyCap: String(profile.daily_cap), remotePolicy: profile.remote_policy }); }
  function editMonitor(config?: IngestionSourceConfig): void { if (!config) { setActiveMonitorId(null); setMonitorForm(emptyMonitor); return; } setActiveMonitorId(config.id); setMonitorForm({ name: config.name, source: config.source, searchProfileId: config.search_profile_id ?? "", connectionId: config.connection_id ?? "", queryText: config.query_text ?? "", cadenceMinutes: String(config.cadence_minutes), maxResults: String(config.max_results), searchUrl: config.search_url ?? "", enabled: config.enabled }); }
  function editJob(job?: JobPosting): void { if (!job) { setActiveJobId(null); setJobForm(emptyJob); return; } setActiveJobId(job.id); setJobForm({ source: job.source, connectionId: typeof job.metadata_json?.connection_id === "string" ? String(job.metadata_json.connection_id) : "", company: job.company, title: job.title, url: job.source_url, externalId: job.external_id, location: job.location ?? "", workMode: job.work_mode ?? "", description: job.description_text, labels: join(job.classification_labels_json), riskFlags: join(job.risk_flags_json) }); }
  function selectProvider(providerKey: string, connectionId?: string | null): void { setSelectedProviderKey(providerKey); setActiveConnectionId(connectionId ?? null); navigate("integrations"); }
  async function googleSignIn(): Promise<void> {
    const clientId = String(googleConnection?.settings_json?.client_id ?? "");
    if (!auth.google_ready) {
      selectProvider("google_oauth", googleConnection?.id ?? null);
      setBanner({ tone: "error", message: "Google sign-in is not ready. Open Connections, save your Google Web client, and use the exact callback URI shown there." });
      return;
    }
    if (clientId && !clientId.includes(".apps.googleusercontent.com")) {
      selectProvider("google_oauth", googleConnection?.id ?? null);
      setBanner({ tone: "error", message: "The saved Google Client ID does not look valid for a web app. It should end with .apps.googleusercontent.com." });
      return;
    }
    window.location.href = googleAuthStartUrl(`${window.location.origin}${viewPaths.overview}`);
  }

  async function signOut(): Promise<void> {
    startBusySequence("Signing out", ["Closing the current workspace session."]);
    try {
      if (readAuthToken()) {
        try { await logoutCurrentSession(); } catch { /* ignore */ }
      }
      clearAuthToken();
      await refreshAll();
      setBanner({ tone: "success", message: "Signed out from the platform." });
    } finally {
      stopBusySequence();
    }
  }

  async function saveBase(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await act(activeBaseId ? "Updating base profile" : "Creating base profile", () => saveBaseProfile({ full_name: baseForm.fullName, email: baseForm.email || null, phone: baseForm.phone || null, location: baseForm.location || null, website: baseForm.website || null, summary: baseForm.summary || null, skills_json: list(baseForm.skills), certifications_json: list(baseForm.certifications), experience_json: encodeEntries(baseForm.experience), projects_json: encodeEntries(baseForm.projects), education_json: encodeEducation(baseForm.education), metadata_json: {} }, activeBaseId ?? undefined), activeBaseId ? "Base profile updated." : "Base profile saved.", (result) => editBase(result));
  }
  async function removeBase(id: string): Promise<void> { await act("Deleting base profile", () => deleteBaseProfile(id), "Base profile deleted.", () => editBase()); }

  async function uploadKnowledge(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!apiOnline) {
      setBanner({ tone: "error", message: "The backend API is offline, so uploads cannot start yet. Restart the platform services first." });
      return;
    }
    if (!uploadForm.files.length) {
      setBanner({ tone: "error", message: "Choose one or more resumes, cover letters, or prompt files first." });
      return;
    }
    const documentType = uploadForm.documentType;
    const result = await actWorkflow(
      "Analyzing document batch",
      () => uploadCorpusFiles({ files: uploadForm.files, collectionName: `${documentType}-library`, roleHint: list(uploadForm.roleHints), documentKind: documentType }),
      fetchCorpusWorkflow,
      (response) => {
        const sectionCount = response.created_section_count ?? response.created_fragments ?? 0;
        return `Parsed ${response.ingested_documents} file${response.ingested_documents === 1 ? "" : "s"}, extracted ${sectionCount} reusable section file${sectionCount === 1 ? "" : "s"}, and refreshed Profile Memory.`;
      },
      (response) => {
        if (response.profile_id) setActiveBaseId(response.profile_id);
        setLibraryFilter(documentType);
        if (response.library_keys?.length) setSelectedLibraryKey(response.library_keys[response.library_keys.length - 1] ?? null);
      },
      uploadProgressMessages(documentType),
    );
    if (result) {
      setUploadForm({ ...emptyUpload, documentType });
      setUploadInputKey((value) => value + 1);
      setShowProfileEditor(false);
      navigate("knowledge");
    }
  }
  async function syncMemory(overwriteSummary = false): Promise<void> { const profileId = activeBaseId ?? baseProfiles[0]?.id; if (!profileId) { setBanner({ tone: "error", message: "Save a base profile before syncing memory." }); return; } await act("Syncing profile memory", () => syncCandidateMemory(profileId, overwriteSummary), "Profile memory synced from your uploaded evidence."); }

  async function savePromptVersion(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await act(activePromptId ? "Updating prompt" : "Saving prompt", () => savePrompt({ name: promptForm.name, role_tags: list(promptForm.roleTags), prompt_text: promptForm.promptText, temperature: Number(promptForm.temperature || 0.2), success_rate_metric: Number(promptForm.successRate || 0) }, activePromptId ?? undefined), activePromptId ? "Prompt updated." : "Prompt saved.", (result) => editPrompt(result));
  }
  async function removePrompt(id: string): Promise<void> { await act("Deleting prompt", () => deletePrompt(id), "Prompt deleted.", () => editPrompt()); }

  async function saveTemplateVariant(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (templateForm.file) {
      const result = await act("Uploading template", () => uploadTemplate({ file: templateForm.file as File, name: templateForm.name, documentKind: templateForm.documentKind }), "Template uploaded.", (value) => editTemplate(value));
      if (result) setTemplateForm(emptyTemplate);
      return;
    }
    await act(activeTemplateId ? "Updating template" : "Saving template", () => saveTemplate({ name: templateForm.name, document_kind: templateForm.documentKind, template_path: templateForm.templatePath }, activeTemplateId ?? undefined), activeTemplateId ? "Template updated." : "Template saved.", (result) => editTemplate(result));
  }
  async function removeTemplate(id: string): Promise<void> { await act("Deleting template", () => deleteTemplate(id), "Template deleted.", () => editTemplate()); }

  async function saveSearch(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await act(activeSearchId ? "Updating search profile" : "Saving search profile", () => saveSearchProfile({ name: searchForm.name, roles: list(searchForm.roles), keywords: list(searchForm.keywords), excluded_terms: [], locations: list(searchForm.locations), remote_policy: searchForm.remotePolicy, salary_floor: null, source_allowlist: list(searchForm.sources), daily_cap: Number(searchForm.dailyCap || 12), review_policy: "manual_review_for_complex_forms", schedule_window: { start: "08:00", end: "18:00" } }, activeSearchId ?? undefined), activeSearchId ? "Search profile updated." : "Search profile saved.", (result) => editSearch(result));
  }
  async function removeSearch(id: string): Promise<void> { await act("Deleting search profile", () => deleteSearchProfile(id), "Search profile deleted.", () => editSearch()); }

  async function saveMonitorConfig(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await act(activeMonitorId ? "Updating monitor" : "Saving monitor", () => saveIngestionConfig({ name: monitorForm.name, search_profile_id: monitorForm.searchProfileId || null, connection_id: monitorForm.connectionId || null, source: monitorForm.source, enabled: monitorForm.enabled, cadence_minutes: Number(monitorForm.cadenceMinutes || 45), query_text: monitorForm.queryText || null, location_override: null, max_results: Number(monitorForm.maxResults || 25), auto_start_pipeline: true, search_url: monitorForm.searchUrl || null, metadata_json: {} }, activeMonitorId ?? undefined), activeMonitorId ? "Monitor updated." : "Monitor saved.", (result) => editMonitor(result));
  }
  async function runMonitor(id: string, continuous: boolean): Promise<void> { await act(continuous ? "Starting continuous monitoring" : "Running discovery sweep", () => triggerIngestion({ config_id: id, iterations: 1, continuous }), continuous ? "Continuous monitoring started." : "Discovery sweep started."); }

  async function saveTrackedJob(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await act(activeJobId ? "Updating job" : "Saving job", () => saveJob({ source: jobForm.source, external_id: jobForm.externalId.trim() || `manual-${Date.now()}`, source_url: jobForm.url, company: jobForm.company, title: jobForm.title, location: jobForm.location || undefined, work_mode: jobForm.workMode || undefined, description_text: jobForm.description, classification_labels: list(jobForm.labels), eligibility_flags: [], risk_flags: list(jobForm.riskFlags), metadata_json: jobForm.connectionId ? { connection_id: jobForm.connectionId } : {} }, activeJobId ?? undefined), activeJobId ? "Job updated." : "Job saved.", (result) => editJob(result));
  }
  async function removeTrackedJob(id: string): Promise<void> { await act("Deleting job", () => deleteJob(id), "Job deleted.", () => editJob()); }
  async function runPipeline(jobId: string): Promise<void> { await act("Starting job pipeline", () => startJobPipeline(jobId), "Durable job pipeline started."); }

  async function generateDraft(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!draftForm.jobId || !draftForm.resumeTemplate || !draftForm.coverTemplate) {
      setBanner({ tone: "error", message: "Choose a job plus resume and cover templates before generating." });
      return;
    }
    const result = await actWorkflow(
      "Generating tailored draft",
      () => createGenerationRequest({ job_id: draftForm.jobId, template_variant_name: draftForm.resumeTemplate, cover_template_variant_name: draftForm.coverTemplate, force_regenerate: false }),
      fetchGenerationWorkflow,
      "Tailored resume and cover letter generated.",
    );
    if (result) setDraftForm((prev) => ({ ...prev, generationResultId: result.id, planJobId: prev.jobId }));
  }
  async function createPlan(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!draftForm.planJobId || !draftForm.generationResultId) {
      setBanner({ tone: "error", message: "Choose a job and a generated draft before creating a plan." });
      return;
    }
    await act("Creating application plan", () => createApplicationPlan({ job_id: draftForm.planJobId, generation_result_id: draftForm.generationResultId }), "Application plan created.");
  }
  async function startRun(planId: string): Promise<void> { await act("Starting application run", () => startApplicationRun({ plan_id: planId }), "Application run started."); }

  async function saveOutcome(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!outcomeForm.applicationPlanId) {
      setBanner({ tone: "error", message: "Choose an application plan before recording an outcome." });
      return;
    }
    await act("Recording outcome", () => createLearningOutcome({ application_plan_id: outcomeForm.applicationPlanId, application_run_id: outcomeForm.applicationRunId || null, response_type: outcomeForm.responseType, interview: outcomeForm.interview, response_time_days: num(outcomeForm.responseTimeDays), outcome_source: "manual", notes: outcomeForm.notes || null }), "Outcome recorded and learning scores updated.");
  }

  async function saveNotifications(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await act("Saving notifications", async () => { await Promise.all([saveNotificationPreference({ channel: "email", enabled: notifyForm.emailEnabled, target: notifyForm.emailTarget || null }), saveNotificationPreference({ channel: "slack", enabled: notifyForm.slackEnabled, target: notifyForm.slackTarget || null })]); return true; }, "Notification preferences saved.");
  }
  async function testNotification(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    await act("Sending test notification", () => sendTestNotification({ channel: notifyForm.testChannel, subject: notifyForm.testSubject, body: notifyForm.testBody }), "Test notification queued.");
  }

  async function saveConnection(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!selectedProvider) return;
    const clientId = connectionForm.settings.client_id?.trim();
    if (selectedProvider.key === "google_oauth" && clientId && !clientId.includes(".apps.googleusercontent.com")) {
      setBanner({ tone: "error", message: "Google Client ID looks invalid. It should end with .apps.googleusercontent.com." });
      return;
    }
    const settings = Object.fromEntries(Object.entries(connectionForm.settings).filter(([, value]) => value.trim() !== ""));
    if (selectedProvider.key === "google_oauth") settings.redirect_uri = REQUIRED_GOOGLE_REDIRECT_URI;
    const result = await act(activeConnectionId ? "Updating connection" : "Creating connection", () => saveIntegrationConnection({ name: connectionForm.name || selectedProvider.name, provider_key: selectedProvider.key, login_hint: connectionForm.loginHint || null, settings_json: settings, metadata_json: {} }, activeConnectionId ?? undefined), activeConnectionId ? "Connection updated." : "Connection created.");
    if (result) { setActiveConnectionId(result.id); setConnectNotice({ title: `${selectedProvider.name} saved`, lines: [`${selectedProvider.name} is now available to monitors and application flows.`] }); }
  }
  async function removeConnection(id: string): Promise<void> { await act("Deleting connection", () => deleteIntegrationConnection(id), "Connection deleted.", () => { setActiveConnectionId(null); setConnectNotice(null); setBrowserCapture(null); }); }
  async function connectProvider(): Promise<void> {
    if (!selectedProvider) return;
    if (selectedProvider.key === "google_oauth") { await googleSignIn(); return; }
    if (!activeConnectionId) { setBanner({ tone: "error", message: "Save the connection first, then start the provider flow." }); return; }
    const result = await act("Starting provider connection", () => connectIntegrationConnection(activeConnectionId));
    if (!result) return;
    if (selectedProvider.auth_type === "browser_session") {
      const capture = await fetchIntegrationBrowserCapture(activeConnectionId).catch(() => null);
      if (capture) setBrowserCapture(capture);
      setConnectNotice({ title: `${selectedProvider.name} sign-in`, lines: capture?.instructions ?? result.instructions, url: capture?.login_url ?? result.launch_url ?? null });
      return;
    }
    setConnectNotice({ title: `${selectedProvider.name} connection`, lines: result.instructions, url: result.auth_url ?? result.launch_url ?? null });
    if (result.auth_url) { window.location.href = result.auth_url; return; }
    if (result.launch_url) window.open(result.launch_url, "_blank", "noopener,noreferrer");
  }
  async function refreshBrowserCaptureState(): Promise<void> {
    if (!activeConnectionId) { setBanner({ tone: "error", message: "Save the connection first." }); return; }
    const capture = await act("Checking sign-in status", () => fetchIntegrationBrowserCapture(activeConnectionId));
    if (capture) setBrowserCapture(capture);
  }
  async function finalizeBrowserCaptureState(): Promise<void> {
    if (!activeConnectionId) { setBanner({ tone: "error", message: "Save the connection first." }); return; }
    const capture = await act("Finishing connection", () => finalizeIntegrationBrowserCapture(activeConnectionId), "Browser session captured.");
    if (capture) setBrowserCapture(capture);
  }
  async function cancelBrowserCaptureState(): Promise<void> {
    if (!activeConnectionId) return;
    const capture = await act("Cancelling sign-in", () => cancelIntegrationBrowserCapture(activeConnectionId), "Sign-in helper cancelled.");
    if (capture) setBrowserCapture(capture);
  }
  async function copyBrowserHelperCommand(): Promise<void> {
    if (!browserCapture?.helper_command) return;
    await copyText(browserCapture.helper_command);
    setBanner({ tone: "success", message: "Guided sign-in command copied." });
  }
  function scoreJobFit(job: JobPosting): number {
    const sourceText = `${job.title} ${job.company} ${job.description_text} ${job.classification_labels_json.join(" ")}`.toLowerCase();
    const profileTerms = [...memory.skills, ...memory.certifications, ...searchProfiles.flatMap((profile) => [...profile.roles, ...profile.keywords])]
      .map((value) => String(value).toLowerCase())
      .filter(Boolean);
    const matchedSignals = profileTerms.filter((term) => sourceText.includes(term)).length;
    const labelBonus = Math.min(job.classification_labels_json.length * 6, 18);
    const signalBonus = Math.min(matchedSignals * 4, 24);
    const riskPenalty = Math.min(job.risk_flags_json.length * 5, 20);
    return Math.max(42, Math.min(96, 48 + labelBonus + signalBonus - riskPenalty));
  }

  function fitReasons(job: JobPosting): string[] {
    const reasons: string[] = [];
    if (job.classification_labels_json.length) reasons.push(`${job.classification_labels_json.slice(0, 3).join(', ')} align with your target tracks.`);
    if (job.work_mode) reasons.push(`${cleanCopy(job.work_mode)} work mode fits the current search strategy.`);
    if (job.location) reasons.push(`${cleanCopy(job.location)} is within the active geography.`);
    if (job.risk_flags_json.length) reasons.push(`Needs review for ${job.risk_flags_json.slice(0, 2).join(', ')}.`);
    if (!reasons.length) reasons.push('The agent found keyword overlap against your profile memory and current search profile.');
    return reasons.slice(0, 3);
  }

  function getPlanJob(plan: ApplicationPlan): JobPosting | null {
    return jobs.find((job) => job.id === plan.job_id) ?? null;
  }

  function getPlanRun(plan: ApplicationPlan): ApplicationRun | null {
    return runs.find((run) => run.plan_id === plan.id) ?? null;
  }

  function getPlanDraft(plan: ApplicationPlan): GenerationResult | null {
    return drafts.find((draft) => draft.id === plan.generation_result_id) ?? null;
  }

  function queueBucket(plan: ApplicationPlan): "review" | "ready" | "moving" {
    const run = getPlanRun(plan);
    if (run && !["completed", "failed"].includes(run.status.toLowerCase())) return "moving";
    if (plan.approval_state && !["approved", "auto_approved", "waived"].includes(plan.approval_state.toLowerCase())) return "review";
    if (plan.mode.toLowerCase().includes("review")) return "review";
    return "ready";
  }

  function openJobInLab(job: JobPosting): void {
    patch(setDraftForm, { jobId: job.id, planJobId: job.id });
    navigate("library");
  }

  function openDraftInLab(draftId: string): void {
    patch(setDraftForm, { generationResultId: draftId });
    setPreviewDraftId(draftId);
    navigate("library");
  }

  function PageHero({ eyebrow, title, copy, metrics, actions }: { eyebrow: string; title: string; copy: string; metrics: { label: string; value: string | number; note?: string }[]; actions?: ReactNode }): JSX.Element {
    return (
      <section className="page-hero">
        <div className="page-hero-copy">
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          <p className="hero-copy">{copy}</p>
          {actions ? <div className="hero-action-row">{actions}</div> : null}
        </div>
        <div className="hero-metrics">
          {metrics.map((metric) => (
            <div className="hero-metric-card" key={metric.label}>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
              {metric.note ? <small>{metric.note}</small> : null}
            </div>
          ))}
        </div>
      </section>
    );
  }

  function AgentRail(): JSX.Element {
    const ranked = [...jobs].sort((left, right) => scoreJobFit(right) - scoreJobFit(left));
    const reviewPlans = plans.filter((plan) => queueBucket(plan) === "review");
    const scoutState = monitors.length ? `${monitors.length} radars armed` : "No active radars";
    const scoutDetail = ingestionRuns[0] ? `${ingestionRuns[0].discovered_count} roles found on the latest sweep.` : "Waiting for the first discovery run.";
    const tailorState = drafts.length ? `${drafts.length} draft variants available` : "No draft in motion";
    const tailorDetail = normalizeReasoning(drafts[0]?.grounding_notes, "The tailoring agent will explain why it chose each section.").slice(0, 120);
    const applyState = plans.length ? `${plans.length} items in the queue` : "Queue is empty";
    const applyDetail = reviewPlans.length ? `${reviewPlans.length} items currently need human review.` : runs[0] ? `${runs[0].status} on the latest run.` : "Nothing is blocked right now.";
    return (
      <aside className="agent-rail">
        <div className="agent-rail-head">
          <p className="eyebrow">Live Agents</p>
          <h3>The system is always reasoning in the background.</h3>
        </div>
        <div className="agent-stack">
          <div className="agent-card agent-card-scout">
            <div className="agent-card-head"><strong>Scout</strong><span className="status-orb status-orb-cyan" /></div>
            <p className="agent-state">{scoutState}</p>
            <p className="agent-detail">{scoutDetail}</p>
          </div>
          <div className="agent-card agent-card-tailor">
            <div className="agent-card-head"><strong>Tailor</strong><span className="status-orb status-orb-violet" /></div>
            <p className="agent-state">{tailorState}</p>
            <p className="agent-detail">{tailorDetail}</p>
          </div>
          <div className="agent-card agent-card-apply">
            <div className="agent-card-head"><strong>Apply</strong><span className="status-orb status-orb-copper" /></div>
            <p className="agent-state">{applyState}</p>
            <p className="agent-detail">{applyDetail}</p>
          </div>
        </div>
        <section className="rail-section">
          <div className="rail-section-head"><span>Latest matches</span><button className="ghost-link-button" type="button" onClick={() => navigate("monitoring")}>Open radar</button></div>
          <div className="rail-list">
            {ranked.slice(0, 4).map((job) => (
              <button className="rail-list-card" type="button" key={job.id} onClick={() => openJobInLab(job)}>
                <div className="data-card-row"><strong>{cleanCopy(job.title)}</strong><span className="score-chip">{scoreJobFit(job)}</span></div>
                <p>{cleanCopy(job.company)} | {cleanCopy(job.source)}</p>
              </button>
            ))}
            {!ranked.length ? <div className="empty-state compact-empty">No live matches yet.</div> : null}
          </div>
        </section>
        <section className="rail-section">
          <div className="rail-section-head"><span>Approval watch</span><button className="ghost-link-button" type="button" onClick={() => navigate("applications")}>Open queue</button></div>
          <div className="rail-list">
            {reviewPlans.slice(0, 3).map((plan) => {
              const job = getPlanJob(plan);
              return (
                <div className="rail-list-card" key={plan.id}>
                  <div className="data-card-row"><strong>{job ? cleanCopy(job.title) : `Plan ${plan.id.slice(0, 8)}`}</strong><span className={tone(plan.approval_state)}>{plan.approval_state}</span></div>
                  <p>{job ? cleanCopy(job.company) : cleanCopy(plan.source_adapter)}</p>
                </div>
              );
            })}
            {!reviewPlans.length ? <div className="empty-state compact-empty">Nothing waiting for approval.</div> : null}
          </div>
        </section>
        <section className="rail-section">
          <div className="rail-section-head"><span>Reasoning</span><button className="ghost-link-button" type="button" onClick={() => navigate("library")}>Open lab</button></div>
          <div className="rail-list">
            {drafts.slice(0, 2).map((draft) => (
              <div className="rail-list-card" key={draft.id}>
                <div className="data-card-row"><strong>Draft {draft.id.slice(0, 8)}</strong><span className={tone(draft.compile_status)}>{draft.compile_status}</span></div>
                <p>{normalizeReasoning(draft.grounding_notes, "Grounded from your profile memory and uploaded history.")}</p>
              </div>
            ))}
            {!drafts.length ? <div className="empty-state compact-empty">The lab will explain itself once a draft exists.</div> : null}
          </div>
        </section>
      </aside>
    );
  }

  function landingPage(): JSX.Element {
    const process = ["Scout", "Match", "Tailor", "Review", "Apply", "Learn"];
    return (
      <div className="landing-shell dark-shell">
        <section className="landing-hero-grid">
          <div className="landing-copy-panel">
            <p className="eyebrow">AI Career Operations Cockpit</p>
            <h1>A calm autonomous system for finding, tailoring, reviewing, and sending job applications.</h1>
            <p className="hero-copy">Teach the platform once. It keeps monitoring the market, composing one-page resumes, and moving your apply queue while still giving you control where trust matters.</p>
            <div className="hero-action-row">
              <button className="primary-button" type="button" onClick={() => navigate("overview")}>Start my AI job system</button>
              <button className="secondary-button" type="button" onClick={() => navigate("knowledge")}>See how it works</button>
            </div>
          </div>
          <div className="landing-vignette">
            <div className="vignette-stream">
              <div className="vignette-card"><span className="status-orb status-orb-cyan" />Scout found 6 new roles across active sources.</div>
              <div className="vignette-card"><span className="status-orb status-orb-violet" />Tailor promoted 2 higher-fit resume variants.</div>
              <div className="vignette-card"><span className="status-orb status-orb-copper" />Apply queue is holding 1 application for approval.</div>
            </div>
            <div className="landing-vignette-grid">
              <div className="hero-metric-card"><span>Sources watched</span><strong>{Math.max(monitors.length, sourceProviders.length)}</strong></div>
              <div className="hero-metric-card"><span>Profile assets</span><strong>{docs.length}</strong></div>
              <div className="hero-metric-card"><span>Drafts composed</span><strong>{drafts.length}</strong></div>
              <div className="hero-metric-card"><span>Queue items</span><strong>{plans.length}</strong></div>
            </div>
          </div>
        </section>
        <section className="landing-flow-panel">
          <div>
            <p className="eyebrow">How the agents work</p>
            <h3>Scout to Learn, in one continuous loop.</h3>
          </div>
          <div className="process-strip">
            {process.map((step, index) => (
              <div className="process-node" key={step}>
                <span>{index + 1}</span>
                <strong>{step}</strong>
              </div>
            ))}
          </div>
        </section>
        <section className="landing-panels-grid">
          <div className="signal-panel">
            <p className="eyebrow">Teach the system</p>
            <h3>Upload resumes, cover letters, and prompt memory.</h3>
            <p>The parser phrases each document, separates reusable sections, and stores them as internal evidence for future tailoring.</p>
          </div>
          <div className="signal-panel">
            <p className="eyebrow">Let the agents scan</p>
            <h3>Keep Opportunity Radar running across active sources.</h3>
            <p>Search strategy, source health, and fit scoring stay visible while Scout keeps discovering new roles.</p>
          </div>
          <div className="signal-panel">
            <p className="eyebrow">Approve and improve</p>
            <h3>Review what went out and let the system learn.</h3>
            <p>Every application can be previewed, scored, and fed back into the learning loop after outcomes arrive.</p>
          </div>
        </section>
      </div>
    );
  }
  function commandCenterPage(): JSX.Element {
    const rankedJobs = [...jobs].sort((left, right) => scoreJobFit(right) - scoreJobFit(left));
    const reviewPlans = plans.filter((plan) => queueBucket(plan) === "review");
    const movingPlans = plans.filter((plan) => queueBucket(plan) === "moving");
    const heroLine = monitors.length
      ? `Scout is monitoring ${monitors.length} source${monitors.length === 1 ? "" : "s"} and has ${jobs.length} roles in play.`
      : "No radar is active yet. Connect sources and start the first discovery mission.";
    return (
      <div className="view-stack page-stack">
        <PageHero
          eyebrow="Command Center"
          title="The system should feel aware before the user touches anything."
          copy={heroLine}
          metrics={[
            { label: "Active sources", value: Math.max(monitors.length, sourceProviders.length), note: monitors.length ? "radars live" : "connectors available" },
            { label: "Strong matches", value: rankedJobs.length, note: "fit-scored opportunities" },
            { label: "Needs review", value: reviewPlans.length, note: "human checkpoints" },
            { label: "In motion", value: movingPlans.length || runs.length, note: "applications progressing" },
          ]}
          actions={<><button className="primary-button" type="button" onClick={() => navigate("monitoring")}>Open Opportunity Radar</button><button className="secondary-button" type="button" onClick={() => navigate("applications")}>Open Apply Queue</button></>}
        />
        <div className="cockpit-grid">
          <Panel eyebrow="Mission feed" title="Where the system is spending time right now">
            <div className="priority-feed">
              {rankedJobs.slice(0, 4).map((job) => (
                <div className="priority-card" key={job.id}>
                  <div className="priority-card-head">
                    <div>
                      <strong>{cleanCopy(job.title)}</strong>
                      <p>{cleanCopy(job.company)} | {cleanCopy(job.source)}</p>
                    </div>
                    <span className="score-chip">{scoreJobFit(job)}</span>
                  </div>
                  <div className="tag-row">{job.classification_labels_json.slice(0, 4).map((label) => <span className="tag" key={label}>{cleanCopy(label)}</span>)}</div>
                  <ul className="signal-list">{fitReasons(job).map((reason) => <li key={reason}>{reason}</li>)}</ul>
                  <div className="card-actions"><button className="secondary-button" type="button" onClick={() => openJobInLab(job)}>Open in lab</button></div>
                </div>
              ))}
              {!rankedJobs.length ? <div className="empty-state">No tracked opportunities yet. Start with Profile Memory or Opportunity Radar.</div> : null}
            </div>
          </Panel>
          <Panel eyebrow="System pressure" title="What needs attention next">
            <div className="signal-grid">
              <div className="signal-panel compact-panel">
                <p className="eyebrow">Approvals</p>
                <h3>{reviewPlans.length}</h3>
                <p>Applications are waiting for review before the system can proceed.</p>
              </div>
              <div className="signal-panel compact-panel">
                <p className="eyebrow">Drafts</p>
                <h3>{drafts.length}</h3>
                <p>Resume variants are available for inspection or direct queueing.</p>
              </div>
              <div className="signal-panel compact-panel">
                <p className="eyebrow">Outcome signals</p>
                <h3>{outcomes.length}</h3>
                <p>Recorded responses are feeding the learning loop and prompt scoring.</p>
              </div>
            </div>
            <div className="stack-list top-gap">
              {notifyEvents.slice(0, 3).map((event) => (
                <div className="timeline-item" key={event.id}>
                  <div className="timeline-head"><strong>{cleanCopy(event.subject)}</strong><span className={tone(event.delivery_status)}>{event.delivery_status}</span></div>
                  <p>{cleanCopy(event.channel)} | {cleanCopy(event.body)}</p>
                </div>
              ))}
              {!notifyEvents.length ? <div className="empty-state compact-empty">No notifications have been sent yet.</div> : null}
            </div>
          </Panel>
        </div>
        <div className="two-column-grid">
          <Panel eyebrow="Agent activity" title="Latest system actions">
            <div className="stack-list">
              {ingestionRuns.slice(0, 3).map((run) => <div className="timeline-item" key={run.id}><div className="timeline-head"><strong>Scout sweep</strong><span className={tone(run.status)}>{run.status}</span></div><p>{run.discovered_count} discovered | {run.pipeline_triggered_count} pipeline starts</p></div>)}
              {drafts.slice(0, 2).map((draft) => <div className="timeline-item" key={draft.id}><div className="timeline-head"><strong>Tailor draft {draft.id.slice(0, 8)}</strong><span className={tone(draft.compile_status)}>{draft.compile_status}</span></div><p>{normalizeReasoning(draft.grounding_notes, "Grounded from the uploaded library.")}</p></div>)}
              {runs.slice(0, 2).map((run) => <div className="timeline-item" key={run.id}><div className="timeline-head"><strong>Apply run {run.id.slice(0, 8)}</strong><span className={tone(run.status)}>{run.status}</span></div><p>{run.execution_log_json.length} logged steps</p></div>)}
              {!ingestionRuns.length && !drafts.length && !runs.length ? <div className="empty-state">Once the pipeline starts, agent activity will stream here.</div> : null}
            </div>
          </Panel>
          <Panel eyebrow="Connector health" title="Where automation is strongest">
            <div className="stack-list">
              {overview.source_health.map((source) => <div className="status-row-card" key={source.source}><div><strong>{cleanCopy(source.source)}</strong><p>{source.notes.join(' ') || 'Connector health looks stable.'}</p></div><span className={tone(source.status)}>{source.status}</span></div>)}
              {!overview.source_health.length ? <div className="empty-state">Source health appears once the connectors are configured.</div> : null}
            </div>
          </Panel>
        </div>
      </div>
    );
  }

  function profileMemoryPage(): JSX.Element {
    const filteredDocs = docs.filter((doc) => doc.document_kind === libraryFilter);
    const selectedDoc = filteredDocs.find((doc) => (doc.library_key ?? doc.source_document) === selectedLibraryKey) ?? filteredDocs[0] ?? null;
    const visibleSections = selectedDoc ? selectedDoc.sections.filter((section) => !["source", "role_signals"].includes(section.key)) : [];
    const sectionFileCount = docs.reduce((total, doc) => total + Object.values(doc.section_counts ?? {}).reduce((sum, value) => sum + value, 0), 0);
    return (
      <div className="view-stack page-stack">
        <PageHero
          eyebrow="Profile Memory"
          title="Upload your history once and let the platform build reusable memory from it."
          copy="This is where resumes, cover letters, and prompts become a structured internal library the system can mine later when it tailors a one-page application package."
          metrics={[
            { label: "Assets", value: docs.length, note: "folders in memory" },
            { label: "Section files", value: sectionFileCount, note: "reusable text blocks" },
            { label: "Skills learned", value: memory.skills.length, note: "live signal map" },
            { label: "Prompt assets", value: docs.filter((doc) => doc.document_kind === "prompt").length, note: "decision logic saved" },
          ]}
          actions={<><button className="primary-button" type="button" onClick={() => navigate("knowledge")}>Add new files</button><button className="secondary-button" type="button" onClick={() => navigate("library")}>Open Tailoring Lab</button></>}
        />
        <div className="memory-lanes">
          <div className="memory-lane"><span className="lane-code">RS</span><div><strong>Resume memory</strong><p>Reusable role variants, experience blocks, and education sections.</p></div></div>
          <div className="memory-lane"><span className="lane-code">CL</span><div><strong>Cover language</strong><p>Company-facing tone, emphasis, and narrative positioning.</p></div></div>
          <div className="memory-lane"><span className="lane-code">PR</span><div><strong>Prompt memory</strong><p>Tailoring logic the platform can reuse when it rewrites future drafts.</p></div></div>
        </div>
        <div className="two-column-grid memory-grid">
          <Panel eyebrow="Ingest" title="Teach the platform with another file batch">
            <div className="segment-row">
              <button className={uploadForm.documentType === "resume" ? "segment-button segment-button-active" : "segment-button"} type="button" onClick={() => patch(setUploadForm, { documentType: "resume" })}><span>Resume or CV</span><small>Extract experience, projects, certifications, and education.</small></button>
              <button className={uploadForm.documentType === "cover_letter" ? "segment-button segment-button-active" : "segment-button"} type="button" onClick={() => patch(setUploadForm, { documentType: "cover_letter" })}><span>Cover letter</span><small>Preserve tone, structure, and company-facing language.</small></button>
              <button className={uploadForm.documentType === "prompt" ? "segment-button segment-button-active" : "segment-button"} type="button" onClick={() => patch(setUploadForm, { documentType: "prompt" })}><span>Prompt file</span><small>Store the decision logic you already trust.</small></button>
            </div>
            <form className="form-grid top-gap" onSubmit={uploadKnowledge}>
              <Field label="Role hints" hint="Optional. Helps the parser classify the upload faster."><input value={uploadForm.roleHints} onChange={(e) => patch(setUploadForm, { roleHints: e.target.value })} placeholder="DevOps, Cloud, Infrastructure" /></Field>
              <Field label="Files" hint="PDF, DOCX, TXT, MD, and TeX are supported."><input key={uploadInputKey} type="file" multiple onChange={(e) => patch(setUploadForm, { files: Array.from(e.target.files ?? []) })} /></Field>
              <button className="primary-button" type="submit" disabled={!apiOnline || Boolean(busy)}>{apiOnline ? "Upload into Profile Memory" : "API offline"}</button>
            </form>
            {!apiOnline ? <div className="banner banner-error top-gap">The backend API is offline right now, so uploads and refreshes cannot complete. Restart the platform services, then reload this page.</div> : null}
            <div className="stack-list top-gap">
              <div className="status-row-card"><div><strong>Internal OpenAI parsing</strong><p>The parser restores the document, phrases it cleanly, and splits it into reusable internal section files.</p></div><span className="pill pill-ok">Always on</span></div>
              <div className="status-row-card"><div><strong>Hidden working profile</strong><p>The platform updates its internal profile silently. The user only sees the resulting document library and later the tailored resume preview.</p></div><span className="pill pill-muted">Behind the scenes</span></div>
            </div>
          </Panel>
          <Panel eyebrow="Library" title="Browse the extracted folders the system built for you">
            <div className="segment-row compact-segment-row">
              <button className={libraryFilter === "resume" ? "segment-button segment-button-active" : "segment-button"} type="button" onClick={() => setLibraryFilter("resume")}><span>Resumes</span><small>{docs.filter((doc) => doc.document_kind === "resume").length} folders</small></button>
              <button className={libraryFilter === "cover_letter" ? "segment-button segment-button-active" : "segment-button"} type="button" onClick={() => setLibraryFilter("cover_letter")}><span>Cover letters</span><small>{docs.filter((doc) => doc.document_kind === "cover_letter").length} folders</small></button>
              <button className={libraryFilter === "prompt" ? "segment-button segment-button-active" : "segment-button"} type="button" onClick={() => setLibraryFilter("prompt")}><span>Prompts</span><small>{docs.filter((doc) => doc.document_kind === "prompt").length} folders</small></button>
            </div>
            <div className="library-folder-list top-gap">
              {filteredDocs.map((doc, index) => (
                <button className={(selectedDoc?.library_key ?? selectedDoc?.source_document) === (doc.library_key ?? doc.source_document) ? "library-folder-card library-folder-card-active" : "library-folder-card"} type="button" key={doc.source_document} onClick={() => setSelectedLibraryKey(doc.library_key ?? doc.source_document)}>
                  <div className="library-folder-icon">{kind(doc.document_kind).slice(0, 2).toUpperCase()}</div>
                  <div className="library-folder-meta">
                    <div className="data-card-row"><strong>{cleanCopy(doc.folder_name ?? `${kind(doc.document_kind)} ${index + 1}`)}</strong><span className={tone(doc.status)}>{doc.status}</span></div>
                    <p>{cleanCopy(doc.display_name)}</p>
                    <div className="tag-row">{doc.role_tags.slice(0, 3).map((tag) => <span className="tag" key={tag}>{cleanCopy(tag)}</span>)}</div>
                  </div>
                </button>
              ))}
              {!filteredDocs.length ? <div className="empty-state compact-empty">No assets in this lane yet.</div> : null}
            </div>
          </Panel>
        </div>
        <div className="two-column-grid memory-grid">
          <Panel eyebrow="Selected folder" title={selectedDoc ? cleanCopy(selectedDoc.folder_name ?? selectedDoc.display_name) : "Select a folder"}>
            {selectedDoc ? visibleSections.length ? <div className="library-section-grid">
              {visibleSections.map((section) => {
                const displayFiles = displayLibraryFiles(section);
                if (!displayFiles.length) return null;
                return (
                  <div className="library-section-card" key={section.key}>
                    <div className="data-card-row"><strong>{cleanCopy(section.title)}</strong><span className="pill pill-muted">{displayFiles.length}</span></div>
                    <div className="stack-list top-gap">
                      {displayFiles.map((file) => (
                        <div className="library-file-row" key={file.key}>
                          <div className="library-file-head">
                            <strong>{cleanCopy(file.title)}</strong>
                            {file.subtitle ? <span className="library-file-subtitle">{cleanCopy(file.subtitle)}</span> : null}
                          </div>
                          {file.chips?.length ? <div className="tag-row">{file.chips.map((chip) => <span className="tag" key={chip}>{cleanCopy(chip)}</span>)}</div> : null}
                          {file.lines.length ? <ul className="library-line-list">{file.lines.map((line) => <li key={`${file.key}-${line}`}>{cleanCopy(line)}</li>)}</ul> : null}
                          {!file.chips?.length && !file.lines.length ? <p>{cleanCopy(file.preview ?? "Ready for reuse in tailoring.")}</p> : null}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div> : <div className="empty-state">The file is stored, but the extracted section folders have not been written yet.</div> : <div className="empty-state">Upload a document to see its extracted folder structure.</div>}
          </Panel>
          <Panel eyebrow="Signals" title="What the platform is already capable of reusing">
            <div className="signal-grid">
              <div className="signal-panel compact-panel"><p className="eyebrow">Summary</p><h3>{memory.summary ? "Ready" : "Growing"}</h3><p>{cleanCopy(memory.summary ?? "The platform will compose a working summary once it learns enough from uploads.")}</p></div>
              <div className="signal-panel compact-panel"><p className="eyebrow">Skills</p><h3>{memory.skills.length}</h3><p>{memory.skills.length ? cleanCopy(memory.skills.slice(0, 10).join(', ')) : 'Skills appear here once resumes are parsed.'}</p></div>
              <div className="signal-panel compact-panel"><p className="eyebrow">Experience blocks</p><h3>{memory.experience.length}</h3><p>{memory.experience.length ? 'Reusable experience sections are now available for the tailoring engine.' : 'Experience blocks appear after resume parsing.'}</p></div>
              <div className="signal-panel compact-panel"><p className="eyebrow">Prompt assets</p><h3>{prompts.length}</h3><p>{prompts.length ? 'Playbooks are ready to steer future rewrites.' : 'Prompt memory strengthens the tailoring engine over time.'}</p></div>
            </div>
          </Panel>
        </div>
      </div>
    );
  }

  function opportunityRadarPage(): JSX.Element {
    const rankedJobs = [...jobs].sort((left, right) => scoreJobFit(right) - scoreJobFit(left));
    return (
      <div className="view-stack page-stack">
        <PageHero
          eyebrow="Opportunity Radar"
          title="Monitor the market like a recruiting analyst, not a manual searcher."
          copy="Search strategy defines what matters. Radar keeps scanning sources, scoring fit, and pushing the strongest roles into the system."
          metrics={[
            { label: "Search profiles", value: searchProfiles.length, note: "targeting strategies" },
            { label: "Live radars", value: monitors.length, note: "active monitors" },
            { label: "Matches", value: rankedJobs.length, note: "tracked roles" },
            { label: "Latest sweep", value: ingestionRuns[0]?.discovered_count ?? 0, note: "roles discovered" },
          ]}
          actions={<><button className="primary-button" type="button" onClick={() => navigate("integrations")}>Manage sources</button><button className="secondary-button" type="button" onClick={() => navigate("library")}>Open Tailoring Lab</button></>}
        />
        <div className="two-column-grid radar-grid">
          <Panel eyebrow="Search strategy" title="Role targeting and radar control">
            <form className="form-grid" onSubmit={saveSearch}>
              <Field label="Strategy name"><input value={searchForm.name} onChange={(e) => patch(setSearchForm, { name: e.target.value })} required /></Field>
              <Field label="Role families"><input value={searchForm.roles} onChange={(e) => patch(setSearchForm, { roles: e.target.value })} placeholder="DevOps, Cloud, Security" /></Field>
              <Field label="Keywords"><input value={searchForm.keywords} onChange={(e) => patch(setSearchForm, { keywords: e.target.value })} placeholder="AWS, Terraform, Kubernetes" /></Field>
              <div className="split-grid">
                <Field label="Locations"><input value={searchForm.locations} onChange={(e) => patch(setSearchForm, { locations: e.target.value })} placeholder="Melbourne, Remote" /></Field>
                <Field label="Daily cap"><input value={searchForm.dailyCap} onChange={(e) => patch(setSearchForm, { dailyCap: e.target.value })} /></Field>
              </div>
              <Field label="Sources"><input value={searchForm.sources} onChange={(e) => patch(setSearchForm, { sources: e.target.value })} /></Field>
              <Field label="Remote policy"><input value={searchForm.remotePolicy} onChange={(e) => patch(setSearchForm, { remotePolicy: e.target.value })} /></Field>
              <div className="card-actions"><button className="primary-button" type="submit">Save strategy</button><button className="secondary-button" type="button" onClick={() => editSearch()}>New</button>{activeSearchId ? <button className="secondary-button danger-button" type="button" onClick={() => void removeSearch(activeSearchId)}>Delete</button> : null}</div>
            </form>
            <form className="form-grid top-gap" onSubmit={saveMonitorConfig}>
              <Field label="Radar name"><input value={monitorForm.name} onChange={(e) => patch(setMonitorForm, { name: e.target.value })} required /></Field>
              <div className="split-grid">
                <Field label="Source"><select value={monitorForm.source} onChange={(e) => patch(setMonitorForm, { source: e.target.value })}>{sourceProviders.map((provider) => <option key={provider.key} value={provider.key}>{provider.name}</option>)}</select></Field>
                <Field label="Connection"><select value={monitorForm.connectionId} onChange={(e) => patch(setMonitorForm, { connectionId: e.target.value })}><option value="">Auto-select</option>{connections.filter((connection) => connection.category === "source" || connection.provider_key.endsWith("_account")).map((connection) => <option key={connection.id} value={connection.id}>{connection.name}</option>)}</select></Field>
              </div>
              <Field label="Search profile"><select value={monitorForm.searchProfileId} onChange={(e) => patch(setMonitorForm, { searchProfileId: e.target.value })}><option value="">Select a strategy</option>{searchProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select></Field>
              <div className="split-grid">
                <Field label="Cadence minutes"><input value={monitorForm.cadenceMinutes} onChange={(e) => patch(setMonitorForm, { cadenceMinutes: e.target.value })} /></Field>
                <Field label="Max results"><input value={monitorForm.maxResults} onChange={(e) => patch(setMonitorForm, { maxResults: e.target.value })} /></Field>
              </div>
              <Field label="Search URL override"><input value={monitorForm.searchUrl} onChange={(e) => patch(setMonitorForm, { searchUrl: e.target.value })} placeholder="Optional source-specific query URL" /></Field>
              <div className="checkbox-row"><input type="checkbox" checked={monitorForm.enabled} onChange={(e) => patch(setMonitorForm, { enabled: e.target.checked })} /><span>Radar enabled</span></div>
              <div className="card-actions"><button className="primary-button" type="submit">Save radar</button><button className="secondary-button" type="button" onClick={() => editMonitor()}>New</button>{activeMonitorId ? <button className="secondary-button" type="button" onClick={() => void runMonitor(activeMonitorId, false)}>Run now</button> : null}</div>
            </form>
          </Panel>
          <Panel eyebrow="Live opportunity feed" title="Highest-confidence matches right now">
            <div className="opportunity-feed">
              {rankedJobs.slice(0, 6).map((job) => (
                <div className="opportunity-card" key={job.id}>
                  <div className="priority-card-head">
                    <div>
                      <strong>{cleanCopy(job.title)}</strong>
                      <p>{cleanCopy(job.company)} | {cleanCopy(job.location ?? job.source)}</p>
                    </div>
                    <span className="score-chip score-chip-strong">{scoreJobFit(job)}</span>
                  </div>
                  <div className="tag-row">{job.classification_labels_json.slice(0, 4).map((label) => <span className="tag" key={label}>{cleanCopy(label)}</span>)}{job.work_mode ? <span className="tag tag-muted">{cleanCopy(job.work_mode)}</span> : null}</div>
                  <ul className="signal-list">{fitReasons(job).map((reason) => <li key={reason}>{reason}</li>)}</ul>
                  <div className="card-actions"><button className="secondary-button" type="button" onClick={() => openJobInLab(job)}>Send to Tailoring Lab</button>{job.source_url ? <a className="artifact-link" href={job.source_url} target="_blank" rel="noreferrer">Open source</a> : null}</div>
                </div>
              ))}
              {!rankedJobs.length ? <div className="empty-state">No roles have been pulled into the radar yet.</div> : null}
            </div>
          </Panel>
        </div>
        <div className="two-column-grid">
          <Panel eyebrow="Saved radars" title="What is actively watching the market">
            <div className="stack-list">{monitors.map((monitor) => <div className="timeline-item" key={monitor.id}><div className="timeline-head"><strong>{cleanCopy(monitor.name)}</strong><span className={monitor.enabled ? "pill pill-ok" : "pill pill-muted"}>{monitor.enabled ? "Live" : "Paused"}</span></div><p>{cleanCopy(monitor.source)} | every {monitor.cadence_minutes} minutes | {monitor.max_results} max results</p><div className="card-actions"><button className="secondary-button" type="button" onClick={() => editMonitor(monitor)}>Edit</button><button className="secondary-button" type="button" onClick={() => void runMonitor(monitor.id, false)}>Sweep now</button></div></div>)}{!monitors.length ? <div className="empty-state">No radar has been configured yet.</div> : null}</div>
          </Panel>
          <Panel eyebrow="Sweep history" title="Recent discovery runs">
            <div className="stack-list">{ingestionRuns.map((run) => <div className="timeline-item" key={run.id}><div className="timeline-head"><strong>{run.workflow_id ?? run.id}</strong><span className={tone(run.status)}>{run.status}</span></div><p>{run.discovered_count} discovered | {run.ingested_count} ingested | {run.pipeline_triggered_count} handed to the pipeline</p></div>)}{!ingestionRuns.length ? <div className="empty-state">Discovery history will appear here after the first sweep.</div> : null}</div>
          </Panel>
        </div>
      </div>
    );
  }

  function tailoringLabPage(): JSX.Element {
    const rankedJobs = [...jobs].sort((left, right) => scoreJobFit(right) - scoreJobFit(left));
    const selectedJob = jobs.find((job) => job.id === draftForm.jobId) ?? rankedJobs[0] ?? null;
    const selectedDraft = drafts.find((draft) => draft.id === previewDraftId) ?? drafts[0] ?? null;
    const selectedBundle = selectedDraft ? artifacts[selectedDraft.id] ?? null : null;
    const selectedPlan = plans.find((plan) => plan.generation_result_id === selectedDraft?.id) ?? null;
    const selectedPagePlan = (selectedDraft?.resume_json?.page_plan ?? {}) as Record<string, unknown>;
    return (
      <div className="view-stack page-stack">
        <PageHero
          eyebrow="Tailoring Lab"
          title="Inspect what the AI is changing before it becomes a real application."
          copy="This is where job requirements, grounded evidence, one-page composition, and AI reasoning come together in a single workspace."
          metrics={[
            { label: "Drafts", value: drafts.length, note: "tailored outputs" },
            { label: "Resume playbooks", value: resumeTemplates.length, note: "output structures" },
            { label: "Prompt playbooks", value: prompts.length, note: "strategy memory" },
            { label: "Preview ready", value: selectedDraft ? "Yes" : "No", note: "A4 draft inspection" },
          ]}
          actions={<><button className="primary-button" type="button" onClick={() => selectedJob && openJobInLab(selectedJob)}>Keep current job focused</button><button className="secondary-button" type="button" onClick={() => navigate("applications")}>Open Apply Queue</button></>}
        />
        <section className="lab-control-bar">
          <Field label="Job"><select value={draftForm.jobId} onChange={(e) => patch(setDraftForm, { jobId: e.target.value, planJobId: e.target.value })}><option value="">Select a job</option>{rankedJobs.map((job) => <option key={job.id} value={job.id}>{job.title} | {job.company}</option>)}</select></Field>
          <Field label="Resume playbook"><select value={draftForm.resumeTemplate} onChange={(e) => patch(setDraftForm, { resumeTemplate: e.target.value })}><option value="">Select</option>{resumeTemplates.map((template) => <option key={template.id} value={template.name}>{template.name}</option>)}</select></Field>
          <Field label="Cover playbook"><select value={draftForm.coverTemplate} onChange={(e) => patch(setDraftForm, { coverTemplate: e.target.value })}><option value="">Select</option>{coverTemplates.map((template) => <option key={template.id} value={template.name}>{template.name}</option>)}</select></Field>
          <div className="lab-actions"><button className="primary-button" type="button" onClick={() => void generateDraft({ preventDefault() {} } as FormEvent<HTMLFormElement>)}>Generate draft</button>{selectedDraft ? <button className="secondary-button" type="button" onClick={() => patch(setDraftForm, { generationResultId: selectedDraft.id, planJobId: selectedJob?.id ?? draftForm.planJobId })}>Keep this draft</button> : null}</div>
        </section>
        <div className="lab-grid">
          <Panel eyebrow="Job signal map" title={selectedJob ? cleanCopy(selectedJob.title) : "Choose a job"}>
            {selectedJob ? <div className="stack-list">
              <div className="status-row-card"><div><strong>{cleanCopy(selectedJob.company)}</strong><p>{cleanCopy(selectedJob.location ?? "Location not listed")} | {cleanCopy(selectedJob.work_mode ?? "Work mode unknown")}</p></div><span className="score-chip score-chip-strong">{scoreJobFit(selectedJob)}</span></div>
              <div className="tag-row">{selectedJob.classification_labels_json.map((label) => <span className="tag" key={label}>{cleanCopy(label)}</span>)}</div>
              <div className="reasoning-panel"><strong>Why the match looks strong</strong><ul className="signal-list">{fitReasons(selectedJob).map((reason) => <li key={reason}>{reason}</li>)}</ul></div>
              <div className="reasoning-panel"><strong>Risk watch</strong><div className="tag-row top-gap">{selectedJob.risk_flags_json.length ? selectedJob.risk_flags_json.map((risk) => <span className="tag tag-muted" key={risk}>{cleanCopy(risk)}</span>) : <span className="tag tag-muted">No explicit risk flags</span>}</div></div>
              {selectedJob.source_url ? <a className="artifact-link" href={selectedJob.source_url} target="_blank" rel="noreferrer">Open original posting</a> : null}
            </div> : <div className="empty-state">Choose a job from Opportunity Radar or the selector above.</div>}
          </Panel>
          <Panel eyebrow="One-page preview" title="What the system would send">
            <ResumePreview draft={selectedDraft} bundle={selectedBundle} />
          </Panel>
          <Panel eyebrow="AI reasoning" title="What changed and why">
            <div className="stack-list">
              <div className="status-row-card"><div><strong>Current draft</strong><p>{selectedDraft ? `Draft ${selectedDraft.id.slice(0, 8)} is active in the lab.` : 'Generate a draft to reveal the AI reasoning chain.'}</p></div><span className={selectedDraft ? tone(selectedDraft.compile_status) : 'pill pill-muted'}>{selectedDraft ? selectedDraft.compile_status : 'waiting'}</span></div>
              <div className="reasoning-panel"><strong>Grounding note</strong><p>{normalizeReasoning(selectedDraft?.grounding_notes, "The system will explain how it used memory, prompt playbooks, and job signals here.")}</p></div>
              <div className="reasoning-panel"><strong>Section balance</strong><ul className="signal-list"><li>Summary lines: {String(selectedPagePlan.summary_lines ?? '-')}</li><li>Experience lines: {String(selectedPagePlan.experience_lines ?? '-')}</li><li>Project lines: {String(selectedPagePlan.project_lines ?? '-')}</li><li>Line budget: {String(selectedPagePlan.line_budget ?? '1 page')}</li></ul></div>
              <div className="reasoning-panel"><strong>Next action</strong><p>{selectedPlan ? 'A plan already exists for this draft. Move to Apply Queue to control the execution state.' : 'Create an application plan once you are satisfied with the tailored resume.'}</p></div>
              <form className="form-grid" onSubmit={createPlan}>
                <Field label="Draft for queueing"><select value={draftForm.generationResultId} onChange={(e) => { patch(setDraftForm, { generationResultId: e.target.value }); setPreviewDraftId(e.target.value); }}><option value="">Select a draft</option>{drafts.map((draft) => <option key={draft.id} value={draft.id}>{draft.id.slice(0, 8)} | {draft.compile_status}</option>)}</select></Field>
                <button className="primary-button" type="submit">Create application plan</button>
              </form>
            </div>
          </Panel>
        </div>
        <Panel eyebrow="Draft gallery" title="Recent tailored variants">
          <div className="draft-gallery">
            {drafts.map((draft) => <div className="draft-card" key={draft.id}><div className="draft-head"><strong>{draft.id.slice(0, 8)}</strong><span className={tone(draft.compile_status)}>{draft.compile_status}</span></div><p>{normalizeReasoning(draft.grounding_notes, "Grounded from the uploaded profile memory and active playbooks.")}</p><div className="artifact-row">{(artifacts[draft.id]?.artifacts ?? []).filter((artifact) => artifact.available && artifact.url).map((artifact) => <a className="artifact-link" href={artifactUrl(String(artifact.url))} target="_blank" rel="noreferrer" key={artifact.kind}>{artifact.label}</a>)}</div><div className="card-actions"><button className="secondary-button" type="button" onClick={() => openDraftInLab(draft.id)}>Inspect</button></div></div>)}
            {!drafts.length ? <div className="empty-state">No tailored drafts yet. Generate the first one from this lab.</div> : null}
          </div>
        </Panel>
      </div>
    );
  }
  function applyQueuePage(): JSX.Element {
    const reviewPlans = plans.filter((plan) => queueBucket(plan) === "review");
    const readyPlans = plans.filter((plan) => queueBucket(plan) === "ready");
    const movingPlans = plans.filter((plan) => queueBucket(plan) === "moving");
    return (
      <div className="view-stack page-stack">
        <PageHero
          eyebrow="Apply Queue"
          title="Calm execution matters more than raw automation."
          copy="This queue makes the current state of every application obvious: what is waiting for review, what is ready to move, and what is already in motion."
          metrics={[
            { label: "Review needed", value: reviewPlans.length, note: "human checkpoints" },
            { label: "Ready to send", value: readyPlans.length, note: "approved queue items" },
            { label: "In motion", value: movingPlans.length, note: "live runs" },
            { label: "Submitted history", value: runs.length, note: "execution records" },
          ]}
          actions={<><button className="primary-button" type="button" onClick={() => navigate("library")}>Open Tailoring Lab</button><button className="secondary-button" type="button" onClick={() => navigate("insights")}>Open Learning Loop</button></>}
        />
        <div className="queue-grid">
          <Panel eyebrow="Review lane" title="Needs review">
            <div className="stack-list">{reviewPlans.map((plan) => { const job = getPlanJob(plan); const draft = getPlanDraft(plan); return <div className="queue-card" key={plan.id}><div className="timeline-head"><strong>{job ? cleanCopy(job.title) : `Plan ${plan.id.slice(0, 8)}`}</strong><span className={tone(plan.approval_state)}>{plan.approval_state}</span></div><p>{job ? cleanCopy(job.company) : cleanCopy(plan.source_adapter)}</p><div className="tag-row top-gap">{plan.risk_reasons_json.map((reason) => <span className="tag tag-muted" key={reason}>{cleanCopy(reason)}</span>)}</div><div className="card-actions">{draft ? <button className="secondary-button" type="button" onClick={() => openDraftInLab(draft.id)}>Review draft</button> : null}</div></div>; })}{!reviewPlans.length ? <div className="empty-state">Nothing is blocked in review.</div> : null}</div>
          </Panel>
          <Panel eyebrow="Ready lane" title="Ready to apply">
            <div className="stack-list">{readyPlans.map((plan) => { const job = getPlanJob(plan); const draft = getPlanDraft(plan); return <div className="queue-card" key={plan.id}><div className="timeline-head"><strong>{job ? cleanCopy(job.title) : `Plan ${plan.id.slice(0, 8)}`}</strong><span className={tone(plan.mode)}>{plan.mode}</span></div><p>{job ? cleanCopy(job.company) : cleanCopy(plan.source_adapter)}</p><p>{cleanCopy(plan.source_adapter)} | {cleanCopy(plan.terminal_status)}</p><div className="card-actions"><button className="primary-button" type="button" onClick={() => void startRun(plan.id)}>Start run</button>{draft ? <button className="secondary-button" type="button" onClick={() => openDraftInLab(draft.id)}>Preview resume</button> : null}</div></div>; })}{!readyPlans.length ? <div className="empty-state">No approved plans are waiting to launch.</div> : null}</div>
          </Panel>
          <Panel eyebrow="In motion" title="Live execution">
            <div className="stack-list">{movingPlans.map((plan) => { const job = getPlanJob(plan); const run = getPlanRun(plan); return <div className="queue-card" key={plan.id}><div className="timeline-head"><strong>{job ? cleanCopy(job.title) : `Plan ${plan.id.slice(0, 8)}`}</strong><span className={tone(run?.status ?? plan.terminal_status)}>{run?.status ?? plan.terminal_status}</span></div><p>{job ? cleanCopy(job.company) : cleanCopy(plan.source_adapter)}</p><p>{run ? `${run.execution_log_json.length} execution steps logged.` : 'Waiting for run telemetry.'}</p></div>; })}{!movingPlans.length ? <div className="empty-state">No application is actively moving right now.</div> : null}</div>
          </Panel>
        </div>
        <Panel eyebrow="Submission log" title="Recent application activity">
          <div className="stack-list">{runs.map((run) => <div className="timeline-item" key={run.id}><div className="timeline-head"><strong>Run {run.id.slice(0, 8)}</strong><span className={tone(run.status)}>{run.status}</span></div><p>{run.execution_log_json.length} steps | {(run.uploaded_artifacts_json ?? []).length} uploaded artifacts</p></div>)}{!runs.length ? <div className="empty-state">Execution history appears here once the queue starts moving.</div> : null}</div>
        </Panel>
      </div>
    );
  }

  function learningLoopPage(): JSX.Element {
    return (
      <div className="view-stack page-stack">
        <PageHero
          eyebrow="Learning Loop"
          title="A job system only becomes intelligent if it learns from outcomes."
          copy="This area tracks what converts, what underperforms, and which playbooks are genuinely improving the pipeline over time."
          metrics={[
            { label: "Outcomes", value: outcomes.length, note: "recorded responses" },
            { label: "Prompt signals", value: promptPerf.length, note: "playbook scoring" },
            { label: "Resume signals", value: resumeScores.length, note: "variant scoring" },
            { label: "Notifications", value: notifyEvents.length, note: "delivery history" },
          ]}
          actions={<><button className="primary-button" type="button" onClick={() => navigate("applications")}>Open Apply Queue</button><button className="secondary-button" type="button" onClick={() => navigate("studio")}>Open Playbooks</button></>}
        />
        <div className="two-column-grid">
          <Panel eyebrow="Feedback capture" title="Record real outcomes">
            <form className="form-grid" onSubmit={saveOutcome}>
              <Field label="Application plan"><select value={outcomeForm.applicationPlanId} onChange={(e) => patch(setOutcomeForm, { applicationPlanId: e.target.value })}><option value="">Select a plan</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.id.slice(0, 8)} | {plan.mode}</option>)}</select></Field>
              <Field label="Application run"><select value={outcomeForm.applicationRunId} onChange={(e) => patch(setOutcomeForm, { applicationRunId: e.target.value })}><option value="">None</option>{runs.map((run) => <option key={run.id} value={run.id}>{run.id.slice(0, 8)}</option>)}</select></Field>
              <div className="split-grid">
                <Field label="Response type"><select value={outcomeForm.responseType} onChange={(e) => patch(setOutcomeForm, { responseType: e.target.value })}><option value="no_response">No response</option><option value="reject">Rejected</option><option value="interview">Interview</option></select></Field>
                <Field label="Response time days"><input value={outcomeForm.responseTimeDays} onChange={(e) => patch(setOutcomeForm, { responseTimeDays: e.target.value })} /></Field>
              </div>
              <div className="checkbox-row"><input type="checkbox" checked={outcomeForm.interview} onChange={(e) => patch(setOutcomeForm, { interview: e.target.checked })} /><span>Interview outcome</span></div>
              <Field label="Notes"><textarea value={outcomeForm.notes} onChange={(e) => patch(setOutcomeForm, { notes: e.target.value })} /></Field>
              <button className="primary-button" type="submit">Record outcome</button>
            </form>
          </Panel>
          <Panel eyebrow="Delivery" title="Notification and operator feedback">
            <form className="form-grid" onSubmit={saveNotifications}>
              <div className="checkbox-row"><input type="checkbox" checked={notifyForm.emailEnabled} onChange={(e) => patch(setNotifyForm, { emailEnabled: e.target.checked })} /><span>Email notifications</span></div>
              <Field label="Email target"><input value={notifyForm.emailTarget} onChange={(e) => patch(setNotifyForm, { emailTarget: e.target.value })} /></Field>
              <div className="checkbox-row"><input type="checkbox" checked={notifyForm.slackEnabled} onChange={(e) => patch(setNotifyForm, { slackEnabled: e.target.checked })} /><span>Slack notifications</span></div>
              <Field label="Slack target"><input value={notifyForm.slackTarget} onChange={(e) => patch(setNotifyForm, { slackTarget: e.target.value })} /></Field>
              <button className="secondary-button" type="submit">Save delivery settings</button>
            </form>
            <form className="form-grid top-gap" onSubmit={testNotification}>
              <div className="split-grid">
                <Field label="Test channel"><select value={notifyForm.testChannel} onChange={(e) => patch(setNotifyForm, { testChannel: e.target.value })}><option value="dashboard">Dashboard</option><option value="email">Email</option><option value="slack">Slack</option></select></Field>
                <Field label="Subject"><input value={notifyForm.testSubject} onChange={(e) => patch(setNotifyForm, { testSubject: e.target.value })} /></Field>
              </div>
              <Field label="Body"><textarea value={notifyForm.testBody} onChange={(e) => patch(setNotifyForm, { testBody: e.target.value })} /></Field>
              <button className="secondary-button" type="submit">Send test notification</button>
            </form>
          </Panel>
        </div>
        <div className="three-column-grid">
          <Panel eyebrow="Prompt performance" title="Which playbooks convert better">
            <div className="stack-list">{promptPerf.map((item) => <div className="timeline-item" key={item.id}><div className="timeline-head"><strong>{cleanCopy(item.role_tag || 'General')}</strong><span className="pill pill-ok">{(item.success_rate * 100).toFixed(0)}%</span></div><p>{item.applications_count} applications | {item.interviews_count} interviews</p></div>)}{!promptPerf.length ? <div className="empty-state">Prompt performance appears after outcomes are recorded.</div> : null}</div>
          </Panel>
          <Panel eyebrow="Resume scoring" title="Which variants are holding up">
            <div className="stack-list">{resumeScores.map((score) => <div className="timeline-item" key={score.id}><div className="timeline-head"><strong>{cleanCopy(score.role_tag ?? 'General')}</strong><span className="pill pill-ok">{score.score.toFixed(2)}</span></div><p>Coverage {score.keyword_coverage.toFixed(2)} | Hallucination risk {score.hallucination_risk.toFixed(2)}</p></div>)}{!resumeScores.length ? <div className="empty-state">Variant scoring appears as the system gathers more feedback.</div> : null}</div>
          </Panel>
          <Panel eyebrow="Notification history" title="Signals sent to the operator">
            <div className="stack-list">{notifyEvents.map((event) => <div className="timeline-item" key={event.id}><div className="timeline-head"><strong>{cleanCopy(event.subject)}</strong><span className={tone(event.delivery_status)}>{event.delivery_status}</span></div><p>{cleanCopy(event.channel)} | {cleanCopy(event.body)}</p></div>)}{!notifyEvents.length ? <div className="empty-state">No notification history yet.</div> : null}</div>
          </Panel>
        </div>
      </div>
    );
  }

  function playbooksPage(): JSX.Element {
    return (
      <div className="view-stack page-stack">
        <PageHero
          eyebrow="Playbooks"
          title="Strategy lives here: prompts, templates, and the rules that shape the output."
          copy="Advanced users should feel power here. Playbooks decide how the system thinks, how the resume looks, and what rules it follows before anything is sent."
          metrics={[
            { label: "Prompt playbooks", value: prompts.length, note: "strategy memory" },
            { label: "Resume templates", value: resumeTemplates.length, note: "layout variants" },
            { label: "Cover templates", value: coverTemplates.length, note: "narrative variants" },
            { label: "Drafts using playbooks", value: drafts.length, note: "current outputs" },
          ]}
          actions={<><button className="primary-button" type="button" onClick={() => navigate("library")}>Open Tailoring Lab</button><button className="secondary-button" type="button" onClick={() => navigate("insights")}>Open Learning Loop</button></>}
        />
        <div className="two-column-grid">
          <Panel eyebrow="Prompt playbooks" title="How the system writes and prioritizes">
            <form className="form-grid" onSubmit={savePromptVersion}>
              <Field label="Playbook name"><input value={promptForm.name} onChange={(e) => patch(setPromptForm, { name: e.target.value })} required /></Field>
              <Field label="Role tags"><input value={promptForm.roleTags} onChange={(e) => patch(setPromptForm, { roleTags: e.target.value })} /></Field>
              <Field label="Prompt text"><textarea value={promptForm.promptText} onChange={(e) => patch(setPromptForm, { promptText: e.target.value })} required /></Field>
              <div className="split-grid"><Field label="Temperature"><input value={promptForm.temperature} onChange={(e) => patch(setPromptForm, { temperature: e.target.value })} /></Field><Field label="Success score"><input value={promptForm.successRate} onChange={(e) => patch(setPromptForm, { successRate: e.target.value })} /></Field></div>
              <div className="card-actions"><button className="primary-button" type="submit">{activePromptId ? 'Update playbook' : 'Save playbook'}</button><button className="secondary-button" type="button" onClick={() => editPrompt()}>New</button>{activePromptId ? <button className="secondary-button danger-button" type="button" onClick={() => void removePrompt(activePromptId)}>Delete</button> : null}</div>
            </form>
            <div className="stack-list top-gap">{prompts.map((prompt) => <div className="data-card" key={prompt.id}><div className="data-card-row"><strong>{cleanCopy(prompt.name)}</strong><span className="pill pill-muted">{prompt.success_rate_metric.toFixed(2)}</span></div><div className="tag-row top-gap">{prompt.role_tags_json.map((tag) => <span className="tag" key={tag}>{cleanCopy(tag)}</span>)}</div><p className="inline-note top-gap">{cleanCopy(prompt.prompt_text.slice(0, 180))}{prompt.prompt_text.length > 180 ? '...' : ''}</p><div className="card-actions"><button className="secondary-button" type="button" onClick={() => editPrompt(prompt)}>Edit</button></div></div>)}{!prompts.length ? <div className="empty-state">No prompt playbooks yet.</div> : null}</div>
          </Panel>
          <Panel eyebrow="Output playbooks" title="How the system lays out final documents">
            <form className="form-grid" onSubmit={saveTemplateVariant}>
              <Field label="Template name"><input value={templateForm.name} onChange={(e) => patch(setTemplateForm, { name: e.target.value })} required /></Field>
              <Field label="Document kind"><select value={templateForm.documentKind} onChange={(e) => patch(setTemplateForm, { documentKind: e.target.value })}><option value="resume">Resume</option><option value="cover_letter">Cover letter</option></select></Field>
              <Field label="Template path"><input value={templateForm.templatePath} onChange={(e) => patch(setTemplateForm, { templatePath: e.target.value })} placeholder="D:\\...\\resume.tex.j2" /></Field>
              <Field label="Upload file"><input type="file" onChange={(e) => patch(setTemplateForm, { file: e.target.files?.[0] ?? null })} /></Field>
              <div className="card-actions"><button className="primary-button" type="submit">{activeTemplateId ? 'Update template' : 'Save template'}</button><button className="secondary-button" type="button" onClick={() => editTemplate()}>New</button>{activeTemplateId ? <button className="secondary-button danger-button" type="button" onClick={() => void removeTemplate(activeTemplateId)}>Delete</button> : null}</div>
            </form>
            <div className="stack-list top-gap">{templates.map((template) => <div className="data-card" key={template.id}><div className="data-card-row"><strong>{cleanCopy(template.name)}</strong><span className="pill pill-ok">{kind(template.document_kind)}</span></div><p>{cleanCopy(template.template_path)}</p><div className="card-actions"><button className="secondary-button" type="button" onClick={() => editTemplate(template)}>Edit</button></div></div>)}{!templates.length ? <div className="empty-state">No output playbooks yet.</div> : null}</div>
          </Panel>
        </div>
      </div>
    );
  }

  function integrationsPage(): JSX.Element {
    const googleClientId = String(connectionForm.settings.client_id ?? googleConnection?.settings_json?.client_id ?? "");
    const googleLooksValid = !googleClientId || googleClientId.includes(".apps.googleusercontent.com");
    const groups = [
      { title: "Workspace sign-in", items: workspaceProviders },
      { title: "Job board accounts", items: jobBoardAccountProviders },
      { title: "Opportunity sources", items: sourceProviders },
      { title: "Notifications", items: notificationProviders },
    ].filter((group) => group.items.length > 0);
    const directSourceProvider = Boolean(selectedProvider && selectedProvider.category === "source" && ["public_search", "search_url_optional"].includes(selectedProvider.auth_type));
    const visibleFields = (selectedProvider?.fields ?? []).filter((field) => !(selectedProvider?.key === "google_oauth" && field.key === "redirect_uri"));
    return (
      <div className="view-stack page-stack">
        <PageHero
          eyebrow="Integrations"
          title="Connect identity, job sources, and delivery channels without touching infrastructure."
          copy="Integrations should feel operational, not technical. Each provider shows what the agents can do with it, whether the session is healthy, and what still needs your approval."
          metrics={[
            { label: "Providers", value: providers.length, note: "available systems" },
            { label: "Connected", value: connections.length, note: "saved credentials" },
            { label: "Sessions", value: connections.filter((connection) => connection.has_session_state).length, note: "browser-backed" },
            { label: "Google", value: auth.google_ready ? "Ready" : "Needs setup", note: auth.authenticated ? "workspace unlocked" : "sign-in pending" },
          ]}
          actions={<><button className="primary-button" type="button" onClick={() => selectedProvider?.key === "google_oauth" ? void googleSignIn() : navigate("monitoring")}>{selectedProvider?.key === "google_oauth" ? "Sign in with Google" : "Open Opportunity Radar"}</button><button className="secondary-button" type="button" onClick={() => navigate("overview")}>Back to Command Center</button></>}
        />
        <div className="two-column-grid">
          <div className="stack-list">
            {groups.map((group) => (
              <Panel eyebrow="Provider map" title={group.title} key={group.title}>
                <div className="priority-feed">
                  {group.items.map((provider) => {
                    const connection = connections.find((item) => item.provider_key === provider.key) ?? null;
                    const directSource = provider.category === "source" && ["public_search", "search_url_optional"].includes(provider.auth_type);
                    return (
                      <button className={(selectedProvider?.key === provider.key ? "priority-card priority-card-active" : "priority-card")} type="button" key={provider.key} onClick={() => selectProvider(provider.key, connection?.id ?? null)}>
                        <div className="priority-card-head">
                          <div>
                            <strong>{provider.name}</strong>
                            <p>{cleanCopy(provider.description)}</p>
                          </div>
                          <span className={directSource ? "pill pill-ok" : connection ? tone(connection.status) : "pill pill-muted"}>{directSource ? "Built in" : connection?.status ?? "Not connected"}</span>
                        </div>
                        <div className="tag-row top-gap">
                          {provider.capabilities.slice(0, 4).map((capability) => <span className="tag" key={capability}>{cleanCopy(capability)}</span>)}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </Panel>
            ))}
          </div>
          <div className="stack-list">
            <Panel eyebrow="Selected integration" title={selectedProvider?.name ?? "Choose a provider"}>
              {selectedProvider ? <>
                <div className="reasoning-panel">
                  <strong>What the agents can do with this</strong>
                  <p>{cleanCopy(selectedProvider.description)}</p>
                  <div className="tag-row top-gap">{selectedProvider.capabilities.map((capability) => <span className="tag" key={capability}>{cleanCopy(capability)}</span>)}</div>
                </div>
                {selectedProvider.key === "google_oauth" ? <div className="reasoning-panel top-gap">
                  <strong>Required Google callback URI</strong>
                  <p className="callback-uri">{REQUIRED_GOOGLE_REDIRECT_URI}</p>
                  <div className="card-actions">
                    <button className="secondary-button" type="button" onClick={() => void copyText(REQUIRED_GOOGLE_REDIRECT_URI).then(() => setBanner({ tone: "success", message: "Google callback URI copied." }))}>Copy callback</button>
                    <button className="primary-button" type="button" onClick={() => void googleSignIn()}>Sign in with Google</button>
                  </div>
                  {!googleLooksValid ? <div className="banner banner-error top-gap">The saved Google Client ID does not look like a valid web application client. It should end with .apps.googleusercontent.com.</div> : null}
                </div> : null}
                {directSourceProvider ? <div className="reasoning-panel top-gap">
                  <strong>No separate sign-in is required</strong>
                  <p>{selectedProvider.name} is already available inside Opportunity Radar. Attach it to a search strategy when you want the Scout agent to start scanning.</p>
                  <div className="card-actions">
                    <button className="primary-button" type="button" onClick={() => navigate("monitoring")}>Open Opportunity Radar</button>
                    {selectedProvider.launch_url ? <a className="artifact-link" href={selectedProvider.launch_url} target="_blank" rel="noreferrer">Open provider</a> : null}
                  </div>
                </div> : <>
                  <form className="form-grid top-gap" onSubmit={saveConnection}>
                    <Field label="Connection name"><input value={connectionForm.name} onChange={(e) => patch(setConnectionForm, { name: e.target.value })} required /></Field>
                    <Field label="Login hint" hint="Optional. Helps you remember which account is connected."><input value={connectionForm.loginHint} onChange={(e) => patch(setConnectionForm, { loginHint: e.target.value })} placeholder={selectedProvider.auth_type === "browser_session" ? "your-login@example.com" : "Optional"} /></Field>
                    {visibleFields.map((field) => (
                      <Field key={field.key} label={field.label} hint={field.help_text ?? undefined}>
                        <input
                          type={field.input_type === "password" ? "password" : field.input_type === "number" ? "number" : field.input_type === "email" ? "email" : field.input_type === "url" ? "url" : "text"}
                          value={connectionForm.settings[field.key] ?? ""}
                          onChange={(e) => patch(setConnectionForm, { settings: { ...connectionForm.settings, [field.key]: e.target.value } })}
                          placeholder={field.placeholder ?? undefined}
                        />
                      </Field>
                    ))}
                    <div className="card-actions">
                      <button className="primary-button" type="submit">{activeConnectionId ? "Save changes" : "Create connection"}</button>
                      {selectedProvider.key === "google_oauth" ? <button className="secondary-button" type="button" onClick={() => void googleSignIn()}>Sign in now</button> : selectedProvider.auth_type === "browser_session" ? <button className="secondary-button" type="button" onClick={() => void connectProvider()} disabled={!activeConnectionId}>Start guided sign-in</button> : null}
                      {activeConnectionId ? <button className="secondary-button danger-button" type="button" onClick={() => void removeConnection(activeConnectionId)}>Delete</button> : null}
                    </div>
                  </form>
                  {selectedProvider.auth_type === "browser_session" ? <div className="stack-list top-gap">
                    <div className="status-row-card">
                      <div>
                        <strong>Guided job-board sign-in</strong>
                        <p>The platform will try to open the correct browser flow on this machine. If the host bridge is unavailable, it will fall back to a helper command automatically.</p>
                      </div>
                      <span className={browserCapture?.has_session_state ? "pill pill-ok" : browserCapture?.browser_reachable ? "pill pill-warn" : "pill pill-muted"}>{browserCapture?.has_session_state ? "Session ready" : browserCapture?.browser_reachable ? "Browser detected" : "Waiting"}</span>
                    </div>
                    {browserCapture?.helper_command ? <div className="command-card">
                      <p className="inline-note">Fallback helper command</p>
                      <code className="command-block">{browserCapture.helper_command}</code>
                      <div className="card-actions">
                        <button className="secondary-button" type="button" onClick={() => void copyBrowserHelperCommand()}>Copy command</button>
                        {browserCapture.login_url ? <a className="artifact-link" href={browserCapture.login_url} target="_blank" rel="noreferrer">Open login page</a> : null}
                      </div>
                    </div> : null}
                    <div className="card-actions">
                      <button className="secondary-button" type="button" onClick={() => void connectProvider()} disabled={!activeConnectionId}>Start sign-in</button>
                      <button className="secondary-button" type="button" onClick={() => void refreshBrowserCaptureState()} disabled={!activeConnectionId}>Check status</button>
                      <button className="primary-button" type="button" onClick={() => void finalizeBrowserCaptureState()} disabled={!activeConnectionId}>Finish connection</button>
                      {browserCapture ? <button className="secondary-button danger-button" type="button" onClick={() => void cancelBrowserCaptureState()}>Cancel</button> : null}
                    </div>
                    {browserCapture ? <div className="banner banner-neutral">
                      <strong>{browserCapture.has_session_state ? "Account connected" : "Sign-in status"}</strong>
                      {typeof browserCapture.details?.launch_message === "string" && browserCapture.details.launch_message ? <p className="inline-note top-gap">{cleanCopy(String(browserCapture.details.launch_message))}</p> : null}
                      <ul className="signal-list top-gap">{browserCapture.instructions.map((line) => <li key={line}>{cleanCopy(line)}</li>)}</ul>
                    </div> : null}
                  </div> : null}
                </>}
                {connectNotice ? <div className="banner banner-neutral top-gap"><strong>{connectNotice.title}</strong><ul className="signal-list top-gap">{connectNotice.lines.map((line) => <li key={line}>{cleanCopy(line)}</li>)}</ul>{connectNotice.url ? <div className="card-actions"><a className="artifact-link" href={connectNotice.url} target="_blank" rel="noreferrer">Open flow</a></div> : null}</div> : null}
              </> : <div className="empty-state">Choose an integration from the left to configure it.</div>}
            </Panel>
            <Panel eyebrow="Connection library" title="Saved system access">
              <div className="stack-list">
                {connections.map((connection) => (
                  <div className="data-card" key={connection.id}>
                    <div className="data-card-row"><strong>{cleanCopy(connection.name)}</strong><span className={tone(connection.status)}>{connection.status}</span></div>
                    <p>{cleanCopy(connection.provider_key)} | {cleanCopy(connection.login_hint ?? "No login hint saved")}</p>
                    <div className="tag-row top-gap">
                      {connection.has_session_state ? <span className="tag">session ready</span> : null}
                      {connection.secret_fields_present.map((field) => <span className="tag tag-muted" key={field}>{cleanCopy(field)}</span>)}
                    </div>
                    <div className="card-actions"><button className="secondary-button" type="button" onClick={() => selectProvider(connection.provider_key, connection.id)}>Open</button></div>
                  </div>
                ))}
                {!connections.length ? <div className="empty-state">No saved integrations yet. Public sources are already available in Opportunity Radar.</div> : null}
              </div>
            </Panel>
          </div>
        </div>
      </div>
    );
  }

  function workspacePage(): JSX.Element {
    if (view === "overview") return commandCenterPage();
    if (view === "knowledge") return profileMemoryPage();
    if (view === "monitoring") return opportunityRadarPage();
    if (view === "library") return tailoringLabPage();
    if (view === "applications") return applyQueuePage();
    if (view === "insights") return learningLoopPage();
    if (view === "studio") return playbooksPage();
    return integrationsPage();
  }

  if (view === "landing") return landingPage();

  return (
    <div className="cockpit-shell dark-shell">
      {busy ? <div className="busy-overlay" aria-live="polite"><div className="busy-card"><div className="busy-spinner" aria-hidden="true" /><strong>{busy.title}</strong><p>{busy.detail}</p></div></div> : null}
      <aside className="mission-rail">
        <div className="mission-brand">
          <p className="brand-kicker">JobOps</p>
          <h1>AI Career Operations</h1>
          <p className="brand-copy">A calm cockpit for teaching, monitoring, tailoring, reviewing, and learning.</p>
        </div>
        <div className="mission-nav">
          {nav.map((item) => <button key={item.key} className={view === item.key ? "mission-nav-item mission-nav-item-active" : "mission-nav-item"} type="button" onClick={() => navigate(item.key)}><span className="mission-glyph">{item.glyph}</span><span>{item.label}</span></button>)}
        </div>
        <div className="mission-status">
          <div className="status-row-card"><div><strong>Workspace sign-in</strong><p>{auth.user?.email ?? "No active session"}</p></div><span className={auth.google_ready ? "pill pill-ok" : "pill pill-warn"}>{auth.google_ready ? "Ready" : "Setup"}</span></div>
          <div className="status-row-card"><div><strong>Pipeline state</strong><p>{busy?.detail ?? (apiOnline ? "Idle and waiting for your next move." : "API offline - waiting for backend recovery.")}</p></div><span className={busy ? "pill pill-warn" : apiOnline ? "pill pill-muted" : "pill pill-warn"}>{busy ? "Busy" : apiOnline ? "Idle" : "Offline"}</span></div>
          <div className="card-actions">
            {auth.authenticated ? <button className="secondary-button full-width" type="button" onClick={() => void signOut()}>Sign out</button> : <button className="primary-button full-width" type="button" onClick={() => void googleSignIn()}>Sign in with Google</button>}
          </div>
        </div>
      </aside>
      <main className="cockpit-main">
        {loading ? <div className="banner banner-neutral">Loading the cockpit...</div> : null}
        {!apiOnline ? <div className="banner banner-error">The backend API on localhost:8013 is offline. Restart the platform services and then refresh the cockpit.</div> : null}
        {banner ? <div className={`banner ${banner.tone === "success" ? "banner-success" : banner.tone === "error" ? "banner-error" : "banner-neutral"}`}>{banner.message}</div> : null}
        {workspacePage()}
      </main>
      <AgentRail />
    </div>
  );
}
