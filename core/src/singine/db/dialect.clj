(ns singine.db.dialect
  "HiveQL dialect translation service.
   defmulti dispatches on :dialect key.
   First target: :sqlite. Production: :hive (identity).
   Additional dialects can be added without modifying existing code."
  (:require [singine.db.schema :as schema]
            [singine.meta.root :as root]))

(defmulti translate-ddl
  "Translate HiveQL DDL to the target dialect.
   Dispatch value: {:dialect :sqlite} or {:dialect :hive} etc."
  :dialect)

(defmethod translate-ddl :sqlite [{:keys [ddl]}]
  (schema/hiveql->sqlite (or ddl schema/hiveql-ddl)))

(defmethod translate-ddl :hive [{:keys [ddl]}]
  ;; Hive is the canonical backend — DDL is returned unchanged
  (or ddl schema/hiveql-ddl))

(defmethod translate-ddl :default [{:keys [dialect ddl]}]
  (throw (ex-info (str "Unknown dialect: " dialect
                       ". Supported: :sqlite :hive")
                  {:dialect dialect})))

(defn translate
  "Convenience wrapper: translate hiveql-ddl to the configured default dialect.
   Reads default-dialect from root.xml."
  ([]          (translate schema/hiveql-ddl))
  ([ddl]       (translate-ddl {:dialect (root/default-dialect) :ddl ddl}))
  ([dialect ddl] (translate-ddl {:dialect dialect :ddl ddl})))
