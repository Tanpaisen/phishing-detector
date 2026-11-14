-- G0 design baseline 1.0, PostgreSQL 17. Not an automatically applied migration.
-- Run only in a new disposable database when reviewing. Existing schemas fail safely.
BEGIN;
CREATE SCHEMA app;
SET LOCAL search_path = app, public;

CREATE TYPE task_type AS ENUM ('PHISHING_DETECTION','SPAM_DETECTION','SCAM_DETECTION');
CREATE TYPE input_type AS ENUM ('URL','QR_URL','MESSAGE');
CREATE TYPE processing_status AS ENUM ('COMPLETED','PARTIAL','FAILED');
CREATE TYPE risk_level AS ENUM ('VERIFIED_PHISHING','HIGH_RISK','NEEDS_REVIEW','NO_SIGNIFICANT_RISK_FOUND','UNABLE_TO_ANALYZE');
CREATE TYPE review_status AS ENUM ('PENDING','IN_REVIEW','ACCEPTED','REJECTED','INSUFFICIENT_EVIDENCE');
CREATE TYPE job_status AS ENUM ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED');

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL CHECK (length(email) BETWEEN 3 AND 254),
  password_hash text NOT NULL,
  role text NOT NULL CHECK (role IN ('ADMIN','MEMBER')),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','DISABLED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_ci ON users(lower(email));

-- A subject survives session rotation. No fingerprint or persistent tracking IP.
CREATE TABLE subjects (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  token_hash bytea UNIQUE NOT NULL CHECK (octet_length(token_hash)=32),
  csrf_hash bytea NOT NULL CHECK (octet_length(csrf_hash)=32),
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  CHECK (expires_at > created_at)
);
CREATE INDEX sessions_expiry ON sessions(expires_at);
CREATE INDEX sessions_subject ON sessions(subject_id);

CREATE TABLE brands (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  aliases jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(aliases)='array'),
  category text,
  verification_status text NOT NULL DEFAULT 'PENDING' CHECK (verification_status IN ('PENDING','VERIFIED','RETIRED')),
  version integer NOT NULL DEFAULT 1 CHECK (version>0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE brand_domains (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id uuid NOT NULL REFERENCES brands(id) ON DELETE RESTRICT,
  ascii_domain text NOT NULL CHECK (ascii_domain=lower(ascii_domain) AND length(ascii_domain) BETWEEN 1 AND 253),
  include_subdomains boolean NOT NULL DEFAULT false,
  source_url text,
  verified_by uuid REFERENCES users(id) ON DELETE RESTRICT,
  verified_at timestamptz,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','VERIFIED','RETIRED')),
  version integer NOT NULL DEFAULT 1 CHECK (version>0),
  UNIQUE(brand_id,ascii_domain),
  CHECK (status<>'VERIFIED' OR (source_url IS NOT NULL AND verified_by IS NOT NULL AND verified_at IS NOT NULL))
);

CREATE TABLE config_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind text NOT NULL CHECK (kind IN ('BRANDS','PSL','RULES')),
  version text NOT NULL,
  checksum char(64) NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
  artifact_reference text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(kind,version), UNIQUE(id,kind)
);
CREATE TABLE policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version text UNIQUE NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','APPROVED','RETIRED')),
  definition_json jsonb NOT NULL CHECK (jsonb_typeof(definition_json)='object'),
  checksum char(64) NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
  approved_by uuid REFERENCES users(id) ON DELETE RESTRICT,
  approved_at timestamptz,
  CHECK (status<>'APPROVED' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE TABLE dataset_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version text UNIQUE NOT NULL,
  task_type task_type NOT NULL,
  manifest_reference text NOT NULL,
  split_manifest_reference text NOT NULL,
  checksum char(64) NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
  label_schema_version text NOT NULL,
  status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','FROZEN','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(id,task_type)
);
CREATE TABLE model_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_type task_type NOT NULL,
  model_name text NOT NULL,
  version text NOT NULL,
  dataset_version_id uuid NOT NULL,
  feature_schema_version text NOT NULL,
  preprocessing_version text NOT NULL,
  runtime_manifest jsonb NOT NULL CHECK (jsonb_typeof(runtime_manifest)='object'),
  artifact_reference text NOT NULL,
  checksum char(64) NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version>0),
  status text NOT NULL DEFAULT 'CANDIDATE' CHECK (status IN ('CANDIDATE','EVALUATED','APPROVED','REJECTED','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(dataset_version_id,task_type) REFERENCES dataset_versions(id,task_type) ON DELETE RESTRICT,
  UNIQUE(task_type,model_name,version), UNIQUE(id,task_type)
);
CREATE TABLE model_releases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version text UNIQUE NOT NULL,
  environment text NOT NULL DEFAULT 'local' CHECK (environment IN ('local','test','production')),
  scope text NOT NULL CHECK (scope IN ('URL_ONLY','MULTI_INPUT')),
  url_model_id uuid NOT NULL,
  url_task task_type NOT NULL DEFAULT 'PHISHING_DETECTION' CHECK (url_task='PHISHING_DETECTION'),
  message_model_id uuid,
  message_task task_type CHECK (message_task IN ('SPAM_DETECTION','SCAM_DETECTION')),
  policy_id uuid NOT NULL REFERENCES policies(id) ON DELETE RESTRICT,
  brand_snapshot_id uuid NOT NULL,
  brand_kind text NOT NULL DEFAULT 'BRANDS' CHECK (brand_kind='BRANDS'),
  psl_snapshot_id uuid NOT NULL,
  psl_kind text NOT NULL DEFAULT 'PSL' CHECK (psl_kind='PSL'),
  rule_snapshot_id uuid NOT NULL,
  rule_kind text NOT NULL DEFAULT 'RULES' CHECK (rule_kind='RULES'),
  checksum char(64) NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
  status text NOT NULL DEFAULT 'STAGED' CHECK (status IN ('STAGED','ACTIVE','RETIRED')),
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version>0),
  activated_at timestamptz,
  FOREIGN KEY(url_model_id,url_task) REFERENCES model_versions(id,task_type) ON DELETE RESTRICT,
  FOREIGN KEY(message_model_id,message_task) REFERENCES model_versions(id,task_type) ON DELETE RESTRICT,
  FOREIGN KEY(brand_snapshot_id,brand_kind) REFERENCES config_snapshots(id,kind) ON DELETE RESTRICT,
  FOREIGN KEY(psl_snapshot_id,psl_kind) REFERENCES config_snapshots(id,kind) ON DELETE RESTRICT,
  FOREIGN KEY(rule_snapshot_id,rule_kind) REFERENCES config_snapshots(id,kind) ON DELETE RESTRICT,
  CHECK ((scope='URL_ONLY' AND message_model_id IS NULL AND message_task IS NULL) OR
         (scope='MULTI_INPUT' AND message_model_id IS NOT NULL AND message_task IS NOT NULL)),
  CHECK (status<>'ACTIVE' OR activated_at IS NOT NULL)
);
CREATE UNIQUE INDEX one_active_release_per_environment ON model_releases(environment) WHERE status='ACTIVE';

CREATE TABLE scan_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
  input_type input_type NOT NULL,
  processing_status processing_status NOT NULL,
  risk_level risk_level NOT NULL,
  release_id uuid NOT NULL REFERENCES model_releases(id) ON DELETE RESTRICT,
  request_id uuid UNIQUE NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  CHECK (expires_at>created_at),
  CHECK ((processing_status='FAILED') = (risk_level='UNABLE_TO_ANALYZE')),
  CHECK (processing_status<>'PARTIAL' OR risk_level<>'NO_SIGNIFICANT_RISK_FOUND')
);
CREATE INDEX scans_owner_created ON scan_requests(owner_subject_id,created_at DESC,id);
CREATE INDEX scans_expiry ON scan_requests(expires_at);
CREATE TABLE scan_components (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_id uuid NOT NULL REFERENCES scan_requests(id) ON DELETE CASCADE,
  component_type text NOT NULL CHECK (component_type IN ('URL','TEXT')),
  ordinal integer NOT NULL CHECK (ordinal>=0),
  component_status processing_status NOT NULL,
  model_version_id uuid,
  task_type task_type,
  predicted_label text CHECK (predicted_label IN ('LEGITIMATE','PHISHING','HAM','SPAM_OR_SCAM','NON_SCAM','SCAM')),
  score double precision CHECK (score NOT IN ('NaN'::float8,'Infinity'::float8,'-Infinity'::float8)),
  score_type text CHECK (score_type IN ('RAW_MARGIN','MODEL_SCORE','CALIBRATED_PROBABILITY')),
  calibration_version text,
  explanation_status text NOT NULL CHECK (explanation_status IN ('AVAILABLE','UNAVAILABLE','NOT_APPLICABLE')),
  error_code text,
  sanitized_summary jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(sanitized_summary)='object'),
  processing_time_ms integer NOT NULL CHECK (processing_time_ms>=0),
  FOREIGN KEY(model_version_id,task_type) REFERENCES model_versions(id,task_type) ON DELETE RESTRICT,
  UNIQUE(scan_id,component_type,ordinal), UNIQUE(id,scan_id),
  CHECK ((model_version_id IS NULL) = (task_type IS NULL)),
  CHECK ((score IS NULL) = (score_type IS NULL)),
  CHECK (score IS NULL OR model_version_id IS NOT NULL),
  CHECK (score_type<>'CALIBRATED_PROBABILITY' OR (score BETWEEN 0 AND 1 AND calibration_version IS NOT NULL)),
  CHECK (task_type IS NULL OR (component_type='URL' AND task_type='PHISHING_DETECTION') OR
         (component_type='TEXT' AND task_type IN ('SPAM_DETECTION','SCAM_DETECTION'))),
  CHECK (predicted_label IS NULL OR
         (task_type='PHISHING_DETECTION' AND predicted_label IN ('LEGITIMATE','PHISHING')) OR
         (task_type='SPAM_DETECTION' AND predicted_label IN ('HAM','SPAM_OR_SCAM')) OR
         (task_type='SCAM_DETECTION' AND predicted_label IN ('NON_SCAM','SCAM'))),
  CHECK (predicted_label IS NULL OR task_type IS NOT NULL)
);
CREATE TABLE scan_results (
  scan_id uuid PRIMARY KEY REFERENCES scan_requests(id) ON DELETE CASCADE,
  schema_version text NOT NULL,
  explanation_json jsonb NOT NULL CHECK (jsonb_typeof(explanation_json)='object'),
  evidence_summary jsonb NOT NULL CHECK (jsonb_typeof(evidence_summary)='array'),
  coverage_json jsonb NOT NULL CHECK (jsonb_typeof(coverage_json)='object'),
  total_processing_ms integer NOT NULL CHECK (total_processing_ms>=0)
);
CREATE TABLE threat_indicators (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  indicator_type text NOT NULL CHECK (indicator_type IN ('URL','DOMAIN')),
  canonical_key_hash bytea NOT NULL CHECK (octet_length(canonical_key_hash)=32),
  normalization_version text NOT NULL,
  source text NOT NULL,
  source_reference text NOT NULL,
  verified_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  last_checked_at timestamptz,
  status text NOT NULL CHECK (status IN ('ACTIVE','EXPIRED','REVOKED')),
  CHECK (expires_at>verified_at),
  UNIQUE(source,indicator_type,normalization_version,canonical_key_hash)
);
CREATE INDEX indicators_lookup ON threat_indicators(normalization_version,canonical_key_hash,status);
CREATE TABLE scan_evidence (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_id uuid NOT NULL REFERENCES scan_requests(id) ON DELETE CASCADE,
  component_id uuid NOT NULL,
  indicator_id uuid REFERENCES threat_indicators(id) ON DELETE SET NULL,
  evidence_snapshot jsonb NOT NULL CHECK (jsonb_typeof(evidence_snapshot)='object'),
  checked_at timestamptz NOT NULL,
  FOREIGN KEY(component_id,scan_id) REFERENCES scan_components(id,scan_id) ON DELETE CASCADE
);

CREATE TABLE consents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
  purpose text NOT NULL CHECK (purpose='MODEL_RESEARCH'),
  policy_version text NOT NULL,
  granted_at timestamptz NOT NULL DEFAULT now(),
  withdrawn_at timestamptz,
  expires_at timestamptz NOT NULL,
  CHECK (expires_at>granted_at), CHECK (withdrawn_at IS NULL OR withdrawn_at>=granted_at)
);
CREATE TABLE research_submissions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  consent_id uuid UNIQUE NOT NULL REFERENCES consents(id) ON DELETE RESTRICT,
  scan_id uuid REFERENCES scan_requests(id) ON DELETE SET NULL,
  input_type input_type NOT NULL,
  sample_reference text NOT NULL,
  withdrawal_token_hash bytea UNIQUE NOT NULL CHECK (octet_length(withdrawal_token_hash)=32),
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','REVIEWED','WITHDRAWN','EXPIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  retention_until timestamptz NOT NULL,
  CHECK (retention_until>created_at)
);
CREATE INDEX research_expiry ON research_submissions(retention_until);
CREATE TABLE labeled_samples (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  input_type input_type NOT NULL,
  task_type task_type NOT NULL,
  sample_reference text NOT NULL,
  fingerprint bytea NOT NULL CHECK (octet_length(fingerprint)=32),
  verified_label text NOT NULL,
  label_schema_version text NOT NULL,
  source_type text NOT NULL CHECK (source_type IN ('PUBLIC_DATASET','USER_SUBMISSION')),
  source_reference text NOT NULL,
  submission_id uuid UNIQUE REFERENCES research_submissions(id) ON DELETE RESTRICT,
  verified_by uuid REFERENCES users(id) ON DELETE RESTRICT,
  verified_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'ELIGIBLE' CHECK (status IN ('ELIGIBLE','QUARANTINED','WITHDRAWN','EXPIRED')),
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version>0),
  CHECK ((source_type='PUBLIC_DATASET' AND submission_id IS NULL) OR
         (source_type='USER_SUBMISSION' AND submission_id IS NOT NULL AND verified_by IS NOT NULL)),
  CHECK ((task_type='PHISHING_DETECTION' AND input_type IN ('URL','QR_URL') AND verified_label IN ('LEGITIMATE','PHISHING')) OR
         (task_type='SPAM_DETECTION' AND input_type='MESSAGE' AND verified_label IN ('HAM','SPAM_OR_SCAM')) OR
         (task_type='SCAM_DETECTION' AND input_type='MESSAGE' AND verified_label IN ('NON_SCAM','SCAM')))
);
CREATE INDEX samples_fingerprint ON labeled_samples(task_type,fingerprint);
CREATE TABLE label_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sample_id uuid NOT NULL REFERENCES labeled_samples(id) ON DELETE RESTRICT,
  old_label text,
  new_label text NOT NULL,
  reason text NOT NULL,
  reviewer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_id uuid REFERENCES scan_requests(id) ON DELETE SET NULL,
  submitter_subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE RESTRICT,
  feedback_type text NOT NULL CHECK (feedback_type IN ('FALSE_POSITIVE','FALSE_NEGATIVE','OTHER')),
  comment_redacted text NOT NULL DEFAULT '' CHECK (length(comment_redacted)<=2000),
  status review_status NOT NULL DEFAULT 'PENDING',
  sample_id uuid REFERENCES labeled_samples(id) ON DELETE SET NULL,
  reviewed_by uuid REFERENCES users(id) ON DELETE RESTRICT,
  review_reason text,
  reviewed_at timestamptz,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version>0),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status NOT IN ('ACCEPTED','REJECTED','INSUFFICIENT_EVIDENCE') OR
         (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL AND review_reason IS NOT NULL))
);
CREATE INDEX feedback_queue ON feedback(status,created_at,id);

CREATE TABLE model_evaluations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id uuid NOT NULL REFERENCES model_versions(id) ON DELETE RESTRICT,
  evaluation_dataset_id uuid NOT NULL REFERENCES dataset_versions(id) ON DELETE RESTRICT,
  evaluation_role text NOT NULL CHECK (evaluation_role IN ('VALIDATION','PROMOTION','FINAL_TEST','OLD_HOLDOUT')),
  split_manifest_checksum char(64) NOT NULL CHECK (split_manifest_checksum ~ '^[0-9a-f]{64}$'),
  policy_id uuid REFERENCES policies(id) ON DELETE RESTRICT,
  metrics_json jsonb NOT NULL CHECK (jsonb_typeof(metrics_json)='object'),
  sample_count integer NOT NULL CHECK (sample_count>0),
  evaluated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX evaluations_model ON model_evaluations(model_version_id,evaluated_at DESC);
CREATE TABLE training_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  requested_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  dataset_version_id uuid NOT NULL,
  task_type task_type NOT NULL,
  status job_status NOT NULL DEFAULT 'QUEUED',
  config_json jsonb NOT NULL CHECK (jsonb_typeof(config_json)='object'),
  lease_token_hash bytea CHECK (octet_length(lease_token_hash)=32),
  lease_expires_at timestamptz,
  attempt integer NOT NULL DEFAULT 0 CHECK (attempt>=0),
  heartbeat_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  result_model_id uuid,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(dataset_version_id,task_type) REFERENCES dataset_versions(id,task_type) ON DELETE RESTRICT,
  FOREIGN KEY(result_model_id,task_type) REFERENCES model_versions(id,task_type) ON DELETE RESTRICT,
  CHECK (status<>'RUNNING' OR (lease_token_hash IS NOT NULL AND lease_expires_at IS NOT NULL AND started_at IS NOT NULL)),
  CHECK (status<>'SUCCEEDED' OR (result_model_id IS NOT NULL AND completed_at IS NOT NULL)),
  CHECK (status NOT IN ('FAILED','CANCELLED') OR completed_at IS NOT NULL)
);
CREATE INDEX jobs_claim ON training_jobs(status,created_at,id);
CREATE TABLE idempotency_records (
  subject_id uuid NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  operation text NOT NULL,
  key text NOT NULL CHECK (length(key) BETWEEN 16 AND 128),
  request_hash bytea NOT NULL CHECK (octet_length(request_hash)=32),
  resource_id uuid NOT NULL REFERENCES training_jobs(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  PRIMARY KEY(subject_id,operation,key)
);
CREATE INDEX idempotency_expiry ON idempotency_records(expires_at);
CREATE TABLE audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_id uuid,
  request_id uuid NOT NULL,
  redacted_details jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(redacted_details)='object'),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_entity ON audit_logs(entity_type,entity_id,created_at DESC);

COMMENT ON TABLE scan_requests IS 'No raw URL/SMS; owner checks and TTL enforced in Node.';
COMMENT ON TABLE research_submissions IS 'sample_reference points to restricted storage, never public API.';
COMMENT ON TABLE model_releases IS 'Activation gate and immutable manifest validation are application transactions.';
COMMENT ON COLUMN threat_indicators.canonical_key_hash IS 'SHA-256 of versioned canonical lookup key; do not treat a hash as encryption.';
COMMIT;
