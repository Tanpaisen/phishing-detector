"""Generate G0 OpenAPI design contracts, not runtime implementation."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages/contracts"
S = {}


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required, "additionalProperties": False}


def string(maximum=200): return {"type": "string", "maxLength": maximum}
def enum(*values): return {"type": "string", "enum": list(values)}
def ref(name): return {"$ref": "#/components/schemas/" + name}
def arr(item, maximum=100): return {"type": "array", "items": item, "maxItems": maximum}
def nullable(item): return {"anyOf": [item, {"type": "null"}]}
def integer(minimum=0): return {"type": "integer", "minimum": minimum}
UUID = {"type": "string", "format": "uuid"}
DATE = {"type": "string", "format": "date-time"}
BOOL = {"type": "boolean"}
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
TASK = enum("PHISHING_DETECTION", "SPAM_DETECTION", "SCAM_DETECTION")
STATE = enum("COMPLETED", "PARTIAL", "FAILED")
RISK = enum("VERIFIED_PHISHING", "HIGH_RISK", "NEEDS_REVIEW", "NO_SIGNIFICANT_RISK_FOUND", "UNABLE_TO_ANALYZE")
REVIEW = enum("PENDING", "IN_REVIEW", "ACCEPTED", "REJECTED", "INSUFFICIENT_EVIDENCE")
S["Error"] = obj({"request_id": UUID, "error": obj({"code": string(80), "message": string(500), "field": string(80)}, ["code", "message"])})
S["InternalError"] = obj({"error": obj({"code": string(80), "message": string(500)})})
S["InspectRequest"] = obj({"url": {"type": "string", "minLength": 1, "maxLength": 4096}})
S["Inspection"] = obj({
    "schema_version": {"const": "1.0"}, "stage": {"const": "URL_INSPECTION"},
    "model_loaded": {"const": False}, "preprocessing_version": {"const": "url-inspection-v1"},
    "resources": obj({"psl_sha256": HASH, "tldextract_version": string(), "idna_version": string(),
                      "python_version": string(), "unicode_version": string(), "private_suffixes_included": {"const": True}}),
    "url": obj({"normalized_url": string(20000), "scheme": enum("http", "https"), "hostname_input": string(4096),
                "hostname_ascii": string(253), "hostname_unicode": string(4096), "registered_domain": nullable(string(253)),
                "public_suffix": string(253), "subdomain": string(253),
                "port": nullable({"type": "integer", "minimum": 1, "maximum": 65535}),
                "is_ip": BOOL, "is_private_suffix": BOOL}),
    "features": obj({**{k: integer() for k in ("url_length", "hostname_length", "subdomain_count", "digit_count")},
                     **{k: BOOL for k in ("has_unicode_input", "has_unicode_hostname", "has_format_characters_in_hostname", "has_punycode_hostname", "has_query", "has_fragment")}}),
    "limitations": arr(string(500), 20),
})
S["InspectionResponse"] = copy.deepcopy(S["Inspection"])
S["InspectionResponse"]["properties"]["request_id"] = UUID
S["InspectionResponse"]["required"].append("request_id")
S["User"] = obj({"id": UUID, "email": {"type": "string", "format": "email"}, "role": enum("ADMIN", "MEMBER")})
S["Session"] = obj({"request_id": UUID, "csrf_token": string(128), "expires_at": DATE, "user": nullable(ref("User"))})
S["LoginRequest"] = obj({"email": {"type": "string", "format": "email", "maxLength": 254}, "password": {"type": "string", "minLength": 1, "maxLength": 256, "writeOnly": True}})
S["ScanURLRequest"] = obj({"url": {"type": "string", "minLength": 1, "maxLength": 4096}, "input_type": enum("URL", "QR_URL")})
S["ScanMessageRequest"] = obj({"text": {"type": "string", "minLength": 1, "maxLength": 10000}})
S["Signal"] = obj({"code": string(80), "message": string(500)})
S["Evidence"] = obj({"indicator_id": UUID, "source": string(200), "source_reference_id": string(200),
                      "verified_at": DATE, "expires_at": DATE, "checked_at": DATE, "match_type": enum("EXACT_URL", "DOMAIN_SIGNAL")})
S["Contribution"] = obj({"feature_name": string(80), "feature_value": {"type": ["number", "boolean"]}, "contribution": {"type": "number"}})
S["Explanation"] = obj({"method": enum("SHAP"), "output_space": enum("RAW_MARGIN", "PROBABILITY"),
                         "base_value": {"type": "number"}, "contributions": arr(ref("Contribution"), 5),
                         "remaining_contribution": {"type": "number"}, "explainer_version": string()})
model_common = {"model_version_id": UUID, "model_version": string(), "task_type": TASK,
                "predicted_label": enum("LEGITIMATE", "PHISHING", "HAM", "SPAM_OR_SCAM", "NON_SCAM", "SCAM")}
S["ModelOutput"] = {"oneOf": [
    obj({**model_common, "score": {"type": "number"}, "score_type": enum("RAW_MARGIN", "MODEL_SCORE"), "calibration_version": {"type": "null"}}),
    obj({**model_common, "score": {"type": "number", "minimum": 0, "maximum": 1}, "score_type": enum("CALIBRATED_PROBABILITY"), "calibration_version": {"type": "string", "minLength": 1, "maxLength": 200}})
]}
S["Component"] = obj({"component_id": UUID, "component_type": enum("URL", "TEXT"), "ordinal": integer(),
                       "status": STATE, "model_output": nullable(ref("ModelOutput")),
                       "explanation_status": enum("AVAILABLE", "UNAVAILABLE", "NOT_APPLICABLE"),
                       "model_explanation": nullable(ref("Explanation")), "rule_signals": arr(ref("Signal"), 30),
                       "verified_evidence": arr(ref("Evidence"), 20), "limitations": arr(string(500), 20),
                       "error_code": nullable(string(80)), "processing_time_ms": integer()})
S["Coverage"] = obj({"urls_detected": integer(), "urls_analyzed": integer(), "urls_failed": integer(), "text_analyzed": BOOL})
S["ScanResult"] = obj({"schema_version": {"const": "1.1"}, "request_id": UUID, "scan_id": UUID,
                       "input_type": enum("URL", "QR_URL", "MESSAGE"), "processing_status": STATE,
                       "risk_level": RISK, "release_version": string(), "policy_version": string(),
                       "components": arr(ref("Component"), 11), "coverage": ref("Coverage"),
                       "recommendation": string(1000), "created_at": DATE, "expires_at": DATE})
S["FeedbackRequest"] = obj({"scan_id": UUID, "feedback_type": enum("FALSE_POSITIVE", "FALSE_NEGATIVE", "OTHER"), "comment": string(2000)}, ["scan_id", "feedback_type"])
S["Feedback"] = obj({"id": UUID, "scan_id": nullable(UUID), "feedback_type": enum("FALSE_POSITIVE", "FALSE_NEGATIVE", "OTHER"),
                     "comment_redacted": string(2000), "status": REVIEW, "version": integer(1),
                     "review_reason": nullable(string(2000)), "created_at": DATE})
S["FeedbackReviewRequest"] = obj({"status": enum("IN_REVIEW", "ACCEPTED", "REJECTED", "INSUFFICIENT_EVIDENCE"), "reason": {"type": "string", "minLength": 1, "maxLength": 2000}, "sample_id": nullable(UUID)}, ["status", "reason"])
consent = obj({"purpose": {"const": "MODEL_RESEARCH"}, "accepted": {"const": True}, "policy_version": string(80)})
S["ResearchRequest"] = {"oneOf": [
    obj({"scan_id": UUID, "input_type": enum("URL", "QR_URL"), "sample_text": {"type": "string", "minLength": 1, "maxLength": 4096, "writeOnly": True}, "consent": consent}),
    obj({"scan_id": UUID, "input_type": enum("MESSAGE"), "sample_text": {"type": "string", "minLength": 1, "maxLength": 10000, "writeOnly": True}, "consent": consent})
]}
S["ResearchReceipt"] = obj({"id": UUID, "status": enum("PENDING"), "retention_until": DATE,
                           "withdrawal_token": {"type": "string", "minLength": 32, "maxLength": 128, "description": "Returned once. Save privately; never put in query string or logs."}})
S["BrandWrite"] = obj({"name": {"type": "string", "minLength": 1, "maxLength": 200}, "aliases": arr(string(200), 30), "category": nullable(string()), "verification_status": enum("PENDING", "VERIFIED", "RETIRED")})
S["Brand"] = obj({"id": UUID, **S["BrandWrite"]["properties"], "version": integer(1)})
S["DomainWrite"] = obj({"ascii_domain": {"type": "string", "minLength": 1, "maxLength": 253}, "include_subdomains": BOOL,
                       "source_url": nullable({"type": "string", "format": "uri", "maxLength": 4096}), "status": enum("PENDING", "VERIFIED", "RETIRED")})
S["BrandDomain"] = obj({"id": UUID, "brand_id": UUID, **S["DomainWrite"]["properties"], "version": integer(1), "verified_at": nullable(DATE)})
S["SampleLabelRequest"] = obj({"task_type": TASK, "verified_label": enum("LEGITIMATE", "PHISHING", "HAM", "SPAM_OR_SCAM", "NON_SCAM", "SCAM"), "source_reference": string(1000), "reason": string(2000)})
S["SampleLabel"] = obj({"id": UUID, "task_type": TASK, "verified_label": string(40), "version": integer(1), "verified_at": DATE})
S["Dataset"] = obj({"id": UUID, "version": string(), "task_type": TASK, "label_schema_version": string(), "status": enum("DRAFT", "FROZEN", "RETIRED"), "checksum": HASH})
S["Model"] = obj({"id": UUID, "version": string(), "model_name": string(), "task_type": TASK, "dataset_version_id": UUID,
                  "feature_schema_version": string(), "status": enum("CANDIDATE", "EVALUATED", "APPROVED", "REJECTED", "RETIRED"), "created_at": DATE, "row_version": integer(1)})
S["TrainingRequest"] = obj({"dataset_version_id": UUID, "task_type": TASK, "recipe": enum("URL_BASELINE_V1", "MESSAGE_BASELINE_V1"), "seed": {"type": "integer", "minimum": 0, "maximum": 2147483647}})
S["TrainingJob"] = obj({"id": UUID, "dataset_version_id": UUID, "task_type": TASK,
                        "status": enum("QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"),
                        "result_model_id": nullable(UUID), "error_code": nullable(string(80)), "created_at": DATE})
S["Release"] = obj({"id": UUID, "version": string(), "scope": enum("URL_ONLY", "MULTI_INPUT"),
                    "environment": enum("local", "test", "production"), "url_model_id": UUID,
                    "message_model_id": nullable(UUID), "policy_id": UUID,
                    "status": enum("STAGED", "ACTIVE", "RETIRED"), "row_version": integer(1), "activated_at": nullable(DATE)})
S["ReleaseAction"] = obj({"expected_active_release_id": nullable(UUID), "reason": {"type": "string", "minLength": 1, "maxLength": 2000}})
S["Report"] = obj({"from": DATE, "to": DATE, "total_scans": integer(), "failed_scans": integer(),
                   "risk_counts": obj({k: integer() for k in RISK["enum"]}),
                   "latency_p50_ms": nullable({"type": "number", "minimum": 0}), "latency_p95_ms": nullable({"type": "number", "minimum": 0})})
S["Evaluation"] = obj({"id": UUID, "model_version_id": UUID, "evaluation_dataset_id": UUID,
                       "evaluation_role": enum("VALIDATION", "PROMOTION", "FINAL_TEST", "OLD_HOLDOUT"), "sample_count": integer(1),
                       "metrics": obj({k: nullable({"type": "number", "minimum": 0, "maximum": 1}) for k in ("precision", "recall", "f1", "fpr", "average_precision", "brier_score")}), "evaluated_at": DATE})
for name in ("Feedback", "Brand", "BrandDomain", "Model", "Dataset", "TrainingJob", "Release", "Evaluation"):
    S[name + "List"] = obj({"items": arr(ref(name)), "next_cursor": nullable(string(512))})

SEC = {"SessionCookie": {"type": "apiKey", "in": "cookie", "name": "pd_session"},
       "CsrfToken": {"type": "apiKey", "in": "header", "name": "X-CSRF-Token"},
       "WithdrawalToken": {"type": "apiKey", "in": "header", "name": "X-Withdrawal-Token"},
       "AIServiceToken": {"type": "apiKey", "in": "header", "name": "X-Service-Token"},
       "WorkerToken": {"type": "apiKey", "in": "header", "name": "X-Worker-Token"},
       "ModelAdminToken": {"type": "apiKey", "in": "header", "name": "X-Model-Admin-Token"}}
SESSION = [{"SessionCookie": []}]
WRITE = [{"SessionCookie": [], "CsrfToken": []}]
PAGINATION = [{"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}}, {"name": "cursor", "in": "query", "schema": string(512)}]
IF_MATCH = {"name": "If-Match", "in": "header", "required": True, "schema": {"type": "string", "pattern": '^"[1-9][0-9]*"$'}, "description": 'Quoted row version, e.g. "1". Missing/invalid: 422; stale: 409.'}
IDEMPOTENCY = {"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string", "minLength": 16, "maxLength": 128}}


def response(code, schema=None):
    descriptions = {200: "Thành công (scan có thể PARTIAL).", 201: "Đã tạo.", 202: "Đã nhận tác vụ.", 204: "Hoàn tất, không có body."}
    value = {"description": descriptions.get(code, "Lỗi có cấu trúc; không phản chiếu dữ liệu đầu vào.")}
    if schema: value["content"] = {"application/json": {"schema": ref(schema)}}
    return value


def operation(paths, path, method, operation_id, summary, result=None, body=None, code=200,
              security=None, admin=False, parameters=None, implemented=False, errors=None):
    params = [] if parameters is None else copy.deepcopy(parameters)
    for name in ("id",):
        if "{" + name + "}" in path:
            params.append({"name": name, "in": "path", "required": True, "schema": UUID})
    value = {"operationId": operation_id, "summary": summary,
             "x-implementation-status": "implemented" if implemented else "planned",
             "security": security or [], "responses": {str(code): response(code, result)}}
    if admin: value["x-required-role"] = "ADMIN"
    if params: value["parameters"] = params
    if body: value["requestBody"] = {"required": True, "content": {"application/json": {"schema": ref(body)}}}
    if errors is None: errors = [400, 401, 403, 404, 409, 413, 415, 422, 429, 503, 504] if not implemented else [400,413,415,422,429,503,504]
    for e in errors: value["responses"][str(e)] = response(e, "Error")
    paths.setdefault(path, {})[method] = value


def build():
    paths = {}
    operation(paths, "/api/v1/url/inspect", "post", "inspectURL", "Kiểm tra cấu trúc URL, không tạo scan hoặc dự đoán", "InspectionResponse", "InspectRequest", implemented=True)
    operation(paths, "/api/v1/sessions", "post", "createGuestSession", "Tạo phiên khách cùng CSRF token; kiểm tra Origin và X-Client-Request", "Session", code=201,
              parameters=[{"name":"X-Client-Request","in":"header","required":True,"schema":{"const":"1"}}])
    operation(paths, "/api/v1/scans/url", "post", "scanURL", "Phân tích URL hoặc URL từ QR", "ScanResult", "ScanURLRequest", security=WRITE)
    operation(paths, "/api/v1/scans/message", "post", "scanMessage", "Phân tích nội dung và tối đa 10 URL duy nhất", "ScanResult", "ScanMessageRequest", security=WRITE)
    operation(paths, "/api/v1/scans/{id}", "get", "getScan", "Kết quả đã giảm thiểu, chỉ chủ sở hữu, chưa hết hạn", "ScanResult", security=SESSION)
    operation(paths, "/api/v1/scans/{id}", "delete", "deleteScan", "Xóa scan của chủ sở hữu và kết quả con", code=204, security=WRITE)
    operation(paths, "/api/v1/feedback", "post", "createFeedback", "Phản hồi không tự đổi nhãn", "Feedback", "FeedbackRequest", code=201, security=WRITE)
    operation(paths, "/api/v1/research-submissions", "post", "submitResearchSample", "Đồng ý riêng và gửi mẫu có kiểm duyệt", "ResearchReceipt", "ResearchRequest", code=201, security=WRITE)
    operation(paths, "/api/v1/research-submissions/{id}", "delete", "withdrawResearchSample", "Rút đồng ý theo chủ sở hữu hoặc receipt bí mật; lặp hợp lệ trả 204", code=204,
              security=WRITE + [{"WithdrawalToken": []}])
    operation(paths, "/api/v1/auth/login", "post", "login", "Đăng nhập admin, thay token phiên và CSRF", "Session", "LoginRequest", security=WRITE)
    operation(paths, "/api/v1/auth/logout", "post", "logout", "Thu hồi phiên phía server", code=204, security=WRITE)
    operation(paths, "/api/v1/auth/me", "get", "getSession", "Lấy thông tin phiên và CSRF hiện tại", "Session", security=SESSION)
    for segment, name in [("brands","Brand"),("feedback","Feedback"),("models","Model"),("datasets","Dataset"),("training-jobs","TrainingJob"),("releases","Release")]:
        operation(paths, f"/api/v1/admin/{segment}", "get", "list"+name, "Danh sách có phân trang", name+"List", security=SESSION, admin=True, parameters=PAGINATION)
    operation(paths, "/api/v1/admin/brands", "post", "createBrand", "Tạo thương hiệu", "Brand", "BrandWrite", code=201, security=WRITE, admin=True)
    operation(paths, "/api/v1/admin/brands/{id}", "patch", "updateBrand", "Thay thế các trường quản trị; không sửa snapshot model", "Brand", "BrandWrite", security=WRITE, admin=True, parameters=[IF_MATCH])
    operation(paths, "/api/v1/admin/brands/{id}/domains", "get", "listBrandDomains", "Tên miền của thương hiệu", "BrandDomainList", security=SESSION, admin=True, parameters=PAGINATION)
    operation(paths, "/api/v1/admin/brands/{id}/domains", "post", "createBrandDomain", "Thêm tên miền và nguồn xác minh", "BrandDomain", "DomainWrite", code=201, security=WRITE, admin=True)
    operation(paths, "/api/v1/admin/brand-domains/{id}", "patch", "updateBrandDomain", "Xác minh hoặc ngưng hiệu lực tên miền", "BrandDomain", "DomainWrite", security=WRITE, admin=True, parameters=[IF_MATCH])
    operation(paths, "/api/v1/admin/feedback/{id}", "patch", "reviewFeedback", "Kiểm duyệt, không tự huấn luyện", "Feedback", "FeedbackReviewRequest", security=WRITE, admin=True, parameters=[IF_MATCH])
    operation(paths, "/api/v1/admin/samples/{id}/label", "patch", "verifySampleLabel", "Gán nhãn mẫu đủ bằng chứng, ghi label history", "SampleLabel", "SampleLabelRequest", security=WRITE, admin=True, parameters=[IF_MATCH])
    operation(paths, "/api/v1/admin/models/{id}/evaluations", "get", "listModelEvaluations", "Báo cáo có nhãn; tách khỏi thống kê vận hành", "EvaluationList", security=SESSION, admin=True, parameters=PAGINATION)
    operation(paths, "/api/v1/admin/training-jobs", "post", "createTrainingJob", "Chỉ snapshot FROZEN và recipe cho phép", "TrainingJob", "TrainingRequest", code=202, security=WRITE, admin=True, parameters=[IDEMPOTENCY])
    operation(paths, "/api/v1/admin/training-jobs/{id}", "get", "getTrainingJob", "Trạng thái job", "TrainingJob", security=SESSION, admin=True)
    for action in ("activate", "rollback"):
        operation(paths, f"/api/v1/admin/releases/{{id}}/{action}", "post", action+"Release", "Kiểm tra release, gate đánh giá, warm load rồi đổi con trỏ", "Release", "ReleaseAction", security=WRITE, admin=True, parameters=[IF_MATCH])
    operation(paths, "/api/v1/admin/reports", "get", "getReports", "Thống kê vận hành, không suy diễn accuracy", "Report", security=SESSION, admin=True,
              parameters=[{"name": k,"in":"query","required":True,"schema":DATE} for k in ("from","to")])
    S["ReleaseCreate"] = obj({"version": string(), "scope": enum("URL_ONLY", "MULTI_INPUT"),
        "environment": enum("local", "test", "production"), "url_model_id": UUID,
        "message_model_id": nullable(UUID), "policy_id": UUID, "brand_snapshot_id": UUID,
        "psl_snapshot_id": UUID, "rule_snapshot_id": UUID})
    operation(paths, "/api/v1/admin/releases", "post", "createRelease", "Tạo release STAGED từ mô hình đã duyệt và snapshot đã đăng ký", "Release", "ReleaseCreate", code=201, security=WRITE, admin=True)
    S["ModelApproval"] = obj({"evaluation_id": UUID, "reason": {"type":"string","minLength":1,"maxLength":2000}})
    operation(paths, "/api/v1/admin/models/{id}/approve", "post", "approveModel", "Chỉ duyệt khi promotion gate đã đóng băng và đạt; không kích hoạt", "Model", "ModelApproval", security=WRITE, admin=True, parameters=[IF_MATCH])
    for endpoint in ("/api/v1/sessions", "/api/v1/auth/login"):
        method = paths[endpoint]["post"]
        success = "201" if endpoint.endswith("sessions") else "200"
        method["responses"][success]["headers"] = {"Set-Cookie": {"schema": {"type":"string"}, "description":"pd_session opaque secret; HttpOnly, SameSite=Lax, Path=/; Secure in HTTPS deployments; localhost development exception."}}
    for endpoint in ("/api/v1/scans/{id}", "/api/v1/research-submissions/{id}"):
        for method in paths[endpoint].values():
            method["responses"].pop("403", None)
    S["Health"] = obj({"status": {"const":"ok"}, "service": {"const":"phishing-detector-api"}})
    S["DatabaseHealth"] = obj({"status": {"const":"ok"}, "database": string()})
    S["AIHealth"] = obj({"status": {"const":"ok"}, "service": {"const":"phishing-detector-ai"}, "model_loaded": BOOL})
    S["GatewayAIHealth"] = obj({"status": {"const":"ok"}, "service": {"const":"phishing-detector-api"}, "ai": ref("AIHealth")})
    S["LegacyHealthError"] = obj({"status": {"const":"error"}, "message": string(500)})
    for path, schema in [("health","Health"),("health/db","DatabaseHealth"),("health/ai","GatewayAIHealth")]:
        operation(paths, "/api/v1/"+path, "get", schema, "Health probe hiện có; không chứng minh model sẵn sàng", schema, implemented=True, errors=[])
        if path!="health":
            paths["/api/v1/"+path]["get"]["responses"]["503"] = response(503,"LegacyHealthError")
        if path=="health/ai": paths["/api/v1/"+path]["get"]["responses"]["504"] = response(504,"LegacyHealthError")

    internal = {}
    operation(internal, "/internal/v1/url/inspect", "post", "internalInspectURL", "Offline inspection hiện có", "Inspection", "InspectRequest", security=[{"AIServiceToken":[]}], implemented=True, errors=[])
    internal["/internal/v1/url/inspect"]["post"]["responses"]["422"] = response(422,"InternalError")
    S["InternalAuthError"] = obj({"detail": string(500)})
    internal["/internal/v1/url/inspect"]["post"]["responses"]["401"] = response(401,"InternalAuthError")
    S["PredictURLRequest"] = obj({"request_id": UUID, "release_id": UUID, "deadline_at": DATE, "url": {"type":"string","minLength":1,"maxLength":4096}})
    S["PredictMessageRequest"] = obj({"request_id": UUID, "release_id": UUID, "deadline_at": DATE, "text": {"type":"string","minLength":1,"maxLength":10000}})
    S["PredictURLResponse"] = obj({"schema_version":{"const":"1.1"},"request_id":UUID,"release_id":UUID,"component":ref("Component"),
                                   "canonical_lookup_key":string(20000),"normalization_version":string(),"coverage_limitations":arr(string(500),20)})
    S["ExtractedURL"] = obj({"ordinal":integer(),"url":string(4096),"occurrences":arr(obj({"start":integer(),"end":integer()}),1000)})
    S["PredictMessageResponse"] = obj({"schema_version":{"const":"1.1"},"request_id":UUID,"release_id":UUID,"text_component":ref("Component"),"urls":arr(ref("ExtractedURL"),10),"coverage_limitations":arr(string(500),20)})
    for kind in ("URL","Message"):
        operation(internal, "/internal/v1/predict/"+kind.lower(), "post", "predict"+kind, "Suy luận trên release yêu cầu; chưa triển khai", "Predict"+kind+"Response", "Predict"+kind+"Request", security=[{"AIServiceToken":[]}])
    S["Ready"] = obj({"status":enum("ready","not_ready"),"release_id":nullable(UUID),"reason":nullable(string(80))})
    S["LegacyNotReady"] = obj({"status":{"const":"not_ready"},"reason":{"const":"MODEL_NOT_LOADED"}})
    operation(internal,"/internal/v1/health","get","internalHealth","Tiến trình Python hiện có","AIHealth",security=[{"AIServiceToken":[]}],implemented=True,errors=[])
    internal["/internal/v1/health"]["get"]["responses"]["401"]=response(401,"InternalAuthError")
    operation(internal,"/internal/v1/ready","get","internalReady","Hiện trả 503 MODEL_NOT_LOADED; future readiness theo release","Ready",security=[{"AIServiceToken":[]}],implemented=True,errors=[])
    internal["/internal/v1/ready"]["get"]["responses"]["503"]=response(503,"LegacyNotReady")
    internal["/internal/v1/ready"]["get"]["responses"]["401"]=response(401,"InternalAuthError")
    internal["/internal/v1/ready"]["get"]["responses"]["200"]["description"]="Planned only after model load; current implementation never returns 200."
    S["LoadReleaseRequest"]=obj({"release_id":UUID,"manifest_checksum":HASH})
    S["LoadedRelease"]=obj({"release_id":UUID,"manifest_checksum":HASH,"status":enum("LOADED")})
    operation(internal,"/internal/v1/releases/load","post","loadRelease","Warm-load approved immutable manifest; does not select active release","LoadedRelease","LoadReleaseRequest",security=[{"ModelAdminToken":[]}])
    S["ClaimRequest"]=obj({"worker_id":string(100)})
    S["Lease"]=obj({"job":ref("TrainingJob"),"lease_token":string(128),"lease_expires_at":DATE,"dataset_manifest_reference":string(1000)})
    S["Heartbeat"]=obj({"lease_token":string(128)})
    S["LeaseRenewal"]=obj({"lease_expires_at":DATE})
    S["CompleteJob"]= {"oneOf":[obj({"lease_token":string(128),"status":enum("SUCCEEDED"),"result_model_id":UUID}),obj({"lease_token":string(128),"status":enum("FAILED"),"error_code":string(80)})]}
    operation(internal,"/internal/v1/training-jobs/claim","post","claimJob","Node-owned job lease; 204 if queue empty","Lease","ClaimRequest",security=[{"WorkerToken":[]}])
    internal["/internal/v1/training-jobs/claim"]["post"]["responses"]["204"]=response(204)
    operation(internal,"/internal/v1/training-jobs/{id}/heartbeat","post","heartbeatJob","Renew valid current lease","LeaseRenewal","Heartbeat",security=[{"WorkerToken":[]}])
    operation(internal,"/internal/v1/training-jobs/{id}/complete","post","completeJob","Idempotent completion for same lease and payload; stale lease is 409","TrainingJob","CompleteJob",security=[{"WorkerToken":[]}])

    S["CandidateRegistration"] = obj({"job_id":UUID, "lease_token":string(128),
        "model_name":string(), "version":string(), "task_type":TASK, "dataset_version_id":UUID,
        "feature_schema_version":string(), "preprocessing_version":string(),
        "artifact_reference":string(1000), "checksum":HASH,
        "runtime_manifest":obj({"python_version":string(), "unicode_version":string(), "psl_sha256":HASH, "requirements_sha256":HASH})})
    operation(internal,"/internal/v1/model-candidates","post","registerCandidate", "Node validates current job lease, dataset/task and allowlisted artifact store, then creates CANDIDATE metadata", "Model", "CandidateRegistration", code=201,security=[{"WorkerToken":[]}])
    S["EvaluationRegistration"] = obj({"job_id":UUID,"lease_token":string(128),"model_version_id":UUID,
        "evaluation_dataset_id":UUID,"evaluation_role":enum("VALIDATION","PROMOTION","FINAL_TEST","OLD_HOLDOUT"),
        "split_manifest_checksum":HASH,"policy_id":nullable(UUID),"sample_count":integer(1),
        "metrics":S["Evaluation"]["properties"]["metrics"]})
    operation(internal,"/internal/v1/model-evaluations","post","registerEvaluation", "Append evaluation for candidate in current job; no auto approval", "Evaluation", "EvaluationRegistration",code=201,security=[{"WorkerToken":[]}])

    S["ModelOutput"]["allOf"] = [
        {"if":{"properties":{"task_type":{"const":task}},"required":["task_type"]},
         "then":{"properties":{"predicted_label":enum(*labels)}}}
        for task,labels in [("PHISHING_DETECTION",["LEGITIMATE","PHISHING"]),
                            ("SPAM_DETECTION",["HAM","SPAM_OR_SCAM"]),
                            ("SCAM_DETECTION",["NON_SCAM","SCAM"])]]
    S["Component"]["allOf"] = [
        {"if":{"properties":{"component_type":{"const":kind}}},
         "then":{"properties":{"model_output":{"anyOf":[{"type":"null"},
             {"type":"object","properties":{"task_type":enum(*tasks)}}]}}}}
        for kind,tasks in [("URL",["PHISHING_DETECTION"]),("TEXT",["SPAM_DETECTION","SCAM_DETECTION"])]]
    S["Component"]["allOf"].append({"if":{"properties":{"status":{"const":"FAILED"}}},
        "then":{"properties":{"model_output":{"type":"null"},"model_explanation":{"type":"null"},
                              "explanation_status":enum("UNAVAILABLE","NOT_APPLICABLE")}}})
    S["ScanResult"]["properties"]["processing_status"]=enum("COMPLETED","PARTIAL")
    S["ScanResult"]["properties"]["risk_level"]=enum("VERIFIED_PHISHING","HIGH_RISK","NEEDS_REVIEW","NO_SIGNIFICANT_RISK_FOUND")
    S["ScanResult"]["allOf"]=[{"if":{"properties":{"processing_status":{"const":"PARTIAL"}}},
        "then":{"properties":{"risk_level":enum("VERIFIED_PHISHING","HIGH_RISK","NEEDS_REVIEW")}}}]

    def document(title, port, path_map):
        return {"openapi":"3.1.0","info":{"title":title,"version":"g0-1.0","description":"Design baseline aligned with specification 1.1. x-implementation-status distinguishes planned APIs. Admin authorization and business invariants require implementation and tests, not just schema validation."},
                "servers":[{"url":f"http://127.0.0.1:{port}"}],"paths":path_map,"components":{"schemas":S,"securitySchemes":SEC}}
    OUT.mkdir(parents=True,exist_ok=True)
    public=document("Phishing Detector public API",3001,paths)
    inner=document("Phishing Detector internal APIs",8000,internal)
    for path,item in inner["paths"].items():
        if path.startswith(("/internal/v1/training-jobs", "/internal/v1/model-candidates", "/internal/v1/model-evaluations")):
            item["servers"]=[{"url":"http://127.0.0.1:3001","description":"Node internal listener/network; never expose through public proxy."}]
    for name,data in (("public.openapi.json",public),("internal.openapi.json",inner)):
        (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    print("Generated public and internal OpenAPI contracts.")


if __name__=="__main__": build()
