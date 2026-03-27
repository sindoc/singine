// ballerina/singine.bal
// Singine integration module — Ballerina
//
// High-level abstractions that read like poetry.
// Each function maps to a singine CLI action or REST endpoint.
//
// Design principle: legibility first.
// A non-technical reader should understand what each block does.
//
// Identity:
//   All actions that change infrastructure require a presenceToken.
//   Obtain one via singine:verifyPresence() — calls 1Password / Touch ID.
//
// Usage:
//   import ballerina/http;
//   import singine;
//
//   public function main() returns error? {
//       var token = check singine:verifyPresence();
//       check singine:deployWebSite("markupware.com", token);
//       check singine:auditWebSite("markupware.com");
//   }

import ballerina/http;
import ballerina/log;
import ballerina/lang.'string as strings;
import ballerina/time;

// ── Panel client configuration ──────────────────────────────────────────────

const PANEL_BASE_URL = "http://localhost:9090";

http:Client panelClient = check new (PANEL_BASE_URL, {
    timeout: 30
});

// ── Types ────────────────────────────────────────────────────────────────────

public type PresenceToken record {|
    string jwt;
    string method;
    string agent;
    string verifiedAt;
    int expiresIn;
    boolean humanPresence = true;
|};

public type ServiceStatus record {|
    string id;
    string label;
    int port;
    string proto;
    string host;
    string kind;
    boolean? reachable;
    float? latencyMs;
    string? probedAt;
|};

public type CommandResult record {|
    boolean ok;
    int exitCode;
    string stdout;
    string stderr;
    string[] cmd;
|};

public type FeedRef record {|
    string name;
    string url;
    string contentType;
|};

// ── Human presence attestation ───────────────────────────────────────────────
// This is the first thing to call.
// singine will ask for Touch ID or 1Password biometric.

public function verifyPresence() returns PresenceToken|error {
    log:printInfo("Requesting human presence verification — Touch ID / 1Password");
    http:Response resp = check panelClient->post("/api/presence/verify", {});
    json body = check resp.getJsonPayload();
    boolean ok = check body.ok;
    if (!ok) {
        string errMsg = check body.'error;
        return error("Presence verification failed: " + errMsg);
    }
    return {
        jwt:          check body.jwt,
        method:       check body.method,
        agent:        check body.agent,
        verifiedAt:   check body.'verified_at,
        expiresIn:    check body.expires_in,
        humanPresence: true
    };
}

public function presenceStatus() returns record {|boolean present; string? method; string? lastVerified; int? remainingSeconds;|}|error {
    http:Response resp = check panelClient->get("/api/presence/status");
    json body = check resp.getJsonPayload();
    return {
        present:          check body.present,
        method:           body.method is () ? () : check body.method,
        lastVerified:     body.last_verified is () ? () : check body.last_verified,
        remainingSeconds: body.remaining_seconds is () ? () : check body.remaining_seconds
    };
}

// ── Network / service inventory ───────────────────────────────────────────────

public function listServices() returns ServiceStatus[]|error {
    http:Response resp = check panelClient->get("/api/net/services");
    json body = check resp.getJsonPayload();
    json[] services = check body.services.ensureType();
    ServiceStatus[] result = [];
    foreach json svc in services {
        result.push({
            id:         check svc.id,
            label:      check svc.label,
            port:       check svc.port,
            proto:      check svc.proto,
            host:       check svc.host,
            kind:       check svc.kind,
            reachable:  svc.reachable is () ? () : check svc.reachable,
            latencyMs:  svc.latency_ms is () ? () : check svc.latency_ms,
            probedAt:   svc.probed_at is () ? () : check svc.probed_at
        });
    }
    return result;
}

public function probeService(string serviceId) returns ServiceStatus|error {
    http:Response resp = check panelClient->post("/api/net/probe", {"service": serviceId});
    json body = check resp.getJsonPayload();
    return {
        id:         check body.id,
        label:      check body.label,
        port:       check body.port,
        proto:      check body.proto,
        host:       check body.host,
        kind:       check body.kind,
        reachable:  body.reachable is () ? () : check body.reachable,
        latencyMs:  body.latency_ms is () ? () : check body.latency_ms,
        probedAt:   body.probed_at is () ? () : check body.probed_at
    };
}

// ── singine command invocation ────────────────────────────────────────────────
// Low-level: send any singine command through the panel.
// Higher-level functions below use this.

public function invoke(string[] cmd, PresenceToken? token = ()) returns CommandResult|error {
    map<string> headers = {};
    if token != () {
        headers["Authorization"] = "Bearer " + token.jwt;
    }
    http:Request req = new;
    req.setJsonPayload({"cmd": cmd});
    foreach string k in headers.keys() {
        req.addHeader(k, headers.get(k));
    }
    http:Response resp = check panelClient->post("/api/net/invoke", req);
    json body = check resp.getJsonPayload();
    return {
        ok:       check body.ok,
        exitCode: check body.exit_code,
        stdout:   check body.stdout,
        stderr:   check body.stderr,
        cmd:      cmd
    };
}

// ── Edge stack ────────────────────────────────────────────────────────────────

public function edgeStatus() returns CommandResult|error {
    return invoke(["singine", "edge", "status", "--json"]);
}

public function edgeUp(PresenceToken token) returns CommandResult|error {
    log:printInfo("Starting edge stack — human presence required");
    return invoke(["singine", "edge", "up", "--detach"], token);
}

public function edgeDown(PresenceToken token) returns CommandResult|error {
    log:printInfo("Stopping edge stack — human presence required");
    return invoke(["singine", "edge", "down"], token);
}

public function edgeDeploy(PresenceToken token) returns CommandResult|error {
    log:printInfo("Deploying edge stack — human presence required");
    return invoke(["singine", "edge", "deploy"], token);
}

// ── Web surface ───────────────────────────────────────────────────────────────

public function deployWebSite(string site, PresenceToken token) returns CommandResult|error {
    log:printInfo("Deploying site: " + site + " — human presence required");
    return invoke(["singine", "www", "deploy", "--site", site], token);
}

public function auditWebSite(string site) returns CommandResult|error {
    return invoke(["singine", "vww", "audit", "--site", site, "--json"]);
}

public function checkTlsCert(string site) returns CommandResult|error {
    return invoke(["singine", "vww", "cert", "--site", site, "--json"]);
}

public function fixTlsCert(string site, PresenceToken token) returns CommandResult|error {
    log:printInfo("Fixing TLS cert for: " + site + " — human presence required");
    return invoke(["singine", "wsec", "cert", "--site", site, "--fix-san", "--method", "certbot"], token);
}

public function mintDeployToken(string site, PresenceToken token) returns CommandResult|error {
    log:printInfo("Minting deploy JWT for: " + site + " — human presence required");
    return invoke(["singine", "wsec", "token", "--site", site, "--json"], token);
}

// ── Bridge / semantic layer ───────────────────────────────────────────────────

public function bridgeSources(string db = "/tmp/sqlite.db") returns CommandResult|error {
    return invoke(["singine", "bridge", "sources", "--db", db]);
}

public function bridgeSearch(string query, string db = "/tmp/sqlite.db") returns CommandResult|error {
    return invoke(["singine", "bridge", "search", "--db", db, query]);
}

public function bridgeSparql(string query, string db = "/tmp/sqlite.db") returns CommandResult|error {
    return invoke(["singine", "bridge", "sparql", "--db", db, query]);
}

public function bridgeGraphql(string query, string db = "/tmp/sqlite.db") returns CommandResult|error {
    return invoke(["singine", "bridge", "graphql", "--db", db, query]);
}

// ── Governance decisions ──────────────────────────────────────────────────────

public function decide(string subject, string decision, string reason, PresenceToken token) returns CommandResult|error {
    log:printInfo("Recording governance decision: " + subject + " → " + decision);
    return invoke(["singine", "decide", subject, "--decision", decision, "--reason", reason, "--json"], token);
}

// ── Feeds ─────────────────────────────────────────────────────────────────────

public function activityFeedUrl() returns string {
    return PANEL_BASE_URL + "/feeds/activity.atom";
}

public function decisionsFeedUrl() returns string {
    return PANEL_BASE_URL + "/feeds/decisions.atom";
}

public function availableFeeds() returns FeedRef[] {
    return [
        { name: "Activity (Atom)",     url: PANEL_BASE_URL + "/feeds/activity.atom",   contentType: "application/atom+xml" },
        { name: "Activity (RSS 1.0)",  url: PANEL_BASE_URL + "/feeds/activity.rss",    contentType: "application/rss+xml"  },
        { name: "Decisions (Atom)",    url: PANEL_BASE_URL + "/feeds/decisions.atom",  contentType: "application/atom+xml" },
        { name: "Decisions (RSS 1.0)", url: PANEL_BASE_URL + "/feeds/decisions.rss",   contentType: "application/rss+xml"  }
    ];
}

// ── Vocabulary ────────────────────────────────────────────────────────────────

public function knowyouraiVocabUrl() returns string {
    return PANEL_BASE_URL + "/vocab/knowyourai.ttl";
}

// ── Demo: a complete daily workflow that reads like poetry ────────────────────

public function morningWorkflow() returns error? {
    log:printInfo("=== singine morning workflow ===");

    // Am I here? (biometric verification)
    log:printInfo("Verifying human presence…");
    var token = check verifyPresence();
    log:printInfo("Present: " + token.agent + " via " + token.method);

    // What is the state of the intranet?
    log:printInfo("Checking edge stack…");
    var edgeState = check edgeStatus();
    log:printInfo(edgeState.stdout);

    // Are all services reachable?
    log:printInfo("Probing services…");
    var services = check listServices();
    foreach ServiceStatus svc in services {
        string state = svc.reachable == true ? "✓" : "✗";
        log:printInfo(state + " " + svc.id + " :" + svc.port.toString());
    }

    // What does the semantic bridge know?
    log:printInfo("Searching bridge…");
    var bridgeResult = check bridgeSearch("elia electricity domain");
    log:printInfo(bridgeResult.stdout);

    log:printInfo("=== workflow complete ===");
}
