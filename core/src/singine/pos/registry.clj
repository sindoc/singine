(ns singine.pos.registry
  "POS opcode registry — registers BLKP, CATC, MCEL, GITP, IDNT, FORM, LOCP, IDPR
   in sinedge-engine.

   Requiring this namespace has a side effect: all eight opcodes are registered.
   The engine.clj requires this namespace at startup.

   Registration contract per sinedge.engine/register!:
     factory: (fn [auth args] -> zero-arg thunk)"
  (:require [singine.sinedge.engine      :as engine]
            [singine.pos.block-processor  :as bp]
            [singine.pos.category         :as catc]
            [singine.meta.cell            :as cell]
            [singine.pos.git-op           :as gitp]
            [singine.pos.identity         :as idnt]
            [singine.pos.form             :as form]
            [singine.pos.location         :as loc]
            [singine.pos.idp              :as idp]))

;; ── BLKP — Block Processor ───────────────────────────────────────────────────

(engine/register! "BLKP"
  (fn [auth args]
    (let [sindoc-path (or (:sindoc-path args) (get args "sindoc-path"))]
      (if sindoc-path
        (bp/process-blocks! auth sindoc-path)
        ;; No path: process inline content if supplied
        (let [content (or (:content args) (get args "content") "#lang singine\n</>")]
          (fn []
            (bp/process-blocks-str content)))))))

;; ── CATC — Category C ────────────────────────────────────────────────────────

(engine/register! "CATC"
  (fn [auth args]
    (let [processed-blocks (or (:processed-blocks args)
                               (get args "processed-blocks")
                               [])]
      (catc/activate! auth processed-blocks))))

;; ── MCEL — Meta Cell ─────────────────────────────────────────────────────────

(engine/register! "MCEL"
  (fn [auth args]
    (let [exec-dir (or (:exec-dir args) (get args "exec-dir"))]
      (if exec-dir
        (cell/wire-cwd! auth exec-dir)
        (cell/wire-cwd! auth)))))

;; ── GITP — Git Push ──────────────────────────────────────────────────────────

(engine/register! "GITP"
  (fn [auth args]
    (gitp/push-algorithm! auth args)))

;; ── IDNT — Identity ──────────────────────────────────────────────────────────

(engine/register! "IDNT"
  (fn [auth args]
    (idnt/authenticate! auth args)))

;; ── FORM — Form via Policy p + Template t ────────────────────────────────────

(engine/register! "FORM"
  (fn [auth args]
    (let [policy-map   (or (:policy args) (get args "policy"))
          template-src (or (:template args) (get args "template"))
          contact      (or (:contact args) (get args "contact"))]
      (form/emit-form! auth policy-map template-src contact))))

;; ── LOCP — Location Probe ─────────────────────────────────────────────────────

(engine/register! "LOCP"
  (fn [auth args]
    (let [location (or (:location args) (get args "location") "BE")
          opts     (select-keys args [:subject :dry-run :cc])]
      (loc/probe! auth location opts))))

;; ── IDPR — Identity Provider ─────────────────────────────────────────────────

(engine/register! "IDPR"
  (fn [auth args]
    (let [op   (or (:op args) (keyword (get args "op" "discover")))
          opts (dissoc args :op "op")]
      (idp/idpr! auth op opts))))

;; ── Registry summary ─────────────────────────────────────────────────────────

(defn registered-opcodes
  "Return the list of opcodes registered by this namespace."
  []
  ["BLKP" "CATC" "MCEL" "GITP" "IDNT" "FORM" "LOCP" "IDPR"])
