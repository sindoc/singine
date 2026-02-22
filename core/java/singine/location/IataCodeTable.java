package singine.location;

import java.util.HashMap;
import java.util.List;
import java.util.ArrayList;
import java.util.Map;

/**
 * IataCodeTable — IATA airport code + ISO 3166 country code lookup table.
 *
 * Phase 1: hardcoded seed data for the Belgium CDN context (BRU, LGG, ANR, CRL)
 * plus full ISO 3166 country codes for common European contexts.
 *
 * Phase 2: full IATA DB load from SQLite (CodeTable.java pattern).
 * Topic: singine.ref.iata  Output port: urn:singine:ref:iata:v1
 *
 * URN pattern:
 *   IATA 3-char  → urn:singine:location:<cc>:<iata>   (e.g. urn:singine:location:BE:BRU)
 *   ISO  2-char  → urn:singine:location:<cc>           (e.g. urn:singine:location:BE)
 *   Postal code  → urn:singine:location:<cc>:<zip>     (e.g. urn:singine:location:BE:1000)
 *
 * Level hierarchy (from singine identity URN levels):
 *   l1  1-char ASCII → urn:singine:id:l1:<char>
 *   l2  2-char cc    → urn:singine:id:l2:<cc>   (ISO 3166)
 *   l3  3-char iata  → urn:singine:id:l3:<iata>
 */
public class IataCodeTable {

    private static final Map<String, String> IATA_TO_COUNTRY = new HashMap<>();
    private static final Map<String, String> IATA_TO_NAME    = new HashMap<>();
    private static final Map<String, String> ISO_TO_NAME     = new HashMap<>();

    static {
        // Belgium (primary CDN context per CLAUDE.md + Logseq)
        put("BRU", "BE", "Brussels Airport");
        put("LGG", "BE", "Liège Airport");
        put("ANR", "BE", "Antwerp International Airport");
        put("CRL", "BE", "Brussels South Charleroi Airport");
        put("OST", "BE", "Ostend-Bruges International Airport");

        // Netherlands
        put("AMS", "NL", "Amsterdam Airport Schiphol");
        put("RTM", "NL", "Rotterdam The Hague Airport");
        put("EIN", "NL", "Eindhoven Airport");

        // France
        put("CDG", "FR", "Charles de Gaulle Airport");
        put("ORY", "FR", "Paris Orly Airport");
        put("LYS", "FR", "Lyon–Saint-Exupéry Airport");

        // Germany
        put("FRA", "DE", "Frankfurt Airport");
        put("MUC", "DE", "Munich Airport");
        put("BER", "DE", "Berlin Brandenburg Airport");

        // United Kingdom
        put("LHR", "GB", "London Heathrow Airport");
        put("LGW", "GB", "London Gatwick Airport");
        put("MAN", "GB", "Manchester Airport");

        // Luxembourg
        put("LUX", "LU", "Luxembourg Airport");

        // Iran (Sina / SinDoc context)
        put("IKA", "IR", "Tehran Imam Khomeini International Airport");
        put("THR", "IR", "Mehrabad International Airport");
        put("MHD", "IR", "Mashhad International Airport");
        put("SYZ", "IR", "Shiraz International Airport");
        put("TBZ", "IR", "Tabriz International Airport");
        put("IFN", "IR", "Isfahan International Airport");

        // ISO 3166 country names
        ISO_TO_NAME.put("BE", "Belgium");
        ISO_TO_NAME.put("NL", "Netherlands");
        ISO_TO_NAME.put("FR", "France");
        ISO_TO_NAME.put("DE", "Germany");
        ISO_TO_NAME.put("GB", "United Kingdom");
        ISO_TO_NAME.put("LU", "Luxembourg");
        ISO_TO_NAME.put("IR", "Iran (Islamic Republic of)");
        ISO_TO_NAME.put("US", "United States");
        ISO_TO_NAME.put("CA", "Canada");
        ISO_TO_NAME.put("AU", "Australia");
        ISO_TO_NAME.put("JP", "Japan");
        ISO_TO_NAME.put("CN", "China");
        ISO_TO_NAME.put("IN", "India");
        ISO_TO_NAME.put("BR", "Brazil");
        ISO_TO_NAME.put("ZA", "South Africa");
    }

    private static void put(String iata, String cc, String name) {
        IATA_TO_COUNTRY.put(iata, cc);
        IATA_TO_NAME.put(iata, name);
    }

    /**
     * Resolves an IATA 3-char or ISO 3166 2-char code to a Singine location URN.
     *
     * @param code IATA airport code (3 uppercase chars) or ISO 3166 country code (2 uppercase chars)
     * @return URN string in the form urn:singine:location:<cc>[:<code>]
     */
    public static String resolveUrn(String code) {
        if (code == null || code.isEmpty()) {
            return "urn:singine:location:unknown";
        }
        String upper = code.toUpperCase();
        if (upper.length() == 3 && IATA_TO_COUNTRY.containsKey(upper)) {
            String cc = IATA_TO_COUNTRY.get(upper);
            return "urn:singine:location:" + cc + ":" + upper;
        }
        if (upper.length() == 2) {
            return "urn:singine:location:" + upper;
        }
        // Fallback: treat as postal code with unknown country
        return "urn:singine:location:XX:" + upper;
    }

    /**
     * Returns the ISO 3166 country code for a given IATA code.
     *
     * @param iata 3-char IATA airport code
     * @return 2-char ISO 3166 country code, or "XX" if unknown
     */
    public static String countryFor(String iata) {
        return IATA_TO_COUNTRY.getOrDefault(
            iata == null ? "" : iata.toUpperCase(), "XX");
    }

    /**
     * Returns all known IATA codes as a list of maps.
     * Each map has: code, country, name, urn.
     */
    public static List<Map<String, String>> allCodes() {
        List<Map<String, String>> result = new ArrayList<>();
        for (Map.Entry<String, String> e : IATA_TO_COUNTRY.entrySet()) {
            Map<String, String> entry = new HashMap<>();
            entry.put("code",    e.getKey());
            entry.put("country", e.getValue());
            entry.put("name",    IATA_TO_NAME.getOrDefault(e.getKey(), ""));
            entry.put("urn",     resolveUrn(e.getKey()));
            result.add(entry);
        }
        return result;
    }

    /**
     * Returns the human-readable name for an ISO 3166 country code.
     *
     * @param cc 2-char ISO 3166 country code
     * @return country name, or "Unknown" if not in the seed table
     */
    public static String countryName(String cc) {
        return ISO_TO_NAME.getOrDefault(
            cc == null ? "" : cc.toUpperCase(), "Unknown");
    }

    /**
     * Zip code (postal code) → URN using explicit country code.
     *
     * @param cc  ISO 3166 country code (2 chars)
     * @param zip postal code string
     * @return urn:singine:location:<cc>:<zip>
     */
    public static String zip2urn(String cc, String zip) {
        if (cc == null || zip == null) return "urn:singine:location:unknown";
        return "urn:singine:location:" + cc.toUpperCase() + ":" + zip;
    }

    /**
     * Level-based URN lookup (1-char, 2-char, 3-char).
     *
     * l1: 1-char ASCII → urn:singine:id:l1:<char>
     * l2: 2-char code  → urn:singine:id:l2:<cc>  (ISO 3166)
     * l3: 3-char code  → urn:singine:id:l3:<iata>
     */
    public static String levelUrn(String code) {
        if (code == null) return "urn:singine:id:l0:null";
        switch (code.length()) {
            case 1: return "urn:singine:id:l1:" + code.toUpperCase();
            case 2: return "urn:singine:id:l2:" + code.toUpperCase();
            case 3: return "urn:singine:id:l3:" + code.toUpperCase();
            default:
                // Unicode / long code: use codepoint of first char
                int cp = code.codePointAt(0);
                return "urn:singine:id:u:" + cp;
        }
    }
}
