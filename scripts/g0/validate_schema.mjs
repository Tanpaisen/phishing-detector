// In-memory PostgreSQL/WASM only. Does not read PG* settings or user databases.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { PGlite } from "@electric-sql/pglite";

const db = new PGlite();
const passed = [];
const q = (sql, args = []) => db.query(sql, args);
const id = async (sql, args = []) => (await q(sql + " RETURNING id", args)).rows[0].id;
async function rejects(name, sql, args, code) {
  await assert.rejects(q(sql, args), error => error.code === code);
  passed.push(name);
}
const hash = "a".repeat(64);
try {
  await db.exec(readFileSync(new URL("../../database/design/g0-schema.sql", import.meta.url), "utf8"));
  await q("SET search_path=app,public");
  const tables = (await q("SELECT count(*)::int n FROM information_schema.tables WHERE table_schema='app'")).rows[0].n;
  assert.equal(tables, 24);
  passed.push("DDL creates 24 tables in an isolated database");
  const user = await id("INSERT INTO users(email,password_hash,role) VALUES ('test@example.invalid','test-hash','ADMIN')");
  await rejects("email uniqueness is case-insensitive", "INSERT INTO users(email,password_hash,role) VALUES ('TEST@example.invalid','hash','ADMIN')", [], "23505");
  const owner = await id("INSERT INTO subjects DEFAULT VALUES");
  await rejects("sessions reject invalid secret hashes", "INSERT INTO sessions(subject_id,token_hash,csrf_hash,expires_at) VALUES ($1,decode('01','hex'),decode(repeat('ab',32),'hex'),now()+interval '1 day')", [owner], "23514");
  const dataset = await id("INSERT INTO dataset_versions(version,task_type,manifest_reference,split_manifest_reference,checksum,label_schema_version,status) VALUES ('url-v1','PHISHING_DETECTION','private:data','private:split',$1,'labels-v1','FROZEN')", [hash]);
  const smsDataset = await id("INSERT INTO dataset_versions(version,task_type,manifest_reference,split_manifest_reference,checksum,label_schema_version,status) VALUES ('sms-v1','SPAM_DETECTION','private:data','private:split',$1,'labels-v1','FROZEN')", [hash]);
  const modelSql = "INSERT INTO model_versions(task_type,model_name,version,dataset_version_id,feature_schema_version,preprocessing_version,runtime_manifest,artifact_reference,checksum,status) VALUES ($1,'baseline',$2,$3,'f1','p1','{}','private:model',$4,'APPROVED')";
  const urlModel = await id(modelSql, ["PHISHING_DETECTION","url-v1",dataset,hash]);
  const smsModel = await id(modelSql, ["SPAM_DETECTION","sms-v1",smsDataset,hash]);
  await rejects("model cannot use a dataset of another task", modelSql, ["PHISHING_DETECTION","bad",smsDataset,hash], "23503");
  const snapshots = [];
  for (const kind of ["BRANDS","PSL","RULES"]) snapshots.push(await id("INSERT INTO config_snapshots(kind,version,checksum,artifact_reference) VALUES ($1,'v1',$2,'private:config')",[kind,hash]));
  const policy = await id("INSERT INTO policies(version,status,definition_json,checksum,approved_by,approved_at) VALUES ('p1','APPROVED','{}',$1,$2,now())",[hash,user]);
  const releaseSql = "INSERT INTO model_releases(version,scope,url_model_id,policy_id,brand_snapshot_id,psl_snapshot_id,rule_snapshot_id,checksum,status,activated_at) VALUES ($1,'URL_ONLY',$2,$3,$4,$5,$6,$7,'ACTIVE',now())";
  const releaseArgs = ["r1",urlModel,policy,...snapshots,hash];
  const release = await id(releaseSql,releaseArgs);
  await rejects("only one active release per environment",releaseSql,["r2",...releaseArgs.slice(1)],"23505");
  await rejects("release snapshot kinds cannot be swapped",releaseSql.replace("'ACTIVE'","'STAGED'"),["r3",urlModel,policy,snapshots[1],snapshots[0],snapshots[2],hash],"23503");
  // Use STAGED to test the model FK independently of the unique active index.
  await rejects("URL release cannot load a spam model",releaseSql.replace("'ACTIVE'","'STAGED'"),["r4",smsModel,policy,...snapshots,hash],"23503");
  const scanSql="INSERT INTO scan_requests(owner_subject_id,input_type,processing_status,risk_level,release_id,request_id,expires_at) VALUES ($1,'URL',$2,$3,$4,gen_random_uuid(),now()+interval '1 day')";
  const scan=await id(scanSql,[owner,"COMPLETED","NO_SIGNIFICANT_RISK_FOUND",release]);
  const scan2=await id(scanSql,[owner,"COMPLETED","HIGH_RISK",release]);
  await rejects("partial result cannot be low risk",scanSql,[owner,"PARTIAL","NO_SIGNIFICANT_RISK_FOUND",release],"23514");
  await rejects("failed result cannot be low risk",scanSql,[owner,"FAILED","NO_SIGNIFICANT_RISK_FOUND",release],"23514");
  await rejects("completed result cannot be unable to analyze",scanSql,[owner,"COMPLETED","UNABLE_TO_ANALYZE",release],"23514");
  const componentSql="INSERT INTO scan_components(scan_id,component_type,ordinal,component_status,model_version_id,task_type,predicted_label,score,score_type,calibration_version,explanation_status,processing_time_ms) VALUES ($1,'URL',$2,'COMPLETED',$3,'PHISHING_DETECTION','LEGITIMATE',$4,$5,$6,'AVAILABLE',10)";
  const component=await id(componentSql,[scan,0,urlModel,0.1,"MODEL_SCORE",null]);
  await rejects("component ordinal is unique within scan and type",componentSql,[scan,0,urlModel,0.1,"MODEL_SCORE",null],"23505");
  await rejects("calibrated probability is bounded",componentSql,[scan,1,urlModel,1.2,"CALIBRATED_PROBABILITY","cal1"],"23514");
  await rejects("calibrated output requires calibration version",componentSql,[scan,1,urlModel,0.2,"CALIBRATED_PROBABILITY",null],"23514");
  await rejects("nonfinite model score is rejected",componentSql,[scan,1,urlModel,"NaN","MODEL_SCORE",null],"23514");
  await rejects("evidence cannot reference another scan component","INSERT INTO scan_evidence(scan_id,component_id,evidence_snapshot,checked_at) VALUES ($1,$2,'{}',now())",[scan2,component],"23503");
  await q("INSERT INTO scan_results(scan_id,schema_version,explanation_json,evidence_summary,coverage_json,total_processing_ms) VALUES ($1,'1.1','{}','[]','{}',10)",[scan]);
  const feedback=await id("INSERT INTO feedback(scan_id,submitter_subject_id,feedback_type) VALUES ($1,$2,'OTHER')",[scan,owner]);
  await rejects("terminal feedback requires review evidence","UPDATE feedback SET status='ACCEPTED' WHERE id=$1",[feedback],"23514");
  const consent=await id("INSERT INTO consents(subject_id,purpose,policy_version,expires_at) VALUES ($1,'MODEL_RESEARCH','v1',now()+interval '180 days')",[owner]);
  const submission=await id("INSERT INTO research_submissions(consent_id,scan_id,input_type,sample_reference,withdrawal_token_hash,retention_until) VALUES ($1,$2,'URL','private:sample',decode(repeat('cd',32),'hex'),now()+interval '180 days')",[consent,scan]);
  await rejects("user sample requires reviewer","INSERT INTO labeled_samples(input_type,task_type,sample_reference,fingerprint,verified_label,label_schema_version,source_type,source_reference,submission_id,verified_at) VALUES ('URL','PHISHING_DETECTION','private:sample',decode(repeat('ef',32),'hex'),'PHISHING','v1','USER_SUBMISSION','private:evidence',$1,now())",[submission],"23514");
  await rejects("job success requires result model","INSERT INTO training_jobs(requested_by,dataset_version_id,task_type,status,config_json,completed_at) VALUES ($1,$2,'PHISHING_DETECTION','SUCCEEDED','{}',now())",[user,dataset],"23514");
  await q("DELETE FROM scan_requests WHERE id=$1",[scan]);
  assert.equal((await q("SELECT count(*)::int n FROM scan_components WHERE scan_id=$1",[scan])).rows[0].n,0);
  assert.equal((await q("SELECT count(*)::int n FROM scan_results WHERE scan_id=$1",[scan])).rows[0].n,0);
  assert.equal((await q("SELECT scan_id FROM feedback WHERE id=$1",[feedback])).rows[0].scan_id,null);
  assert.equal((await q("SELECT scan_id FROM research_submissions WHERE id=$1",[submission])).rows[0].scan_id,null);
  passed.push("scan deletion cascades results but detaches feedback and research submissions");
  await rejects("referenced models cannot be deleted","DELETE FROM model_versions WHERE id=$1",[urlModel],"23001");
  const version=(await q("SELECT version() v")).rows[0].v;
  if (process.argv.includes("--write-catalog")) {
    const columns=(await q(`SELECT c.relname AS table_name,a.attname AS column_name,
      pg_catalog.format_type(a.atttypid,a.atttypmod) AS type,a.attnotnull AS not_null,
      pg_get_expr(d.adbin,d.adrelid) AS default_value
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
      LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
      WHERE n.nspname='app' AND c.relkind='r' ORDER BY c.relname,a.attnum`)).rows;
    const constraints=(await q(`SELECT c.relname AS table_name,co.conname AS name,
      pg_get_constraintdef(co.oid) AS definition FROM pg_constraint co
      JOIN pg_class c ON c.oid=co.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='app' ORDER BY c.relname,co.conname`)).rows;
    let md="# G0 — Từ điển dữ liệu sinh từ DDL\n\nNguồn: database/design/g0-schema.sql, thực thi trong PostgreSQL/WASM cô lập.\nKhông phải schema đã áp dụng vào database người dùng. NOT NULL và CHECK được ghi đúng theo catalog; các quyền nghiệp vụ xem 02-database-design.md.\n";
    for (const table of [...new Set(columns.map(c=>c.table_name))]) {
      md+=`\n## ${table}\n\n| Cột | Kiểu | NULL? | Mặc định |\n|---|---|---|---|\n`;
      for (const col of columns.filter(c=>c.table_name===table)) md+=`| ${col.column_name} | ${col.type} | ${col.not_null ? "Không" : "Có"} | ${col.default_value ?? "—"} |\n`;
      md+="\nRàng buộc:\n\n";
      for (const con of constraints.filter(c=>c.table_name===table)) md+=`- \`${con.name}\`: \`${con.definition}\`\n`;
    }
    writeFileSync(new URL("../../docs/g0/data-dictionary.md",import.meta.url),md);
  }
  console.log(JSON.stringify({engine:version,table_count:tables,checks_passed:passed.length,checks:passed},null,2));
} finally { await db.close(); }
