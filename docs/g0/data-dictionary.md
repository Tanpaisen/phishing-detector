# G0 — Từ điển dữ liệu sinh từ DDL

Nguồn: database/design/g0-schema.sql, thực thi trong PostgreSQL/WASM cô lập.
Không phải schema đã áp dụng vào database người dùng. NOT NULL và CHECK được ghi đúng theo catalog; các quyền nghiệp vụ xem 02-database-design.md.

## audit_logs

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| actor_user_id | uuid | Có | — |
| action | text | Không | — |
| entity_type | text | Không | — |
| entity_id | uuid | Có | — |
| request_id | uuid | Không | — |
| redacted_details | jsonb | Không | '{}'::jsonb |
| created_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `audit_logs_action_not_null`: `NOT NULL action`
- `audit_logs_actor_user_id_fkey`: `FOREIGN KEY (actor_user_id) REFERENCES users(id) ON DELETE SET NULL`
- `audit_logs_created_at_not_null`: `NOT NULL created_at`
- `audit_logs_entity_type_not_null`: `NOT NULL entity_type`
- `audit_logs_id_not_null`: `NOT NULL id`
- `audit_logs_pkey`: `PRIMARY KEY (id)`
- `audit_logs_redacted_details_check`: `CHECK ((jsonb_typeof(redacted_details) = 'object'::text))`
- `audit_logs_redacted_details_not_null`: `NOT NULL redacted_details`
- `audit_logs_request_id_not_null`: `NOT NULL request_id`

## brand_domains

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| brand_id | uuid | Không | — |
| ascii_domain | text | Không | — |
| include_subdomains | boolean | Không | false |
| source_url | text | Có | — |
| verified_by | uuid | Có | — |
| verified_at | timestamp with time zone | Có | — |
| status | text | Không | 'PENDING'::text |
| version | integer | Không | 1 |

Ràng buộc:

- `brand_domains_ascii_domain_check`: `CHECK (((ascii_domain = lower(ascii_domain)) AND ((length(ascii_domain) >= 1) AND (length(ascii_domain) <= 253))))`
- `brand_domains_ascii_domain_not_null`: `NOT NULL ascii_domain`
- `brand_domains_brand_id_ascii_domain_key`: `UNIQUE (brand_id, ascii_domain)`
- `brand_domains_brand_id_fkey`: `FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE RESTRICT`
- `brand_domains_brand_id_not_null`: `NOT NULL brand_id`
- `brand_domains_check`: `CHECK (((status <> 'VERIFIED'::text) OR ((source_url IS NOT NULL) AND (verified_by IS NOT NULL) AND (verified_at IS NOT NULL))))`
- `brand_domains_id_not_null`: `NOT NULL id`
- `brand_domains_include_subdomains_not_null`: `NOT NULL include_subdomains`
- `brand_domains_pkey`: `PRIMARY KEY (id)`
- `brand_domains_status_check`: `CHECK ((status = ANY (ARRAY['PENDING'::text, 'VERIFIED'::text, 'RETIRED'::text])))`
- `brand_domains_status_not_null`: `NOT NULL status`
- `brand_domains_verified_by_fkey`: `FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT`
- `brand_domains_version_check`: `CHECK ((version > 0))`
- `brand_domains_version_not_null`: `NOT NULL version`

## brands

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| name | text | Không | — |
| aliases | jsonb | Không | '[]'::jsonb |
| category | text | Có | — |
| verification_status | text | Không | 'PENDING'::text |
| version | integer | Không | 1 |
| created_at | timestamp with time zone | Không | now() |
| updated_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `brands_aliases_check`: `CHECK ((jsonb_typeof(aliases) = 'array'::text))`
- `brands_aliases_not_null`: `NOT NULL aliases`
- `brands_created_at_not_null`: `NOT NULL created_at`
- `brands_id_not_null`: `NOT NULL id`
- `brands_name_check`: `CHECK (((length(name) >= 1) AND (length(name) <= 200)))`
- `brands_name_not_null`: `NOT NULL name`
- `brands_pkey`: `PRIMARY KEY (id)`
- `brands_updated_at_not_null`: `NOT NULL updated_at`
- `brands_verification_status_check`: `CHECK ((verification_status = ANY (ARRAY['PENDING'::text, 'VERIFIED'::text, 'RETIRED'::text])))`
- `brands_verification_status_not_null`: `NOT NULL verification_status`
- `brands_version_check`: `CHECK ((version > 0))`
- `brands_version_not_null`: `NOT NULL version`

## config_snapshots

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| kind | text | Không | — |
| version | text | Không | — |
| checksum | character(64) | Không | — |
| artifact_reference | text | Không | — |
| created_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `config_snapshots_artifact_reference_not_null`: `NOT NULL artifact_reference`
- `config_snapshots_checksum_check`: `CHECK ((checksum ~ '^[0-9a-f]{64}$'::text))`
- `config_snapshots_checksum_not_null`: `NOT NULL checksum`
- `config_snapshots_created_at_not_null`: `NOT NULL created_at`
- `config_snapshots_id_kind_key`: `UNIQUE (id, kind)`
- `config_snapshots_id_not_null`: `NOT NULL id`
- `config_snapshots_kind_check`: `CHECK ((kind = ANY (ARRAY['BRANDS'::text, 'PSL'::text, 'RULES'::text])))`
- `config_snapshots_kind_not_null`: `NOT NULL kind`
- `config_snapshots_kind_version_key`: `UNIQUE (kind, version)`
- `config_snapshots_pkey`: `PRIMARY KEY (id)`
- `config_snapshots_version_not_null`: `NOT NULL version`

## consents

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| subject_id | uuid | Không | — |
| purpose | text | Không | — |
| policy_version | text | Không | — |
| granted_at | timestamp with time zone | Không | now() |
| withdrawn_at | timestamp with time zone | Có | — |
| expires_at | timestamp with time zone | Không | — |

Ràng buộc:

- `consents_check`: `CHECK ((expires_at > granted_at))`
- `consents_check1`: `CHECK (((withdrawn_at IS NULL) OR (withdrawn_at >= granted_at)))`
- `consents_expires_at_not_null`: `NOT NULL expires_at`
- `consents_granted_at_not_null`: `NOT NULL granted_at`
- `consents_id_not_null`: `NOT NULL id`
- `consents_pkey`: `PRIMARY KEY (id)`
- `consents_policy_version_not_null`: `NOT NULL policy_version`
- `consents_purpose_check`: `CHECK ((purpose = 'MODEL_RESEARCH'::text))`
- `consents_purpose_not_null`: `NOT NULL purpose`
- `consents_subject_id_fkey`: `FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE RESTRICT`
- `consents_subject_id_not_null`: `NOT NULL subject_id`

## dataset_versions

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| version | text | Không | — |
| task_type | task_type | Không | — |
| manifest_reference | text | Không | — |
| split_manifest_reference | text | Không | — |
| checksum | character(64) | Không | — |
| label_schema_version | text | Không | — |
| status | text | Không | 'DRAFT'::text |
| created_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `dataset_versions_checksum_check`: `CHECK ((checksum ~ '^[0-9a-f]{64}$'::text))`
- `dataset_versions_checksum_not_null`: `NOT NULL checksum`
- `dataset_versions_created_at_not_null`: `NOT NULL created_at`
- `dataset_versions_id_not_null`: `NOT NULL id`
- `dataset_versions_id_task_type_key`: `UNIQUE (id, task_type)`
- `dataset_versions_label_schema_version_not_null`: `NOT NULL label_schema_version`
- `dataset_versions_manifest_reference_not_null`: `NOT NULL manifest_reference`
- `dataset_versions_pkey`: `PRIMARY KEY (id)`
- `dataset_versions_split_manifest_reference_not_null`: `NOT NULL split_manifest_reference`
- `dataset_versions_status_check`: `CHECK ((status = ANY (ARRAY['DRAFT'::text, 'FROZEN'::text, 'RETIRED'::text])))`
- `dataset_versions_status_not_null`: `NOT NULL status`
- `dataset_versions_task_type_not_null`: `NOT NULL task_type`
- `dataset_versions_version_key`: `UNIQUE (version)`
- `dataset_versions_version_not_null`: `NOT NULL version`

## feedback

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| scan_id | uuid | Có | — |
| submitter_subject_id | uuid | Không | — |
| feedback_type | text | Không | — |
| comment_redacted | text | Không | ''::text |
| status | review_status | Không | 'PENDING'::review_status |
| sample_id | uuid | Có | — |
| reviewed_by | uuid | Có | — |
| review_reason | text | Có | — |
| reviewed_at | timestamp with time zone | Có | — |
| row_version | integer | Không | 1 |
| created_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `feedback_check`: `CHECK (((status <> ALL (ARRAY['ACCEPTED'::review_status, 'REJECTED'::review_status, 'INSUFFICIENT_EVIDENCE'::review_status])) OR ((reviewed_by IS NOT NULL) AND (reviewed_at IS NOT NULL) AND (review_reason IS NOT NULL))))`
- `feedback_comment_redacted_check`: `CHECK ((length(comment_redacted) <= 2000))`
- `feedback_comment_redacted_not_null`: `NOT NULL comment_redacted`
- `feedback_created_at_not_null`: `NOT NULL created_at`
- `feedback_feedback_type_check`: `CHECK ((feedback_type = ANY (ARRAY['FALSE_POSITIVE'::text, 'FALSE_NEGATIVE'::text, 'OTHER'::text])))`
- `feedback_feedback_type_not_null`: `NOT NULL feedback_type`
- `feedback_id_not_null`: `NOT NULL id`
- `feedback_pkey`: `PRIMARY KEY (id)`
- `feedback_reviewed_by_fkey`: `FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE RESTRICT`
- `feedback_row_version_check`: `CHECK ((row_version > 0))`
- `feedback_row_version_not_null`: `NOT NULL row_version`
- `feedback_sample_id_fkey`: `FOREIGN KEY (sample_id) REFERENCES labeled_samples(id) ON DELETE SET NULL`
- `feedback_scan_id_fkey`: `FOREIGN KEY (scan_id) REFERENCES scan_requests(id) ON DELETE SET NULL`
- `feedback_status_not_null`: `NOT NULL status`
- `feedback_submitter_subject_id_fkey`: `FOREIGN KEY (submitter_subject_id) REFERENCES subjects(id) ON DELETE RESTRICT`
- `feedback_submitter_subject_id_not_null`: `NOT NULL submitter_subject_id`

## idempotency_records

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| subject_id | uuid | Không | — |
| operation | text | Không | — |
| key | text | Không | — |
| request_hash | bytea | Không | — |
| resource_id | uuid | Không | — |
| expires_at | timestamp with time zone | Không | — |

Ràng buộc:

- `idempotency_records_expires_at_not_null`: `NOT NULL expires_at`
- `idempotency_records_key_check`: `CHECK (((length(key) >= 16) AND (length(key) <= 128)))`
- `idempotency_records_key_not_null`: `NOT NULL key`
- `idempotency_records_operation_not_null`: `NOT NULL operation`
- `idempotency_records_pkey`: `PRIMARY KEY (subject_id, operation, key)`
- `idempotency_records_request_hash_check`: `CHECK ((octet_length(request_hash) = 32))`
- `idempotency_records_request_hash_not_null`: `NOT NULL request_hash`
- `idempotency_records_resource_id_fkey`: `FOREIGN KEY (resource_id) REFERENCES training_jobs(id) ON DELETE CASCADE`
- `idempotency_records_resource_id_not_null`: `NOT NULL resource_id`
- `idempotency_records_subject_id_fkey`: `FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE`
- `idempotency_records_subject_id_not_null`: `NOT NULL subject_id`

## label_history

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| sample_id | uuid | Không | — |
| old_label | text | Có | — |
| new_label | text | Không | — |
| reason | text | Không | — |
| reviewer_id | uuid | Không | — |
| created_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `label_history_created_at_not_null`: `NOT NULL created_at`
- `label_history_id_not_null`: `NOT NULL id`
- `label_history_new_label_not_null`: `NOT NULL new_label`
- `label_history_pkey`: `PRIMARY KEY (id)`
- `label_history_reason_not_null`: `NOT NULL reason`
- `label_history_reviewer_id_fkey`: `FOREIGN KEY (reviewer_id) REFERENCES users(id) ON DELETE RESTRICT`
- `label_history_reviewer_id_not_null`: `NOT NULL reviewer_id`
- `label_history_sample_id_fkey`: `FOREIGN KEY (sample_id) REFERENCES labeled_samples(id) ON DELETE RESTRICT`
- `label_history_sample_id_not_null`: `NOT NULL sample_id`

## labeled_samples

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| input_type | input_type | Không | — |
| task_type | task_type | Không | — |
| sample_reference | text | Không | — |
| fingerprint | bytea | Không | — |
| verified_label | text | Không | — |
| label_schema_version | text | Không | — |
| source_type | text | Không | — |
| source_reference | text | Không | — |
| submission_id | uuid | Có | — |
| verified_by | uuid | Có | — |
| verified_at | timestamp with time zone | Không | — |
| status | text | Không | 'ELIGIBLE'::text |
| row_version | integer | Không | 1 |

Ràng buộc:

- `labeled_samples_check`: `CHECK ((((source_type = 'PUBLIC_DATASET'::text) AND (submission_id IS NULL)) OR ((source_type = 'USER_SUBMISSION'::text) AND (submission_id IS NOT NULL) AND (verified_by IS NOT NULL))))`
- `labeled_samples_check1`: `CHECK ((((task_type = 'PHISHING_DETECTION'::task_type) AND (input_type = ANY (ARRAY['URL'::input_type, 'QR_URL'::input_type])) AND (verified_label = ANY (ARRAY['LEGITIMATE'::text, 'PHISHING'::text]))) OR ((task_type = 'SPAM_DETECTION'::task_type) AND (input_type = 'MESSAGE'::input_type) AND (verified_label = ANY (ARRAY['HAM'::text, 'SPAM_OR_SCAM'::text]))) OR ((task_type = 'SCAM_DETECTION'::task_type) AND (input_type = 'MESSAGE'::input_type) AND (verified_label = ANY (ARRAY['NON_SCAM'::text, 'SCAM'::text])))))`
- `labeled_samples_fingerprint_check`: `CHECK ((octet_length(fingerprint) = 32))`
- `labeled_samples_fingerprint_not_null`: `NOT NULL fingerprint`
- `labeled_samples_id_not_null`: `NOT NULL id`
- `labeled_samples_input_type_not_null`: `NOT NULL input_type`
- `labeled_samples_label_schema_version_not_null`: `NOT NULL label_schema_version`
- `labeled_samples_pkey`: `PRIMARY KEY (id)`
- `labeled_samples_row_version_check`: `CHECK ((row_version > 0))`
- `labeled_samples_row_version_not_null`: `NOT NULL row_version`
- `labeled_samples_sample_reference_not_null`: `NOT NULL sample_reference`
- `labeled_samples_source_reference_not_null`: `NOT NULL source_reference`
- `labeled_samples_source_type_check`: `CHECK ((source_type = ANY (ARRAY['PUBLIC_DATASET'::text, 'USER_SUBMISSION'::text])))`
- `labeled_samples_source_type_not_null`: `NOT NULL source_type`
- `labeled_samples_status_check`: `CHECK ((status = ANY (ARRAY['ELIGIBLE'::text, 'QUARANTINED'::text, 'WITHDRAWN'::text, 'EXPIRED'::text])))`
- `labeled_samples_status_not_null`: `NOT NULL status`
- `labeled_samples_submission_id_fkey`: `FOREIGN KEY (submission_id) REFERENCES research_submissions(id) ON DELETE RESTRICT`
- `labeled_samples_submission_id_key`: `UNIQUE (submission_id)`
- `labeled_samples_task_type_not_null`: `NOT NULL task_type`
- `labeled_samples_verified_at_not_null`: `NOT NULL verified_at`
- `labeled_samples_verified_by_fkey`: `FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT`
- `labeled_samples_verified_label_not_null`: `NOT NULL verified_label`

## model_evaluations

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| model_version_id | uuid | Không | — |
| evaluation_dataset_id | uuid | Không | — |
| evaluation_role | text | Không | — |
| split_manifest_checksum | character(64) | Không | — |
| policy_id | uuid | Có | — |
| metrics_json | jsonb | Không | — |
| sample_count | integer | Không | — |
| evaluated_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `model_evaluations_evaluated_at_not_null`: `NOT NULL evaluated_at`
- `model_evaluations_evaluation_dataset_id_fkey`: `FOREIGN KEY (evaluation_dataset_id) REFERENCES dataset_versions(id) ON DELETE RESTRICT`
- `model_evaluations_evaluation_dataset_id_not_null`: `NOT NULL evaluation_dataset_id`
- `model_evaluations_evaluation_role_check`: `CHECK ((evaluation_role = ANY (ARRAY['VALIDATION'::text, 'PROMOTION'::text, 'FINAL_TEST'::text, 'OLD_HOLDOUT'::text])))`
- `model_evaluations_evaluation_role_not_null`: `NOT NULL evaluation_role`
- `model_evaluations_id_not_null`: `NOT NULL id`
- `model_evaluations_metrics_json_check`: `CHECK ((jsonb_typeof(metrics_json) = 'object'::text))`
- `model_evaluations_metrics_json_not_null`: `NOT NULL metrics_json`
- `model_evaluations_model_version_id_fkey`: `FOREIGN KEY (model_version_id) REFERENCES model_versions(id) ON DELETE RESTRICT`
- `model_evaluations_model_version_id_not_null`: `NOT NULL model_version_id`
- `model_evaluations_pkey`: `PRIMARY KEY (id)`
- `model_evaluations_policy_id_fkey`: `FOREIGN KEY (policy_id) REFERENCES policies(id) ON DELETE RESTRICT`
- `model_evaluations_sample_count_check`: `CHECK ((sample_count > 0))`
- `model_evaluations_sample_count_not_null`: `NOT NULL sample_count`
- `model_evaluations_split_manifest_checksum_check`: `CHECK ((split_manifest_checksum ~ '^[0-9a-f]{64}$'::text))`
- `model_evaluations_split_manifest_checksum_not_null`: `NOT NULL split_manifest_checksum`

## model_releases

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| version | text | Không | — |
| environment | text | Không | 'local'::text |
| scope | text | Không | — |
| url_model_id | uuid | Không | — |
| url_task | task_type | Không | 'PHISHING_DETECTION'::task_type |
| message_model_id | uuid | Có | — |
| message_task | task_type | Có | — |
| policy_id | uuid | Không | — |
| brand_snapshot_id | uuid | Không | — |
| brand_kind | text | Không | 'BRANDS'::text |
| psl_snapshot_id | uuid | Không | — |
| psl_kind | text | Không | 'PSL'::text |
| rule_snapshot_id | uuid | Không | — |
| rule_kind | text | Không | 'RULES'::text |
| checksum | character(64) | Không | — |
| status | text | Không | 'STAGED'::text |
| row_version | integer | Không | 1 |
| activated_at | timestamp with time zone | Có | — |

Ràng buộc:

- `model_releases_brand_kind_check`: `CHECK ((brand_kind = 'BRANDS'::text))`
- `model_releases_brand_kind_not_null`: `NOT NULL brand_kind`
- `model_releases_brand_snapshot_id_brand_kind_fkey`: `FOREIGN KEY (brand_snapshot_id, brand_kind) REFERENCES config_snapshots(id, kind) ON DELETE RESTRICT`
- `model_releases_brand_snapshot_id_not_null`: `NOT NULL brand_snapshot_id`
- `model_releases_check`: `CHECK ((((scope = 'URL_ONLY'::text) AND (message_model_id IS NULL) AND (message_task IS NULL)) OR ((scope = 'MULTI_INPUT'::text) AND (message_model_id IS NOT NULL) AND (message_task IS NOT NULL))))`
- `model_releases_check1`: `CHECK (((status <> 'ACTIVE'::text) OR (activated_at IS NOT NULL)))`
- `model_releases_checksum_check`: `CHECK ((checksum ~ '^[0-9a-f]{64}$'::text))`
- `model_releases_checksum_not_null`: `NOT NULL checksum`
- `model_releases_environment_check`: `CHECK ((environment = ANY (ARRAY['local'::text, 'test'::text, 'production'::text])))`
- `model_releases_environment_not_null`: `NOT NULL environment`
- `model_releases_id_not_null`: `NOT NULL id`
- `model_releases_message_model_id_message_task_fkey`: `FOREIGN KEY (message_model_id, message_task) REFERENCES model_versions(id, task_type) ON DELETE RESTRICT`
- `model_releases_message_task_check`: `CHECK ((message_task = ANY (ARRAY['SPAM_DETECTION'::task_type, 'SCAM_DETECTION'::task_type])))`
- `model_releases_pkey`: `PRIMARY KEY (id)`
- `model_releases_policy_id_fkey`: `FOREIGN KEY (policy_id) REFERENCES policies(id) ON DELETE RESTRICT`
- `model_releases_policy_id_not_null`: `NOT NULL policy_id`
- `model_releases_psl_kind_check`: `CHECK ((psl_kind = 'PSL'::text))`
- `model_releases_psl_kind_not_null`: `NOT NULL psl_kind`
- `model_releases_psl_snapshot_id_not_null`: `NOT NULL psl_snapshot_id`
- `model_releases_psl_snapshot_id_psl_kind_fkey`: `FOREIGN KEY (psl_snapshot_id, psl_kind) REFERENCES config_snapshots(id, kind) ON DELETE RESTRICT`
- `model_releases_row_version_check`: `CHECK ((row_version > 0))`
- `model_releases_row_version_not_null`: `NOT NULL row_version`
- `model_releases_rule_kind_check`: `CHECK ((rule_kind = 'RULES'::text))`
- `model_releases_rule_kind_not_null`: `NOT NULL rule_kind`
- `model_releases_rule_snapshot_id_not_null`: `NOT NULL rule_snapshot_id`
- `model_releases_rule_snapshot_id_rule_kind_fkey`: `FOREIGN KEY (rule_snapshot_id, rule_kind) REFERENCES config_snapshots(id, kind) ON DELETE RESTRICT`
- `model_releases_scope_check`: `CHECK ((scope = ANY (ARRAY['URL_ONLY'::text, 'MULTI_INPUT'::text])))`
- `model_releases_scope_not_null`: `NOT NULL scope`
- `model_releases_status_check`: `CHECK ((status = ANY (ARRAY['STAGED'::text, 'ACTIVE'::text, 'RETIRED'::text])))`
- `model_releases_status_not_null`: `NOT NULL status`
- `model_releases_url_model_id_not_null`: `NOT NULL url_model_id`
- `model_releases_url_model_id_url_task_fkey`: `FOREIGN KEY (url_model_id, url_task) REFERENCES model_versions(id, task_type) ON DELETE RESTRICT`
- `model_releases_url_task_check`: `CHECK ((url_task = 'PHISHING_DETECTION'::task_type))`
- `model_releases_url_task_not_null`: `NOT NULL url_task`
- `model_releases_version_key`: `UNIQUE (version)`
- `model_releases_version_not_null`: `NOT NULL version`

## model_versions

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| task_type | task_type | Không | — |
| model_name | text | Không | — |
| version | text | Không | — |
| dataset_version_id | uuid | Không | — |
| feature_schema_version | text | Không | — |
| preprocessing_version | text | Không | — |
| runtime_manifest | jsonb | Không | — |
| artifact_reference | text | Không | — |
| checksum | character(64) | Không | — |
| row_version | integer | Không | 1 |
| status | text | Không | 'CANDIDATE'::text |
| created_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `model_versions_artifact_reference_not_null`: `NOT NULL artifact_reference`
- `model_versions_checksum_check`: `CHECK ((checksum ~ '^[0-9a-f]{64}$'::text))`
- `model_versions_checksum_not_null`: `NOT NULL checksum`
- `model_versions_created_at_not_null`: `NOT NULL created_at`
- `model_versions_dataset_version_id_not_null`: `NOT NULL dataset_version_id`
- `model_versions_dataset_version_id_task_type_fkey`: `FOREIGN KEY (dataset_version_id, task_type) REFERENCES dataset_versions(id, task_type) ON DELETE RESTRICT`
- `model_versions_feature_schema_version_not_null`: `NOT NULL feature_schema_version`
- `model_versions_id_not_null`: `NOT NULL id`
- `model_versions_id_task_type_key`: `UNIQUE (id, task_type)`
- `model_versions_model_name_not_null`: `NOT NULL model_name`
- `model_versions_pkey`: `PRIMARY KEY (id)`
- `model_versions_preprocessing_version_not_null`: `NOT NULL preprocessing_version`
- `model_versions_row_version_check`: `CHECK ((row_version > 0))`
- `model_versions_row_version_not_null`: `NOT NULL row_version`
- `model_versions_runtime_manifest_check`: `CHECK ((jsonb_typeof(runtime_manifest) = 'object'::text))`
- `model_versions_runtime_manifest_not_null`: `NOT NULL runtime_manifest`
- `model_versions_status_check`: `CHECK ((status = ANY (ARRAY['CANDIDATE'::text, 'EVALUATED'::text, 'APPROVED'::text, 'REJECTED'::text, 'RETIRED'::text])))`
- `model_versions_status_not_null`: `NOT NULL status`
- `model_versions_task_type_model_name_version_key`: `UNIQUE (task_type, model_name, version)`
- `model_versions_task_type_not_null`: `NOT NULL task_type`
- `model_versions_version_not_null`: `NOT NULL version`

## policies

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| version | text | Không | — |
| status | text | Không | 'DRAFT'::text |
| definition_json | jsonb | Không | — |
| checksum | character(64) | Không | — |
| approved_by | uuid | Có | — |
| approved_at | timestamp with time zone | Có | — |

Ràng buộc:

- `policies_approved_by_fkey`: `FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE RESTRICT`
- `policies_check`: `CHECK (((status <> 'APPROVED'::text) OR ((approved_by IS NOT NULL) AND (approved_at IS NOT NULL))))`
- `policies_checksum_check`: `CHECK ((checksum ~ '^[0-9a-f]{64}$'::text))`
- `policies_checksum_not_null`: `NOT NULL checksum`
- `policies_definition_json_check`: `CHECK ((jsonb_typeof(definition_json) = 'object'::text))`
- `policies_definition_json_not_null`: `NOT NULL definition_json`
- `policies_id_not_null`: `NOT NULL id`
- `policies_pkey`: `PRIMARY KEY (id)`
- `policies_status_check`: `CHECK ((status = ANY (ARRAY['DRAFT'::text, 'APPROVED'::text, 'RETIRED'::text])))`
- `policies_status_not_null`: `NOT NULL status`
- `policies_version_key`: `UNIQUE (version)`
- `policies_version_not_null`: `NOT NULL version`

## research_submissions

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| consent_id | uuid | Không | — |
| scan_id | uuid | Có | — |
| input_type | input_type | Không | — |
| sample_reference | text | Không | — |
| withdrawal_token_hash | bytea | Không | — |
| status | text | Không | 'PENDING'::text |
| created_at | timestamp with time zone | Không | now() |
| retention_until | timestamp with time zone | Không | — |

Ràng buộc:

- `research_submissions_check`: `CHECK ((retention_until > created_at))`
- `research_submissions_consent_id_fkey`: `FOREIGN KEY (consent_id) REFERENCES consents(id) ON DELETE RESTRICT`
- `research_submissions_consent_id_key`: `UNIQUE (consent_id)`
- `research_submissions_consent_id_not_null`: `NOT NULL consent_id`
- `research_submissions_created_at_not_null`: `NOT NULL created_at`
- `research_submissions_id_not_null`: `NOT NULL id`
- `research_submissions_input_type_not_null`: `NOT NULL input_type`
- `research_submissions_pkey`: `PRIMARY KEY (id)`
- `research_submissions_retention_until_not_null`: `NOT NULL retention_until`
- `research_submissions_sample_reference_not_null`: `NOT NULL sample_reference`
- `research_submissions_scan_id_fkey`: `FOREIGN KEY (scan_id) REFERENCES scan_requests(id) ON DELETE SET NULL`
- `research_submissions_status_check`: `CHECK ((status = ANY (ARRAY['PENDING'::text, 'REVIEWED'::text, 'WITHDRAWN'::text, 'EXPIRED'::text])))`
- `research_submissions_status_not_null`: `NOT NULL status`
- `research_submissions_withdrawal_token_hash_check`: `CHECK ((octet_length(withdrawal_token_hash) = 32))`
- `research_submissions_withdrawal_token_hash_key`: `UNIQUE (withdrawal_token_hash)`
- `research_submissions_withdrawal_token_hash_not_null`: `NOT NULL withdrawal_token_hash`

## scan_components

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| scan_id | uuid | Không | — |
| component_type | text | Không | — |
| ordinal | integer | Không | — |
| component_status | processing_status | Không | — |
| model_version_id | uuid | Có | — |
| task_type | task_type | Có | — |
| predicted_label | text | Có | — |
| score | double precision | Có | — |
| score_type | text | Có | — |
| calibration_version | text | Có | — |
| explanation_status | text | Không | — |
| error_code | text | Có | — |
| sanitized_summary | jsonb | Không | '{}'::jsonb |
| processing_time_ms | integer | Không | — |

Ràng buộc:

- `scan_components_check`: `CHECK (((model_version_id IS NULL) = (task_type IS NULL)))`
- `scan_components_check1`: `CHECK (((score IS NULL) = (score_type IS NULL)))`
- `scan_components_check2`: `CHECK (((score IS NULL) OR (model_version_id IS NOT NULL)))`
- `scan_components_check3`: `CHECK (((score_type <> 'CALIBRATED_PROBABILITY'::text) OR (((score >= (0)::double precision) AND (score <= (1)::double precision)) AND (calibration_version IS NOT NULL))))`
- `scan_components_check4`: `CHECK (((task_type IS NULL) OR ((component_type = 'URL'::text) AND (task_type = 'PHISHING_DETECTION'::task_type)) OR ((component_type = 'TEXT'::text) AND (task_type = ANY (ARRAY['SPAM_DETECTION'::task_type, 'SCAM_DETECTION'::task_type])))))`
- `scan_components_check5`: `CHECK (((predicted_label IS NULL) OR ((task_type = 'PHISHING_DETECTION'::task_type) AND (predicted_label = ANY (ARRAY['LEGITIMATE'::text, 'PHISHING'::text]))) OR ((task_type = 'SPAM_DETECTION'::task_type) AND (predicted_label = ANY (ARRAY['HAM'::text, 'SPAM_OR_SCAM'::text]))) OR ((task_type = 'SCAM_DETECTION'::task_type) AND (predicted_label = ANY (ARRAY['NON_SCAM'::text, 'SCAM'::text])))))`
- `scan_components_check6`: `CHECK (((predicted_label IS NULL) OR (task_type IS NOT NULL)))`
- `scan_components_component_status_not_null`: `NOT NULL component_status`
- `scan_components_component_type_check`: `CHECK ((component_type = ANY (ARRAY['URL'::text, 'TEXT'::text])))`
- `scan_components_component_type_not_null`: `NOT NULL component_type`
- `scan_components_explanation_status_check`: `CHECK ((explanation_status = ANY (ARRAY['AVAILABLE'::text, 'UNAVAILABLE'::text, 'NOT_APPLICABLE'::text])))`
- `scan_components_explanation_status_not_null`: `NOT NULL explanation_status`
- `scan_components_id_not_null`: `NOT NULL id`
- `scan_components_id_scan_id_key`: `UNIQUE (id, scan_id)`
- `scan_components_model_version_id_task_type_fkey`: `FOREIGN KEY (model_version_id, task_type) REFERENCES model_versions(id, task_type) ON DELETE RESTRICT`
- `scan_components_ordinal_check`: `CHECK ((ordinal >= 0))`
- `scan_components_ordinal_not_null`: `NOT NULL ordinal`
- `scan_components_pkey`: `PRIMARY KEY (id)`
- `scan_components_predicted_label_check`: `CHECK ((predicted_label = ANY (ARRAY['LEGITIMATE'::text, 'PHISHING'::text, 'HAM'::text, 'SPAM_OR_SCAM'::text, 'NON_SCAM'::text, 'SCAM'::text])))`
- `scan_components_processing_time_ms_check`: `CHECK ((processing_time_ms >= 0))`
- `scan_components_processing_time_ms_not_null`: `NOT NULL processing_time_ms`
- `scan_components_sanitized_summary_check`: `CHECK ((jsonb_typeof(sanitized_summary) = 'object'::text))`
- `scan_components_sanitized_summary_not_null`: `NOT NULL sanitized_summary`
- `scan_components_scan_id_component_type_ordinal_key`: `UNIQUE (scan_id, component_type, ordinal)`
- `scan_components_scan_id_fkey`: `FOREIGN KEY (scan_id) REFERENCES scan_requests(id) ON DELETE CASCADE`
- `scan_components_scan_id_not_null`: `NOT NULL scan_id`
- `scan_components_score_check`: `CHECK ((score <> ALL (ARRAY['NaN'::double precision, 'Infinity'::double precision, '-Infinity'::double precision])))`
- `scan_components_score_type_check`: `CHECK ((score_type = ANY (ARRAY['RAW_MARGIN'::text, 'MODEL_SCORE'::text, 'CALIBRATED_PROBABILITY'::text])))`

## scan_evidence

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| scan_id | uuid | Không | — |
| component_id | uuid | Không | — |
| indicator_id | uuid | Có | — |
| evidence_snapshot | jsonb | Không | — |
| checked_at | timestamp with time zone | Không | — |

Ràng buộc:

- `scan_evidence_checked_at_not_null`: `NOT NULL checked_at`
- `scan_evidence_component_id_not_null`: `NOT NULL component_id`
- `scan_evidence_component_id_scan_id_fkey`: `FOREIGN KEY (component_id, scan_id) REFERENCES scan_components(id, scan_id) ON DELETE CASCADE`
- `scan_evidence_evidence_snapshot_check`: `CHECK ((jsonb_typeof(evidence_snapshot) = 'object'::text))`
- `scan_evidence_evidence_snapshot_not_null`: `NOT NULL evidence_snapshot`
- `scan_evidence_id_not_null`: `NOT NULL id`
- `scan_evidence_indicator_id_fkey`: `FOREIGN KEY (indicator_id) REFERENCES threat_indicators(id) ON DELETE SET NULL`
- `scan_evidence_pkey`: `PRIMARY KEY (id)`
- `scan_evidence_scan_id_fkey`: `FOREIGN KEY (scan_id) REFERENCES scan_requests(id) ON DELETE CASCADE`
- `scan_evidence_scan_id_not_null`: `NOT NULL scan_id`

## scan_requests

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| owner_subject_id | uuid | Không | — |
| input_type | input_type | Không | — |
| processing_status | processing_status | Không | — |
| risk_level | risk_level | Không | — |
| release_id | uuid | Không | — |
| request_id | uuid | Không | — |
| created_at | timestamp with time zone | Không | now() |
| expires_at | timestamp with time zone | Không | — |

Ràng buộc:

- `scan_requests_check`: `CHECK ((expires_at > created_at))`
- `scan_requests_check1`: `CHECK (((processing_status = 'FAILED'::processing_status) = (risk_level = 'UNABLE_TO_ANALYZE'::risk_level)))`
- `scan_requests_check2`: `CHECK (((processing_status <> 'PARTIAL'::processing_status) OR (risk_level <> 'NO_SIGNIFICANT_RISK_FOUND'::risk_level)))`
- `scan_requests_created_at_not_null`: `NOT NULL created_at`
- `scan_requests_expires_at_not_null`: `NOT NULL expires_at`
- `scan_requests_id_not_null`: `NOT NULL id`
- `scan_requests_input_type_not_null`: `NOT NULL input_type`
- `scan_requests_owner_subject_id_fkey`: `FOREIGN KEY (owner_subject_id) REFERENCES subjects(id) ON DELETE RESTRICT`
- `scan_requests_owner_subject_id_not_null`: `NOT NULL owner_subject_id`
- `scan_requests_pkey`: `PRIMARY KEY (id)`
- `scan_requests_processing_status_not_null`: `NOT NULL processing_status`
- `scan_requests_release_id_fkey`: `FOREIGN KEY (release_id) REFERENCES model_releases(id) ON DELETE RESTRICT`
- `scan_requests_release_id_not_null`: `NOT NULL release_id`
- `scan_requests_request_id_key`: `UNIQUE (request_id)`
- `scan_requests_request_id_not_null`: `NOT NULL request_id`
- `scan_requests_risk_level_not_null`: `NOT NULL risk_level`

## scan_results

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| scan_id | uuid | Không | — |
| schema_version | text | Không | — |
| explanation_json | jsonb | Không | — |
| evidence_summary | jsonb | Không | — |
| coverage_json | jsonb | Không | — |
| total_processing_ms | integer | Không | — |

Ràng buộc:

- `scan_results_coverage_json_check`: `CHECK ((jsonb_typeof(coverage_json) = 'object'::text))`
- `scan_results_coverage_json_not_null`: `NOT NULL coverage_json`
- `scan_results_evidence_summary_check`: `CHECK ((jsonb_typeof(evidence_summary) = 'array'::text))`
- `scan_results_evidence_summary_not_null`: `NOT NULL evidence_summary`
- `scan_results_explanation_json_check`: `CHECK ((jsonb_typeof(explanation_json) = 'object'::text))`
- `scan_results_explanation_json_not_null`: `NOT NULL explanation_json`
- `scan_results_pkey`: `PRIMARY KEY (scan_id)`
- `scan_results_scan_id_fkey`: `FOREIGN KEY (scan_id) REFERENCES scan_requests(id) ON DELETE CASCADE`
- `scan_results_scan_id_not_null`: `NOT NULL scan_id`
- `scan_results_schema_version_not_null`: `NOT NULL schema_version`
- `scan_results_total_processing_ms_check`: `CHECK ((total_processing_ms >= 0))`
- `scan_results_total_processing_ms_not_null`: `NOT NULL total_processing_ms`

## sessions

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| subject_id | uuid | Không | — |
| token_hash | bytea | Không | — |
| csrf_hash | bytea | Không | — |
| created_at | timestamp with time zone | Không | now() |
| last_seen_at | timestamp with time zone | Không | now() |
| expires_at | timestamp with time zone | Không | — |
| revoked_at | timestamp with time zone | Có | — |

Ràng buộc:

- `sessions_check`: `CHECK ((expires_at > created_at))`
- `sessions_created_at_not_null`: `NOT NULL created_at`
- `sessions_csrf_hash_check`: `CHECK ((octet_length(csrf_hash) = 32))`
- `sessions_csrf_hash_not_null`: `NOT NULL csrf_hash`
- `sessions_expires_at_not_null`: `NOT NULL expires_at`
- `sessions_id_not_null`: `NOT NULL id`
- `sessions_last_seen_at_not_null`: `NOT NULL last_seen_at`
- `sessions_pkey`: `PRIMARY KEY (id)`
- `sessions_subject_id_fkey`: `FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE`
- `sessions_subject_id_not_null`: `NOT NULL subject_id`
- `sessions_token_hash_check`: `CHECK ((octet_length(token_hash) = 32))`
- `sessions_token_hash_key`: `UNIQUE (token_hash)`
- `sessions_token_hash_not_null`: `NOT NULL token_hash`

## subjects

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| user_id | uuid | Có | — |
| created_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `subjects_created_at_not_null`: `NOT NULL created_at`
- `subjects_id_not_null`: `NOT NULL id`
- `subjects_pkey`: `PRIMARY KEY (id)`
- `subjects_user_id_fkey`: `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT`
- `subjects_user_id_key`: `UNIQUE (user_id)`

## threat_indicators

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| indicator_type | text | Không | — |
| canonical_key_hash | bytea | Không | — |
| normalization_version | text | Không | — |
| source | text | Không | — |
| source_reference | text | Không | — |
| verified_at | timestamp with time zone | Không | — |
| expires_at | timestamp with time zone | Không | — |
| last_checked_at | timestamp with time zone | Có | — |
| status | text | Không | — |

Ràng buộc:

- `threat_indicators_canonical_key_hash_check`: `CHECK ((octet_length(canonical_key_hash) = 32))`
- `threat_indicators_canonical_key_hash_not_null`: `NOT NULL canonical_key_hash`
- `threat_indicators_check`: `CHECK ((expires_at > verified_at))`
- `threat_indicators_expires_at_not_null`: `NOT NULL expires_at`
- `threat_indicators_id_not_null`: `NOT NULL id`
- `threat_indicators_indicator_type_check`: `CHECK ((indicator_type = ANY (ARRAY['URL'::text, 'DOMAIN'::text])))`
- `threat_indicators_indicator_type_not_null`: `NOT NULL indicator_type`
- `threat_indicators_normalization_version_not_null`: `NOT NULL normalization_version`
- `threat_indicators_pkey`: `PRIMARY KEY (id)`
- `threat_indicators_source_indicator_type_normalization_versi_key`: `UNIQUE (source, indicator_type, normalization_version, canonical_key_hash)`
- `threat_indicators_source_not_null`: `NOT NULL source`
- `threat_indicators_source_reference_not_null`: `NOT NULL source_reference`
- `threat_indicators_status_check`: `CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'EXPIRED'::text, 'REVOKED'::text])))`
- `threat_indicators_status_not_null`: `NOT NULL status`
- `threat_indicators_verified_at_not_null`: `NOT NULL verified_at`

## training_jobs

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| requested_by | uuid | Không | — |
| dataset_version_id | uuid | Không | — |
| task_type | task_type | Không | — |
| status | job_status | Không | 'QUEUED'::job_status |
| config_json | jsonb | Không | — |
| lease_token_hash | bytea | Có | — |
| lease_expires_at | timestamp with time zone | Có | — |
| attempt | integer | Không | 0 |
| heartbeat_at | timestamp with time zone | Có | — |
| started_at | timestamp with time zone | Có | — |
| completed_at | timestamp with time zone | Có | — |
| result_model_id | uuid | Có | — |
| error_code | text | Có | — |
| created_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `training_jobs_attempt_check`: `CHECK ((attempt >= 0))`
- `training_jobs_attempt_not_null`: `NOT NULL attempt`
- `training_jobs_check`: `CHECK (((status <> 'RUNNING'::job_status) OR ((lease_token_hash IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (started_at IS NOT NULL))))`
- `training_jobs_check1`: `CHECK (((status <> 'SUCCEEDED'::job_status) OR ((result_model_id IS NOT NULL) AND (completed_at IS NOT NULL))))`
- `training_jobs_check2`: `CHECK (((status <> ALL (ARRAY['FAILED'::job_status, 'CANCELLED'::job_status])) OR (completed_at IS NOT NULL)))`
- `training_jobs_config_json_check`: `CHECK ((jsonb_typeof(config_json) = 'object'::text))`
- `training_jobs_config_json_not_null`: `NOT NULL config_json`
- `training_jobs_created_at_not_null`: `NOT NULL created_at`
- `training_jobs_dataset_version_id_not_null`: `NOT NULL dataset_version_id`
- `training_jobs_dataset_version_id_task_type_fkey`: `FOREIGN KEY (dataset_version_id, task_type) REFERENCES dataset_versions(id, task_type) ON DELETE RESTRICT`
- `training_jobs_id_not_null`: `NOT NULL id`
- `training_jobs_lease_token_hash_check`: `CHECK ((octet_length(lease_token_hash) = 32))`
- `training_jobs_pkey`: `PRIMARY KEY (id)`
- `training_jobs_requested_by_fkey`: `FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE RESTRICT`
- `training_jobs_requested_by_not_null`: `NOT NULL requested_by`
- `training_jobs_result_model_id_task_type_fkey`: `FOREIGN KEY (result_model_id, task_type) REFERENCES model_versions(id, task_type) ON DELETE RESTRICT`
- `training_jobs_status_not_null`: `NOT NULL status`
- `training_jobs_task_type_not_null`: `NOT NULL task_type`

## users

| Cột | Kiểu | NULL? | Mặc định |
|---|---|---|---|
| id | uuid | Không | gen_random_uuid() |
| email | text | Không | — |
| password_hash | text | Không | — |
| role | text | Không | — |
| status | text | Không | 'ACTIVE'::text |
| created_at | timestamp with time zone | Không | now() |
| updated_at | timestamp with time zone | Không | now() |

Ràng buộc:

- `users_created_at_not_null`: `NOT NULL created_at`
- `users_email_check`: `CHECK (((length(email) >= 3) AND (length(email) <= 254)))`
- `users_email_not_null`: `NOT NULL email`
- `users_id_not_null`: `NOT NULL id`
- `users_password_hash_not_null`: `NOT NULL password_hash`
- `users_pkey`: `PRIMARY KEY (id)`
- `users_role_check`: `CHECK ((role = ANY (ARRAY['ADMIN'::text, 'MEMBER'::text])))`
- `users_role_not_null`: `NOT NULL role`
- `users_status_check`: `CHECK ((status = ANY (ARRAY['ACTIVE'::text, 'DISABLED'::text])))`
- `users_status_not_null`: `NOT NULL status`
- `users_updated_at_not_null`: `NOT NULL updated_at`
