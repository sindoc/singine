package singine.db;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

/**
 * CodeTable — minimal SQLite key/value code table for singine.
 *
 * Schema (single table, two columns):
 *   CREATE TABLE IF NOT EXISTS code (key TEXT PRIMARY KEY, val TEXT);
 *
 * This is the master data layer described in proto/PLAN.md §4.
 * Every singine execution stores its state here.
 *
 * Bootstrap rows (pre-seeded):
 *   c=code, n=number, i=input, o=output, s=state, a=action,
 *   t=time, k=key, v=value, TZ=Europe/London, ROOT=singine execution root
 *
 * Style: follows IcebergDescriptor.java — no external deps, try-with-resources,
 * hand-rolled SQL. The JDBC URL is "jdbc:sqlite:<path>".
 */
public class CodeTable {

    private static final String DDL =
        "CREATE TABLE IF NOT EXISTS code (key TEXT NOT NULL PRIMARY KEY, val TEXT NOT NULL)";

    private static final String[][] BOOTSTRAP = {
        {"c", "code"}, {"n", "number"}, {"i", "input"}, {"o", "output"},
        {"s", "state"}, {"a", "action"}, {"t", "time"}, {"k", "key"},
        {"v", "value"}, {"ACTN", "Action"}, {"HLED", "Human-led activity"},
        {"MLED", "Machine-led activity"}, {"ACTR", "Actor"},
        {"CNSQ", "Consequence"}, {"CNTX", "Context"}, {"EVAL", "Evaluation"},
        {"TICK", "86400"}, {"TZ", "Europe/London"},
        {"ROOT", "singine execution root"}
    };

    private final String url;

    /**
     * Create a CodeTable bound to the given SQLite file path.
     * Call {@link #init()} before any other operation.
     *
     * @param dbPath absolute or relative path to the .db file
     */
    public CodeTable(String dbPath) {
        this.url = "jdbc:sqlite:" + dbPath;
    }

    /** Open a JDBC connection. Caller must close it (use try-with-resources). */
    public Connection connect() throws SQLException {
        return DriverManager.getConnection(url);
    }

    /**
     * Create the code table if it does not exist and insert bootstrap rows.
     * Idempotent — safe to call multiple times.
     */
    public void init() throws SQLException {
        try (Connection conn = connect();
             Statement  stmt = conn.createStatement()) {
            stmt.execute(DDL);
            for (String[] row : BOOTSTRAP) {
                stmt.execute(
                    "INSERT OR IGNORE INTO code (key, val) VALUES ('" +
                    escape(row[0]) + "', '" + escape(row[1]) + "')");
            }
        }
    }

    /**
     * Insert or replace a key/value pair in the code table.
     *
     * @param key the lookup key (max 255 chars recommended)
     * @param val the value to store
     */
    public void set(String key, String val) throws SQLException {
        try (Connection conn  = connect();
             PreparedStatement ps = conn.prepareStatement(
                 "INSERT OR REPLACE INTO code (key, val) VALUES (?, ?)")) {
            ps.setString(1, key);
            ps.setString(2, val);
            ps.executeUpdate();
        }
    }

    /**
     * Query a value by key.
     *
     * @param key the lookup key
     * @return the value, or {@code null} if not found
     */
    public String query(String key) throws SQLException {
        try (Connection conn = connect();
             PreparedStatement ps = conn.prepareStatement(
                 "SELECT val FROM code WHERE key = ?")) {
            ps.setString(1, key);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getString("val") : null;
            }
        }
    }

    /**
     * Return all key/value pairs as a list of two-element String arrays.
     * Order is undefined (SQLite rowid order in practice).
     */
    public List<String[]> listAll() throws SQLException {
        List<String[]> rows = new ArrayList<>();
        try (Connection conn = connect();
             Statement  stmt = conn.createStatement();
             ResultSet  rs   = stmt.executeQuery("SELECT key, val FROM code ORDER BY key")) {
            while (rs.next()) {
                rows.add(new String[]{rs.getString("key"), rs.getString("val")});
            }
        }
        return rows;
    }

    /** Delete a key (no-op if not present). */
    public void delete(String key) throws SQLException {
        try (Connection conn = connect();
             PreparedStatement ps = conn.prepareStatement(
                 "DELETE FROM code WHERE key = ?")) {
            ps.setString(1, key);
            ps.executeUpdate();
        }
    }

    /** Minimal SQL string escape — replaces single quotes with two single quotes. */
    private static String escape(String s) {
        return s == null ? "" : s.replace("'", "''");
    }
}
