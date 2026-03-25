;; -*- lexical-binding: t; -*-
;;
;; singine-fa-proof.el -- Build Persian/Arabic font proof PDFs from Emacs
;;
;; The workflow is intentionally simple:
;; 1. resolve each requested family to an exact font file via fontconfig
;; 2. emit a self-contained TeX specimen
;; 3. compile to PDF with XeLaTeX
;; 4. optionally render HarfBuzz previews with hb-view

(require 'cl-lib)
(require 'json)
(require 'seq)
(require 'subr-x)

(defgroup singine-fa-proof nil
  "Persian font proofing helpers for Singine."
  :group 'tools
  :prefix "singine-fa-proof-")

(defcustom singine-fa-proof-latex-bin "xelatex"
  "LaTeX engine used to compile the generated specimen."
  :type 'string)

(defcustom singine-fa-proof-fc-match-bin "fc-match"
  "fontconfig executable used to resolve font families to exact files."
  :type 'string)

(defcustom singine-fa-proof-hb-view-bin "hb-view"
  "HarfBuzz preview executable."
  :type 'string)

(defcustom singine-fa-proof-default-fonts
  '("Amiri"
    "Geeza Pro"
    "Al Bayan"
    "Damascus"
    "Baghdad"
    "Tahoma")
  "Default Persian/Arabic-capable font families to compare."
  :type '(repeat string))

(defcustom singine-fa-proof-default-title "Singine Persian Font Proof"
  "Default title for generated proof documents."
  :type 'string)

(defcustom singine-fa-proof-artifacts-dir nil
  "Directory for generated TeX, PDF, and manifest artifacts.
When nil, defaults to docs/target/farsi-proof under the singine repo."
  :type '(choice (const :tag "Use repo docs/target" nil)
                 directory))

(defcustom singine-fa-proof-default-text
  (string-join
   '("اَللّهُمَّ اَهْلَ الْكِبْرِيَاءِ وَالْعَظَمَةِ وَأَهْلَ الْجُودِ وَالْجَبَرُوتِ وَأَهْلَ الْعَفْوِ وَالرَّحْمَةِ."
     "می‌خواهم شکل‌گیری حروف، جای‌گیری اعراب، نیم‌فاصله، کشیدگی، و خوانایی متن فارسی را دقیق ببینم."
     "فارسی امروز: کتاب‌ها، می‌روم، نمی‌خواهم، اندازه‌گیری، برنامه‌ریزی، پژوهش‌محور."
     "اعداد و نشانه‌ها: ۰۱۲۳۴۵۶۷۸۹ | 123456789 | () [] {} «»")
   "\n\n")
  "Default specimen text used when no region or buffer text is supplied."
  :type 'string)

(defcustom singine-fa-proof-hb-font-size 42
  "Font size used for HarfBuzz previews."
  :type 'integer)

(defconst singine-fa-proof--source-file
  (or load-file-name buffer-file-name
      (locate-library "singine-fa-proof.el"))
  "Source path for `singine-fa-proof.el'.")

(defun singine-fa-proof-root ()
  "Return the singine repo root inferred from this file."
  (directory-file-name
   (expand-file-name ".." (file-name-directory singine-fa-proof--source-file))))

(defun singine-fa-proof-output-dir ()
  "Return the default generated-artifact directory."
  (or singine-fa-proof-artifacts-dir
      (expand-file-name "docs/target/farsi-proof" (singine-fa-proof-root))))

(defun singine-fa-proof--timestamp ()
  (format-time-string "%Y%m%d-%H%M%S"))

(defun singine-fa-proof--slug (text)
  (let ((slug (downcase (replace-regexp-in-string "[^[:alnum:]]+" "-" text))))
    (setq slug (replace-regexp-in-string "-+" "-" slug))
    (setq slug (replace-regexp-in-string "\\`-\\|-\\'" "" slug))
    (if (string-empty-p slug) "proof" slug)))

(defun singine-fa-proof--trim-lines (text)
  (seq-filter
   (lambda (line) (not (string-empty-p line)))
   (mapcar #'string-trim (split-string text "\n[ \t\n]*"))))

(defun singine-fa-proof--tex-escape (text)
  (let ((value text))
    (setq value (replace-regexp-in-string "\\\\" "\\\\textbackslash{}" value t t))
    (setq value (replace-regexp-in-string "{" "\\\\{" value t t))
    (setq value (replace-regexp-in-string "}" "\\\\}" value t t))
    (setq value (replace-regexp-in-string "\\$" "\\\\$" value t t))
    (setq value (replace-regexp-in-string "%" "\\\\%" value t t))
    (setq value (replace-regexp-in-string "&" "\\\\&" value t t))
    (setq value (replace-regexp-in-string "#" "\\\\#" value t t))
    (setq value (replace-regexp-in-string "_" "\\\\_" value t t))
    (setq value (replace-regexp-in-string "\\^" "\\\\textasciicircum{}" value t t))
    (replace-regexp-in-string "~" "\\\\textasciitilde{}" value t t)))

(defun singine-fa-proof--call (program &rest args)
  (with-temp-buffer
    (let ((exit (apply #'process-file program nil (list (current-buffer) nil) nil args)))
      (list :exit exit :output (string-trim (buffer-string))))))

(defun singine-fa-proof--font-record (family)
  "Resolve FAMILY to a concrete font file."
  (pcase-let* ((`(:exit ,exit :output ,output)
                (singine-fa-proof--call
                 singine-fa-proof-fc-match-bin
                 "-f" "%{family[0]}\t%{style[0]}\t%{file}\n"
                 (format "%s:lang=fa" family)))
               (parts (split-string output "\t")))
    (unless (and (zerop exit) (= (length parts) 3))
      (error "Could not resolve font family %s via %s" family singine-fa-proof-fc-match-bin))
    (list
     :request family
     :family (nth 0 parts)
     :style (nth 1 parts)
     :file (nth 2 parts)
     :directory (file-name-directory (nth 2 parts))
     :filename (file-name-nondirectory (nth 2 parts))
     :tex-safe-file
     (not (string-match-p "[\\[\\]]" (file-name-nondirectory (nth 2 parts)))))))

(defun singine-fa-proof--read-font-list (&optional prompt)
  (split-string
   (read-string (or prompt "Font families (comma separated): ")
                (string-join singine-fa-proof-default-fonts ", "))
   "[[:space:]]*,[[:space:]]*" t))

(defun singine-fa-proof--read-text ()
  (cond
   ((use-region-p)
    (buffer-substring-no-properties (region-beginning) (region-end)))
   ((derived-mode-p 'text-mode 'org-mode 'markdown-mode)
    (string-trim (buffer-substring-no-properties (point-min) (point-max))))
   (t
    singine-fa-proof-default-text)))

(defun singine-fa-proof--output-stem (title)
  (format "%s-%s"
          (singine-fa-proof--timestamp)
          (singine-fa-proof--slug title)))

(defun singine-fa-proof--latex-symbol-suffix (index)
  (let ((n index)
        (chars '()))
    (while (> n 0)
      (setq n (1- n))
      (push (+ ?a (% n 26)) chars)
      (setq n (/ n 26)))
    (apply #'string chars)))

(defun singine-fa-proof--latex-block (font index lines)
  (let* ((command (format "\\singinefaprooffont%s"
                          (singine-fa-proof--latex-symbol-suffix index)))
         (header (format "%s  ->  %s / %s"
                         (plist-get font :request)
                         (plist-get font :family)
                         (plist-get font :style)))
         (body (mapconcat
                (lambda (line)
                  (format "{%s\\fontsize{20}{30}\\selectfont %s\\\\[5mm]}"
                          command
                          (singine-fa-proof--tex-escape line)))
                lines
                "\n")))
    (string-join
     (list
      (format "\\newfontfamily%s[Path=%s, UprightFont={%s}, Script=Arabic, Language=Persian, Ligatures=TeX, RawFeature={+kern,+mark,+mkmk}]{%s}"
              command
              (singine-fa-proof--tex-escape (plist-get font :directory))
              (singine-fa-proof--tex-escape (plist-get font :filename))
              (singine-fa-proof--tex-escape (plist-get font :filename)))
      "\\begin{tcolorbox}[breakable,colback=cream,colframe=accent,title={\\texttt{"
      (singine-fa-proof--tex-escape header)
      "}}]"
      "\\begin{RTL}"
      body
      "\\end{RTL}"
      "\\end{tcolorbox}")
     "\n")))

(defun singine-fa-proof--tex (title fonts text)
  (let* ((lines (singine-fa-proof--trim-lines text))
         (font-blocks
          (cl-loop for font in fonts
                   for idx from 1
                   collect (singine-fa-proof--latex-block font idx lines))))
    (string-join
     (append
      '("\\documentclass[12pt]{article}"
        "\\usepackage[a4paper,margin=16mm]{geometry}"
        "\\usepackage{fontspec}"
        "\\usepackage{bidi}"
        "\\usepackage{xcolor}"
        "\\usepackage{parskip}"
        "\\usepackage{tcolorbox}"
        "\\tcbuselibrary{breakable,skins}"
        "\\definecolor{accent}{HTML}{174C43}"
        "\\definecolor{cream}{HTML}{F7F0E3}"
        "\\definecolor{ink}{HTML}{1D1B18}"
        "\\pagestyle{empty}"
        "\\setlength{\\parindent}{0pt}"
        "\\begin{document}"
        "{\\Large\\bfseries "
        )
      (list (singine-fa-proof--tex-escape title)
            "}\\\\[2mm]")
      '("{\\small Built by singine-fa-proof.el. Each block uses an exact font file resolved through fontconfig.}\\\\[4mm]"
        "\\color{ink}")
      font-blocks
      '("\\end{document}"))
     "\n")))

(defun singine-fa-proof--manifest (title fonts text pdf tex)
  `(("title" . ,title)
    ("timestamp" . ,(format-time-string "%FT%T%z"))
    ("latex_bin" . ,singine-fa-proof-latex-bin)
    ("output_pdf" . ,pdf)
    ("output_tex" . ,tex)
    ("text" . ,text)
    ("fonts" . ,(mapcar
                 (lambda (font)
                   `(("request" . ,(plist-get font :request))
                     ("resolved_family" . ,(plist-get font :family))
                     ("style" . ,(plist-get font :style))
                     ("file" . ,(plist-get font :file))))
                 fonts))))

(defun singine-fa-proof-build (fonts text &optional title)
  "Build a proof PDF for FONTS using TEXT.
Returns a plist with the generated paths."
  (let* ((title (or title singine-fa-proof-default-title))
         (out-dir (singine-fa-proof-output-dir))
         (stem (singine-fa-proof--output-stem title))
         (tex-file (expand-file-name (format "%s.tex" stem) out-dir))
         (pdf-file (expand-file-name (format "%s.pdf" stem) out-dir))
         (json-file (expand-file-name (format "%s.json" stem) out-dir))
         (records (mapcar #'singine-fa-proof--font-record fonts))
         (default-directory out-dir)
         (process-environment (cons "TEXMFVAR=/tmp/texmf-var" process-environment)))
    (let ((unsafe
           (seq-filter
            (lambda (font) (not (plist-get font :tex-safe-file)))
            records)))
      (when unsafe
        (error
         "These fonts resolve to variable-font filenames that this XeLaTeX path does not handle cleanly: %s. Use singine-fa-proof-preview-with-harfbuzz or choose static font files"
         (mapconcat (lambda (font) (plist-get font :request)) unsafe ", "))))
    (make-directory out-dir t)
    (with-temp-file tex-file
      (set-buffer-file-coding-system 'utf-8-unix)
      (insert (singine-fa-proof--tex title records text)))
    (with-temp-file json-file
      (set-buffer-file-coding-system 'utf-8-unix)
      (insert (json-encode (singine-fa-proof--manifest title records text pdf-file tex-file))))
    (let ((exit (call-process singine-fa-proof-latex-bin nil "*singine-fa-proof*" t
                              "-interaction=nonstopmode"
                              "-halt-on-error"
                              (file-name-nondirectory tex-file))))
      (unless (zerop exit)
        (error "LaTeX build failed; see *singine-fa-proof*"))
      ;; second pass for stable references/output
      (setq exit (call-process singine-fa-proof-latex-bin nil "*singine-fa-proof*" t
                               "-interaction=nonstopmode"
                               "-halt-on-error"
                               (file-name-nondirectory tex-file)))
      (unless (zerop exit)
        (error "Second LaTeX pass failed; see *singine-fa-proof*")))
    (list :pdf pdf-file :tex tex-file :json json-file :fonts records :title title)))

(defun singine-fa-proof-build-sample (&optional fonts)
  "Build a specimen PDF from `singine-fa-proof-default-text'."
  (interactive)
  (let* ((fonts (or fonts singine-fa-proof-default-fonts))
         (result (singine-fa-proof-build fonts singine-fa-proof-default-text)))
    (when (called-interactively-p 'interactive)
      (message "Built %s" (plist-get result :pdf)))
    result))

(defun singine-fa-proof-buffer-to-pdf (fonts &optional title)
  "Build a specimen PDF from the current buffer or active region."
  (interactive (list (singine-fa-proof--read-font-list)
                     (read-string "Title: " singine-fa-proof-default-title)))
  (let ((result (singine-fa-proof-build fonts (singine-fa-proof--read-text) title)))
    (when (called-interactively-p 'interactive)
      (message "Built %s" (plist-get result :pdf)))
    result))

(defun singine-fa-proof-preview-with-harfbuzz (font &optional text)
  "Render TEXT with FONT using hb-view and return the generated preview path."
  (interactive
   (list (completing-read "Font family: " singine-fa-proof-default-fonts nil nil nil nil
                          (car singine-fa-proof-default-fonts))
         (read-string "Text: " singine-fa-proof-default-text)))
  (let* ((record (singine-fa-proof--font-record font))
         (out-dir (singine-fa-proof-output-dir))
         (stem (format "%s-%s-hb"
                       (singine-fa-proof--timestamp)
                       (singine-fa-proof--slug font)))
         (pdf-file (expand-file-name (format "%s.pdf" stem) out-dir))
         (sample (or text singine-fa-proof-default-text)))
    (make-directory out-dir t)
    (let ((exit (call-process singine-fa-proof-hb-view-bin nil "*singine-fa-proof*" t
                              "--output-format=pdf"
                              (format "--output-file=%s" pdf-file)
                              "--direction=rtl"
                              "--language=fa"
                              "--script=Arab"
                              "--margin=32"
                              (format "--font-size=%d" singine-fa-proof-hb-font-size)
                              (plist-get record :file)
                              sample)))
      (unless (zerop exit)
        (error "hb-view failed; see *singine-fa-proof*")))
    (when (called-interactively-p 'interactive)
      (message "Built HarfBuzz preview %s" pdf-file))
    pdf-file))

(defun singine-fa-proof-list-font-candidates ()
  "Show resolved default font candidates in a temporary buffer."
  (interactive)
  (with-current-buffer (get-buffer-create "*singine-fa-fonts*")
    (read-only-mode -1)
    (erase-buffer)
    (insert "Singine Persian font candidates\n")
    (insert "==============================\n\n")
    (dolist (font singine-fa-proof-default-fonts)
      (condition-case err
          (let ((record (singine-fa-proof--font-record font)))
            (insert (format "%-20s -> %s\n" font (plist-get record :file))))
        (error
         (insert (format "%-20s -> ERROR: %s\n" font (error-message-string err))))))
    (goto-char (point-min))
    (view-mode 1)
    (display-buffer (current-buffer))))

(provide 'singine-fa-proof)
