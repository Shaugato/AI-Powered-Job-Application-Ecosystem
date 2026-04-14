export type AuthUser = {
  id: string;
  email: string;
  full_name?: string | null;
  avatar_url?: string | null;
  last_login_at?: string | null;
};

export type AuthStatus = {
  authenticated: boolean;
  google_ready: boolean;
  auth_mode: string;
  session_expires_at?: string | null;
  user?: AuthUser | null;
};

export type SourceHealth = {
  source: string;
  auto_submit_certified: boolean;
  monitoring_enabled: boolean;
  status: string;
  notes: string[];
};

export type EvidenceFragment = {
  id: string;
  source_document: string;
  fragment_type: string;
  truth_status: string;
  payload_text: string;
  role_tags_json: string[];
  seniority?: string | null;
  skills_json?: string[];
  certifications_json?: string[];
  metadata_json?: Record<string, unknown> | null;
};

export type CorpusLibraryFile = {
  name: string;
  path?: string | null;
  title?: string | null;
  subtitle?: string | null;
  lines?: string[];
  preview_excerpt?: string | null;
};

export type CorpusLibrarySection = {
  key: string;
  title: string;
  file_count: number;
  files: CorpusLibraryFile[];
};

export type CorpusDocumentSummary = {
  source_document: string;
  display_name: string;
  document_kind: string;
  fragment_count: number;
  pending_count: number;
  approved_count: number;
  rejected_count: number;
  fragment_types: string[];
  role_tags: string[];
  skills: string[];
  preview_excerpt?: string | null;
  library_key?: string | null;
  folder_name?: string | null;
  library_path?: string | null;
  status: string;
  section_counts: Record<string, number>;
  sections: CorpusLibrarySection[];
};

export type BaseProfile = {
  id: string;
  full_name: string;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  website?: string | null;
  summary?: string | null;
  skills_json?: string[] | null;
  certifications_json?: string[] | null;
  experience_json?: Record<string, unknown>[] | null;
  projects_json?: Record<string, unknown>[] | null;
  education_json?: Record<string, unknown>[] | null;
  metadata_json?: Record<string, unknown> | null;
};

export type PromptVersion = {
  id: string;
  name: string;
  role_tags_json: string[];
  prompt_text: string;
  temperature: number;
  success_rate_metric: number;
  last_used_at?: string | null;
};

export type NotificationPreference = {
  id: string;
  channel: string;
  enabled: boolean;
  target?: string | null;
  metadata_json?: Record<string, unknown> | null;
};

export type NotificationEvent = {
  id: string;
  channel: string;
  subject: string;
  body: string;
  delivery_status: string;
  metadata_json?: Record<string, unknown> | null;
};

export type IntegrationProviderField = {
  key: string;
  label: string;
  input_type: string;
  required: boolean;
  secret: boolean;
  placeholder?: string | null;
  help_text?: string | null;
};

export type IntegrationProvider = {
  key: string;
  name: string;
  category: string;
  auth_type: string;
  description: string;
  capabilities: string[];
  fields: IntegrationProviderField[];
  default_scopes: string[];
  launch_url?: string | null;
};

export type IntegrationConnection = {
  id: string;
  name: string;
  provider_key: string;
  category: string;
  auth_type: string;
  status: string;
  login_hint?: string | null;
  settings_json?: Record<string, unknown> | null;
  scopes_json: string[];
  secret_fields_present: string[];
  last_connected_at?: string | null;
  last_tested_at?: string | null;
  error_message?: string | null;
  metadata_json?: Record<string, unknown> | null;
  has_session_state: boolean;
  session_state_filename?: string | null;
};

export type IntegrationConnectResponse = {
  status: string;
  connection_id: string;
  auth_url?: string | null;
  redirect_uri?: string | null;
  launch_url?: string | null;
  instructions: string[];
  details?: Record<string, unknown> | null;
};

export type IngestionSourceConfig = {
  id: string;
  name: string;
  search_profile_id?: string | null;
  connection_id?: string | null;
  source: string;
  enabled: boolean;
  cadence_minutes: number;
  query_text?: string | null;
  location_override?: string | null;
  max_results: number;
  auto_start_pipeline: boolean;
  search_url?: string | null;
  last_cursor?: string | null;
  last_run_at?: string | null;
  metadata_json?: Record<string, unknown> | null;
};

export type IngestionRun = {
  id: string;
  config_id: string;
  workflow_id?: string | null;
  status: string;
  discovered_count: number;
  ingested_count: number;
  duplicate_count: number;
  pipeline_triggered_count: number;
  error_message?: string | null;
  metadata_json?: Record<string, unknown> | null;
};

export type ApplicationOutcome = {
  id: string;
  application_plan_id: string;
  application_run_id?: string | null;
  generation_result_id?: string | null;
  prompt_version_id?: string | null;
  response_type: string;
  interview: boolean;
  response_time_days?: number | null;
  outcome_source: string;
  notes?: string | null;
  metadata_json?: Record<string, unknown> | null;
  outcome_at?: string | null;
};

export type PromptPerformance = {
  id: string;
  prompt_version_id: string;
  role_tag: string;
  applications_count: number;
  interviews_count: number;
  success_rate: number;
  avg_response_time_days?: number | null;
  last_outcome_at?: string | null;
  metadata_json?: Record<string, unknown> | null;
};

export type ResumeVariantScore = {
  id: string;
  generation_result_id: string;
  role_tag?: string | null;
  score: number;
  keyword_coverage: number;
  hallucination_risk: number;
  interview_rate_proxy: number;
  manual_edit_distance?: number | null;
  metadata_json?: Record<string, unknown> | null;
};

export type JobPosting = {
  id: string;
  source: string;
  external_id: string;
  source_url: string;
  company: string;
  title: string;
  location?: string | null;
  work_mode?: string | null;
  description_text: string;
  classification_labels_json: string[];
  eligibility_flags_json?: string[];
  risk_flags_json: string[];
  dedupe_fingerprint?: string;
  metadata_json?: Record<string, unknown> | null;
};

export type TemplateVariant = {
  id: string;
  name: string;
  document_kind: string;
  template_path: string;
  metadata_json?: Record<string, unknown> | null;
};

export type ArtifactDescriptor = {
  kind: string;
  label: string;
  available: boolean;
  filename?: string | null;
  url?: string | null;
};

export type GenerationArtifactBundle = {
  generation_result_id: string;
  artifacts: ArtifactDescriptor[];
};

export type GenerationResult = {
  id: string;
  request_id: string;
  resume_json?: Record<string, unknown>;
  cover_letter_json?: Record<string, unknown>;
  compile_status: string;
  grounding_notes?: string | null;
  qa_scores_json: Record<string, number>;
  resume_tex_path?: string | null;
  resume_pdf_path?: string | null;
  cover_tex_path?: string | null;
  cover_pdf_path?: string | null;
};

export type ApplicationPlan = {
  id: string;
  job_id?: string;
  generation_result_id?: string;
  source_adapter: string;
  mode: string;
  terminal_status: string;
  approval_state: string;
  notification_state?: string;
  field_map_json?: Record<string, unknown>;
  risk_reasons_json: string[];
};

export type ApplicationRun = {
  id: string;
  plan_id: string;
  status: string;
  execution_log_json: { message?: string; at?: string }[];
  uploaded_artifacts_json?: string[];
  result_payload_json?: Record<string, unknown> | null;
};

export type SearchProfile = {
  id: string;
  name: string;
  roles: string[];
  keywords: string[];
  excluded_terms: string[];
  locations: string[];
  remote_policy: string;
  salary_floor?: number | null;
  source_allowlist: string[];
  daily_cap: number;
  review_policy: string;
  schedule_window?: Record<string, unknown> | null;
};

export type DashboardOverview = {
  totals: Record<string, number>;
  jobs: JobPosting[];
  drafts: GenerationResult[];
  applications: ApplicationPlan[];
  pending_approvals: EvidenceFragment[];
  recent_runs: ApplicationRun[];
  recent_ingestion_runs: IngestionRun[];
  recent_outcomes: ApplicationOutcome[];
  source_health: SourceHealth[];
};

export type CorpusImportRequest = {
  path: string;
  role_hint: string[];
  source_document_glob: string;
  document_kind_override?: string | null;
};

export type CorpusImportResponse = {
  ingested_documents: number;
  created_fragments: number;
  created_prompts: number;
  warnings: string[];
  source_documents?: string[];
  auto_approved_documents?: number;
  profile_id?: string | null;
  profile_updated?: boolean;
  created_asset_ids?: string[];
  created_section_count?: number;
  library_keys?: string[];
  stage_statuses?: Record<string, Record<string, unknown>>;
  parsing_confidence?: number;
  ambiguity_flags?: string[];
  review_queue_item_ids?: string[];
  created_library_manifest?: Record<string, unknown>;
};

export type WorkflowSubmission<T> = {
  accepted: boolean;
  workflow_id: string;
  workflow_status: string;
  result?: T | null;
  error?: string | null;
};

export type JobCreateRequest = {
  source: string;
  external_id: string;
  source_url: string;
  company: string;
  title: string;
  location?: string;
  work_mode?: string;
  description_text: string;
  classification_labels: string[];
  eligibility_flags: string[];
  risk_flags: string[];
  metadata_json: Record<string, unknown>;
};

export type CandidateMemoryEntry = {
  title: string;
  subtitle?: string | null;
  bullets: string[];
  source_document?: string | null;
  confidence: number;
};

export type CandidateMemory = {
  source_profile_id?: string | null;
  summary?: string | null;
  skills: string[];
  certifications: string[];
  experience: CandidateMemoryEntry[];
  projects: CandidateMemoryEntry[];
  education: string[];
  approved_documents: number;
  pending_documents: number;
  source_documents: string[];
};



export type IntegrationBrowserCapture = {
  connection_id: string;
  provider_key: string;
  provider_name: string;
  status: string;
  login_url?: string | null;
  helper_script_path?: string | null;
  helper_command?: string | null;
  debug_port?: number | null;
  browser_reachable: boolean;
  has_session_state: boolean;
  session_state_filename?: string | null;
  started_at?: string | null;
  last_checked_at?: string | null;
  instructions: string[];
  details?: Record<string, unknown> | null;
};
