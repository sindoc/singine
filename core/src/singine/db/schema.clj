(ns singine.db.schema
  "HiveQL DDL (source of truth) and the hiveql->sqlite transpiler.
   The transpiler is regex-based — no AST, fully auditable with sed."
  (:require [clojure.string :as str]
            [next.jdbc      :as jdbc]))

(def hiveql-ddl
  "Canonical HiveQL DDL for all four singine tables."
  "CREATE TABLE extension_probes (
     probe_id      STRING,
     probe_name    STRING,
     command_tpl   STRING,
     dimension     STRING,
     severity_map  STRING
   )
   STORED AS ORC
   TBLPROPERTIES ('table_type'='ICEBERG');

   CREATE TABLE extension_checks (
     check_id      STRING,
     extension     STRING,
     checked_at    TIMESTAMP,
     verdict       STRING,
     soap_doc      STRING
   )
   STORED AS ORC
   TBLPROPERTIES ('table_type'='ICEBERG');

   CREATE TABLE probe_results (
     result_id     STRING,
     check_id      STRING,
     probe_id      STRING,
     command_run   STRING,
     stdout        STRING,
     stderr        STRING,
     exit_code     INT,
     severity      STRING,
     finding       STRING
   )
   STORED AS ORC
   TBLPROPERTIES ('table_type'='ICEBERG');

   CREATE TABLE momentum_snapshots (
     snapshot_id   STRING,
     cell_path     STRING,
     instant       TIMESTAMP,
     kernel_name   STRING,
     entropy       DOUBLE,
     mass          DOUBLE,
     velocity      DOUBLE,
     momentum      DOUBLE
   )
   STORED AS ORC
   TBLPROPERTIES ('table_type'='ICEBERG');")

(defn hiveql->sqlite
  "Transpile HiveQL DDL to SQLite DDL (regex-based, no AST).

   sed equivalent for key transformations:
     sed 's/\\bSTRING\\b/TEXT/g'
     sed 's/\\bTIMESTAMP\\b/TEXT/g'
     sed 's/\\bINT\\b/INTEGER/g'
     sed 's/\\bDOUBLE\\b/REAL/g'
     sed 's/ STORED AS ORC//g'
     sed 's/ TBLPROPERTIES([^)]*)//'
     sed 's/CREATE TABLE/CREATE TABLE IF NOT EXISTS/g'"
  [^String hiveql]
  (-> hiveql
      (str/replace #"(?i)\bSTRING\b"                        "TEXT")
      (str/replace #"(?i)\bTIMESTAMP\b"                     "TEXT")
      (str/replace #"(?i)\bINT\b"                            "INTEGER")
      (str/replace #"(?i)\bDOUBLE\b"                         "REAL")
      (str/replace #"(?i)\s+STORED\s+AS\s+\w+"              "")
      (str/replace #"(?i)\s+TBLPROPERTIES\s*\([^)]*\)"      "")
      (str/replace #"(?i)CREATE\s+TABLE\s+"                  "CREATE TABLE IF NOT EXISTS ")))

(def sqlite-ddl
  "SQLite DDL derived from hiveql-ddl. Computed once at load time."
  (hiveql->sqlite hiveql-ddl))

(defn create-tables!
  "Execute all CREATE TABLE IF NOT EXISTS statements against conn.
   Idempotent — safe to call on every startup."
  [conn]
  (doseq [stmt (str/split sqlite-ddl #";")
          :let [s (str/trim stmt)]
          :when (not (str/blank? s))]
    (jdbc/execute! conn [(str s ";")])))
