/**
 * Javadoc surface for repository-backed Wikipedia contribution workflows.
 *
 * <h2>Purpose</h2>
 * <p>This package documents the stable command contract exposed through
 * {@code singine wikipedia contrib}. The implementation currently lives on the
 * Python CLI side, but the command set is treated as a first-class integration
 * surface so it can be published through Javadoc XML, man pages, Markdown, OpenAPI,
 * Ballerina bindings, and SinLisp rule bundles.</p>
 *
 * <h2>Current topic</h2>
 * <ul>
 *   <li>{@code collibra}</li>
 * </ul>
 *
 * <h2>Supported actions</h2>
 * <table border="1">
 *   <tr><th>Action</th><th>Role</th><th>Underlying repository command</th></tr>
 *   <tr><td>{@code status}</td><td>Read workflow metadata</td><td>none</td></tr>
 *   <tr><td>{@code refresh}</td><td>Rebuild derived artifacts</td><td>{@code python3 scripts/refresh_repo.py}</td></tr>
 *   <tr><td>{@code kernel-sync}</td><td>Project into Logseq kernel pages</td><td>{@code python3 scripts/sync_kernel_views.py}</td></tr>
 *   <tr><td>{@code visualize}</td><td>Render Mermaid from XML process payload</td><td>{@code python3 scripts/render_process_visual.py}</td></tr>
 *   <tr><td>{@code test-case}</td><td>Run end-to-end verification</td><td>{@code python3 scripts/test_case.py}</td></tr>
 *   <tr><td>{@code install-hooks}</td><td>Install repo-local hooks</td><td>{@code python3 scripts/install_hooks.py}</td></tr>
 *   <tr><td>{@code preview-mail}</td><td>Render opt-in updates</td><td>{@code python3 scripts/send_opt_in_update.py}</td></tr>
 *   <tr><td>{@code send-mail}</td><td>Send opt-in updates</td><td>{@code python3 scripts/send_opt_in_update.py --send}</td></tr>
 * </table>
 *
 * <h2>Companion documentation</h2>
 * <ul>
 *   <li>Man page: {@code man/singine-wikipedia.1}</li>
 *   <li>Markdown guide: {@code docs/wikipedia-contrib.md}</li>
 *   <li>OpenAPI: {@code schema/singine-wikipedia-api.json}</li>
 *   <li>SinLisp: {@code runtime/sinlisp/wikipedia_contrib.sinlisp}</li>
 *   <li>Ballerina: {@code ballerina/singine.bal}</li>
 * </ul>
 */
package singine.wikipedia;
