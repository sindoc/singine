package singine.ai;

/**
 * AiProviderType — enumeration of supported AI provider back-ends.
 *
 * Each type maps to a concrete provider configuration in:
 *   singine/ai/config/{claude,collibra,openai}.edn
 *
 * Governance note
 * ───────────────
 * Provider access is always mediated by the singine governance layer.
 * No provider is called directly; all calls go through {@link AiSession}
 * which records every command and permission in a session manifest.
 *
 * Mandate delegation
 * ──────────────────
 * {@code COLLIBRA} can act both as a provider (data governance queries)
 * and as a mandate grantor: it may issue {@link AiMandate} objects that
 * extend singine's authorised scope.
 */
public enum AiProviderType {

    /** Anthropic Claude API (claude-sonnet-4-6, claude-opus-4-6, etc.). */
    CLAUDE,

    /**
     * Collibra REST API.
     * Acts as both a data-governance provider and a mandate grantor.
     */
    COLLIBRA,

    /**
     * OpenAI API — maps to Codex for code generation,
     * GPT-4o for general completion.
     */
    OPENAI,

    /**
     * Local / offline provider (e.g. Ollama, llama.cpp, local Clojure model).
     * Used when no external network is available or during air-gap testing.
     */
    LOCAL
}
