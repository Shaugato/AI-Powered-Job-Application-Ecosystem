import type {
  ApplicationOutcome,
  ApplicationPlan,
  ApplicationRun,
  AuthStatus,
  BaseProfile,
  CandidateMemory,
  CorpusDocumentSummary,
  CorpusImportRequest,
  CorpusImportResponse,
  DashboardOverview,
  EvidenceFragment,
  GenerationArtifactBundle,
  GenerationResult,
  IngestionRun,
  IngestionSourceConfig,
  IntegrationBrowserCapture,
  IntegrationConnectResponse,
  IntegrationConnection,
  IntegrationProvider,
  JobCreateRequest,
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


const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8013/api/v1";

function sessionToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("jobops.auth.token");
}

function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const token = sessionToken();
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  return parseResponse<T>(await fetch(`${API_BASE}${path}`, { method: "POST", headers: authHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(payload) }));
}
async function putJson<T>(path: string, payload: unknown): Promise<T> {
  return parseResponse<T>(await fetch(`${API_BASE}${path}`, { method: "PUT", headers: authHeaders({ "Content-Type": "application/json" }), body: JSON.stringify(payload) }));
}
async function deleteRequest<T>(path: string): Promise<T> {
  return parseResponse<T>(await fetch(`${API_BASE}${path}`, { method: "DELETE", headers: authHeaders() }));
}
async function postForm<T>(path: string, formData: FormData): Promise<T> {
  return parseResponse<T>(await fetch(`${API_BASE}${path}`, { method: "POST", headers: authHeaders(), body: formData }));
}

export async function fetchPlatformHealth(): Promise<{ status: string }> { return parseResponse<{ status: string }>(await fetch(`${API_BASE}/health`, { headers: authHeaders() })); }
export async function fetchDashboardOverview(): Promise<DashboardOverview> { return parseResponse<DashboardOverview>(await fetch(`${API_BASE}/dashboard/overview`, { headers: authHeaders() })); }
export async function fetchBaseProfiles(): Promise<BaseProfile[]> { return parseResponse<BaseProfile[]>(await fetch(`${API_BASE}/base-profiles`, { headers: authHeaders() })); }
export async function fetchCandidateMemory(profileId?: string): Promise<CandidateMemory> {
  const suffix = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : "";
  return parseResponse<CandidateMemory>(await fetch(`${API_BASE}/corpus/memory${suffix}`, { headers: authHeaders() }));
}
export function syncCandidateMemory(profileId?: string, overwriteSummary = false): Promise<{ status: string; profile_id: string }> {
  return postJson("/corpus/memory/sync", { profile_id: profileId ?? null, overwrite_summary: overwriteSummary });
}
export async function fetchPrompts(): Promise<PromptVersion[]> { return parseResponse<PromptVersion[]>(await fetch(`${API_BASE}/prompts`, { headers: authHeaders() })); }
export async function fetchNotificationPreferences(): Promise<NotificationPreference[]> { return parseResponse<NotificationPreference[]>(await fetch(`${API_BASE}/notifications/preferences`, { headers: authHeaders() })); }
export async function fetchNotificationEvents(): Promise<NotificationEvent[]> { return parseResponse<NotificationEvent[]>(await fetch(`${API_BASE}/notifications/events`, { headers: authHeaders() })); }
export async function fetchTemplates(): Promise<TemplateVariant[]> { return parseResponse<TemplateVariant[]>(await fetch(`${API_BASE}/generation/templates`, { headers: authHeaders() })); }
export async function fetchJobs(): Promise<JobPosting[]> { return parseResponse<JobPosting[]>(await fetch(`${API_BASE}/jobs`, { headers: authHeaders() })); }
export async function fetchDrafts(): Promise<GenerationResult[]> { return parseResponse<GenerationResult[]>(await fetch(`${API_BASE}/generation/results`, { headers: authHeaders() })); }
export async function fetchArtifactBundle(generationResultId: string): Promise<GenerationArtifactBundle> { return parseResponse<GenerationArtifactBundle>(await fetch(`${API_BASE}/artifacts/generation-results/${encodeURIComponent(generationResultId)}`, { headers: authHeaders() })); }
export async function fetchApplicationPlans(): Promise<ApplicationPlan[]> { return parseResponse<ApplicationPlan[]>(await fetch(`${API_BASE}/applications/plans`, { headers: authHeaders() })); }
export async function fetchApplicationRuns(): Promise<ApplicationRun[]> { return parseResponse<ApplicationRun[]>(await fetch(`${API_BASE}/applications/runs`, { headers: authHeaders() })); }
export async function fetchPendingEvidence(): Promise<EvidenceFragment[]> { return parseResponse<EvidenceFragment[]>(await fetch(`${API_BASE}/corpus/evidence?truth_status=pending`, { headers: authHeaders() })); }
export async function fetchCorpusLibrary(): Promise<CorpusDocumentSummary[]> { return parseResponse<CorpusDocumentSummary[]>(await fetch(`${API_BASE}/corpus/library`, { headers: authHeaders() })); }
export async function fetchSearchProfiles(): Promise<SearchProfile[]> { return parseResponse<SearchProfile[]>(await fetch(`${API_BASE}/search-profiles`, { headers: authHeaders() })); }
export async function fetchIntegrationProviders(category?: string): Promise<IntegrationProvider[]> { const suffix = category ? `?category=${encodeURIComponent(category)}` : ""; return parseResponse<IntegrationProvider[]>(await fetch(`${API_BASE}/integrations/providers${suffix}`, { headers: authHeaders() })); }
export async function fetchIntegrationConnections(): Promise<IntegrationConnection[]> { return parseResponse<IntegrationConnection[]>(await fetch(`${API_BASE}/integrations/connections`, { headers: authHeaders() })); }
export async function fetchIngestionConfigs(): Promise<IngestionSourceConfig[]> { return parseResponse<IngestionSourceConfig[]>(await fetch(`${API_BASE}/ingestion/configs`, { headers: authHeaders() })); }
export async function fetchIngestionRuns(): Promise<IngestionRun[]> { return parseResponse<IngestionRun[]>(await fetch(`${API_BASE}/ingestion/runs`, { headers: authHeaders() })); }
export async function fetchLearningOutcomes(): Promise<ApplicationOutcome[]> { return parseResponse<ApplicationOutcome[]>(await fetch(`${API_BASE}/learning/outcomes`, { headers: authHeaders() })); }
export async function fetchPromptPerformance(): Promise<PromptPerformance[]> { return parseResponse<PromptPerformance[]>(await fetch(`${API_BASE}/learning/prompt-performance`, { headers: authHeaders() })); }
export async function fetchResumeScores(): Promise<ResumeVariantScore[]> { return parseResponse<ResumeVariantScore[]>(await fetch(`${API_BASE}/learning/resume-scores`, { headers: authHeaders() })); }

export function importCorpus(payload: CorpusImportRequest): Promise<WorkflowSubmission<CorpusImportResponse>> { return postJson("/corpus/ingest", payload); }
export async function fetchCorpusWorkflow(workflowId: string): Promise<WorkflowSubmission<CorpusImportResponse>> {
  return parseResponse<WorkflowSubmission<CorpusImportResponse>>(await fetch(`${API_BASE}/corpus/workflows/${encodeURIComponent(workflowId)}`, { headers: authHeaders() }));
}
export function uploadCorpusFiles(payload: { files: File[]; collectionName: string; roleHint: string[]; documentKind: string }): Promise<WorkflowSubmission<CorpusImportResponse>> {
  const form = new FormData();
  form.append("collection_name", payload.collectionName);
  form.append("role_hint", payload.roleHint.join(", "));
  form.append("document_kind", payload.documentKind);
  payload.files.forEach((file) => form.append("files", file));
  return postForm("/corpus/upload", form);
}
export function approveEvidence(fragmentId: string): Promise<unknown> { return postJson(`/corpus/evidence/${encodeURIComponent(fragmentId)}/approve`, { approved: true, reviewer_notes: "Approved from dashboard" }); }
export function approveSourceDocument(sourceDocument: string): Promise<{ source_document: string; updated_fragments: number; truth_status: string }> { return postJson("/corpus/documents/approve", { source_document: sourceDocument, approved: true, reviewer_notes: "Approved from dashboard" }); }

export function saveBaseProfile(payload: Omit<BaseProfile, "id">, profileId?: string): Promise<BaseProfile> { return profileId ? putJson(`/base-profiles/${encodeURIComponent(profileId)}`, payload) : postJson("/base-profiles", payload); }
export function deleteBaseProfile(profileId: string): Promise<{ status: string; id: string }> { return deleteRequest(`/base-profiles/${encodeURIComponent(profileId)}`); }

export function savePrompt(payload: { name: string; role_tags: string[]; prompt_text: string; temperature: number; success_rate_metric: number; last_used_at?: string | null }, promptId?: string): Promise<PromptVersion> { return promptId ? putJson(`/prompts/${encodeURIComponent(promptId)}`, payload) : postJson("/prompts", payload); }
export function deletePrompt(promptId: string): Promise<{ status: string; id: string }> { return deleteRequest(`/prompts/${encodeURIComponent(promptId)}`); }

export function saveNotificationPreference(payload: { channel: string; enabled: boolean; target?: string | null; metadata_json?: Record<string, unknown> }, ): Promise<NotificationPreference> { return postJson("/notifications/preferences", payload); }
export function sendTestNotification(payload: { channel: string; subject: string; body: string }): Promise<NotificationEvent> { return postJson("/notifications/test", payload); }

export function saveTemplate(payload: { name: string; document_kind: string; template_path: string; metadata_json?: Record<string, unknown> }, templateId?: string): Promise<TemplateVariant> { return templateId ? putJson(`/generation/templates/${encodeURIComponent(templateId)}`, payload) : postJson("/generation/templates", payload); }
export function deleteTemplate(templateId: string): Promise<{ status: string; id: string }> { return deleteRequest(`/generation/templates/${encodeURIComponent(templateId)}`); }
export function uploadTemplate(payload: { file: File; name: string; documentKind: string }): Promise<TemplateVariant> { const form = new FormData(); form.append("file", payload.file); form.append("name", payload.name); form.append("document_kind", payload.documentKind); return postForm("/generation/templates/upload", form); }

export function saveSearchProfile(payload: { name: string; roles: string[]; keywords: string[]; excluded_terms: string[]; locations: string[]; remote_policy: string; salary_floor?: number | null; source_allowlist: string[]; daily_cap: number; review_policy: string; schedule_window: Record<string, unknown> }, profileId?: string): Promise<SearchProfile> { return profileId ? putJson(`/search-profiles/${encodeURIComponent(profileId)}`, payload) : postJson("/search-profiles", payload); }
export function deleteSearchProfile(profileId: string): Promise<{ status: string; id: string }> { return deleteRequest(`/search-profiles/${encodeURIComponent(profileId)}`); }
export function saveIntegrationConnection(payload: { name: string; provider_key: string; login_hint?: string | null; settings_json?: Record<string, unknown>; metadata_json?: Record<string, unknown> | null }, connectionId?: string): Promise<IntegrationConnection> { return connectionId ? putJson(`/integrations/connections/${encodeURIComponent(connectionId)}`, payload) : postJson("/integrations/connections", payload); }
export function deleteIntegrationConnection(connectionId: string): Promise<{ status: string; id: string }> { return deleteRequest(`/integrations/connections/${encodeURIComponent(connectionId)}`); }
export function connectIntegrationConnection(connectionId: string): Promise<IntegrationConnectResponse> { return postJson(`/integrations/connections/${encodeURIComponent(connectionId)}/connect`, {}); }
export async function fetchIntegrationBrowserCapture(connectionId: string): Promise<IntegrationBrowserCapture> { return parseResponse<IntegrationBrowserCapture>(await fetch(`${API_BASE}/integrations/connections/${encodeURIComponent(connectionId)}/browser-capture`, { headers: authHeaders() })); }
export function finalizeIntegrationBrowserCapture(connectionId: string): Promise<IntegrationBrowserCapture> { return postJson(`/integrations/connections/${encodeURIComponent(connectionId)}/browser-capture/finalize`, {}); }
export function cancelIntegrationBrowserCapture(connectionId: string): Promise<IntegrationBrowserCapture> { return postJson(`/integrations/connections/${encodeURIComponent(connectionId)}/browser-capture/cancel`, {}); }

export function saveIngestionConfig(payload: { name: string; search_profile_id?: string | null; connection_id?: string | null; source: string; enabled: boolean; cadence_minutes: number; query_text?: string | null; location_override?: string | null; max_results: number; auto_start_pipeline: boolean; search_url?: string | null; metadata_json?: Record<string, unknown> | null }, configId?: string): Promise<IngestionSourceConfig> { return configId ? putJson(`/ingestion/configs/${encodeURIComponent(configId)}`, payload) : postJson("/ingestion/configs", payload); }
export function deleteIngestionConfig(configId: string): Promise<{ status: string; id: string }> { return deleteRequest(`/ingestion/configs/${encodeURIComponent(configId)}`); }
export function triggerIngestion(payload: { config_id: string; iterations: number; continuous: boolean }): Promise<{ mode: string; workflow_id: string; status: string; details: Record<string, unknown> }> { return postJson("/ingestion/trigger", payload); }

export function saveJob(payload: JobCreateRequest, jobId?: string): Promise<JobPosting> { return jobId ? putJson(`/jobs/${encodeURIComponent(jobId)}`, payload) : postJson("/jobs", payload); }
export function deleteJob(jobId: string): Promise<{ status: string; id: string }> { return deleteRequest(`/jobs/${encodeURIComponent(jobId)}`); }
export function startJobPipeline(jobId: string): Promise<{ mode: string; workflow_id: string; status: string; details: Record<string, unknown> }> { return postJson(`/jobs/${encodeURIComponent(jobId)}/pipeline`, {}); }

export function createGenerationRequest(payload: { job_id: string; template_variant_name: string; cover_template_variant_name: string; force_regenerate: boolean }): Promise<WorkflowSubmission<GenerationResult>> { return postJson("/generation/requests", payload); }
export async function fetchGenerationWorkflow(workflowId: string): Promise<WorkflowSubmission<GenerationResult>> {
  return parseResponse<WorkflowSubmission<GenerationResult>>(await fetch(`${API_BASE}/generation/workflows/${encodeURIComponent(workflowId)}`, { headers: authHeaders() }));
}
export function createApplicationPlan(payload: { job_id: string; generation_result_id: string }): Promise<ApplicationPlan> { return postJson("/applications/plans", payload); }
export function startApplicationRun(payload: { plan_id: string }): Promise<ApplicationRun> { return postJson("/applications/runs", payload); }

export function createLearningOutcome(payload: { application_plan_id: string; application_run_id?: string | null; response_type: string; interview: boolean; response_time_days?: number | null; outcome_source: string; notes?: string | null; metadata_json?: Record<string, unknown> | null; outcome_at?: string | null }): Promise<ApplicationOutcome> { return postJson("/learning/outcomes", payload); }

export async function fetchAuthStatus(): Promise<AuthStatus> { return parseResponse<AuthStatus>(await fetch(`${API_BASE}/auth/status`, { headers: authHeaders() })); }
export function googleAuthStartUrl(nextUrl?: string): string { const url = new URL(`${API_BASE}/auth/google/start`); if (nextUrl) url.searchParams.set("next_url", nextUrl); return url.toString(); }
export function clearAuthToken(): void { if (typeof window !== "undefined") window.localStorage.removeItem("jobops.auth.token"); }
export function storeAuthToken(token: string): void { if (typeof window !== "undefined") window.localStorage.setItem("jobops.auth.token", token); }
export function readAuthToken(): string | null { return sessionToken(); }
export function logoutCurrentSession(): Promise<{ status: string }> { return postJson("/auth/logout", {}); }

export function artifactUrl(relativeUrl: string): string {
  if (relativeUrl.startsWith("http://") || relativeUrl.startsWith("https://")) return relativeUrl;
  const origin = API_BASE.replace(/\/api\/v1$/, "");
  return `${origin}${relativeUrl}`;
}

