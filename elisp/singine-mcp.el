;;; singine-mcp.el --- Singine Collibra MCP explorer for Emacs -*- lexical-binding: t; -*-
;;
;; Provides tabulated-list views for domain assets, events, AI sessions,
;; transactions, and the cortex bridge (sources/entities/fragments), plus an
;; interactive SQL scratch buffer and server process management — all backed
;; by `singine mcp call'.
;;
;; Requires singine-runtime.el (for `singine-runtime--run-json' and env helpers).
;;
;; Usage:
;;   (load "~/ws/git/github/sindoc/singine/elisp/singine-mcp.el")
;;
;; Commands — domain DB (singine-mcp-db):
;;   M-x singine-mcp-seed          Seed the test database
;;   M-x singine-mcp-serve-sse     Start the MCP server (SSE) in a process buffer
;;   M-x singine-mcp-kill-server   Stop the running MCP server process
;;   M-x singine-mcp-assets        Browse domain assets (tabulated, choose type)
;;   M-x singine-mcp-events        Browse domain events (tabulated)
;;   M-x singine-mcp-sessions      Browse AI sessions (tabulated)
;;   M-x singine-mcp-transactions  Browse governed transactions (tabulated)
;;   M-x singine-mcp-refdata       Browse reference data (tabulated)
;;   M-x singine-mcp-sql           Interactive SELECT scratch buffer
;;   M-x singine-mcp-tables        List tables (minibuffer + describe)
;;   M-x singine-mcp-shell         Open a shell buffer with singine env set
;;
;; Commands — cortex bridge (singine-mcp-cortex-db, default /tmp/sqlite.db):
;;   M-x singine-mcp-cortex        Browse sources (tabulated); RET → entities
;;   M-x singine-mcp-entities      Browse entities (completing-read source)
;;   M-x singine-mcp-search        Fragment full-text search → detail buffer
;;   M-x singine-mcp-cortex-sql    SQL scratch pre-pointed at cortex DB
;;
;; Keybindings (prefix C-c s m — singine mcp):
;;   C-c s m s   singine-mcp-seed
;;   C-c s m S   singine-mcp-serve-sse
;;   C-c s m k   singine-mcp-kill-server
;;   C-c s m a   singine-mcp-assets
;;   C-c s m e   singine-mcp-events
;;   C-c s m i   singine-mcp-sessions
;;   C-c s m t   singine-mcp-transactions
;;   C-c s m r   singine-mcp-refdata
;;   C-c s m q   singine-mcp-sql
;;   C-c s m T   singine-mcp-tables
;;   C-c s m !   singine-mcp-shell
;;   C-c s m c   singine-mcp-cortex      (cortex sources browser)
;;   C-c s m /   singine-mcp-search      (fragment full-text search)
;;   C-c s m Q   singine-mcp-cortex-sql  (SQL scratch on cortex DB)

(require 'json)
(require 'tabulated-list)
(require 'compile)
(require 'singine-runtime)  ; for singine-runtime--run, singine-runtime-command, env

;;; ── Configuration ─────────────────────────────────────────────────────────

(defgroup singine-mcp nil
  "Singine Collibra MCP explorer."
  :group 'tools
  :prefix "singine-mcp-")

(defcustom singine-mcp-db "/tmp/singine-mcp-test.db"
  "Path to the SQLite database used by the MCP tools."
  :type 'string
  :group 'singine-mcp)

(defcustom singine-mcp-cortex-db "/tmp/sqlite.db"
  "Path to the cortex bridge SQLite database (sources/entities/fragments schema).
Default is the live bridge at /tmp/sqlite.db."
  :type 'string
  :group 'singine-mcp)

(defcustom singine-mcp-sse-port 8765
  "HTTP port for the SSE transport."
  :type 'integer
  :group 'singine-mcp)

;;; ── Core helpers ──────────────────────────────────────────────────────────

(defun singine-mcp--call (tool &optional params)
  "Call MCP TOOL with PARAMS alist; return parsed JSON or nil on error.
PARAMS is an alist of keyword→value pairs encoded as a JSON object."
  (let* ((params-json (if params
                          (json-encode (let ((ht (make-hash-table :test 'equal)))
                                         (dolist (kv params ht)
                                           (puthash (car kv) (cdr kv) ht))))
                        "{}"))
         (output (singine-runtime--run
                  "mcp" "call" tool
                  "--db" singine-mcp-db
                  "--params" params-json))
         (json-object-type 'alist)
         (json-array-type  'list)
         (json-key-type    'symbol))
    (condition-case err
        (json-read-from-string output)
      (error
       (message "singine-mcp: JSON error calling %s: %s\n%s"
                tool (error-message-string err) output)
       nil))))

(defun singine-mcp--call-list (tool &optional params)
  "Like `singine-mcp--call' but always return a list (nil → empty list)."
  (let ((result (singine-mcp--call tool params)))
    (cond ((listp result) result)
          (t (message "singine-mcp: unexpected result type from %s" tool)
             nil))))

(defun singine-mcp--trunc (str maxlen)
  "Truncate STR to MAXLEN characters, appending … if needed."
  (if (> (length str) maxlen)
      (concat (substring str 0 (1- maxlen)) "…")
    str))

;;; ── Asset types ───────────────────────────────────────────────────────────

(defconst singine-mcp--asset-types
  '("BusinessTerm" "BusinessCapability" "BusinessProcess" "DataCategory")
  "Valid Collibra asset types for `list_assets'.")

;;; ── Domain Assets buffer ─────────────────────────────────────────────────

(defvar singine-mcp-assets-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map tabulated-list-mode-map)
    (define-key map (kbd "g")   #'singine-mcp-assets-refresh)
    (define-key map (kbd "t")   #'singine-mcp-assets-change-type)
    (define-key map (kbd "RET") #'singine-mcp-assets-show-at-point)
    (define-key map (kbd "q")   #'quit-window)
    map)
  "Keymap for `singine-mcp-assets-mode'.

  g   Refresh
  t   Change asset type
  RET Show full record in *singine-mcp-detail* buffer
  q   Quit")

(define-derived-mode singine-mcp-assets-mode tabulated-list-mode "Singine:Assets"
  "Major mode for browsing Collibra domain assets."
  (setq tabulated-list-format
        [("Name"         32 t)
         ("CollibraID"   14 t)
         ("Type"         22 t)
         ("Owner/Unit"   16 nil)
         ("Definition"    0 nil)])
  (setq tabulated-list-sort-key '("Name" . nil))
  (tabulated-list-init-header))

(defvar-local singine-mcp-assets--type "BusinessTerm")
(defvar-local singine-mcp-assets--data nil)

(defun singine-mcp-assets--col-for-type (type)
  "Return the owner/unit column name for asset TYPE."
  (pcase type
    ("BusinessTerm"       "business_unit")
    ("BusinessCapability" "owner")
    ("BusinessProcess"    "owner")
    ("DataCategory"       "parent_id")
    (_ "owner")))

(defun singine-mcp-assets--text-col (type)
  "Return the definition/description column name for asset TYPE."
  (if (string= type "BusinessTerm") "definition" "description"))

(defun singine-mcp-assets--make-entries (rows asset-type)
  "Convert ROWS (list of alists) to tabulated-list entries for ASSET-TYPE."
  (let ((owner-col  (singine-mcp-assets--col-for-type asset-type))
        (text-col   (intern (singine-mcp-assets--text-col asset-type))))
    (mapcar
     (lambda (row)
       (let* ((id      (or (alist-get 'id   row) ""))
              (name    (or (alist-get 'name row) ""))
              (cid     (or (alist-get 'collibra_id   row) ""))
              (ctype   (or (alist-get 'collibra_type row) ""))
              (owner   (or (alist-get (intern owner-col) row) ""))
              (defn    (or (alist-get text-col row) ""))
              (face    (if (string-empty-p cid) 'default 'font-lock-string-face)))
         (list id
               (vector
                (propertize (singine-mcp--trunc name 32)  'face face)
                (propertize (singine-mcp--trunc cid 14)   'face 'font-lock-comment-face)
                (propertize ctype 'face 'font-lock-type-face)
                (propertize (singine-mcp--trunc owner 16) 'face 'default)
                (propertize (singine-mcp--trunc defn 60)  'face 'font-lock-doc-face)))))
     rows)))

(defun singine-mcp-assets-refresh ()
  "Reload and redisplay assets for the current type."
  (interactive)
  (let ((rows (singine-mcp--call-list "list_assets"
                                      `(("asset_type" . ,singine-mcp-assets--type)
                                        ("limit" . 200)))))
    (setq singine-mcp-assets--data rows
          tabulated-list-entries
          (singine-mcp-assets--make-entries rows singine-mcp-assets--type))
    (tabulated-list-print t)
    (message "Singine Assets: %d %s records  (t=change type, RET=detail)"
             (length rows) singine-mcp-assets--type)))

(defun singine-mcp-assets-change-type (type)
  "Switch the asset TYPE displayed in this buffer."
  (interactive
   (list (completing-read "Asset type: " singine-mcp--asset-types nil t)))
  (setq singine-mcp-assets--type type)
  (rename-buffer (format "*Singine Assets: %s*" type) t)
  (singine-mcp-assets-refresh))

(defun singine-mcp-assets-show-at-point ()
  "Display the full JSON record for the asset on the current line."
  (interactive)
  (let* ((id   (tabulated-list-get-id))
         (row  (when id
                 (singine-mcp--call "get_asset"
                                    `(("asset_type" . ,singine-mcp-assets--type)
                                      ("asset_id" . ,id))))))
    (if (null row)
        (message "No asset at point")
      (singine-mcp--show-json row (format "Asset: %s" id)))))

;;; ── Domain Events buffer ─────────────────────────────────────────────────

(defvar singine-mcp-events-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map tabulated-list-mode-map)
    (define-key map (kbd "g")   #'singine-mcp-events-refresh)
    (define-key map (kbd "f")   #'singine-mcp-events-filter)
    (define-key map (kbd "F")   #'singine-mcp-events-clear-filter)
    (define-key map (kbd "q")   #'quit-window)
    map)
  "Keymap for `singine-mcp-events-mode'.

  g   Refresh
  f   Filter by event type
  F   Clear filter
  q   Quit")

(define-derived-mode singine-mcp-events-mode tabulated-list-mode "Singine:Events"
  "Major mode for browsing domain events."
  (setq tabulated-list-format
        [("Type"       36 t)
         ("Subject"    36 nil)
         ("Actor"      10 nil)
         ("OccurredAt" 28 t)])
  (setq tabulated-list-sort-key '("OccurredAt" . t))
  (tabulated-list-init-header))

(defvar-local singine-mcp-events--filter nil)

(defconst singine-mcp--event-types
  '("CATALOG_ASSET_REGISTERED" "CATALOG_ASSET_UPDATED" "CATALOG_ASSET_DEPRECATED"
    "AI_SESSION_STARTED" "AI_SESSION_CLOSED" "AI_SESSION_FLUSHED"
    "GOVERNANCE_MANDATE_ISSUED" "GOVERNANCE_MANDATE_EXPIRED"
    "GOVERNANCE_POLICY_EVALUATED" "GOVERNANCE_DECISION_RECORDED"
    "IDENTITY_LOGIN" "IDENTITY_LOGOUT"))

(defun singine-mcp-events--make-entries (rows)
  "Convert event ROWS to tabulated-list entries."
  (mapcar
   (lambda (row)
     (let* ((eid    (or (alist-get 'event_id   row) ""))
            (etype  (or (alist-get 'event_type row) ""))
            (subj   (or (alist-get 'subject_id row) ""))
            (actor  (or (alist-get 'actor_id   row) ""))
            (at     (or (alist-get 'occurred_at row) ""))
            (face   (cond ((string-prefix-p "CATALOG" etype)    'font-lock-string-face)
                          ((string-prefix-p "AI" etype)         'font-lock-keyword-face)
                          ((string-prefix-p "GOVERNANCE" etype) 'font-lock-warning-face)
                          (t 'default))))
       (list eid
             (vector
              (propertize etype 'face face)
              (propertize (singine-mcp--trunc subj 36) 'face 'font-lock-comment-face)
              (propertize actor 'face 'default)
              (propertize at    'face 'font-lock-doc-face)))))
   rows))

(defun singine-mcp-events-refresh ()
  "Reload domain events."
  (interactive)
  (let* ((params (when singine-mcp-events--filter
                   `(("event_type" . ,singine-mcp-events--filter))))
         (rows   (singine-mcp--call-list "list_domain_events"
                                         (append params '(("limit" . 200))))))
    (setq tabulated-list-entries (singine-mcp-events--make-entries rows))
    (tabulated-list-print t)
    (message "Domain events: %d records%s  (f=filter F=clear)"
             (length rows)
             (if singine-mcp-events--filter
                 (format "  [%s]" singine-mcp-events--filter)
               ""))))

(defun singine-mcp-events-filter (event-type)
  "Show only events of EVENT-TYPE."
  (interactive
   (list (completing-read "Event type: " singine-mcp--event-types nil nil)))
  (setq singine-mcp-events--filter event-type)
  (singine-mcp-events-refresh))

(defun singine-mcp-events-clear-filter ()
  "Remove event type filter."
  (interactive)
  (setq singine-mcp-events--filter nil)
  (singine-mcp-events-refresh))

;;; ── AI Sessions buffer ───────────────────────────────────────────────────

(defvar singine-mcp-sessions-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map tabulated-list-mode-map)
    (define-key map (kbd "g")   #'singine-mcp-sessions-refresh)
    (define-key map (kbd "RET") #'singine-mcp-sessions-show-at-point)
    (define-key map (kbd "q")   #'quit-window)
    map)
  "Keymap for `singine-mcp-sessions-mode'.

  g   Refresh
  RET Show session detail (interactions + mandates)
  q   Quit")

(define-derived-mode singine-mcp-sessions-mode tabulated-list-mode "Singine:Sessions"
  "Major mode for browsing AI sessions."
  (setq tabulated-list-format
        [("Provider"  10 t)
         ("Model"     24 t)
         ("Status"     8 t)
         ("StartedAt" 28 t)
         ("Topic"      0 nil)])
  (setq tabulated-list-sort-key '("StartedAt" . t))
  (tabulated-list-init-header))

(defun singine-mcp-sessions--make-entries (rows)
  "Convert session ROWS to tabulated-list entries."
  (mapcar
   (lambda (row)
     (let* ((sid      (or (alist-get 'session_id row) ""))
            (provider (or (alist-get 'provider   row) ""))
            (model    (or (alist-get 'model      row) ""))
            (status   (or (alist-get 'status     row) ""))
            (started  (or (alist-get 'started_at row) ""))
            (meta-str (or (alist-get 'metadata_json row) "{}"))
            (topic    (condition-case nil
                          (let ((json-object-type 'alist)
                                (json-key-type    'symbol))
                            (or (alist-get 'topic (json-read-from-string meta-str)) ""))
                        (error "")))
            (face     (if (string= status "OPEN")
                          'font-lock-keyword-face
                        'default)))
       (list sid
             (vector
              (propertize provider 'face face)
              (propertize model    'face 'font-lock-type-face)
              (propertize status   'face (if (string= status "OPEN")
                                             'font-lock-string-face
                                           'font-lock-comment-face))
              (propertize started  'face 'font-lock-doc-face)
              (propertize (singine-mcp--trunc topic 60) 'face 'default)))))
   rows))

(defun singine-mcp-sessions-refresh ()
  "Reload AI sessions."
  (interactive)
  (let ((rows (singine-mcp--call-list "list_ai_sessions" '(("limit" . 50)))))
    (setq tabulated-list-entries (singine-mcp-sessions--make-entries rows))
    (tabulated-list-print t)
    (message "AI sessions: %d  (RET=detail)" (length rows))))

(defun singine-mcp-sessions-show-at-point ()
  "Show the full session bundle for the session at point."
  (interactive)
  (let* ((sid  (tabulated-list-get-id))
         (data (when sid
                 (singine-mcp--call "get_ai_session" `(("session_id" . ,sid))))))
    (if (null data)
        (message "No session at point")
      (singine-mcp--show-json data (format "Session: %s" (substring sid 0 8))))))

;;; ── Governed Transactions buffer ─────────────────────────────────────────

(defvar singine-mcp-transactions-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map tabulated-list-mode-map)
    (define-key map (kbd "g") #'singine-mcp-transactions-refresh)
    (define-key map (kbd "f") #'singine-mcp-transactions-filter-status)
    (define-key map (kbd "F") #'singine-mcp-transactions-clear-filter)
    (define-key map (kbd "q") #'quit-window)
    map)
  "Keymap for `singine-mcp-transactions-mode'.")

(define-derived-mode singine-mcp-transactions-mode tabulated-list-mode "Singine:Transactions"
  "Major mode for browsing governed transactions."
  (setq tabulated-list-format
        [("Type"      26 t)
         ("Status"    10 t)
         ("Initiator"  8 nil)
         ("AI"        10 t)
         ("Reason"     0 nil)
         ("CreatedAt" 28 t)])
  (setq tabulated-list-sort-key '("CreatedAt" . t))
  (tabulated-list-init-header))

(defvar-local singine-mcp-transactions--status nil)

(defun singine-mcp-transactions--make-entries (rows)
  "Convert transaction ROWS to tabulated-list entries."
  (mapcar
   (lambda (row)
     (let* ((tid    (or (alist-get 'transaction_id row) ""))
            (type   (or (alist-get 'type          row) ""))
            (status (or (alist-get 'status        row) ""))
            (init   (or (alist-get 'initiator_id  row) ""))
            (ai     (or (alist-get 'ai_system     row) ""))
            (reason (or (alist-get 'reason        row) ""))
            (at     (or (alist-get 'created_at    row) ""))
            (face   (pcase status
                      ("APPROVED"  'font-lock-string-face)
                      ("COMPLETED" 'font-lock-string-face)
                      ("REJECTED"  'font-lock-warning-face)
                      ("FAILED"    'font-lock-warning-face)
                      (_           'default))))
       (list tid
             (vector
              (propertize type   'face 'font-lock-type-face)
              (propertize status 'face face)
              (propertize init   'face 'default)
              (propertize ai     'face 'font-lock-keyword-face)
              (propertize (singine-mcp--trunc reason 40) 'face 'font-lock-doc-face)
              (propertize at     'face 'font-lock-comment-face)))))
   rows))

(defun singine-mcp-transactions-refresh ()
  "Reload governed transactions."
  (interactive)
  (let* ((params (when singine-mcp-transactions--status
                   `(("status" . ,singine-mcp-transactions--status))))
         (rows   (singine-mcp--call-list "list_transactions"
                                         (append params '(("limit" . 100))))))
    (setq tabulated-list-entries (singine-mcp-transactions--make-entries rows))
    (tabulated-list-print t)
    (message "Transactions: %d%s  (f=filter-status F=clear)"
             (length rows)
             (if singine-mcp-transactions--status
                 (format "  [%s]" singine-mcp-transactions--status)
               ""))))

(defun singine-mcp-transactions-filter-status (status)
  "Filter transactions to STATUS."
  (interactive
   (list (completing-read "Status: "
                          '("PENDING" "APPROVED" "REJECTED"
                            "COMPLETED" "FAILED" "EXPIRED")
                          nil t)))
  (setq singine-mcp-transactions--status status)
  (singine-mcp-transactions-refresh))

(defun singine-mcp-transactions-clear-filter ()
  "Remove status filter."
  (interactive)
  (setq singine-mcp-transactions--status nil)
  (singine-mcp-transactions-refresh))

;;; ── Reference Data buffer ────────────────────────────────────────────────

(defvar singine-mcp-refdata-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map tabulated-list-mode-map)
    (define-key map (kbd "g") #'singine-mcp-refdata-refresh)
    (define-key map (kbd "f") #'singine-mcp-refdata-filter)
    (define-key map (kbd "F") #'singine-mcp-refdata-clear-filter)
    (define-key map (kbd "q") #'quit-window)
    map)
  "Keymap for `singine-mcp-refdata-mode'.")

(define-derived-mode singine-mcp-refdata-mode tabulated-list-mode "Singine:RefData"
  "Major mode for browsing reference data entries."
  (setq tabulated-list-format
        [("CodeSet"   20 t)
         ("Code"      12 t)
         ("Label"     30 t)
         ("Description" 0 nil)])
  (setq tabulated-list-sort-key '("CodeSet" . nil))
  (tabulated-list-init-header))

(defvar-local singine-mcp-refdata--code-set nil)

(defun singine-mcp-refdata--make-entries (rows)
  "Convert reference data ROWS to tabulated-list entries."
  (mapcar
   (lambda (row)
     (let* ((id   (or (alist-get 'id          row) ""))
            (cs   (or (alist-get 'code_set    row) ""))
            (code (or (alist-get 'code        row) ""))
            (lbl  (or (alist-get 'label       row) ""))
            (desc (or (alist-get 'description row) "")))
       (list id
             (vector
              (propertize cs   'face 'font-lock-type-face)
              (propertize code 'face 'font-lock-keyword-face)
              (propertize (singine-mcp--trunc lbl 30) 'face 'default)
              (propertize (singine-mcp--trunc desc 60) 'face 'font-lock-doc-face)))))
   rows))

(defun singine-mcp-refdata-refresh ()
  "Reload reference data."
  (interactive)
  (let* ((params (when singine-mcp-refdata--code-set
                   `(("code_set" . ,singine-mcp-refdata--code-set))))
         (rows   (singine-mcp--call-list "list_reference_data"
                                         (append params '(("limit" . 200))))))
    (setq tabulated-list-entries (singine-mcp-refdata--make-entries rows))
    (tabulated-list-print t)
    (message "RefData: %d entries%s  (f=filter F=clear)"
             (length rows)
             (if singine-mcp-refdata--code-set
                 (format "  [%s]" singine-mcp-refdata--code-set)
               ""))))

(defun singine-mcp-refdata-filter (code-set)
  "Filter to CODE-SET."
  (interactive (list (read-string "Code set (e.g. scenario-codes): ")))
  (setq singine-mcp-refdata--code-set (if (string-empty-p code-set) nil code-set))
  (singine-mcp-refdata-refresh))

(defun singine-mcp-refdata-clear-filter ()
  "Remove code-set filter."
  (interactive)
  (setq singine-mcp-refdata--code-set nil)
  (singine-mcp-refdata-refresh))

;;; ── JSON detail buffer ───────────────────────────────────────────────────

(defun singine-mcp--show-json (data title)
  "Display DATA (any Lisp value) as pretty JSON in a detail buffer with TITLE."
  (let ((buf (get-buffer-create (format "*singine-mcp: %s*" title))))
    (with-current-buffer buf
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert (json-encode data))
        ;; Pretty-print via json.tool if available, else leave as-is
        (condition-case nil
            (progn
              (json-pretty-print-buffer)
              (goto-char (point-min)))
          (error nil))
        (view-mode 1)
        (local-set-key (kbd "q") #'quit-window)))
    (pop-to-buffer buf)))

;;; ── SQL scratch buffer ───────────────────────────────────────────────────

(defvar singine-mcp-sql-mode-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "C-c C-c") #'singine-mcp-sql-execute)
    (define-key map (kbd "C-c C-k") #'singine-mcp-sql-clear-results)
    (define-key map (kbd "C-c C-t") #'singine-mcp-sql-insert-table-name)
    map)
  "Keymap for `singine-mcp-sql-mode'.

  C-c C-c   Execute SQL at or before point
  C-c C-k   Clear results section
  C-c C-t   Insert a table name (completing-read)")

(define-derived-mode singine-mcp-sql-mode sql-mode "Singine:SQL"
  "SQL scratch buffer connected to the Singine MCP database.
Write SELECT queries and evaluate them with C-c C-c.

\\{singine-mcp-sql-mode-map}")

(defun singine-mcp-sql--current-statement ()
  "Return the SQL statement around point (between -- separators or whole buffer)."
  (save-excursion
    (let ((end (progn
                 (if (re-search-forward "^--\\s-*$" nil t)
                     (line-beginning-position)
                   (point-max))))
          (start (progn
                   (goto-char (point-min))
                   (if (re-search-forward "^--\\s-*$" nil t)
                       (line-end-position)
                     (point-min)))))
      (string-trim (buffer-substring-no-properties start end)))))

(defun singine-mcp-sql-execute ()
  "Execute the SELECT statement in the buffer and show results."
  (interactive)
  (let* ((sql     (string-trim
                   (buffer-substring-no-properties (point-min) (point-max))))
         (result  (singine-mcp--call "execute_sql" `(("sql" . ,sql)))))
    (singine-mcp--show-json result (format "SQL result (%d rows)"
                                           (if (listp result) (length result) 0)))))

(defun singine-mcp-sql-clear-results ()
  "No-op placeholder — results live in a separate buffer."
  (interactive)
  (message "Results are in *singine-mcp: SQL result* buffer"))

(defun singine-mcp-sql-insert-table-name ()
  "Insert a table name chosen from completing-read."
  (interactive)
  (let* ((tables (singine-mcp--call-list "list_tables")))
    (insert (completing-read "Table: " tables nil t))))

;;; ── Server process management ────────────────────────────────────────────

(defvar singine-mcp--server-process nil
  "The running MCP SSE server process, or nil.")

(defun singine-mcp-serve-sse ()
  "Start the Singine MCP server in SSE mode in a dedicated process buffer.
The server will listen on `singine-mcp-sse-port'.
Output appears in *Singine MCP Server* buffer."
  (interactive)
  (when (and singine-mcp--server-process
             (process-live-p singine-mcp--server-process))
    (user-error "MCP server already running (M-x singine-mcp-kill-server to stop)"))
  (let* ((buf  (get-buffer-create "*Singine MCP Server*"))
         (env  (append (singine-runtime--env) process-environment))
         (proc (let ((process-environment env))
                 (start-process
                  "singine-mcp-server" buf
                  singine-runtime-command
                  "mcp" "serve"
                  "--db"        singine-mcp-db
                  "--transport" "sse"
                  "--port"      (number-to-string singine-mcp-sse-port)))))
    (setq singine-mcp--server-process proc)
    (set-process-sentinel
     proc
     (lambda (p _event)
       (unless (process-live-p p)
         (setq singine-mcp--server-process nil)
         (message "Singine MCP server stopped"))))
    (pop-to-buffer buf)
    (message "Singine MCP server starting on port %d…  (kill: M-x singine-mcp-kill-server)"
             singine-mcp-sse-port)))

(defun singine-mcp-kill-server ()
  "Stop the running Singine MCP SSE server."
  (interactive)
  (if (and singine-mcp--server-process
           (process-live-p singine-mcp--server-process))
      (progn
        (delete-process singine-mcp--server-process)
        (setq singine-mcp--server-process nil)
        (message "Singine MCP server killed"))
    (message "No MCP server running")))

(defun singine-mcp-server-status ()
  "Report whether the MCP server process is running."
  (interactive)
  (if (and singine-mcp--server-process
           (process-live-p singine-mcp--server-process))
      (message "MCP server running (PID %d, port %d)"
               (process-id singine-mcp--server-process)
               singine-mcp-sse-port)
    (message "MCP server not running")))

;;; ── Shell helper ─────────────────────────────────────────────────────────

(defun singine-mcp-shell ()
  "Open a shell buffer with SINGINE_ROOT and singine on PATH already set.
Use this to run `singine mcp call', `singine mcp serve', sqlite3, etc."
  (interactive)
  (let* ((buf-name "*Singine Shell*")
         (buf      (get-buffer-create buf-name)))
    (with-current-buffer buf
      (unless (get-buffer-process buf)
        ;; Set env before starting the shell
        (let ((process-environment
               (append (singine-runtime--env) process-environment)))
          (shell buf))))
    (pop-to-buffer buf)
    ;; Inject a banner so the user knows what's available
    (when (get-buffer-process buf)
      (comint-send-string
       (get-buffer-process buf)
       (format "echo '=== Singine shell (SINGINE_ROOT=%s) ===' && singine mcp tools\n"
               singine-runtime-singine-root)))))

;;; ── Top-level interactive commands ──────────────────────────────────────

;;;###autoload
(defun singine-mcp-seed ()
  "Seed the MCP test database at `singine-mcp-db'."
  (interactive)
  (let ((output (singine-runtime--run "mcp" "seed" "--db" singine-mcp-db)))
    (message "%s" (string-trim output))))

;;;###autoload
(defun singine-mcp-assets (&optional type)
  "Browse Collibra domain assets (completing-read TYPE then tabulated list)."
  (interactive
   (list (completing-read "Asset type: " singine-mcp--asset-types nil t
                          nil nil "BusinessTerm")))
  (let* ((type (or type "BusinessTerm"))
         (buf  (get-buffer-create (format "*Singine Assets: %s*" type))))
    (with-current-buffer buf
      (singine-mcp-assets-mode)
      (setq singine-mcp-assets--type type)
      (singine-mcp-assets-refresh))
    (switch-to-buffer buf)))

;;;###autoload
(defun singine-mcp-events ()
  "Browse domain events in a tabulated buffer."
  (interactive)
  (let ((buf (get-buffer-create "*Singine Events*")))
    (with-current-buffer buf
      (singine-mcp-events-mode)
      (singine-mcp-events-refresh))
    (switch-to-buffer buf)))

;;;###autoload
(defun singine-mcp-sessions ()
  "Browse AI sessions in a tabulated buffer."
  (interactive)
  (let ((buf (get-buffer-create "*Singine AI Sessions*")))
    (with-current-buffer buf
      (singine-mcp-sessions-mode)
      (singine-mcp-sessions-refresh))
    (switch-to-buffer buf)))

;;;###autoload
(defun singine-mcp-transactions ()
  "Browse governed transactions in a tabulated buffer."
  (interactive)
  (let ((buf (get-buffer-create "*Singine Transactions*")))
    (with-current-buffer buf
      (singine-mcp-transactions-mode)
      (singine-mcp-transactions-refresh))
    (switch-to-buffer buf)))

;;;###autoload
(defun singine-mcp-refdata ()
  "Browse reference data (scenario-codes, iata-codes, …) in a tabulated buffer."
  (interactive)
  (let ((buf (get-buffer-create "*Singine RefData*")))
    (with-current-buffer buf
      (singine-mcp-refdata-mode)
      (singine-mcp-refdata-refresh))
    (switch-to-buffer buf)))

;;;###autoload
(defun singine-mcp-sql ()
  "Open a SQL scratch buffer connected to the Singine MCP database.
Write a SELECT query and hit C-c C-c to execute it."
  (interactive)
  (let ((buf (get-buffer-create "*Singine SQL*")))
    (with-current-buffer buf
      (unless (derived-mode-p 'singine-mcp-sql-mode)
        (singine-mcp-sql-mode))
      (when (= (buffer-size) 0)
        (insert "-- Singine MCP SQL scratch  (C-c C-c = execute, C-c C-t = insert table name)\n")
        (insert "-- Database: " singine-mcp-db "\n\n")
        (insert "SELECT name, collibra_type FROM business_term ORDER BY name;\n")))
    (switch-to-buffer buf)
    (message "C-c C-c to execute  |  C-c C-t to insert table name")))

;;;###autoload
(defun singine-mcp-tables ()
  "Show all tables; describe the selected one in a JSON detail buffer."
  (interactive)
  (let* ((tables (singine-mcp--call-list "list_tables"))
         (choice (completing-read "Table: " tables nil t))
         (cols   (singine-mcp--call "describe_table" `(("table_name" . ,choice)))))
    (singine-mcp--show-json cols (format "describe: %s" choice))))

;;; ── Cortex bridge helpers ────────────────────────────────────────────────

(defun singine-mcp--call-cortex (tool &optional params)
  "Like `singine-mcp--call' but always targets `singine-mcp-cortex-db'."
  (let* ((params-json (if params
                          (json-encode
                           (let ((ht (make-hash-table :test 'equal)))
                             (dolist (kv params ht)
                               (puthash (car kv) (cdr kv) ht))))
                        "{}"))
         (output (singine-runtime--run
                  "mcp" "call" tool
                  "--db" singine-mcp-cortex-db
                  "--params" params-json))
         (json-object-type 'alist)
         (json-array-type  'list)
         (json-key-type    'symbol))
    (condition-case err
        (json-read-from-string output)
      (error
       (message "singine-mcp cortex: error calling %s: %s\n%s"
                tool (error-message-string err) output)
       nil))))

(defun singine-mcp--cortex-source-names ()
  "Return list of source name strings from the cortex bridge."
  (let ((rows (singine-mcp--call-cortex "list_sources")))
    (mapcar (lambda (r) (alist-get 'name r)) (or rows '()))))

;;; ── Cortex Sources buffer ────────────────────────────────────────────────

(defvar singine-mcp-cortex-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map tabulated-list-mode-map)
    (define-key map (kbd "g")   #'singine-mcp-cortex-refresh)
    (define-key map (kbd "RET") #'singine-mcp-cortex-browse-at-point)
    (define-key map (kbd "/")   #'singine-mcp-search)
    (define-key map (kbd "q")   #'quit-window)
    map)
  "Keymap for `singine-mcp-cortex-mode'.

  g   Refresh sources
  RET Browse entities in this source
  /   Fragment full-text search
  q   Quit")

(define-derived-mode singine-mcp-cortex-mode tabulated-list-mode "Singine:Cortex"
  "Major mode for browsing cortex bridge sources."
  (setq tabulated-list-format
        [("Source"     36 t)
         ("Kind"       20 t)
         ("Entities"    9 t)
         ("Fragments"   9 t)
         ("Scanned"     0 nil)])
  (setq tabulated-list-sort-key '("Entities" . t))
  (tabulated-list-init-header))

(defun singine-mcp-cortex-refresh ()
  "Reload cortex sources."
  (interactive)
  (let ((rows (singine-mcp--call-cortex "list_sources")))
    (setq tabulated-list-entries
          (mapcar
           (lambda (row)
             (let* ((name  (or (alist-get 'name          row) ""))
                    (kind  (or (alist-get 'kind          row) ""))
                    (ne    (or (alist-get 'entity_count  row) 0))
                    (nf    (or (alist-get 'fragment_count row) 0))
                    (at    (or (alist-get 'scanned_at    row) ""))
                    (face  (pcase kind
                             ("logseq-graph"      'font-lock-string-face)
                             ("agent-home"        'font-lock-keyword-face)
                             ("rdf-knowledge-pack" 'font-lock-type-face)
                             ("filesystem"        'font-lock-comment-face)
                             (_                   'default))))
               (list name
                     (vector
                      (propertize name 'face face)
                      (propertize kind 'face 'font-lock-comment-face)
                      (propertize (number-to-string ne) 'face 'default)
                      (propertize (number-to-string nf) 'face 'default)
                      (propertize (substring at 0 (min 19 (length at))) 'face 'font-lock-doc-face)))))
           (or rows '())))
    (tabulated-list-print t)
    (message "Cortex bridge: %d sources  (RET=browse entities  /=search)"
             (length (or rows '())))))

(defun singine-mcp-cortex-browse-at-point ()
  "Open an entity browser for the source on the current line."
  (interactive)
  (let ((source-name (tabulated-list-get-id)))
    (unless source-name (user-error "No source at point"))
    (singine-mcp-entities source-name)))

;;; ── Cortex Entities buffer ───────────────────────────────────────────────

(defvar singine-mcp-entities-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map tabulated-list-mode-map)
    (define-key map (kbd "g")   #'singine-mcp-entities-refresh)
    (define-key map (kbd "f")   #'singine-mcp-entities-filter-type)
    (define-key map (kbd "F")   #'singine-mcp-entities-clear-filter)
    (define-key map (kbd "RET") #'singine-mcp-entities-detail-at-point)
    (define-key map (kbd "/")   #'singine-mcp-search)
    (define-key map (kbd "q")   #'quit-window)
    map)
  "Keymap for `singine-mcp-entities-mode'.

  g   Refresh
  f   Filter by entity type
  F   Clear filter
  RET Full detail (statements + fragments) in JSON buffer
  /   Fragment search (all sources)
  q   Quit")

(define-derived-mode singine-mcp-entities-mode tabulated-list-mode "Singine:Entities"
  "Major mode for browsing cortex bridge entities."
  (setq tabulated-list-format
        [("Type"     20 t)
         ("Label"    36 t)
         ("Source"   22 nil)
         ("Path"      0 nil)])
  (setq tabulated-list-sort-key '("Label" . nil))
  (tabulated-list-init-header))

(defvar-local singine-mcp-entities--source nil)
(defvar-local singine-mcp-entities--type-filter nil)

(defun singine-mcp-entities--make-entries (rows)
  "Convert entity ROWS to tabulated-list entries."
  (mapcar
   (lambda (row)
     (let* ((eid   (or (alist-get 'entity_id   row) ""))
            (etype (or (alist-get 'entity_type  row) ""))
            (lbl   (or (alist-get 'label        row) ""))
            (src   (or (alist-get 'source_name  row) ""))
            (path  (or (alist-get 'path         row) ""))
            (face  (pcase etype
                     ("logseq-page"      'font-lock-keyword-face)
                     ("markdown"         'font-lock-string-face)
                     ("task"             'font-lock-warning-face)
                     ("json"             'font-lock-type-face)
                     ("jsonl"            'font-lock-type-face)
                     (_                  'default))))
       (list eid
             (vector
              (propertize etype 'face face)
              (propertize (singine-mcp--trunc lbl  36) 'face 'default)
              (propertize (singine-mcp--trunc src  22) 'face 'font-lock-comment-face)
              (propertize (singine-mcp--trunc path 60) 'face 'font-lock-doc-face)))))
   rows))

(defun singine-mcp-entities-refresh ()
  "Reload entities for this buffer's source and type filter."
  (interactive)
  (let* ((params `(("limit" . 300)
                   ,@(when singine-mcp-entities--source
                       `(("source_name" . ,singine-mcp-entities--source)))
                   ,@(when singine-mcp-entities--type-filter
                       `(("entity_type" . ,singine-mcp-entities--type-filter)))))
         (rows (singine-mcp--call-cortex "search_entities" params)))
    (setq tabulated-list-entries (singine-mcp-entities--make-entries (or rows '())))
    (tabulated-list-print t)
    (message "Entities: %d%s%s  (f=filter-type F=clear RET=detail /=search)"
             (length (or rows '()))
             (if singine-mcp-entities--source
                 (format " in %s" singine-mcp-entities--source) "")
             (if singine-mcp-entities--type-filter
                 (format " [%s]" singine-mcp-entities--type-filter) ""))))

(defun singine-mcp-entities-filter-type (entity-type)
  "Filter entities to ENTITY-TYPE."
  (interactive
   (let* ((types (singine-mcp--call-cortex
                  "list_entity_types"
                  (when singine-mcp-entities--source
                    `(("source_name" . ,singine-mcp-entities--source)))))
          (names (mapcar (lambda (r) (alist-get 'entity_type r)) (or types '()))))
     (list (completing-read "Entity type: " names nil t))))
  (setq singine-mcp-entities--type-filter entity-type)
  (singine-mcp-entities-refresh))

(defun singine-mcp-entities-clear-filter ()
  "Remove entity type filter."
  (interactive)
  (setq singine-mcp-entities--type-filter nil)
  (singine-mcp-entities-refresh))

(defun singine-mcp-entities-detail-at-point ()
  "Show full detail (statements + fragments) for the entity at point."
  (interactive)
  (let* ((eid  (tabulated-list-get-id))
         (data (when eid
                 (singine-mcp--call-cortex "get_entity_detail"
                                           `(("entity_id" . ,eid))))))
    (if (null data)
        (message "No entity at point")
      (let* ((label (or (alist-get 'label data) eid))
             (frags (alist-get 'fragments data))
             (stmts (alist-get 'statements data)))
        ;; Show fragments as readable text, not raw JSON
        (let ((buf (get-buffer-create (format "*Cortex: %s*" (singine-mcp--trunc label 40)))))
          (with-current-buffer buf
            (let ((inhibit-read-only t))
              (erase-buffer)
              (insert (format "Entity: %s\n" label))
              (insert (format "Type:   %s\n" (or (alist-get 'entity_type data) "")))
              (insert (format "Source: %s (%s)\n"
                              (or (alist-get 'source_name data) "")
                              (or (alist-get 'source_kind data) "")))
              (insert (format "IRI:    %s\n" (or (alist-get 'iri data) "")))
              (when (alist-get 'path data)
                (insert (format "Path:   %s\n" (alist-get 'path data))))
              (insert "\n")
              (when stmts
                (insert (format "── Statements (%d) ─────────────────\n" (length stmts)))
                (dolist (s stmts)
                  (insert (format "  %-30s  %s\n"
                                  (or (alist-get 'predicate s) "")
                                  (or (alist-get 'object_value s) ""))))
                (insert "\n"))
              (when frags
                (insert (format "── Fragments (%d) ──────────────────\n" (length frags)))
                (dolist (f frags)
                  (insert (format "[%d] %s\n\n"
                                  (or (alist-get 'seq f) 0)
                                  (or (alist-get 'text f) ""))))))
            (goto-char (point-min))
            (view-mode 1)
            (local-set-key (kbd "q") #'quit-window))
          (pop-to-buffer buf))))))

;;; ── Fragment search ───────────────────────────────────────────────────────

;;;###autoload
(defun singine-mcp-search (query)
  "Search fragment text across the cortex bridge (full-text LIKE match).
Results open in a tabulated buffer with entity and source context.
Optionally follow with RET to get entity detail."
  (interactive (list (read-string "Search cortex fragments: ")))
  (when (string-empty-p query)
    (user-error "Search query cannot be empty"))
  (let* ((rows (singine-mcp--call-cortex "search_fragments"
                                          `(("query" . ,query) ("limit" . 50))))
         (buf  (get-buffer-create (format "*Cortex Search: %s*" query))))
    (with-current-buffer buf
      (let ((inhibit-read-only t))
        (erase-buffer)
        (insert (format "Cortex fragment search: %S  (%d results)\n"
                        query (length (or rows '()))))
        (insert (make-string 60 ?─) "\n\n")
        (if (null rows)
            (insert "(no results)\n")
          (dolist (row rows)
            (let* ((label  (or (alist-get 'entity_label row) ""))
                   (etype  (or (alist-get 'entity_type  row) ""))
                   (src    (or (alist-get 'source_name  row) ""))
                   (seq    (or (alist-get 'seq          row) 0))
                   (text   (or (alist-get 'text_preview row) "")))
              (insert (propertize (format "[%s] %s  (%s #%d)\n" src label etype seq)
                                  'face 'font-lock-comment-face))
              (insert text)
              (insert "\n\n"))))
        (goto-char (point-min))
        (view-mode 1)
        (local-set-key (kbd "q") #'quit-window)))
    (pop-to-buffer buf)
    (message "Cortex search: %d fragments matched %S" (length (or rows '())) query)))

;;; ── Cortex SQL scratch ────────────────────────────────────────────────────

;;;###autoload
(defun singine-mcp-cortex-sql ()
  "Open a SQL scratch buffer pre-pointed at the cortex bridge DB.
Write a SELECT query and hit C-c C-c to execute it.
The cortex schema: sources, entities, statements, fragments, query_templates."
  (interactive)
  (let* ((buf (get-buffer-create "*Singine Cortex SQL*"))
         (singine-mcp-db singine-mcp-cortex-db))  ; rebind for execute
    (with-current-buffer buf
      (unless (derived-mode-p 'singine-mcp-sql-mode)
        (singine-mcp-sql-mode))
      ;; Override execute to use cortex db
      (setq-local singine-mcp-db singine-mcp-cortex-db)
      (when (= (buffer-size) 0)
        (insert ";; Singine Cortex SQL  (C-c C-c = execute, C-c C-t = table name)\n")
        (insert ";; Database: " singine-mcp-cortex-db "\n")
        (insert ";; Schema:   sources  entities  statements  fragments  query_templates\n\n")
        (insert "SELECT s.name, s.kind,\n")
        (insert "       COUNT(DISTINCT e.entity_id)   AS entities,\n")
        (insert "       COUNT(DISTINCT f.fragment_id) AS fragments\n")
        (insert "FROM sources s\n")
        (insert "LEFT JOIN entities  e ON e.source_id = s.source_id\n")
        (insert "LEFT JOIN fragments f ON f.source_id = s.source_id\n")
        (insert "GROUP BY s.source_id\n")
        (insert "ORDER BY entities DESC;\n")))
    (switch-to-buffer buf)
    (message "C-c C-c to execute against cortex bridge (%s)" singine-mcp-cortex-db)))

;;; ── Collibra Edge refresh ────────────────────────────────────────────────

(defcustom singine-mcp-edge-url "https://localhost"
  "Base URL of the Collibra Edge / DGC node to ingest from."
  :type 'string
  :group 'singine-mcp)

(defcustom singine-mcp-edge-site-id ""
  "Collibra Edge site ID stored in entity metadata (optional)."
  :type 'string
  :group 'singine-mcp)

;;;###autoload
(defun singine-mcp-refresh-edge (&optional edge-url)
  "Ingest assets from the Collibra Edge into the cortex bridge, then refresh sources.
With prefix arg, prompt for the edge URL instead of using `singine-mcp-edge-url'."
  (interactive
   (list (if current-prefix-arg
             (read-string "Collibra Edge URL: " singine-mcp-edge-url)
           singine-mcp-edge-url)))
  (let* ((url  (or edge-url singine-mcp-edge-url))
         (result (singine-mcp--call-cortex
                  "refresh_from_edge"
                  `(("edge_url" . ,url)
                    ("site_id"  . ,singine-mcp-edge-site-id)
                    ("verify_tls" . :json-false)))))
    (if (null result)
        (message "singine-mcp-refresh-edge: failed (check Edge URL and server)")
      (let* ((ingest  (alist-get 'ingest  result))
             (sources (alist-get 'sources result))
             (comms   (or (alist-get 'communities ingest) 0))
             (assets  (or (alist-get 'assets      ingest) 0)))
        (message "Collibra Edge ingested: %d communities, %d assets from %s  (%d total sources)"
                 comms assets url (length sources))
        ;; Refresh cortex buffer if open
        (when-let ((buf (get-buffer "*Singine Cortex*")))
          (with-current-buffer buf
            (singine-mcp-cortex-refresh)))))))

;;; ── Top-level cortex commands ────────────────────────────────────────────

;;;###autoload
(defun singine-mcp-cortex ()
  "Browse cortex bridge sources in a tabulated buffer.
RET opens entity browser for the source at point.
/ runs a fragment full-text search."
  (interactive)
  (let ((buf (get-buffer-create "*Singine Cortex*")))
    (with-current-buffer buf
      (singine-mcp-cortex-mode)
      (singine-mcp-cortex-refresh))
    (switch-to-buffer buf)))

;;;###autoload
(defun singine-mcp-entities (&optional source-name)
  "Browse cortex entities, optionally pre-filtered to SOURCE-NAME."
  (interactive
   (list (completing-read "Source (blank=all): "
                          (singine-mcp--cortex-source-names) nil nil)))
  (let* ((src (if (string-empty-p (or source-name "")) nil source-name))
         (buf (get-buffer-create
               (if src (format "*Cortex Entities: %s*" src)
                 "*Cortex Entities*"))))
    (with-current-buffer buf
      (singine-mcp-entities-mode)
      (setq singine-mcp-entities--source src
            singine-mcp-entities--type-filter nil)
      (singine-mcp-entities-refresh))
    (switch-to-buffer buf)))

;;; ── Prefix keymap  C-c s m ───────────────────────────────────────────────

(defvar singine-mcp-map
  (let ((map (make-sparse-keymap)))
    ;; domain DB
    (define-key map (kbd "s") #'singine-mcp-seed)
    (define-key map (kbd "S") #'singine-mcp-serve-sse)
    (define-key map (kbd "k") #'singine-mcp-kill-server)
    (define-key map (kbd "a") #'singine-mcp-assets)
    (define-key map (kbd "e") #'singine-mcp-events)
    (define-key map (kbd "i") #'singine-mcp-sessions)
    (define-key map (kbd "t") #'singine-mcp-transactions)
    (define-key map (kbd "r") #'singine-mcp-refdata)
    (define-key map (kbd "q") #'singine-mcp-sql)
    (define-key map (kbd "T") #'singine-mcp-tables)
    (define-key map (kbd "!") #'singine-mcp-shell)
    ;; cortex bridge
    (define-key map (kbd "c") #'singine-mcp-cortex)
    (define-key map (kbd "/") #'singine-mcp-search)
    (define-key map (kbd "Q") #'singine-mcp-cortex-sql)
    (define-key map (kbd "R") #'singine-mcp-refresh-edge)
    map)
  "Prefix keymap for Singine MCP commands (bound at C-c s m).")

(global-set-key (kbd "C-c s m") singine-mcp-map)

(provide 'singine-mcp)
;;; singine-mcp.el ends here
