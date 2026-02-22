(ns singine.db.code-table
  "SQLite code table — the master data access layer for singine.

   Schema (single table, two columns — per proto/PLAN.md §4):
     CREATE TABLE IF NOT EXISTS code (key TEXT PRIMARY KEY, val TEXT);

   The code table is the minimal persistent state of any singine process.
   The philosophy: the fewer rows your program needs, the better you've
   thought it through. (N4 principle from ~/ws/today/00-WORK/N4)

   All public functions accept an auth map and are designed to be wrapped
   in singine.pos.lambda/govern for auth-gated governed lambda pipelines.

   DB path: resolved from c.prop key 'singine.db' or env SINGINE_DB.
   Default: ./db/singine.db (relative to execution directory)."
  (:require [singine.pos.lambda :as lam])
  (:import [singine.db CodeTable]
           [java.sql SQLException]))

;; ── Default DB path ──────────────────────────────────────────────────────────

(def ^:private default-db-path
  (or (System/getenv "SINGINE_DB") "./db/singine.db"))

(defn db-path
  "Resolve the database path. Checks env SINGINE_DB, else uses default."
  ([]       default-db-path)
  ([path]   (or path default-db-path)))

;; ── Connection factory ───────────────────────────────────────────────────────

(defn make-table
  "Create a CodeTable instance for the given db-path (or default)."
  ([]       (CodeTable. (db-path)))
  ([path]   (CodeTable. (db-path path))))

;; ── Init ─────────────────────────────────────────────────────────────────────

(defn init!
  "Create the code table and bootstrap rows if they don't exist.
   Idempotent — safe to call on every startup.
   Returns {:ok true :path db-path} or {:error msg}."
  ([]        (init! (db-path)))
  ([db-path]
   (try
     (let [ct (CodeTable. db-path)]
       (.mkdirs (java.io.File. (.getParent (java.io.File. db-path))))
       (.init ct)
       {:ok true :path db-path})
     (catch SQLException e
       {:ok false :error (.getMessage e) :path db-path}))))

;; ── Governed operations ──────────────────────────────────────────────────────

(defn set-val!
  "Governed: insert or replace key=val in the code table.
   Returns a zero-arg thunk (per govern contract).

   Usage:
     ((set-val! auth \"msg\" \"singine core test\")) ; => {:ok true :key :val}"
  [auth key val]
  (lam/govern auth
    (fn [t]
      (try
        (let [ct (make-table)]
          (.set ct key val)
          {:ok true :key key :val val
           :time (select-keys t [:iso :path])})
        (catch SQLException e
          {:ok false :key key :error (.getMessage e)})))))

(defn get-val
  "Governed: query a value by key from the code table.
   Returns a zero-arg thunk.

   Usage:
     ((get-val auth \"msg\")) ; => {:ok true :key \"msg\" :val \"singine core test\"}"
  [auth key]
  (lam/govern auth
    (fn [t]
      (try
        (let [ct  (make-table)
              val (.query ct key)]
          (if val
            {:ok true :key key :val val :time (select-keys t [:iso :path])}
            {:ok false :key key :error "not-found"}))
        (catch SQLException e
          {:ok false :key key :error (.getMessage e)})))))

(defn list-all
  "Governed: return all key/value pairs as a seq of {:key :val} maps."
  [auth]
  (lam/govern auth
    (fn [t]
      (try
        (let [ct   (make-table)
              rows (.listAll ct)]
          {:ok    true
           :rows  (mapv (fn [row] {:key (aget row 0) :val (aget row 1)}) rows)
           :count (count rows)
           :time  (select-keys t [:iso :path])})
        (catch SQLException e
          {:ok false :error (.getMessage e)})))))

(defn delete-key!
  "Governed: delete a key from the code table (no-op if not present)."
  [auth key]
  (lam/govern auth
    (fn [t]
      (try
        (let [ct (make-table)]
          (.delete ct key)
          {:ok true :key key :deleted true :time (select-keys t [:iso :path])})
        (catch SQLException e
          {:ok false :key key :error (.getMessage e)})))))

;; ── Convenience: direct (non-governed) access for boot sequence ──────────────

(defn raw-set!
  "Direct (non-governed) key/value insert — for use inside governed lambdas
   that have already passed auth. Returns true on success."
  [key val]
  (try
    (let [ct (make-table)]
      (.set ct key val)
      true)
    (catch SQLException _ false)))

(defn raw-get
  "Direct (non-governed) key lookup. Returns nil if not found."
  [key]
  (try
    (let [ct (make-table)]
      (.query ct key))
    (catch SQLException _ nil)))
