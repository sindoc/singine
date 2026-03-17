/**
 * Photo review activity bindings for Singine.
 *
 * <p>This nested package is part of the recursively published activity surface
 * exposed by {@code singine server inspect --json}. The generated xmldoclet
 * output and the SilkPage-backed publication manifest include these classes so
 * photo review workflows remain visible in server snapshots, Javadoc, and XML
 * publication output.</p>
 *
 * <p>Operationally, the Python CLI surface remains the primary entry point:</p>
 * <pre>
 * singine photo export-review --help
 * singine photo test-case --help
 * singine server inspect --json
 * singine snapshot save --json
 * </pre>
 */
package singine.activity.photo;
