;;; singine-edge-datasource.el --- Emacs interface for Singine Edge datasource workflows -*- lexical-binding: t; -*-
;;
;; Focus: operator UX for the PostgreSQL-backed Collibra Edge datasource.
;; This library wraps the new `singine collibra edge create datasource connection`
;; command and adds a simple query/sampling surface plus governance hooks for
;; masking, anonymization, and codification.
;;
;; Usage:
;;   (load "~/ws/git/github/sindoc/singine/elisp/singine-runtime.el")
;;   (load "~/ws/git/github/sindoc/singine/elisp/singine-edge-datasource.el")
;;
;; Commands:
;;   M-x singine-edge-datasource-dashboard        Show connection details
;;   M-x singine-edge-datasource-download-driver  Resolve and cache the pgJDBC jar
;;   M-x singine-edge-datasource-test-connection  Run a lightweight connection test
;;   M-x singine-edge-datasource-list-tables      List public tables
;;   M-x singine-edge-datasource-sample-table     Sample rows with governance mode
;;   M-x singine-edge-datasource-set-mode         Switch raw/mask/anonymize/codify

(require 'cl-lib)
(require 'json)
(require 'subr-x)
(require 'singine-runtime)

(defgroup singine-edge-datasource nil
  "Emacs interface for the Singine Edge PostgreSQL datasource."
  :group 'tools
  :prefix "singine-edge-datasource-")

(defcustom singine-edge-datasource-command "singine"
  "Name or path of the singine CLI executable."
  :type 'string
  :group 'singine-edge-datasource)

(defcustom singine-edge-datasource-container "singine-pg"
  "Docker container name for the local PostgreSQL instance."
  :type 'string
  :group 'singine-edge-datasource)

(defcustom singine-edge-datasource-governance-mode 'mask
  "How sample rows should be rendered in Emacs buffers."
  :type '(choice (const :tag "Raw" raw)
                 (const :tag "Mask" mask)
                 (const :tag "Anonymize" anonymize)
                 (const :tag "Codify" codify))
  :group 'singine-edge-datasource)

(defcustom singine-edge-datasource-sensitive-field-regexps
  '("email" "mail" "phone" "mobile" "password" "secret" "token" "key" "name" "label" "path")
  "Regexps matched against field names for governance transformations."
  :type '(repeat string)
  :group 'singine-edge-datasource)

(defcustom singine-edge-datasource-default-sample-limit 10
  "Default row limit for sampling."
  :type 'integer
  :group 'singine-edge-datasource)

(defvar singine-edge-datasource--last-connection nil)
(defvar singine-edge-datasource--last-test nil)
(defvar singine-edge-datasource--last-sample nil)
(defvar singine-edge-datasource--buffer "*Singine Edge Datasource*")

(defun singine-edge-datasource--run-json (&rest args)
  "Run singine ARGS and parse the JSON response."
  (let* ((process-environment
          (append (singine-runtime--env) process-environment))
         (json-object-type 'alist)
         (json-array-type 'list)
         (json-key-type 'symbol))
    (with-temp-buffer
      (let ((rc (apply #'call-process singine-edge-datasource-command nil t nil args)))
        (unless (eq rc 0)
          (error "singine command failed: %s" (buffer-string))))
      (json-read-from-string (buffer-string)))))

(defun singine-edge-datasource--refresh-connection (&optional download-driver)
  "Refresh the datasource connection payload from singine."
  (setq singine-edge-datasource--last-connection
        (apply #'singine-edge-datasource--run-json
               (append
                '("collibra" "edge" "create" "datasource" "connection")
                (when download-driver '("--download-driver")))))
  singine-edge-datasource--last-connection)

(defun singine-edge-datasource--datasource ()
  "Return the cached datasource alist, refreshing it if needed."
  (alist-get 'datasource
             (or singine-edge-datasource--last-connection
                 (singine-edge-datasource--refresh-connection))))

(defun singine-edge-datasource--field-sensitive-p (field-name)
  "Return non-nil when FIELD-NAME should be governed."
  (let ((case-fold-search t))
    (cl-some (lambda (re) (string-match-p re field-name))
             singine-edge-datasource-sensitive-field-regexps)))

(defun singine-edge-datasource--mask-value (value)
  "Mask VALUE for display."
  (let ((text (format "%s" value)))
    (cond
     ((<= (length text) 4) "****")
     (t (concat (substring text 0 2) "…" (substring text (- (length text) 2)))))))

(defun singine-edge-datasource--mask-secret (value)
  "Mask VALUE for dashboard display."
  (if (or (null value) (string-empty-p (format "%s" value)))
      ""
    "********"))

(defun singine-edge-datasource--anonymize-value (value)
  "Return a stable anonymized token for VALUE."
  (format "anon-%08x" (logand (sxhash (format "%s" value)) #xffffffff)))

(defun singine-edge-datasource--codify-value (field value)
  "Return a codified representation for FIELD and VALUE."
  (format "code:%s:%08x"
          (replace-regexp-in-string "[^a-z0-9]+" "-" (downcase field))
          (logand (sxhash (format "%s" value)) #xffffffff)))

(defun singine-edge-datasource--govern-row (row)
  "Apply the configured governance mode to ROW."
  (let ((mode singine-edge-datasource-governance-mode))
    (mapcar
     (lambda (cell)
       (let* ((field (symbol-name (car cell)))
              (value (cdr cell)))
         (cond
          ((or (null value) (eq mode 'raw) (not (singine-edge-datasource--field-sensitive-p field)))
           cell)
          ((eq mode 'mask)
           (cons (car cell) (singine-edge-datasource--mask-value value)))
          ((eq mode 'anonymize)
           (cons (car cell) (singine-edge-datasource--anonymize-value value)))
          ((eq mode 'codify)
           (cons (car cell) (singine-edge-datasource--codify-value field value)))
          (t cell))))
     row)))

(defun singine-edge-datasource--docker-json (sql)
  "Run SQL through dockerized psql and parse the JSON/text result."
  (with-temp-buffer
    (let ((rc (call-process
               "docker" nil t nil
               "exec" singine-edge-datasource-container
               "psql" "-U" (alist-get 'user (singine-edge-datasource--datasource))
               "-d" (alist-get 'database (singine-edge-datasource--datasource))
               "-tA" "-c" sql)))
      (unless (eq rc 0)
        (error "psql failed: %s" (buffer-string)))
      (string-trim (buffer-string)))))

(defun singine-edge-datasource--sql-quote (value)
  "Quote VALUE as a SQL string literal."
  (concat "'" (replace-regexp-in-string "'" "''" value t t) "'"))

(defun singine-edge-datasource--sample-query (table limit)
  "Return a JSON aggregation SQL query for TABLE and LIMIT."
  (format "select coalesce(json_agg(t), '[]'::json)::text from (select * from %s limit %d) t;"
          table limit))

(defun singine-edge-datasource--read-json-string (text)
  "Parse TEXT as JSON."
  (let ((json-object-type 'alist)
        (json-array-type 'list)
        (json-key-type 'symbol))
    (json-read-from-string text)))

(defun singine-edge-datasource--insert-section (title)
  "Insert a section header TITLE."
  (insert (propertize (concat title "\n") 'face 'bold))
  (insert (make-string (length title) ?=))
  (insert "\n\n"))

(defun singine-edge-datasource--render-alist (alist)
  "Insert ALIST into the current buffer."
  (dolist (cell alist)
    (insert (format "%-18s %s\n"
                    (concat (symbol-name (car cell)) ":")
                    (cdr cell)))))

(defvar singine-edge-datasource-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map special-mode-map)
    (define-key map (kbd "g") #'singine-edge-datasource-dashboard)
    (define-key map (kbd "d") #'singine-edge-datasource-download-driver)
    (define-key map (kbd "t") #'singine-edge-datasource-test-connection)
    (define-key map (kbd "l") #'singine-edge-datasource-list-tables)
    (define-key map (kbd "s") #'singine-edge-datasource-sample-table)
    (define-key map (kbd "m") #'singine-edge-datasource-set-mode)
    map))

(define-derived-mode singine-edge-datasource-mode special-mode "Singine:EdgeDatasource"
  "Major mode for the Singine Edge datasource dashboard.")

(defun singine-edge-datasource-dashboard ()
  "Show the current datasource connection profile."
  (interactive)
  (let* ((payload (or singine-edge-datasource--last-connection
                      (singine-edge-datasource--refresh-connection)))
         (ds (alist-get 'datasource payload)))
    (with-current-buffer (get-buffer-create singine-edge-datasource--buffer)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (singine-edge-datasource-mode)
        (singine-edge-datasource--insert-section "Datasource")
        (singine-edge-datasource--render-alist
         `((name . ,(alist-get 'name ds))
           (jdbc_url . ,(alist-get 'jdbc_url ds))
           (local_jdbc_url . ,(alist-get 'local_jdbc_url ds))
           (driver_class . ,(alist-get 'driver_class ds))
           (driver_version . ,(format "%s" (alist-get 'driver_version ds)))
           (driver_path . ,(alist-get 'driver_path ds))
           (driver_status . ,(alist-get 'driver_status ds))
           (host . ,(alist-get 'host ds))
           (port . ,(format "%s" (alist-get 'port ds)))
           (database . ,(alist-get 'database ds))
           (user . ,(alist-get 'user ds))
           (password . ,(singine-edge-datasource--mask-secret (alist-get 'password ds)))))
        (insert "\n")
        (singine-edge-datasource--insert-section "Governance")
        (insert (format "mode: %s\n" singine-edge-datasource-governance-mode))
        (insert (format "sensitive fields: %s\n"
                        (string-join singine-edge-datasource-sensitive-field-regexps ", ")))
        (when singine-edge-datasource--last-test
          (insert "\n")
          (singine-edge-datasource--insert-section "Last Test")
          (insert (format "%s\n" singine-edge-datasource--last-test)))
        (when singine-edge-datasource--last-sample
          (insert "\n")
          (singine-edge-datasource--insert-section "Last Sample")
          (insert singine-edge-datasource--last-sample)
          (insert "\n"))))
    (pop-to-buffer singine-edge-datasource--buffer)))

(defun singine-edge-datasource-download-driver ()
  "Resolve and cache the PostgreSQL JDBC driver."
  (interactive)
  (singine-edge-datasource--refresh-connection t)
  (singine-edge-datasource-dashboard)
  (message "pgJDBC driver cached at %s"
           (alist-get 'driver_path (singine-edge-datasource--datasource))))

(defun singine-edge-datasource-test-connection ()
  "Test the local PostgreSQL connection via dockerized psql."
  (interactive)
  (setq singine-edge-datasource--last-test
        (singine-edge-datasource--docker-json
         "select json_build_object('database', current_database(), 'user', current_user, 'version', version())::text;"))
  (singine-edge-datasource-dashboard)
  (message "Datasource test completed"))

(defun singine-edge-datasource-list-tables ()
  "List public tables in the PostgreSQL database."
  (interactive)
  (let* ((json-text
          (singine-edge-datasource--docker-json
           "select coalesce(json_agg(table_name order by table_name), '[]'::json)::text from information_schema.tables where table_schema = 'public';"))
         (tables (singine-edge-datasource--read-json-string json-text)))
    (message "Tables: %s" (string-join tables ", "))))

(defun singine-edge-datasource-sample-table (table &optional limit)
  "Fetch and display governed sample rows from TABLE."
  (interactive
   (let* ((json-text
           (singine-edge-datasource--docker-json
            "select coalesce(json_agg(table_name order by table_name), '[]'::json)::text from information_schema.tables where table_schema = 'public';"))
          (tables (singine-edge-datasource--read-json-string json-text))
          (table (completing-read "Table: " tables nil t))
          (limit (read-number "Limit: " singine-edge-datasource-default-sample-limit)))
     (list table limit)))
  (let* ((sql (singine-edge-datasource--sample-query table (or limit singine-edge-datasource-default-sample-limit)))
         (json-text (singine-edge-datasource--docker-json sql))
         (rows (mapcar #'singine-edge-datasource--govern-row
                       (singine-edge-datasource--read-json-string json-text))))
    (setq singine-edge-datasource--last-sample
          (mapconcat
           (lambda (row)
             (mapconcat
              (lambda (cell) (format "%s=%s" (car cell) (cdr cell)))
              row "\n"))
           rows "\n\n"))
    (singine-edge-datasource-dashboard)
    (message "Rendered %d row(s) from %s in %s mode"
             (length rows) table singine-edge-datasource-governance-mode)))

(defun singine-edge-datasource-set-mode (mode)
  "Set the governance MODE for sample rendering."
  (interactive
   (list (intern (completing-read "Mode: " '("raw" "mask" "anonymize" "codify") nil t))))
  (setq singine-edge-datasource-governance-mode mode)
  (singine-edge-datasource-dashboard)
  (message "Datasource governance mode set to %s" mode))

(provide 'singine-edge-datasource)

;;; singine-edge-datasource.el ends here
