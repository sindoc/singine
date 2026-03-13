package singine.loc;

import org.apache.commons.lang3.StringUtils;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.*;

/**
 * ConstraintEvaluator — evaluate time, space, and impact constraints for
 * the Location-Action Correlation (LAC) engine.
 *
 * <p>Design: static methods only, no external dependencies beyond Commons Lang3
 * and JDK. All methods return a {@code Map<String,Object>} so results flow
 * naturally through the singine java-map->clj bridge.
 *
 * <p>Time constraint: is the action deadline within an acceptable window?
 * Space constraint: is a target IATA within radius-km of a reference IATA?
 * Impact score: urgency × severity × entity-count heuristic (0.0–1.0).
 * Decision: all three constraints must pass for feasibility = true.
 *
 * <p>IATA lat/lon: a small embedded table covers the most common airports.
 * For production, replace with GeoRefTable.java (Section 15.C) SQLite lookup.
 *
 * <p>URN: urn:singine:loc:constraint
 */
public class ConstraintEvaluator {

    // ── Embedded IATA lat/lon table ────────────────────────────────────────────
    // Covers the airports mentioned across user messages + common hubs.
    // [IATA, lat, lon]
    private static final double[][] IATA_COORDS = {
        // Europe
        // BRU = Brussels Airport, BE
        // LHR = Heathrow, GB
        // CDG = Charles de Gaulle, FR
        // AMS = Amsterdam Schiphol, NL
        // FRA = Frankfurt, DE
        // ZRH = Zurich, CH
        // VIE = Vienna, AT
        // FCO = Rome Fiumicino, IT
        // MAD = Madrid Barajas, ES
        // LIS = Lisbon, PT
        // DUB = Dublin, IE
        // KBL = Kabul, AF
        // HYD = Hyderabad, IN
    };

    // Map: IATA → {lat, lon}
    private static final Map<String, double[]> IATA_MAP;
    static {
        IATA_MAP = new HashMap<>();
        IATA_MAP.put("BRU", new double[]{50.9010, 4.4844});
        IATA_MAP.put("LHR", new double[]{51.4700, -0.4543});
        IATA_MAP.put("LGW", new double[]{51.1481, -0.1903});
        IATA_MAP.put("CDG", new double[]{49.0097, 2.5479});
        IATA_MAP.put("AMS", new double[]{52.3086, 4.7639});
        IATA_MAP.put("FRA", new double[]{50.0379, 8.5622});
        IATA_MAP.put("ZRH", new double[]{47.4647, 8.5492});
        IATA_MAP.put("VIE", new double[]{48.1102, 16.5697});
        IATA_MAP.put("FCO", new double[]{41.7999, 12.2462});
        IATA_MAP.put("MAD", new double[]{40.4936, -3.5668});
        IATA_MAP.put("LIS", new double[]{38.7742, -9.1342});
        IATA_MAP.put("DUB", new double[]{53.4213, -6.2700});
        IATA_MAP.put("MAN", new double[]{53.3537, -2.2750});
        IATA_MAP.put("EDI", new double[]{55.9500, -3.3725});
        // Middle East / Asia
        IATA_MAP.put("KBL", new double[]{34.5658, 69.2123});
        IATA_MAP.put("DXB", new double[]{25.2532, 55.3657});
        IATA_MAP.put("IST", new double[]{41.2608, 28.7416});
        IATA_MAP.put("HYD", new double[]{17.2403, 78.4294});
        IATA_MAP.put("BOM", new double[]{19.0896, 72.8656});
        IATA_MAP.put("DEL", new double[]{28.5562, 77.1000});
        // Americas
        IATA_MAP.put("JFK", new double[]{40.6413, -73.7781});
        IATA_MAP.put("LAX", new double[]{33.9425, -118.4081});
        IATA_MAP.put("ORD", new double[]{41.9742, -87.9073});
        IATA_MAP.put("YYZ", new double[]{43.6777, -79.6248});
        // Oceania
        IATA_MAP.put("SYD", new double[]{-33.9399, 151.1753});
        IATA_MAP.put("MEL", new double[]{-37.6690, 144.8410});
    }

    // ── evaluateTimeWindow() ───────────────────────────────────────────────────

    /**
     * Evaluate whether an action deadline falls within an acceptable time window.
     *
     * @param fromIso   ISO-8601 instant — start of acceptable window (nullable → now)
     * @param toIso     ISO-8601 instant — end of acceptable window (nullable → now+7d)
     * @param deadlineIso ISO-8601 instant — action's own deadline (nullable → now+1d)
     * @return Map with keys: feasible, within-window, hours-remaining,
     *         deadline, window-from, window-to, note
     */
    public static Map<String, Object> evaluateTimeWindow(
            String fromIso, String toIso, String deadlineIso) {
        Map<String, Object> result = new LinkedHashMap<>();
        Instant now = Instant.now();
        Instant from     = parse(fromIso,     now);
        Instant to       = parse(toIso,       now.plus(7, ChronoUnit.DAYS));
        Instant deadline = parse(deadlineIso, now.plus(1, ChronoUnit.DAYS));

        long hoursRemaining = ChronoUnit.HOURS.between(now, deadline);
        boolean withinWindow = !deadline.isBefore(from) && !deadline.isAfter(to);
        boolean notOverdue   = !deadline.isBefore(now);

        result.put("feasible",        withinWindow && notOverdue);
        result.put("within-window",   withinWindow);
        result.put("not-overdue",     notOverdue);
        result.put("hours-remaining", hoursRemaining);
        result.put("deadline",        deadline.toString());
        result.put("window-from",     from.toString());
        result.put("window-to",       to.toString());
        result.put("note",
                withinWindow ? "deadline is within acceptable window"
                : (deadline.isBefore(from) ? "deadline already passed window start"
                : "deadline exceeds window end"));
        return result;
    }

    private static Instant parse(String iso, Instant fallback) {
        if (StringUtils.isBlank(iso)) return fallback;
        try {
            return Instant.parse(iso);
        } catch (Exception e) {
            return fallback;
        }
    }

    // ── evaluateSpaceRadius() ─────────────────────────────────────────────────

    /**
     * Evaluate whether a target IATA is within radius-km of a reference IATA.
     * Uses Haversine formula for great-circle distance.
     *
     * @param referenceIata  reference airport (e.g. "BRU")
     * @param targetIata     target airport to check (e.g. "AMS")
     * @param radiusKm       maximum acceptable distance in km
     * @return Map with keys: feasible, distance-km, radius-km,
     *         reference-iata, target-iata, note
     */
    public static Map<String, Object> evaluateSpaceRadius(
            String referenceIata, String targetIata, double radiusKm) {
        Map<String, Object> result = new LinkedHashMap<>();
        String ref = StringUtils.upperCase(StringUtils.trimToEmpty(referenceIata));
        String tgt = StringUtils.upperCase(StringUtils.trimToEmpty(targetIata));

        result.put("reference-iata", ref);
        result.put("target-iata",    tgt);
        result.put("radius-km",      radiusKm);

        double[] refCoords = IATA_MAP.get(ref);
        double[] tgtCoords = IATA_MAP.get(tgt);

        if (refCoords == null || tgtCoords == null) {
            // Unknown IATA — assume feasible (open world assumption)
            result.put("feasible",    true);
            result.put("distance-km", -1.0);
            result.put("note",        "unknown IATA code(s) — assuming within radius");
            return result;
        }

        double distKm = haversineKm(refCoords[0], refCoords[1], tgtCoords[0], tgtCoords[1]);
        boolean feasible = distKm <= radiusKm;
        result.put("feasible",    feasible);
        result.put("distance-km", Math.round(distKm * 10.0) / 10.0);
        result.put("note", feasible
                ? String.format("%.0f km from %s — within %.0f km radius", distKm, ref, radiusKm)
                : String.format("%.0f km from %s — exceeds %.0f km radius", distKm, ref, radiusKm));
        return result;
    }

    // Haversine great-circle distance formula
    private static double haversineKm(double lat1, double lon1, double lat2, double lon2) {
        double R = 6371.0; // Earth radius km
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    // ── scoreImpact() ─────────────────────────────────────────────────────────

    /**
     * Score the impact of an action (simplified heuristic, no Python dependency).
     * Formula: impact = (urgency × severity × entity_factor) clamped to [0.0, 1.0]
     *
     * @param actionType    "task", "email", "decision", "approval", "escalation"
     * @param agentType     "human", "machine", "collaborative"
     * @param entityCount   number of entities affected (1–N)
     * @param isDeadlineClose true if hours-remaining < 24
     * @return Map with keys: impact-score (0.0–1.0), urgency, severity,
     *         entity-factor, breach-probability, note
     */
    public static Map<String, Object> scoreImpact(
            String actionType, String agentType, int entityCount, boolean isDeadlineClose) {
        Map<String, Object> result = new LinkedHashMap<>();

        // Urgency: deadline proximity raises urgency
        double urgency = isDeadlineClose ? 0.9 : 0.4;

        // Severity: action type drives severity
        double severity;
        String actionLc = StringUtils.lowerCase(StringUtils.defaultIfBlank(actionType, "task"));
        switch (actionLc) {
            case "escalation": severity = 1.0; break;
            case "approval":   severity = 0.85; break;
            case "decision":   severity = 0.75; break;
            case "email":      severity = 0.45; break;
            default:           severity = 0.55; break; // task
        }

        // Agent factor: autonomous machines have lower oversight (higher risk)
        double agentFactor;
        String agentLc = StringUtils.lowerCase(StringUtils.defaultIfBlank(agentType, "human"));
        switch (agentLc) {
            case "machine":      agentFactor = 1.2; break;  // autonomous
            case "collaborative":agentFactor = 1.0; break;  // human-in-loop
            default:             agentFactor = 0.8; break;  // pure human
        }

        // Entity factor: more affected entities = higher impact
        double entityFactor = Math.min(1.0, 0.3 + (entityCount * 0.1));

        double rawScore = urgency * severity * entityFactor * agentFactor;
        double impactScore = Math.min(1.0, Math.max(0.0, rawScore));

        // Breach probability: impact score correlates roughly with breach risk
        double breachProb = Math.min(0.99, impactScore * 0.7);

        result.put("impact-score",       Math.round(impactScore * 100.0) / 100.0);
        result.put("urgency",            urgency);
        result.put("severity",           severity);
        result.put("entity-factor",      entityFactor);
        result.put("agent-factor",       agentFactor);
        result.put("breach-probability", Math.round(breachProb * 100.0) / 100.0);
        result.put("action-type",        actionType);
        result.put("agent-type",         agentType);
        result.put("entity-count",       entityCount);
        result.put("note", String.format("impact=%.2f urgency=%.1f severity=%.2f entities=%d %s",
                impactScore, urgency, severity, entityCount,
                isDeadlineClose ? "(deadline close)" : ""));
        return result;
    }

    // ── decide() ──────────────────────────────────────────────────────────────

    /**
     * Derive a LAC decision from time, space, and impact evaluations.
     *
     * @param timeResult    result of evaluateTimeWindow()
     * @param spaceResult   result of evaluateSpaceRadius()
     * @param impactResult  result of scoreImpact()
     * @param threshold     maximum acceptable impact score (e.g. 0.8)
     * @return Map with keys: feasible, reason, action-urn, impact-score,
     *         breach-probability, constraints-passed, decision-id
     */
    public static Map<String, Object> decide(
            Map<String, Object> timeResult,
            Map<String, Object> spaceResult,
            Map<String, Object> impactResult,
            double threshold) {
        Map<String, Object> result = new LinkedHashMap<>();

        boolean timeFeasible  = Boolean.TRUE.equals(timeResult.get("feasible"));
        boolean spaceFeasible = Boolean.TRUE.equals(spaceResult.get("feasible"));
        double impactScore    = toDouble(impactResult.get("impact-score"), 1.0);
        boolean impactOk      = impactScore <= threshold;

        boolean feasible = timeFeasible && spaceFeasible && impactOk;

        List<String> reasons = new ArrayList<>();
        if (!timeFeasible)  reasons.add("time constraint failed: " + timeResult.get("note"));
        if (!spaceFeasible) reasons.add("space constraint failed: " + spaceResult.get("note"));
        if (!impactOk)      reasons.add(String.format(
                "impact %.2f exceeds threshold %.2f", impactScore, threshold));

        String reason = feasible
                ? "all constraints satisfied — action is feasible"
                : String.join("; ", reasons);

        result.put("feasible",           feasible);
        result.put("reason",             reason);
        result.put("impact-score",       impactScore);
        result.put("breach-probability", impactResult.get("breach-probability"));
        result.put("impact-threshold",   threshold);
        result.put("constraints-passed", feasible ? 3 : (3 - reasons.size()));
        result.put("time-feasible",      timeFeasible);
        result.put("space-feasible",     spaceFeasible);
        result.put("impact-ok",          impactOk);
        result.put("decision-id",        java.util.UUID.randomUUID().toString());
        result.put("decided-at",         Instant.now().toString());
        return result;
    }

    private static double toDouble(Object o, double fallback) {
        if (o instanceof Number) return ((Number) o).doubleValue();
        if (o instanceof String) {
            try { return Double.parseDouble((String) o); } catch (Exception ignore) {}
        }
        return fallback;
    }
}
