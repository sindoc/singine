;;; singine-runtime.el --- Singine JVM runtime management for Emacs -*- lexical-binding: t; -*-
;;
;; Exposes `singine runtime java/groovy/clojure/jvm' as interactive Emacs
;; commands, with tabulated-list views for the Java registry and JVM deps.
;;
;; Usage:
;;   (load "~/ws/git/github/sindoc/singine/elisp/singine-runtime.el")
;;
;; Commands:
;;   M-x singine-java-list         Browse Java registry (tabulated)
;;   M-x singine-java-activate     Completing-read alias → set JAVA_HOME in Emacs
;;   M-x singine-java-inspect      Show resolution for current buffer's directory
;;   M-x singine-java-install      Completing-read alias → sdk install via compile
;;   M-x singine-groovy-list       Browse Groovy registry
;;   M-x singine-groovy-activate   Set GROOVY_HOME in Emacs
;;   M-x singine-jvm-deps          Browse all JVM deps (tabulated, filterable)
;;   M-x singine-jvm-deps-project  Filter deps to one project
;;
;; Keybindings (prefix C-c s r — singine runtime):
;;   C-c s r j   singine-java-list
;;   C-c s r a   singine-java-activate
;;   C-c s r i   singine-java-inspect
;;   C-c s r d   singine-jvm-deps
;;   C-c s r g   singine-groovy-list

;;; Requirements: singine CLI on PATH, jq optional (CLI handles JSON).

(require 'json)
(require 'tabulated-list)
(require 'compile)

;;; ── Configuration ────────────────────────────────────────────────────────────

(defgroup singine-runtime nil
  "Singine JVM runtime management."
  :group 'tools
  :prefix "singine-runtime-")

(defcustom singine-runtime-command "singine"
  "Name or path of the singine CLI executable."
  :type 'string
  :group 'singine-runtime)

(defcustom singine-runtime-singine-root
  "/private/tmp/singine-personal-os"
  "Path to the singine-personal-os checkout (sets SINGINE_ROOT)."
  :type 'directory
  :group 'singine-runtime)

;;; ── Core helpers ─────────────────────────────────────────────────────────────

(defun singine-runtime--env ()
  "Return process-environment additions for singine CLI calls."
  (list (concat "SINGINE_ROOT=" singine-runtime-singine-root)))

(defun singine-runtime--run (&rest args)
  "Run singine ARGS synchronously; return stdout string."
  (let ((process-environment
         (append (singine-runtime--env) process-environment)))
    (with-temp-buffer
      (apply #'call-process singine-runtime-command nil t nil args)
      (buffer-string))))

(defun singine-runtime--run-json (&rest args)
  "Run singine ARGS --json; return parsed alist or nil on error."
  (let* ((output (apply #'singine-runtime--run (append args '("--json"))))
         (json-object-type 'alist)
         (json-array-type 'list)
         (json-key-type 'symbol))
    (condition-case err
        (json-read-from-string output)
      (error
       (message "singine-runtime: JSON parse error: %s\nOutput: %s"
                (error-message-string err) output)
       nil))))

(defun singine-runtime--java-aliases ()
  "Return list of Java alias strings from the registry."
  (let* ((data (singine-runtime--run-json "runtime" "java" "list"))
         (versions (alist-get 'versions data)))
    (mapcar (lambda (v) (alist-get 'alias v)) versions)))

(defun singine-runtime--groovy-aliases ()
  "Return list of Groovy alias strings from the JVM registry."
  (let* ((data (singine-runtime--run-json "runtime" "groovy" "list"))
         (versions (alist-get 'versions data)))
    (mapcar (lambda (v) (alist-get 'alias v)) versions)))

(defun singine-runtime--project-dir ()
  "Return the project root for the current buffer (directory of buffer file, or default-directory)."
  (if buffer-file-name
      (file-name-directory buffer-file-name)
    default-directory))

;;; ── Java Registry buffer ─────────────────────────────────────────────────────

(defvar-local singine-java-list--data nil
  "Cached registry data for the Java registry buffer.")

(defvar singine-java-list-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map tabulated-list-mode-map)
    (define-key map (kbd "RET") #'singine-java-list-activate-at-point)
    (define-key map (kbd "a")   #'singine-java-list-activate-at-point)
    (define-key map (kbd "i")   #'singine-java-list-install-at-point)
    (define-key map (kbd "g")   #'singine-java-list-refresh)
    (define-key map (kbd "q")   #'quit-window)
    map)
  "Keymap for `singine-java-list-mode'.")

(define-derived-mode singine-java-list-mode tabulated-list-mode "Singine:Java"
  "Major mode for browsing the Singine Java runtime registry.

\\{singine-java-list-mode-map}"
  (setq tabulated-list-format
        [("Alias"     12 t)
         ("SDKMAN ID" 26 t)
         ("Major"      6 t)
         ("Status"    10 t)
         ("Installed" 10 t)
         ("Notes"      0 nil)])
  (setq tabulated-list-sort-key '("Status" . nil))
  (tabulated-list-init-header))

(defun singine-java-list--installed-p (sdkman-id)
  "Return t if SDKMAN-ID directory exists under ~/.sdkman/candidates/java/."
  (file-directory-p
   (expand-file-name sdkman-id "~/.sdkman/candidates/java/")))

(defun singine-java-list--make-entries (data)
  "Build tabulated-list entries from registry DATA alist."
  (let ((versions (alist-get 'versions data))
        (default  (alist-get 'default data)))
    (mapcar
     (lambda (v)
       (let* ((alias    (alist-get 'alias     v))
              (sdkid    (alist-get 'sdkman_id v))
              (major    (number-to-string (alist-get 'major v)))
              (status   (alist-get 'status    v))
              (notes    (or (alist-get 'notes v) ""))
              (inst     (if (singine-java-list--installed-p sdkid) "yes" "—"))
              (face     (cond ((string= alias default)  'font-lock-keyword-face)
                              ((string= inst "yes")     'font-lock-string-face)
                              (t                        'default))))
         (list alias
               (vector
                (propertize alias  'face face)
                (propertize sdkid  'face face)
                (propertize major  'face face)
                (propertize status 'face face)
                (propertize inst   'face face)
                (propertize notes  'face face)))))
     versions)))

(defun singine-java-list-refresh ()
  "Reload registry data and redisplay."
  (interactive)
  (let ((data (singine-runtime--run-json "runtime" "java" "list")))
    (if (null data)
        (message "singine-runtime: failed to load Java registry")
      (setq singine-java-list--data data)
      (setq tabulated-list-entries (singine-java-list--make-entries data))
      (tabulated-list-print t)
      (message "Singine Java registry — default: %s" (alist-get 'default data)))))

(defun singine-java-list-activate-at-point ()
  "Activate the Java version on the current line in Emacs's process environment."
  (interactive)
  (let ((alias (tabulated-list-get-id)))
    (unless alias (user-error "No alias at point"))
    (singine-java--activate alias)
    (tabulated-list-print t)))  ; refresh to update Installed column

(defun singine-java-list-install-at-point ()
  "Install the Java version on the current line via SDKMAN (opens compile buffer)."
  (interactive)
  (let ((alias (tabulated-list-get-id)))
    (unless alias (user-error "No alias at point"))
    (singine-java--install alias)))

;;; ── JVM Deps buffer ──────────────────────────────────────────────────────────

(defvar singine-jvm-deps-mode-map
  (let ((map (make-sparse-keymap)))
    (set-keymap-parent map tabulated-list-mode-map)
    (define-key map (kbd "g")   #'singine-jvm-deps-refresh)
    (define-key map (kbd "f")   #'singine-jvm-deps-filter-project)
    (define-key map (kbd "F")   #'singine-jvm-deps-show-all)
    (define-key map (kbd "q")   #'quit-window)
    map)
  "Keymap for `singine-jvm-deps-mode'.")

(define-derived-mode singine-jvm-deps-mode tabulated-list-mode "Singine:JVMDeps"
  "Major mode for browsing aggregated JVM dependencies.

Keybindings:
  g   Refresh
  f   Filter to a project
  F   Show all projects
  s   Sort by column (built-in)
  q   Quit

\\{singine-jvm-deps-mode-map}"
  (setq tabulated-list-format
        [("Project"  18 t)
         ("Scope"    12 t)
         ("Group"    28 t)
         ("Artifact" 28 t)
         ("Version"  14 t)
         ("M2"        4 nil)])
  (setq tabulated-list-sort-key '("Project" . nil))
  (tabulated-list-init-header))

(defun singine-jvm-deps--make-entries (data &optional project-filter)
  "Build tabulated-list entries from jvm deps DATA, optionally filtered."
  (let* ((projects (alist-get 'projects data))
         (entries  '()))
    (dolist (proj projects)
      (let ((name (alist-get 'name proj))
            (deps (alist-get 'deps proj)))
        (when (or (null project-filter) (string= name project-filter))
          (if (null deps)
              (push (list (concat name ":none")
                          (vector name "(no deps)" "" "" "" ""))
                    entries)
            (dolist (dep deps)
              (let* ((key   (format "%s:%s:%s:%s"
                                    name
                                    (alist-get 'group dep)
                                    (alist-get 'artifact dep)
                                    (alist-get 'version dep)))
                     (m2    (if (eq (alist-get 'in_m2 dep) t) "✓" "·"))
                     (face  (if (eq (alist-get 'in_m2 dep) t)
                                'font-lock-string-face
                              'font-lock-warning-face)))
                (push (list key
                            (vector
                             name
                             (alist-get 'scope dep)
                             (alist-get 'group dep)
                             (alist-get 'artifact dep)
                             (alist-get 'version dep)
                             (propertize m2 'face face)))
                      entries)))))))
    (nreverse entries)))

(defvar-local singine-jvm-deps--data nil)
(defvar-local singine-jvm-deps--filter nil)

(defun singine-jvm-deps-refresh ()
  "Reload and redisplay JVM deps."
  (interactive)
  (let ((data (singine-runtime--run-json "runtime" "jvm" "deps")))
    (if (null data)
        (message "singine-runtime: failed to load JVM deps")
      (setq singine-jvm-deps--data data)
      (setq tabulated-list-entries
            (singine-jvm-deps--make-entries data singine-jvm-deps--filter))
      (tabulated-list-print t)
      (let ((total (alist-get 'total_unique data))
            (shared (length (alist-get 'shared data))))
        (message "JVM deps — %d unique, %d shared across projects%s"
                 total shared
                 (if singine-jvm-deps--filter
                     (format "  [filtered: %s]" singine-jvm-deps--filter)
                   ""))))))

(defun singine-jvm-deps-filter-project (project)
  "Filter the deps view to PROJECT."
  (interactive
   (let* ((data (or singine-jvm-deps--data
                    (singine-runtime--run-json "runtime" "jvm" "deps")))
          (names (mapcar (lambda (p) (alist-get 'name p))
                         (alist-get 'projects data))))
     (list (completing-read "Filter to project: " names nil t))))
  (setq singine-jvm-deps--filter project)
  (when singine-jvm-deps--data
    (setq tabulated-list-entries
          (singine-jvm-deps--make-entries singine-jvm-deps--data project))
    (tabulated-list-print t)
    (message "Showing deps for: %s" project)))

(defun singine-jvm-deps-show-all ()
  "Remove project filter and show all deps."
  (interactive)
  (setq singine-jvm-deps--filter nil)
  (when singine-jvm-deps--data
    (setq tabulated-list-entries
          (singine-jvm-deps--make-entries singine-jvm-deps--data nil))
    (tabulated-list-print t)
    (message "Showing all JVM deps")))

;;; ── Activation helpers ───────────────────────────────────────────────────────

(defun singine-java--activate (alias)
  "Set JAVA_HOME and update exec-path in Emacs for Java ALIAS."
  (let* ((data (singine-runtime--run-json "runtime" "java" "env" alias))
         (java-home (alist-get 'java_home data))
         (sdkman-id (alist-get 'sdkman_id data)))
    (if (null java-home)
        (message "singine-java-activate: failed to resolve alias '%s'" alias)
      (setenv "JAVA_HOME" java-home)
      ;; Prepend java bin to exec-path (remove any old sdkman java entry first)
      (setq exec-path
            (cons (expand-file-name "bin" java-home)
                  (cl-remove-if
                   (lambda (p) (string-match-p "sdkman/candidates/java" p))
                   exec-path)))
      (setenv "PATH" (concat (expand-file-name "bin" java-home) ":"
                             (getenv "PATH")))
      (message "JAVA_HOME set to %s  (%s)" java-home sdkman-id))))

(defun singine-java--install (alias)
  "Install Java ALIAS via SDKMAN in a compilation buffer."
  (let* ((env-str (format "SINGINE_ROOT=%s" singine-runtime-singine-root))
         (cmd (format "%s %s runtime java install %s"
                      (concat env-str " ")
                      singine-runtime-command alias)))
    (compile cmd)))

(defun singine-groovy--activate (alias)
  "Set GROOVY_HOME and update exec-path in Emacs for Groovy ALIAS."
  (let* ((data (singine-runtime--run-json "runtime" "groovy" "env" alias))
         (groovy-home (alist-get 'home data)))
    (if (null groovy-home)
        (message "singine-groovy-activate: failed to resolve alias '%s'" alias)
      (setenv "GROOVY_HOME" groovy-home)
      (setq exec-path
            (cons (expand-file-name "bin" groovy-home)
                  (cl-remove-if
                   (lambda (p) (string-match-p "sdkman/candidates/groovy" p))
                   exec-path)))
      (message "GROOVY_HOME set to %s" groovy-home))))

;;; ── Interactive commands ─────────────────────────────────────────────────────

;;;###autoload
(defun singine-java-list ()
  "Browse the Singine Java runtime registry in a tabulated-list buffer."
  (interactive)
  (let ((buf (get-buffer-create "*Singine Java Registry*")))
    (with-current-buffer buf
      (singine-java-list-mode)
      (singine-java-list-refresh))
    (switch-to-buffer buf)))

;;;###autoload
(defun singine-java-activate (alias)
  "Select a Java ALIAS and set JAVA_HOME + exec-path in the current Emacs process."
  (interactive
   (list (completing-read "Activate Java alias: "
                          (singine-runtime--java-aliases) nil t)))
  (singine-java--activate alias))

;;;###autoload
(defun singine-java-inspect ()
  "Show which Java version the current buffer's project resolves to."
  (interactive)
  (let* ((dir  (singine-runtime--project-dir))
         (data (singine-runtime--run-json "runtime" "java" "inspect" dir)))
    (if (null data)
        (message "singine-java-inspect: failed (check SINGINE_ROOT)")
      (message "Java: alias=%s  sdkman_id=%s  source=%s  installed=%s\n%s"
               (alist-get 'alias data)
               (alist-get 'sdkman_id data)
               (alist-get 'source data)
               (alist-get 'installed data)
               (alist-get 'java_home data)))))

;;;###autoload
(defun singine-java-install (alias)
  "Install Java ALIAS via SDKMAN (uses compile-mode for progress)."
  (interactive
   (list (completing-read "Install Java alias: "
                          (singine-runtime--java-aliases) nil t)))
  (singine-java--install alias))

;;;###autoload
(defun singine-groovy-list ()
  "Browse the Singine Groovy runtime registry."
  (interactive)
  (let* ((data (singine-runtime--run-json "runtime" "groovy" "list"))
         (versions (alist-get 'versions data))
         (default  (alist-get 'default data))
         (buf (get-buffer-create "*Singine Groovy Registry*")))
    (with-current-buffer buf
      (singine-java-list-mode)   ; reuse same columns — sdkman_id field present
      (setq tabulated-list-entries
            (mapcar
             (lambda (v)
               (let* ((alias (alist-get 'alias v))
                      (sdkid (alist-get 'sdkman_id v))
                      (major (number-to-string (alist-get 'major v)))
                      (status (alist-get 'status v))
                      (notes  (or (alist-get 'notes v) ""))
                      (inst   (if (file-directory-p
                                   (expand-file-name sdkid "~/.sdkman/candidates/groovy/"))
                                  "yes" "—"))
                      (face (if (string= alias default) 'font-lock-keyword-face 'default)))
                 (list alias
                       (vector (propertize alias 'face face)
                               (propertize sdkid 'face face)
                               (propertize major 'face face)
                               (propertize status 'face face)
                               (propertize inst 'face face)
                               (propertize notes 'face face)))))
             versions))
      (tabulated-list-print t))
    (switch-to-buffer buf)
    (message "Groovy registry — default: %s" default)))

;;;###autoload
(defun singine-groovy-activate (alias)
  "Select a Groovy ALIAS and set GROOVY_HOME in the current Emacs process."
  (interactive
   (list (completing-read "Activate Groovy alias: "
                          (singine-runtime--groovy-aliases) nil t)))
  (singine-groovy--activate alias))

;;;###autoload
(defun singine-jvm-deps ()
  "Browse all JVM dependencies (singine, collibra, silkpage) in a tabulated buffer."
  (interactive)
  (let ((buf (get-buffer-create "*Singine JVM Deps*")))
    (with-current-buffer buf
      (singine-jvm-deps-mode)
      (singine-jvm-deps-refresh))
    (switch-to-buffer buf)))

;;;###autoload
(defun singine-jvm-deps-project (project)
  "Browse JVM deps filtered to PROJECT."
  (interactive
   (let* ((data (singine-runtime--run-json "runtime" "jvm" "deps"))
          (names (mapcar (lambda (p) (alist-get 'name p))
                         (alist-get 'projects data))))
     (list (completing-read "Project: " names nil t))))
  (let ((buf (get-buffer-create (format "*Singine JVM Deps: %s*" project))))
    (with-current-buffer buf
      (singine-jvm-deps-mode)
      (setq singine-jvm-deps--filter project)
      (singine-jvm-deps-refresh))
    (switch-to-buffer buf)))

;;; ── Prefix keymap  C-c s r ───────────────────────────────────────────────────

(defvar singine-runtime-map
  (let ((map (make-sparse-keymap)))
    (define-key map (kbd "j") #'singine-java-list)
    (define-key map (kbd "a") #'singine-java-activate)
    (define-key map (kbd "i") #'singine-java-inspect)
    (define-key map (kbd "n") #'singine-java-install)
    (define-key map (kbd "g") #'singine-groovy-list)
    (define-key map (kbd "G") #'singine-groovy-activate)
    (define-key map (kbd "d") #'singine-jvm-deps)
    (define-key map (kbd "D") #'singine-jvm-deps-project)
    map)
  "Prefix keymap for Singine runtime commands (bound at C-c s r).")

;; Bind the prefix. Calling code may rebind C-c s to a broader singine map.
(global-set-key (kbd "C-c s r") singine-runtime-map)

(provide 'singine-runtime)
;;; singine-runtime.el ends here
