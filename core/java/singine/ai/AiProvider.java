package singine.ai;

import java.util.Map;

/**
 * AiProvider — interface for an AI back-end accessible through singine.
 *
 * Every provider is a passthrough wrapped in the singine governance layer.
 * Direct provider calls are never made; all calls go through an
 * {@link AiSession} which enforces permissions and records every command.
 *
 * Provider registry
 * ─────────────────
 * Providers are declared in:
 *   singine/ai/config/providers.edn
 * and individually configured in:
 *   singine/ai/config/{claude,collibra,openai}.edn
 *
 * The config files are git-managed; changes to provider endpoints,
 * credentials references, or rate limits are visible in git history.
 *
 * Credential handling
 * ───────────────────
 * Credentials are NEVER stored in git.  Config files hold only
 * references to credential sources:
 *   :credential/source  "env:ANTHROPIC_API_KEY"
 *   :credential/source  "~/.singine/auth/{provider}.json"
 *   :credential/source  "cacert:singine-root-ca"
 *
 * cacert.org resolution
 * ─────────────────────
 * For providers requiring custom CA chains, the singine JVM trust store
 * is used.  The trust store is managed via the existing
 * singine/core/resources/identity/trust.edn configuration.
 */
public interface AiProvider {

    // ── Identity ──────────────────────────────────────────────────

    /** Stable provider ID: {@code "claude"}, {@code "collibra"}, {@code "openai"}. */
    String getId();

    /** Human-readable name. */
    String getName();

    /** Enum type for switch-based dispatch. */
    AiProviderType getType();

    /** API base URL or endpoint. */
    String getEndpoint();

    /** API / model version string. */
    String getVersion();

    // ── Configuration ─────────────────────────────────────────────

    /**
     * Provider-specific configuration map loaded from
     * {@code singine/ai/config/{provider}.edn}.
     * Keys are EDN-namespaced strings.
     */
    Map<String, Object> getConfig();

    // ── Session factory ───────────────────────────────────────────

    /**
     * Start a new governed session with this provider.
     *
     * @param context initial session context (user, cwd, activity ref, etc.)
     * @param mandate optional pre-issued mandate from a third party
     * @return a new open {@link AiSession}
     */
    AiSession startSession(Map<String, Object> context, AiMandate mandate);

    // ── Health ────────────────────────────────────────────────────

    /**
     * Check connectivity to the provider.
     * Returns {@code true} if the provider is reachable and configured.
     */
    boolean isAvailable();

    // ── Serialisation ─────────────────────────────────────────────

    /**
     * Serialise the provider record to EDN for the providers registry.
     *
     * <pre>{@code
     * {:provider/id "claude"
     *  :provider/type :CLAUDE
     *  :provider/name "Anthropic Claude"
     *  :provider/endpoint "https://api.anthropic.com/v1"
     *  :provider/version "claude-sonnet-4-6"}
     * }</pre>
     */
    String toEdn();

    /** Serialise to XML for Collibra API asset cataloguing. */
    String toXml();
}
