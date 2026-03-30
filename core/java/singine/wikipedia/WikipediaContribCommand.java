package singine.wikipedia;

/**
 * Contract view of the {@code singine wikipedia contrib} command family.
 *
 * <p>This interface exists as a documentation anchor for Javadoc HTML and XML
 * publication. It makes the action vocabulary explicit for downstream tooling that
 * consumes Singine's JVM documentation surfaces.</p>
 *
 * <h2>CLI form</h2>
 * <pre>
 *   singine wikipedia contrib collibra [--repo-root PATH] [--action ACTION] [--json]
 * </pre>
 *
 * <h2>Canonical topic</h2>
 * <p>The current documented topic is {@code collibra}.</p>
 *
 * <h2>Examples</h2>
 * <pre>
 *   singine wikipedia contrib collibra --json
 *   singine wikipedia contrib collibra --action visualize --json
 *   singine wikipedia contrib collibra --action test-case --json
 * </pre>
 */
public interface WikipediaContribCommand {

    /** Canonical topic name for the current Wikipedia contribution surface. */
    String TOPIC_COLLIBRA = "collibra";

    /** Read workflow metadata without mutating files. */
    String ACTION_STATUS = "status";

    /** Refresh derived repository artifacts such as Org, Logseq, JSON-LD, Atom, and RSS. */
    String ACTION_REFRESH = "refresh";

    /** Ingest live MediaWiki article, talk-page, and template changes into repo artifacts. */
    String ACTION_INGEST_LIVE = "ingest-live";

    /** Synchronize selected repository content into the Singine kernel Logseq graph. */
    String ACTION_KERNEL_SYNC = "kernel-sync";

    /** Render the Mermaid process diagram from the canonical XML process payload. */
    String ACTION_VISUALIZE = "visualize";

    /** Run the end-to-end command-line verification workflow. */
    String ACTION_TEST_CASE = "test-case";

    /** Install the repository-local post-commit hook. */
    String ACTION_INSTALL_HOOKS = "install-hooks";

    /** Render individualized opt-in updates without sending mail. */
    String ACTION_PREVIEW_MAIL = "preview-mail";

    /** Send individualized updates to opted-in recipients only. */
    String ACTION_SEND_MAIL = "send-mail";
}
