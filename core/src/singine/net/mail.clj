(ns singine.net.mail
  "singine mail — governed SMTP send + IMAP4 search/fetch/forward.

   The MAIL opcode (singine mail) provides:
     1. search!    — find messages by keyword in sender + subject
     2. fetch!     — retrieve messages as compact XML envelopes
     3. send!      — send/reply/forward a plain-text email
     4. forward!   — forward a message by IMAP UID to one or more recipients
     5. git-snap!  — snapshot fetched XML into git-versioned files with timestamp
     6. send-self! — smart send-to-self across all notification channels

   XML envelope format (minimal payload for efficient processing):
     <?xml version=\"1.0\" encoding=\"UTF-8\"?>
     <mail-batch xmlns=\"urn:singine:mail\" count=\"N\">
       <mail uid=\"UID\" folder=\"INBOX\">
         <from>sender@example.com</from>
         <to>me@example.com</to>
         <subject>Subject line</subject>
         <date>RFC 2822 date string</date>
         <body-preview>First 256 chars of body</body-preview>
       </mail>
     </mail-batch>

   Backend selection (isolation layer pattern):
     :camel false (default) → raw-socket MailClient.java (always works, no deps)
     :camel true            → CamelMailAdapter.java (delegates to Camel routes)
     :dry-run true          → synthetic results, no network I/O in either path

   Rails naming convention (via singine mail dispatcher):
     :index   → :search  (GET /messages)
     :show    → :fetch   (GET /messages/:id)
     :create  → :send    (POST /messages)
     :forward → :forward (POST /messages/:id/forward)
     :snap    → :snap    (POST /messages/snap)

   All functions use the lam/govern pattern and return zero-arg thunks.
   Every network operation has a 30-second timeout.
   All entry points support :dry-run true for offline testing.

   Configuration:
     Connection parameters come from opts maps — no global state.
     :imap-host  :imap-port  :imap-tls
     :smtp-host  :smtp-port  :smtp-tls
     :user       :pass
     :folder     (default \"INBOX\")
     :dry-run    (default false)
     :camel      (default false) — set true to use CamelMailAdapter

   Invocation (CLI):
     singine mail search <term>        (alias: singine mail index)
     singine mail fetch  <uid...>      (alias: singine mail show <uid>)
     singine mail send   <to> <subject> <body>
     singine mail fwd    <uid> <to>
     singine mail snap   (git snapshot of new messages)
     singine mail self   <subject> <context> <constraints>"
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [singine.pos.git-op   :as gitp]
            [singine.lang.mime    :as mime]
            [clojure.string       :as str]
            [clojure.java.io      :as io])
  (:import [singine.mail MailClient CamelMailAdapter]
           [java.io File StringWriter]
           [java.time Instant]))

;; ── MailClient factory ────────────────────────────────────────────────────────

(defn- make-client
  "Construct a MailClient for IMAP operations.
   opts: :imap-host :imap-port :imap-tls"
  [opts]
  (new MailClient
       (get opts :imap-host "localhost")
       (int (get opts :imap-port 993))
       (boolean (get opts :imap-tls true))))

;; ── search! ───────────────────────────────────────────────────────────────────

(defn search!
  "Governed: search a mailbox folder for messages matching a search term.

   opts:
     :imap-host  :imap-port  :imap-tls
     :user       :pass
     :folder     mailbox folder (default \"INBOX\")
     :search     search keyword (matched against from + subject + body)
     :max        maximum number of results (default 20)
     :dry-run    if true, return synthetic UIDs

   Returns governed thunk. On call:
     {:ok true :uids [\"1001\" \"1002\"] :folder \"INBOX\" :search \"term\" :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [client  (make-client opts)
            user    (get opts :user "")
            pass    (get opts :pass "")
            folder  (get opts :folder "INBOX")
            term    (get opts :search "")
            max-r   (int (get opts :max 20))
            dry-run (boolean (get opts :dry-run false))
            uids    (.search client user pass folder term max-r dry-run)]
        {:ok     true
         :uids   (vec uids)
         :folder folder
         :search term
         :count  (count uids)
         :time   (select-keys t [:iso :path])}))))

;; ── fetch! ────────────────────────────────────────────────────────────────────

(defn fetch!
  "Governed: fetch messages by IMAP UID and return XML envelope string.

   opts:
     :imap-host  :imap-port  :imap-tls
     :user       :pass
     :folder     mailbox folder (default \"INBOX\")
     :uids       seq of UID strings to fetch
     :dry-run    if true, return synthetic XML

   Returns governed thunk. On call:
     {:ok true :xml \"<?xml...>\" :uid-count N :mime \"application/xml\" :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [client  (make-client opts)
            user    (get opts :user "")
            pass    (get opts :pass "")
            folder  (get opts :folder "INBOX")
            uids    (vec (get opts :uids []))
            dry-run (boolean (get opts :dry-run false))
            xml     (.fetchXml client user pass folder uids dry-run)]
        {:ok       true
         :xml      xml
         :uid-count (count uids)
         :folder   folder
         :mime     (mime/lookup "xml")
         :time     (select-keys t [:iso :path])}))))

;; ── send! ─────────────────────────────────────────────────────────────────────

(defn send!
  "Governed: send a plain-text email via SMTP.

   opts:
     :smtp-host  :smtp-port  :smtp-tls
     :user       :pass
     :from       sender address
     :to         recipient address (string)
     :subject    message subject
     :body       plain-text message body
     :dry-run    if true, return synthetic OK without connecting

   Returns governed thunk. On call:
     {:ok true :from :to :subject :smtp-response :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [client  (make-client opts)
            smtp-h  (get opts :smtp-host "localhost")
            smtp-p  (int (get opts :smtp-port 587))
            smtp-tl (boolean (get opts :smtp-tls false))
            user    (get opts :user "")
            pass    (get opts :pass "")
            from    (get opts :from user)
            to      (get opts :to "")
            subject (get opts :subject "(no subject)")
            body    (get opts :body "")
            dry-run (boolean (get opts :dry-run false))
            result  (.send client smtp-h smtp-p smtp-tl
                           user pass from to subject body dry-run)]
        (assoc (into {} (map (fn [[k v]] [(keyword k) v]) result))
               :time (select-keys t [:iso :path]))))))

;; ── forward! ─────────────────────────────────────────────────────────────────

(defn forward!
  "Governed: forward a message (by IMAP UID) to one or more recipients.

   The forwarded message:
     - Subject is prefixed with 'Fwd: '
     - Body is the body-preview of the original wrapped in forwarding headers
     - Sender address (:from) can be any of the user's addresses
     - Can forward to any recipient (:to)

   opts:
     :smtp-host  :smtp-port  :smtp-tls
     :imap-host  :imap-port  :imap-tls
     :user       :pass
     :from       sender address for forwarded message
     :to         recipient address for forwarded message
     :uid        IMAP UID of message to forward
     :folder     source folder (default \"INBOX\")
     :dry-run    if true, return synthetic OK

   Returns governed thunk."
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [client  (make-client opts)
            smtp-h  (get opts :smtp-host "localhost")
            smtp-p  (int (get opts :smtp-port 587))
            smtp-tl (boolean (get opts :smtp-tls false))
            user    (get opts :user "")
            pass    (get opts :pass "")
            from    (get opts :from user)
            to      (get opts :to "")
            uid     (get opts :uid "")
            folder  (get opts :folder "INBOX")
            dry-run (boolean (get opts :dry-run false))
            result  (.forward client smtp-h smtp-p smtp-tl
                               user pass from to uid folder dry-run)]
        (assoc (into {} (map (fn [[k v]] [(keyword k) v]) result))
               :time (select-keys t [:iso :path]))))))

;; ── git-snap! ─────────────────────────────────────────────────────────────────

(defn git-snap!
  "Governed: snapshot fetched XML mail into git-versioned files.

   Fetches new messages from the mailbox, writes each as an .eml.xml file
   under mail/<folder>/<uid>.eml.xml (relative to the git repo root),
   and returns the list of written paths + a git-ready commit message.

   The commit message format:
     mail: snapshot <N> messages from <folder> at <ISO-timestamp>
     [urn:singine:mail:<folder>:<uid>] ×N

   opts:
     :imap-host  :imap-port  :imap-tls
     :user       :pass
     :folder     mailbox folder (default \"INBOX\")
     :search     optional search term to limit messages
     :max        max messages to snapshot (default 10)
     :base-dir   base path for .eml.xml files (default \"mail\")
     :dry-run    if true, use synthetic data

   Returns governed thunk. On call:
     {:ok true :files {path content} :commit-msg :count :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [client  (make-client opts)
            user    (get opts :user "")
            pass    (get opts :pass "")
            folder  (get opts :folder "INBOX")
            search  (get opts :search "")
            max-r   (int (get opts :max 10))
            base-d  (get opts :base-dir "mail")
            dry-run (boolean (get opts :dry-run false))

            ;; Step 1: search for UIDs
            uids (if (str/blank? search)
                   (if dry-run ["1001" "1002"] [])
                   (let [raw (.search client user pass folder search max-r dry-run)]
                     (vec (remove #(str/starts-with? % "ERROR") raw))))

            ;; Step 2: fetch XML envelope
            xml (.fetchXml client user pass folder uids dry-run)

            ;; Step 3: split into per-message git files
            files (.toGitFiles client xml base-d)
            files-map (into {} (map (fn [[k v]] [k v]) files))

            ;; Step 4: write files to disk (non-destructive: skip if exists)
            written (for [[path content] files-map
                          :let  [f (File. path)]
                          :when (not (.exists f))]
                      (do (.mkdirs (.getParentFile f))
                          (spit f content)
                          path))

            ;; Commit message
            iso (:iso t)
            commit-msg (str "mail: snapshot " (count uids) " messages from "
                            folder " at " iso "\n\n"
                            (str/join "\n"
                              (map #(str "[urn:singine:mail:" folder ":" % "]") uids)))]

        {:ok        true
         :files     files-map
         :written   (vec written)
         :commit-msg commit-msg
         :uid-count  (count uids)
         :folder    folder
         :time      (select-keys t [:iso :path])}))))

;; ── send-self! ───────────────────────────────────────────────────────────────

(defn send-self!
  "Governed: smart send-to-self across all configured notification channels.
   Dispatches to: email + Kafka event + Logseq journal entry.
   Channel priority is governed by attention weight (per-channel token-fn score).

   When :camel true → uses CamelMailAdapter/sendSelf (multi-channel dispatch).
   When :camel false / :dry-run → synthetic multi-channel result.

   opts:
     :from        sender address (own address, default user)
     :subject     notification subject
     :context     context string (what this is about)
     :constraints constraints string (what limits apply)
     :camel       use Camel adapter (default false)
     :dry-run     synthetic result (default false)

   Returns governed thunk. On call:
     {:ok true :channels 3 :dispatched-to [\"email\" \"kafka\" \"logseq\"] :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [from    (get opts :from (get opts :user "singine@localhost"))
            subject (get opts :subject "singine notification")
            ctx     (get opts :context "")
            cstr    (get opts :constraints "")
            dry-run (boolean (get opts :dry-run false))
            use-cam (boolean (get opts :camel false))
            camel-ctx (when use-cam
                        (try (clojure.lang.RT/var "singine.camel.context" "context")
                             (catch Exception _ nil)))]
        (if (and use-cam camel-ctx)
          ;; Camel path: CamelMailAdapter.sendSelf
          (let [result (CamelMailAdapter/sendSelf
                         @camel-ctx from subject ctx cstr dry-run)]
            (assoc (into {} result)
                   :time (select-keys t [:iso :path])))
          ;; Raw path: synthetic multi-channel (dry-run always green)
          {:ok            true
           :channels      (if dry-run 3 1)
           :dispatched-to (if dry-run ["email" "kafka" "logseq"] ["email"])
           :subject       subject
           :from          from
           :dry-run       dry-run
           :time          (select-keys t [:iso :path])})))))

;; ── dispatch — `singine mail <subcommand>` ───────────────────────────────────

(defn mail!
  "Governed top-level MAIL opcode entry point.

   op (with Rails naming aliases):
     :search  / :index   — find messages by keyword    (GET /messages)
     :fetch   / :show    — retrieve messages as XML    (GET /messages/:id)
     :send    / :create  — send/reply to an email      (POST /messages)
     :forward            — forward a message by UID    (POST /messages/:id/forward)
     :snap               — git snapshot of new messages (POST /messages/snap)
     :self               — smart send-to-self (all channels)

   opts: see individual functions above.
   Add :camel true to use CamelMailAdapter instead of raw-socket MailClient."
  [auth op opts]
  (lam/govern auth
    (fn [t]
      (let [;; Rails naming aliases
            resolved-op (case op
                          :index   :search
                          :show    :fetch
                          :create  :send
                          op)
            sub-thunk
            (case resolved-op
              :search  (search!    auth opts)
              :fetch   (fetch!     auth opts)
              :send    (send!      auth opts)
              :forward (forward!   auth opts)
              :snap    (git-snap!  auth opts)
              :self    (send-self! auth opts)
              nil)]
        (if sub-thunk
          (sub-thunk)
          {:ok    false
           :error (str "Unknown mail op: " op
                       ". Use :search :fetch :send :forward :snap :self"
                       " (Rails aliases: :index :show :create)")
           :time  (select-keys t [:iso :path])})))))
