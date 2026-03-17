/**
 * Singine Authentication and Cryptography — JWS token production and certificate management.
 *
 * <h2>Overview</h2>
 * <p>The {@code singine.auth} package provides a zero-external-dependency authentication
 * and cryptography layer built entirely on JDK 11+ standard library.</p>
 *
 * <h2>Components</h2>
 * <ul>
 *   <li>{@link singine.auth.JwsToken}     — RFC 7515/7519 JWT/JWS producer and verifier
 *       (RS256 and HS256)</li>
 *   <li>{@link singine.auth.CertAuthority} — JVM keystore management, RSA key-pair generation,
 *       PEM import/export, JVM cacerts enumeration</li>
 * </ul>
 *
 * <h2>JWS Token (singine.crypt)</h2>
 * <p>{@link singine.auth.JwsToken} implements compact JWT serialisation with no third-party
 * library (no Nimbus JOSE, no Auth0 java-jwt). Singine-specific claims are injected
 * automatically on every token:</p>
 * <ul>
 *   <li>{@code iss}  — {@code urn:singine:idp}</li>
 *   <li>{@code iat}  — issued-at epoch seconds</li>
 *   <li>{@code exp}  — expiry = iat + ttlSeconds</li>
 *   <li>{@code jti}  — random UUID (replay prevention)</li>
 *   <li>{@code sid}  — {@code urn:singine:session:<jti-prefix>}</li>
 * </ul>
 *
 * <h3>RS256 (asymmetric — SSH-style cert auth)</h3>
 * <pre>
 *   CertAuthority ca = new CertAuthority("/path/to/singine.jks", "changeit");
 *   CertAuthority.KeyPairEntry kpe = ca.generateKeyPair("singine-idp-2026");
 *   String token = JwsToken.signRS256(kpe.keyPair.getPrivate(), claims, 3600);
 *   Map&lt;String,Object&gt; decoded = JwsToken.verifyRS256(token, kpe.keyPair.getPublic());
 * </pre>
 *
 * <h3>HS256 (symmetric — shared secret)</h3>
 * <pre>
 *   String token   = JwsToken.signHS256("my-secret", claims, 3600);
 *   Map&lt;String,Object&gt; decoded = JwsToken.verifyHS256("my-secret", token);
 * </pre>
 *
 * <h2>Certificate Authority (singine.crypt)</h2>
 * <p>{@link singine.auth.CertAuthority} wraps the JVM's JKS/PKCS12 keystore with
 * singine-specific URN naming:</p>
 * <pre>
 *   urn:singine:ca:&lt;sha256-fingerprint-hex&gt;
 *   urn:singine:keypair:&lt;alias&gt;:&lt;fp-prefix-16&gt;
 * </pre>
 * <p>Design principles:</p>
 * <ul>
 *   <li>Non-destructive: never modifies the JVM system cacerts store</li>
 *   <li>Uses a separate {@code singine.jks} keystore at a configurable path</li>
 *   <li>Custom cacerts path set via {@code -Djavax.net.ssl.trustStore} or
 *       {@code $SINGINE_CACERTS} / {@code $JAVA_HOME/lib/security/cacerts}</li>
 *   <li>RSA 4096-bit key pairs for all generated credentials</li>
 * </ul>
 *
 * <h2>JVM and cacerts Configuration</h2>
 * <p>The effective cacerts file is resolved in this order:</p>
 * <ol>
 *   <li>{@code javax.net.ssl.trustStore} system property</li>
 *   <li>{@code $SINGINE_CACERTS} environment variable</li>
 *   <li>{@code $JAVA_HOME/conf/security/cacerts} (Java 9+)</li>
 *   <li>{@code $JAVA_HOME/lib/security/cacerts} (Java 8)</li>
 * </ol>
 * <p>Use {@link singine.auth.CertAuthority#jvmCacertsPath()} to inspect the resolved path.</p>
 *
 * <h2>DNS and Network</h2>
 * <p>Tokens produced by this package are consumed by {@link singine.local.SingineLocalServer}
 * on {@code singine.local:2000} and verified against registered public keys in
 * {@link singine.local.TrustedIndividualStore}. See {@code singine.local} package for
 * the full HTTP + DNS integration.</p>
 *
 * <h2>Testing</h2>
 * <p>Integration tests in {@link singine.local.SingineLocalIntegrationTest} cover:</p>
 * <ul>
 *   <li>TC-12: HS256 round-trip (sign, verify, reject wrong secret)</li>
 *   <li>TC-13: RS256 round-trip (CertAuthority key-pair, sign, verify, reject wrong key)</li>
 *   <li>TC-05: RS256 SSH operator access to {@code singine.local:2000/ssh/access}</li>
 * </ul>
 * <p>Run: {@code ant test-local}</p>
 *
 * @see singine.auth.JwsToken
 * @see singine.auth.CertAuthority
 * @see singine.local.SingineLocal#TEST_JWT_SECRET
 * @see singine.local.TrustedIndividualStore
 */
package singine.auth;
