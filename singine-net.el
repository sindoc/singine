;; -*- lexical-binding: t -*-
;;
;; singine-net.el — Interactive Emacs interface for singine net / panel / presence / feeds
;;
;; Lexical binding is ON: lambdas genuinely close over their definition-time
;; environment.  Without `lexical-binding: t` Emacs uses dynamic scoping and
;; closures do not work — the header line is mandatory.
;;
;; Everything lives inside one top-level `let*` for encapsulation and
;; lexical scoping.  The `defun`s at the bottom are the only public surface;
;; they capture private lambdas and `state` through the closure.
;;
;; Usage:
;;   M-x load-file RET singine-net.el RET
;;   M-x singine-ensure-panel        ; start panel if not running
;;   M-x singine-run-tests           ; full test suite
;;   M-x singine-net-status          ; live service map
;;
;; Panel must be running for HTTP tests.  `singine-ensure-panel` starts it
;; automatically.  Or manually: make panel-serve (in the singine repo).

(require 'url)
(require 'json)
(require 'cl-lib)

(let* (
  ;; ── Configuration ───────────────────────────────────────────────────────────
  (panel-host    "127.0.0.1")
  (panel-port    9090)
  (panel-base    (format "http://%s:%d" panel-host panel-port))
  (panel-python  (expand-file-name
                  "~/ws/git/github/sindoc/singine/py/bin/python3"))
  (singine-bin   "singine")
  (domain-db     "/tmp/humble-idp.db")
  (bridge-db     "/tmp/sqlite.db")
  (buf-name      "*singine-net*")
  (test-buf-name "*singine-tests*")

  ;; ── Shared mutable state ────────────────────────────────────────────────────
  (state (let ((h (make-hash-table :test 'equal)))
           (puthash :presence-jwt    nil h)
           (puthash :presence-method nil h)
           (puthash :last-refresh    nil h)
           (puthash :test-results    '() h)
           (puthash :panel-process   nil h)
           h))

  ;; ── Panel liveness ──────────────────────────────────────────────────────────
  ;; TCP-knocks port 9090 without making an HTTP request.
  ;; Returns t immediately if port is open, nil if connection is refused.
  (panel-alive-p
   (lambda ()
     (condition-case _
         (let ((proc (open-network-stream
                      "singine-tcp-check" nil panel-host panel-port)))
           (delete-process proc)
           t)
       (error nil))))

  ;; Start the panel as an Emacs subprocess and wait up to MAX-WAIT-S seconds.
  (start-panel
   (lambda (&optional max-wait-s)
     (let ((wait (or max-wait-s 8))
           (proc (gethash :panel-process state)))
       ;; Kill any stale process we own
       (when (and proc (process-live-p proc))
         (delete-process proc))
       (let ((new-proc
              (start-process
               "singine-panel" "*singine-panel-log*"
               panel-python "-m" "singine.command"
               "panel" "serve"
               "--port" (number-to-string panel-port)
               "--bind" panel-host)))
         (puthash :panel-process new-proc state)
         ;; Poll until port opens or timeout
         (let ((deadline (+ (float-time) wait))
               (alive    nil))
           (while (and (not alive) (< (float-time) deadline))
             (sleep-for 0.4)
             (setq alive (funcall panel-alive-p)))
           alive)))))

  ;; Ensure panel is running; start it if not.  Returns t if panel is up.
  (ensure-panel
   (lambda ()
     (or (funcall panel-alive-p)
         (progn
           (message "singine panel not running — starting...")
           (funcall start-panel 10)))))

  ;; ── Buffer helpers ───────────────────────────────────────────────────────────
  (with-output-buf
   (lambda (name fn)
     (with-current-buffer (get-buffer-create name)
       (read-only-mode -1)
       (erase-buffer)
       (funcall fn)
       (goto-char (point-min))
       (view-mode 1))
     (display-buffer name)))

  (insert-header
   (lambda (title)
     (insert (propertize (concat "◈ " title "\n") 'face 'bold))
     (insert (make-string (+ 2 (length title)) ?─))
     (insert "\n\n")))

  (insert-row
   (lambda (key val &optional face)
     (insert (propertize (format "  %-24s" key) 'face 'font-lock-keyword-face))
     (insert (propertize (format "%s\n" val) 'face (or face 'default)))))

  ;; ── Shell helpers ─────────────────────────────────────────────────────────────
  (run-singine
   (lambda (&rest args)
     "Run singine ARGS; return (ok . stdout-string)."
     (let* ((cmd  (mapconcat #'shell-quote-argument (cons singine-bin args) " "))
            (out  (shell-command-to-string cmd)))
       (cons t out))))

  ;; ── HTTP helpers — all errors become nil, never signal ────────────────────────
  (http-get-json
   (lambda (path)
     (condition-case _err
         (let* ((url (concat panel-base path))
                (url-show-status nil)         ; suppress minibuffer noise
                (buf (url-retrieve-synchronously url t nil 5)))
           (when buf
             (with-current-buffer buf
               (goto-char (point-min))
               (when (re-search-forward "^$" nil t)
                 (condition-case _ (json-read) (error nil))))))
       (error nil))))

  (http-post-json
   (lambda (path payload)
     (condition-case _err
         (let* ((url-request-method        "POST")
                (url-request-extra-headers '(("Content-Type" . "application/json")))
                (url-request-data          (encode-coding-string
                                            (json-encode payload) 'utf-8))
                (url-show-status nil)
                (buf (url-retrieve-synchronously
                      (concat panel-base path) t nil 10)))
           (when buf
             (with-current-buffer buf
               (goto-char (point-min))
               (when (re-search-forward "^$" nil t)
                 (condition-case _ (json-read) (error nil))))))
       (error nil))))

  (http-get-text
   (lambda (path)
     (condition-case _err
         (let* ((url (concat panel-base path))
                (url-show-status nil)
                (buf (url-retrieve-synchronously url t nil 5)))
           (when buf
             (with-current-buffer buf
               (goto-char (point-min))
               (when (re-search-forward "^$" nil t)
                 (buffer-substring-no-properties (point) (point-max))))))
       (error nil))))

  ;; ── Domain helpers ───────────────────────────────────────────────────────────
  (assq-str  (lambda (key alist) (cdr (assq key alist))))
  (dot-for   (lambda (ok) (if ok "✓" "✗")))

  (service-reachable-p
   (lambda (svc) (eq (cdr (assq 'reachable svc)) t)))

  (format-services
   (lambda (services)
     (mapconcat
      (lambda (svc)
        (let* ((ok   (funcall service-reachable-p svc))
               (id   (or (cdr (assq 'id   svc)) "?"))
               (port (or (cdr (assq 'port svc)) 0))
               (kind (or (cdr (assq 'kind svc)) ""))
               (ms   (cdr (assq 'latency_ms svc)))
               (lbl  (or (cdr (assq 'label svc)) "")))
          (format "  %s  %-20s :%d  %-8s  %s  %s"
                  (funcall dot-for ok) id port kind
                  (if ms (format "%.1fms" ms) "—") lbl)))
      services "\n")))

  ;; ── Presence JWT ─────────────────────────────────────────────────────────────
  (store-presence!
   (lambda (result)
     (when result
       (puthash :presence-jwt    (cdr (assq 'jwt    result)) state)
       (puthash :presence-method (cdr (assq 'method result)) state)
       (puthash :last-refresh    (current-time)              state))))

  ;; ── Test framework ───────────────────────────────────────────────────────────
  ;;
  ;; A test is a plist: (:desc STRING :tags LIST :thunk LAMBDA)
  ;; Tags: :needs-panel  — skipped (not failed) when panel is down
  ;;       :needs-cli    — skipped when singine binary is absent
  ;;
  ;; run-test returns: (:desc STRING :pass BOOL :skip BOOL :err STRING-OR-NIL)

  (make-test
   (lambda (desc tags thunk)
     (list :desc desc :tags tags :thunk thunk)))

  (run-test
   (lambda (test panel-up cli-up)
     (let ((desc  (plist-get test :desc))
           (tags  (plist-get test :tags))
           (thunk (plist-get test :thunk)))
       (cond
        ((and (memq :needs-panel tags) (not panel-up))
         (list :desc desc :pass nil :skip t  :err "panel not running"))
        ((and (memq :needs-cli   tags) (not cli-up))
         (list :desc desc :pass nil :skip t  :err "singine not on PATH"))
        (t
         (condition-case err
             (list :desc desc :pass (not (null (funcall thunk))) :skip nil :err nil)
           (error
            (list :desc desc :pass nil :skip nil
                  :err (error-message-string err)))))))))

  (run-all-tests
   (lambda (tests)
     (let* ((panel-up (funcall panel-alive-p))
            (cli-up   (= 0 (call-process "which" nil nil nil singine-bin))))
       (mapcar (lambda (t) (funcall run-test t panel-up cli-up)) tests))))

  (format-test-results
   (lambda (results)
     (let ((pass (cl-count-if (lambda (r) (and (plist-get r :pass)
                                               (not (plist-get r :skip)))) results))
           (fail (cl-count-if (lambda (r) (and (not (plist-get r :pass))
                                               (not (plist-get r :skip)))) results))
           (skip (cl-count-if (lambda (r) (plist-get r :skip)) results)))
       (concat
        (mapconcat
         (lambda (r)
           (let ((icon (cond ((plist-get r :skip) "○")
                             ((plist-get r :pass) "✓")
                             (t                   "✗"))))
             (format "  %s  %s%s" icon (plist-get r :desc)
                     (if (plist-get r :err)
                         (format "\n       ↳ %s" (plist-get r :err)) ""))))
         results "\n")
        (format "\n\n  %d passed  /  %d failed  /  %d skipped  /  %d total"
                pass fail skip (length results))))))

  ;; ── Test suite ───────────────────────────────────────────────────────────────
  ;;
  ;; Tests tagged :needs-panel are skipped (○) when panel is not running.
  ;; Tests tagged :needs-cli   are skipped when singine binary is absent.
  ;; All nil-path guards are explicit — no implicit assumptions about shape.

  (tests
   (list

    ;; Panel liveness
    (funcall make-test "panel /api/health ok=true"
             '(:needs-panel)
             (lambda ()
               (let ((r (funcall http-get-json "/api/health")))
                 (and r (eq (cdr (assq 'ok r)) t)))))

    ;; Net services
    (funcall make-test "net services returns ≥ 1 service"
             '(:needs-panel)
             (lambda ()
               (let* ((r    (funcall http-get-json "/api/net/services"))
                      (svcs (and r (cdr (assq 'services r)))))
                 (and svcs (> (length svcs) 0)))))

    (funcall make-test "net summary total = 7"
             '(:needs-panel)
             (lambda ()
               (let* ((r   (funcall http-get-json "/api/net/services"))
                      (sum (and r (cdr (assq 'summary r))))
                      (tot (and sum (cdr (assq 'total sum)))))
                 (and tot (= tot 7)))))

    (funcall make-test "cdn-https service is reachable"
             '(:needs-panel)
             (lambda ()
               (let* ((r    (funcall http-get-json "/api/net/services"))
                      (svcs (and r (cdr (assq 'services r))))
                      (cdn  (and svcs (cl-find-if
                                       (lambda (s)
                                         (string= (cdr (assq 'id s)) "cdn-https"))
                                       svcs))))
                 (and cdn (eq (cdr (assq 'reachable cdn)) t)))))

    (funcall make-test "edge-site service is present in registry"
             '(:needs-panel)
             (lambda ()
               (let* ((r    (funcall http-get-json "/api/net/services"))
                      (svcs (and r (cdr (assq 'services r)))))
                 (cl-find-if (lambda (s)
                               (string= (cdr (assq 'id s)) "edge-site"))
                             (or svcs [])))))

    ;; Presence
    (funcall make-test "presence status endpoint responds"
             '(:needs-panel)
             (lambda ()
               (not (null (funcall http-get-json "/api/presence/status")))))

    (funcall make-test "presence status has :present key"
             '(:needs-panel)
             (lambda ()
               (let ((r (funcall http-get-json "/api/presence/status")))
                 (and r (assq 'present r)))))

    (funcall make-test "presence :present is a boolean"
             '(:needs-panel)
             (lambda ()
               (let* ((r (funcall http-get-json "/api/presence/status"))
                      (v (and r (cdr (assq 'present r)))))
                 (or (eq v t) (eq v :json-false) (eq v nil)))))

    ;; Routing
    (funcall make-test "routing table returns ≥ 5 routes"
             '(:needs-panel)
             (lambda ()
               (let* ((r      (funcall http-get-json "/api/net/routes"))
                      (routes (and r (cdr (assq 'routes r)))))
                 (and routes (>= (length routes) 5)))))

    (funcall make-test "/rest/ route targets collibra-dgc"
             '(:needs-panel)
             (lambda ()
               (let* ((r      (funcall http-get-json "/api/net/routes"))
                      (routes (and r (cdr (assq 'routes r))))
                      (rest   (and routes
                                   (cl-find-if
                                    (lambda (route)
                                      (string= (cdr (assq 'path_pattern route)) "/rest/"))
                                    routes))))
                 (and rest (string= (cdr (assq 'target_service rest)) "collibra-dgc")))))

    (funcall make-test "/panel/ route requires_presence=true"
             '(:needs-panel)
             (lambda ()
               (let* ((r      (funcall http-get-json "/api/net/routes"))
                      (routes (and r (cdr (assq 'routes r))))
                      (panel  (and routes
                                   (cl-find-if
                                    (lambda (route)
                                      (string= (cdr (assq 'path_pattern route)) "/panel/"))
                                    routes))))
                 (and panel (eq (cdr (assq 'requires_presence panel)) t)))))

    ;; Feeds
    (funcall make-test "Atom feed /feeds/activity.atom is valid XML"
             '(:needs-panel)
             (lambda ()
               (let ((body (funcall http-get-text "/feeds/activity.atom")))
                 (and body
                      (string-match-p "<?xml" body)
                      (string-match-p "<feed" body)
                      (string-match-p "Atom" body)))))

    (funcall make-test "RSS 1.0 /feeds/activity.rss is RDF-aligned"
             '(:needs-panel)
             (lambda ()
               (let ((body (funcall http-get-text "/feeds/activity.rss")))
                 (and body
                      (string-match-p "rdf:RDF" body)
                      (string-match-p "rss:channel" body)))))

    (funcall make-test "decisions Atom feed is served"
             '(:needs-panel)
             (lambda ()
               (let ((body (funcall http-get-text "/feeds/decisions.atom")))
                 (and body (string-match-p "<feed" body)))))

    ;; Vocabulary
    (funcall make-test "#knowyourai TTL contains HumanLedActivity"
             '(:needs-panel)
             (lambda ()
               (let ((body (funcall http-get-text "/vocab/knowyourai.ttl")))
                 (and body (string-match-p "HumanLedActivity" body)))))

    (funcall make-test "#knowyourai TTL contains requiresHumanPresence property"
             '(:needs-panel)
             (lambda ()
               (let ((body (funcall http-get-text "/vocab/knowyourai.ttl")))
                 (and body (string-match-p "requiresHumanPresence" body)))))

    (funcall make-test "#knowyourai TTL contains MachineLedActivity"
             '(:needs-panel)
             (lambda ()
               (let ((body (funcall http-get-text "/vocab/knowyourai.ttl")))
                 (and body (string-match-p "MachineLedActivity" body)))))

    ;; Invoke API
    (funcall make-test "invoke: singine net status --json succeeds"
             '(:needs-panel)
             (lambda ()
               (let ((r (funcall http-post-json "/api/net/invoke"
                                 '((cmd . ["singine" "net" "status" "--json"])))))
                 (and r (eq (cdr (assq 'ok r)) t)))))

    (funcall make-test "invoke: non-singine command is rejected (403)"
             '(:needs-panel)
             (lambda ()
               ;; Panel allows only singine/docker.  403 body has "error" key,
               ;; no "ok" key.  Pass if: nil, ok=:json-false, or error key present.
               (let ((r (funcall http-post-json "/api/net/invoke"
                                 '((cmd . ["bash" "-c" "echo pwned"])))))
                 (or (null r)
                     (eq (cdr (assq 'ok r)) :json-false)
                     (not (null (assq 'error r)))))))

    ;; CLI-only (no panel needed)
    (funcall make-test "singine CLI is on PATH"
             '(:needs-cli)
             (lambda ()
               (= 0 (call-process "which" nil nil nil singine-bin))))

    (funcall make-test "singine net ports produces port 443"
             '(:needs-cli)
             (lambda ()
               (string-match-p "443" (cdr (funcall run-singine "net" "ports")))))

    (funcall make-test "singine net route resolves /rest/ to collibra-dgc"
             '(:needs-cli)
             (lambda ()
               (string-match-p "collibra-dgc"
                                (cdr (funcall run-singine "net" "route"
                                              "--from" "/rest/v1/assets")))))

    (funcall make-test "singine presence status returns exit 0"
             '(:needs-cli)
             (lambda ()
               (= 0 (call-process singine-bin nil nil nil
                                   "presence" "status"))))

    ))

  ) ;; end let* bindings

  ;; ── Public defuns — each closes over the let* environment ─────────────────
  ;;
  ;; At this point lexical scope is active: every defun body can reference
  ;; the lambdas and `state` table defined above, just like a method
  ;; referencing instance fields in an OO language.

  (defun singine-ensure-panel ()
    "Ensure the singine net panel is running on port 9090.
Starts it automatically if not running.  Idempotent."
    (interactive)
    (if (funcall panel-alive-p)
        (message "singine panel already running at %s" panel-base)
      (message "Starting singine panel...")
      (if (funcall start-panel 10)
          (message "singine panel started at %s" panel-base)
        (message "Failed to start panel — check *singine-panel-log*"))))

  (defun singine-stop-panel ()
    "Stop the singine panel process started by singine-ensure-panel."
    (interactive)
    (let ((proc (gethash :panel-process state)))
      (if (and proc (process-live-p proc))
          (progn (delete-process proc)
                 (puthash :panel-process nil state)
                 (message "singine panel stopped"))
        (message "No panel process to stop"))))

  (defun singine-run-tests (&optional auto-start)
    "Run the singine-net test suite.
With prefix argument (C-u), auto-start the panel if not running."
    (interactive "P")
    (when (and auto-start (not (funcall panel-alive-p)))
      (message "Auto-starting panel...")
      (funcall start-panel 10))
    (let* ((panel-up (funcall panel-alive-p))
           (results  (funcall run-all-tests tests)))
      (puthash :test-results results state)
      (funcall with-output-buf test-buf-name
       (lambda ()
         (funcall insert-header
                  (format "singine-net test results  [%s]"
                          (format-time-string "%Y-%m-%d %H:%M:%S")))
         (unless panel-up
           (insert "  ⚠  Panel not running — HTTP tests skipped.\n")
           (insert (format "     Start: M-x singine-ensure-panel  or  make panel-serve\n"))
           (insert (format "     Then:  C-u M-x singine-run-tests  (auto-start)\n\n")))
         (insert (funcall format-test-results results))
         (insert "\n")))))

  (defun singine-net-status ()
    "Show live intranet service topology in *singine-net*."
    (interactive)
    (funcall with-output-buf buf-name
     (lambda ()
       (funcall insert-header "singine net — service status")
       (let* ((data    (funcall http-get-json "/api/net/services"))
              (summary (and data (cdr (assq 'summary  data))))
              (svcs    (and data (cdr (assq 'services data))))
              (docker  (and data (cdr (assq 'docker_containers data)))))
         (if (null data)
             (progn
               (insert "  ✗  Panel not running.\n\n")
               (insert "  Start:  M-x singine-ensure-panel\n")
               (insert (format "  Or:     make panel-serve   (in %s)\n"
                               "~/ws/git/github/sindoc/singine")))
           (funcall insert-row "total"       (cdr (assq 'total       summary)))
           (funcall insert-row "reachable"   (cdr (assq 'reachable   summary)))
           (funcall insert-row "unreachable" (cdr (assq 'unreachable summary)))
           (insert "\n")
           (insert (funcall format-services svcs))
           (insert "\n\n")
           (funcall insert-header "Docker containers")
           (if (zerop (length docker))
               (insert "  (no running containers)\n")
             (mapc (lambda (c)
                     (funcall insert-row
                              (cdr (assq 'name c))
                              (format "%-30s %s"
                                      (cdr (assq 'status c))
                                      (cdr (assq 'ports  c)))))
                   docker)))))))

  (defun singine-net-ports ()
    "Show port table in *singine-net*."
    (interactive)
    (funcall with-output-buf buf-name
     (lambda ()
       (funcall insert-header "singine net ports")
       (insert (cdr (funcall run-singine "net" "ports"))))))

  (defun singine-net-probe (service-id)
    "TCP-probe SERVICE-ID and show result in minibuffer."
    (interactive "sService ID (e.g. edge-site): ")
    (let ((r (funcall http-post-json "/api/net/probe"
                      `((service . ,service-id)))))
      (if r
          (message "%s  %s :%d  %s"
                   (funcall dot-for (eq (cdr (assq 'reachable r)) t))
                   service-id
                   (or (cdr (assq 'port  r)) 0)
                   (or (cdr (assq 'label r)) ""))
        (message "Panel not responding — run M-x singine-ensure-panel"))))

  (defun singine-panel-open ()
    "Open the control panel in the default browser."
    (interactive)
    (browse-url (concat panel-base "/"))
    (message "Opening %s" panel-base))

  (defun singine-presence-status ()
    "Show presence status in the minibuffer."
    (interactive)
    (let ((r (funcall http-get-json "/api/presence/status")))
      (if r
          (let* ((present (eq (cdr (assq 'present r)) t))
                 (method  (cdr (assq 'method r)))
                 (rem     (cdr (assq 'remaining_seconds r))))
            (message "Presence: %s  method: %s  remaining: %s"
                     (if present "✓ verified" "✗ not verified")
                     (or method "—")
                     (if rem (format "%dm%ds" (/ rem 60) (mod rem 60)) "—")))
        (message "Panel not responding"))))

  (defun singine-presence-verify ()
    "Trigger biometric / 1Password presence verification."
    (interactive)
    (message "Verifying presence — Touch ID or 1Password...")
    (let ((r (funcall http-post-json "/api/presence/verify" '())))
      (if r
          (if (eq (cdr (assq 'ok r)) t)
              (progn
                (funcall store-presence! r)
                (message "✓ Presence verified via %s  (agent: %s)"
                         (or (cdr (assq 'method r)) "?")
                         (or (cdr (assq 'agent  r)) "?")))
            (message "✗ Verification failed: %s"
                     (or (cdr (assq 'error r)) "unknown")))
        (message "Panel not responding"))))

  (defun singine-invoke (cmd-string)
    "Send CMD-STRING to the panel invoke API and display output."
    (interactive "sCommand (singine …): ")
    (let* ((parts (split-string (string-trim cmd-string)))
           (r     (funcall http-post-json "/api/net/invoke"
                           `((cmd . ,(vconcat parts))))))
      (funcall with-output-buf buf-name
       (lambda ()
         (funcall insert-header (format "invoke: %s" cmd-string))
         (if r
             (progn
               (insert (or (cdr (assq 'stdout r)) ""))
               (let ((err (cdr (assq 'stderr r))))
                 (when (and err (not (string= err "")))
                   (insert "\n[stderr]\n") (insert err))))
           (insert "Panel not responding — run M-x singine-ensure-panel\n"))))))

  (defun singine-feeds ()
    "Preview Atom and RSS 1.0 feeds in *singine-net*."
    (interactive)
    (funcall with-output-buf buf-name
     (lambda ()
       (funcall insert-header "singine feeds")
       (let ((atom (funcall http-get-text "/feeds/activity.atom"))
             (rss  (funcall http-get-text "/feeds/activity.rss")))
         (if atom
             (progn
               (dolist (pair `(("activity · Atom 1.0" . "/feeds/activity.atom")
                               ("activity · RSS 1.0"  . "/feeds/activity.rss")
                               ("decisions · Atom"    . "/feeds/decisions.atom")
                               ("decisions · RSS 1.0" . "/feeds/decisions.rss")))
                 (funcall insert-row (car pair)
                          (concat panel-base (cdr pair))))
               (insert "\n── Atom 1.0 (first 1200 chars) ──────────────────────\n\n")
               (insert (substring atom 0 (min 1200 (length atom))))
               (insert "\n\n── RSS 1.0 / RDF (first 1200 chars) ─────────────────\n\n")
               (insert (substring (or rss "") 0
                                  (min 1200 (length (or rss ""))))))
           (insert "Panel not responding — run M-x singine-ensure-panel\n"))))))

  (defun singine-knowyourai ()
    "Display the #knowyourai SKOS/OWL Turtle vocabulary."
    (interactive)
    (funcall with-output-buf buf-name
     (lambda ()
       (funcall insert-header "#knowyourai — SKOS/OWL vocabulary (Turtle)")
       (let ((body (funcall http-get-text "/vocab/knowyourai.ttl")))
         (if body (insert body)
           (insert "Panel not responding — run M-x singine-ensure-panel\n"))))))

  (defun singine-edge-status ()
    "Show edge stack status via the panel."
    (interactive)
    (funcall with-output-buf buf-name
     (lambda ()
       (funcall insert-header "singine edge status")
       (let ((r (funcall http-post-json "/api/net/invoke"
                         '((cmd . ["singine" "edge" "status" "--json"])))))
         (if r (insert (or (cdr (assq 'stdout r)) "(no output)"))
           (insert "Panel not responding\n"))))))

  (defun singine-test-last-results ()
    "Redisplay the most recent test results without re-running."
    (interactive)
    (let ((results (gethash :test-results state)))
      (if results
          (funcall with-output-buf test-buf-name
           (lambda ()
             (funcall insert-header "last test results (cached)")
             (insert (funcall format-test-results results))
             (insert "\n")))
        (message "No results yet — run M-x singine-run-tests"))))

  (message "singine-net.el loaded (%d tests) — M-x singine-run-tests  |  C-u M-x singine-run-tests (auto-start panel)"
           (length tests))

  ) ;; end let* closure

;; ── Quick REPL scratchpad (evaluate with C-x C-e) ────────────────────────────
;;
;; (singine-ensure-panel)                          ; start panel if needed
;; (singine-run-tests)                             ; run tests (panel must be up)
;; (singine-run-tests t)                           ; run tests + auto-start panel
;; (singine-net-status)                            ; live service map
;; (singine-net-ports)                             ; port table
;; (singine-net-probe "edge-site")                 ; TCP probe one service
;; (singine-presence-status)                       ; are you "there"?
;; (singine-presence-verify)                       ; Touch ID / 1Password
;; (singine-panel-open)                            ; open in browser
;; (singine-feeds)                                 ; Atom + RSS 1.0 preview
;; (singine-knowyourai)                            ; SKOS vocab (Turtle)
;; (singine-invoke "singine net route --from /rest/v1/assets")
;; (singine-edge-status)                           ; edge stack JSON
;; (singine-stop-panel)                            ; stop managed panel process
