(ns singine.cap.machine
  "singine machine capability detection — governed fast-boot probe.

   Wraps CapabilityProbe.java with the singine lambda governance model.

   Usage:
     (detect! auth)        — full machine profile as a governed thunk
     (profile! auth)       — alias for detect!
     (deploy-order! auth)  — just the deploy-order list
     (cap! auth sub-cmd opts) — dispatcher

   CLI subcommands: detect | show | deploy | diff

   URN: urn:singine:cap:machine"
  (:require [singine.pos.lambda :as lam]
            [clojure.set        :as cset])
  (:import [singine.cap CapabilityProbe]))

;; ── java-map->clj ─────────────────────────────────────────────────────────────

(defn- java-map->clj
  "Convert a Java Map<String,Object> to a Clojure map with keyword keys.
   Recursively converts nested maps and lists."
  [m]
  (cond
    (instance? java.util.Map m)
    (reduce (fn [acc [k v]]
              (assoc acc (keyword k) (java-map->clj v)))
            {} m)
    (instance? java.util.List m)
    (mapv java-map->clj m)
    :else m))

;; ── detect! ───────────────────────────────────────────────────────────────────

(defn detect!
  "Run all capability probes for the current machine.
   Returns a governed thunk that yields a full machine profile map.

   The profile includes:
     :hostname, :user, :singine-root, :probed-at
     :java, :os, :git, :python, :clojure, :docker
     :package-managers, :latex, :ssh
     :capabilities (vector of keyword names)
     :deploy-order  (ordered vector: mail → broker → kg → render → checkin)
     :time           (governed timestamp)"
  [auth]
  (lam/govern auth
    (fn [t]
      (let [raw     (CapabilityProbe/probeAll)
            profile (java-map->clj raw)]
        ;; CapabilityProbe returns List<String> for capabilities/deploy-order.
        ;; Keywordize them so callers can use #{:mail} membership checks.
        (-> profile
            (update :capabilities #(mapv keyword %))
            (update :deploy-order  #(mapv keyword %))
            (assoc  :time (select-keys t [:iso :path])))))))

;; ── profile! ──────────────────────────────────────────────────────────────────

(def profile!
  "Alias for detect!."
  detect!)

;; ── deploy-order! ─────────────────────────────────────────────────────────────

(defn deploy-order!
  "Return only the deploy order vector for this machine.
   Returns a governed thunk: {:deploy-order [...] :hostname ... :time ...}"
  [auth]
  (lam/govern auth
    (fn [t]
      (let [raw     (CapabilityProbe/probeAll)
            profile (java-map->clj raw)]
        {:deploy-order (mapv keyword (:deploy-order profile))
         :hostname     (:hostname profile)
         :capabilities (mapv keyword (:capabilities profile))
         :time         (select-keys t [:iso :path])}))))

;; ── diff! ─────────────────────────────────────────────────────────────────────

(defn diff!
  "Compare this machine's capabilities with another profile map.
   Returns a governed thunk: {:added [...] :removed [...] :same [...] :time ...}

   other-profile: a capability map previously produced by detect!
   (can compare across machines by loading a saved JSON profile)"
  [auth other-profile]
  (lam/govern auth
    (fn [t]
      (let [raw     (CapabilityProbe/probeAll)
            this    (java-map->clj raw)
            this-c  (set (map keyword (:capabilities this)))
            other-c (set (map keyword (:capabilities other-profile)))]
        {:added    (vec (cset/difference this-c other-c))
         :removed  (vec (cset/difference other-c this-c))
         :same     (vec (cset/intersection this-c other-c))
         :hostname (:hostname this)
         :time     (select-keys t [:iso :path])}))))

;; ── cap! dispatcher ────────────────────────────────────────────────────────────

(defn cap!
  "CLI dispatcher for singine cap subcommands.

   Sub-commands:
     :detect  — full machine profile (alias: :show, :probe)
     :deploy  — deploy order only
     :diff    — diff with another profile (requires :other-profile in opts)

   Returns a governed thunk."
  [auth sub-cmd opts]
  (case sub-cmd
    (:detect :show :probe) (detect! auth)
    :deploy                (deploy-order! auth)
    :diff                  (diff! auth (get opts :other-profile {}))
    ;; Unknown sub-command
    (lam/govern auth
      (fn [t]
        {:ok      false
         :error   (str "Unknown cap subcommand: " sub-cmd)
         :available [:detect :show :probe :deploy :diff]
         :time    (select-keys t [:iso :path])}))))
