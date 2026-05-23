// scanner — cross-platform disk-space scanner for the singine cleanup pipeline.
//
// Produces report/latest.json (relative to the binary) and report/cleanup.xml
// (silkpage input) describing disk-space consumers ranked by reclaimable bytes.
//
// Usage:
//   scan [--home <dir>] [--out <file>] [--xml <file>] [--pretty]
//
// The binary is called by scan.sh and may also be called directly by singine:
//   singine runtime exec-external bin/scan --pretty
//
// On POSIX the bin/stat-hook binary (built from c/stat_hook.c) is used for
// single-file size queries.  Directory walks always use Go's native fs.WalkDir.

package main

import (
	"encoding/json"
	"encoding/xml"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"time"
)

// ── Schema ───────────────────────────────────────────────────────────────────

type Risk string

const (
	RiskSafe   Risk = "safe"   // delete without review
	RiskReview Risk = "review" // confirm before deleting
	RiskKeep   Risk = "keep"   // informational only
)

type Item struct {
	ID         string `json:"id"`
	Label      string `json:"label"`
	HomeRel    string `json:"path"`       // ~ relative display path
	AbsPath    string `json:"abs_path"`   // resolved at scan time
	SizeBytes  int64  `json:"size_bytes"`
	SizeHuman  string `json:"size_human"`
	Category   string `json:"category"`
	Risk       Risk   `json:"risk"`
	SingineCmd string `json:"singine_cmd"` // copy-ready singine invocation
	ShellCmd   string `json:"shell_cmd"`   // raw POSIX / bash command
	WinCmd     string `json:"win_cmd"`     // PowerShell equivalent
	Notes      string `json:"notes,omitempty"`
}

type Report struct {
	ScannedAt        string  `json:"scanned_at"`
	OS               string  `json:"os"`
	HomeDir          string  `json:"home_dir"`
	Items            []Item  `json:"items"`
	TotalReclaimable int64   `json:"total_reclaimable_bytes"`
	TotalHuman       string  `json:"total_reclaimable_human"`
}

// ── Known cleanup targets ────────────────────────────────────────────────────

type target struct {
	id       string
	label    string
	homePath string // path relative to home; use | as OS separator (posix|windows)
	category string
	risk     Risk
	notes    string
}

var knownTargets = []target{
	{
		id:       "jetbrains-idea2020-tomcat",
		label:    "IntelliJ IDEA 2020.2 — Tomcat server cache",
		homePath: ".IntelliJIdea2020.2/system/tomcat|AppData/Local/JetBrains/IntelliJIdea2020.2/tomcat",
		category: "ide-cache",
		risk:     RiskSafe,
		notes:    "Tomcat runtime output from a 2020 IntelliJ install. Regenerates on next launch.",
	},
	{
		id:       "jetbrains-idea2020-chrome",
		label:    "IntelliJ IDEA 2020.2 — embedded Chrome user-data",
		homePath: ".IntelliJIdea2020.2/system|AppData/Local/JetBrains/IntelliJIdea2020.2",
		category: "ide-cache",
		risk:     RiskSafe,
		notes:    "Embedded browser caches used by the old IDE's internal browser.",
	},
	{
		id:       "jetbrains-idea2020-index",
		label:    "IntelliJ IDEA 2020.2 — all system caches",
		homePath: ".IntelliJIdea2020.2|AppData/Local/JetBrains/IntelliJIdea2020.2",
		category: "ide-cache",
		risk:     RiskReview,
		notes:    "Full 2020.2 system directory. Safe if you no longer use this IDE version.",
	},
	{
		id:       "dropbox-backup-2020-mar",
		label:    "Dropbox — full user backup 2020-03",
		homePath: "Dropbox/backup/20200315T195649_Jay_Users.tar.gz|Dropbox/backup/20200315T195649_Jay_Users.tar.gz",
		category: "backup",
		risk:     RiskReview,
		notes:    "6-year-old full user backup. Verify you have a newer backup before deleting.",
	},
	{
		id:       "dropbox-backup-2020-jan",
		label:    "Dropbox — full user backup 2020-01",
		homePath: "Dropbox/backup/20200126T184105_Jay_Users.tar.gz|Dropbox/backup/20200126T184105_Jay_Users.tar.gz",
		category: "backup",
		risk:     RiskReview,
		notes:    "6-year-old full user backup. Verify you have a newer backup before deleting.",
	},
	{
		id:       "claude-desktop-cache",
		label:    "Claude desktop app — local cache",
		homePath: ".local/share/claude-desktop|AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache",
		category: "app-cache",
		risk:     RiskReview,
		notes:    "Conversation cache for the Claude desktop app. Clears chat history.",
	},
	{
		id:       "claude-cli-old-2148",
		label:    "Claude CLI — old version 2.1.148",
		homePath: ".local/share/claude/versions/2.1.148|.local/share/claude/versions/2.1.148",
		category: "old-binary",
		risk:     RiskSafe,
		notes:    "Superseded by 2.1.150. Claude CLI manages its own version store.",
	},
	{
		id:       "claude-cli-old-2149",
		label:    "Claude CLI — old version 2.1.149",
		homePath: ".local/share/claude/versions/2.1.149|.local/share/claude/versions/2.1.149",
		category: "old-binary",
		risk:     RiskSafe,
		notes:    "Superseded by 2.1.150.",
	},
	{
		id:       "tibco-zip-library",
		label:    "TIBCO BW 6.3.1 dev zip — Library copy (Dropbox copy is canonical)",
		homePath: "Library/Articles/TIBCO/TIBCO DocAndBinaries/TIB_BW-dev_6.3.1_win_x86_64.zip|Library/Articles/TIBCO/TIBCO DocAndBinaries/TIB_BW-dev_6.3.1_win_x86_64.zip",
		category: "duplicate",
		risk:     RiskSafe,
		notes:    "Identical copy exists in Dropbox/Library. Delete local-only duplicate.",
	},
	{
		id:       "oracle-adf-zip-library",
		label:    "Oracle ADF training zip — Library copy (Dropbox copy is canonical)",
		homePath: "Library/Articles/Oracle/training/adf/oracle-adf-training.zip|Library/Articles/Oracle/training/adf/oracle-adf-training.zip",
		category: "duplicate",
		risk:     RiskSafe,
		notes:    "Identical copy exists in Dropbox/Library.",
	},
	{
		id:       "dropbox-installer-idea",
		label:    "Dropbox/Downloads — IntelliJ IDEA 2020.3.1 installer",
		homePath: "Dropbox/Downloads/ideaIU-2020.3.1.exe|Dropbox/Downloads/ideaIU-2020.3.1.exe",
		category: "installer",
		risk:     RiskSafe,
		notes:    "Already installed. Installer no longer needed.",
	},
	{
		id:       "dropbox-installer-nitro",
		label:    "Dropbox/Downloads — Nitro Pro 13 installer",
		homePath: "Dropbox/Downloads/nitro_pro13_ba_x64.msi|Dropbox/Downloads/nitro_pro13_ba_x64.msi",
		category: "installer",
		risk:     RiskSafe,
		notes:    "Already installed.",
	},
	{
		id:       "dropbox-installer-xampp",
		label:    "Dropbox/Downloads — XAMPP installer",
		homePath: "Dropbox/Downloads/xampp-windows-x64-8.0.0-3-VS16-installer.exe|Dropbox/Downloads/xampp-windows-x64-8.0.0-3-VS16-installer.exe",
		category: "installer",
		risk:     RiskSafe,
		notes:    "Already installed.",
	},
	{
		id:       "dropbox-installer-deepl",
		label:    "Dropbox/Downloads — DeepL installer",
		homePath: "Dropbox/Downloads/DeepLSetup.exe|Dropbox/Downloads/DeepLSetup.exe",
		category: "installer",
		risk:     RiskSafe,
		notes:    "Already installed.",
	},
	{
		id:       "logseq-old-version",
		label:    "Logseq — old app version 0.10.15",
		homePath: ".local/share/Logseq/app-0.10.15|AppData/Local/Logseq/app-0.10.15",
		category: "app-cache",
		risk:     RiskReview,
		notes:    "Old Logseq application version. Safe if a newer version is installed.",
	},
}

// ── Path resolution ───────────────────────────────────────────────────────────

func resolvePath(homeDir, homePath string) string {
	isWin := runtime.GOOS == "windows"
	parts := strings.SplitN(homePath, "|", 2)
	rel := parts[0]
	if isWin && len(parts) == 2 {
		rel = parts[1]
	}
	rel = filepath.FromSlash(rel)
	return filepath.Join(homeDir, rel)
}

func homeRelPath(homeDir, abs string) string {
	rel, err := filepath.Rel(homeDir, abs)
	if err != nil {
		return abs
	}
	return "~" + string(filepath.Separator) + rel
}

// ── Size calculation ──────────────────────────────────────────────────────────

func dirSize(path string) int64 {
	var total int64
	_ = filepath.WalkDir(path, func(_ string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil // skip unreadable
		}
		if !d.IsDir() {
			info, e := d.Info()
			if e == nil {
				total += info.Size()
			}
		}
		return nil
	})
	return total
}

func pathSize(path string) int64 {
	info, err := os.Stat(path)
	if err != nil {
		return -1 // not found
	}
	if info.IsDir() {
		return dirSize(path)
	}
	return info.Size()
}

func humanSize(b int64) string {
	if b < 0 {
		return "not found"
	}
	const unit = 1024
	if b < unit {
		return fmt.Sprintf("%d B", b)
	}
	div, exp := int64(unit), 0
	for n := b / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(b)/float64(div), "KMGTPE"[exp])
}

// ── singine command generation ────────────────────────────────────────────────

func singineCmd(absPath string) string {
	// Use a portable path: singine runtime exec-external delegates to the OS shell
	return fmt.Sprintf("singine runtime exec-external bin/scan delete --path %q", absPath)
}

func shellCmd(absPath string) string {
	if runtime.GOOS == "windows" {
		return fmt.Sprintf(`powershell.exe -Command "Remove-Item -Recurse -Force '%s'"`, absPath)
	}
	return fmt.Sprintf("rm -rf %q", absPath)
}

func winCmd(absPath string) string {
	return fmt.Sprintf(`Remove-Item -Recurse -Force '%s'`, absPath)
}

// ── Report generation ─────────────────────────────────────────────────────────

func buildReport(homeDir string) Report {
	r := Report{
		ScannedAt: time.Now().UTC().Format(time.RFC3339),
		OS:        runtime.GOOS,
		HomeDir:   homeDir,
	}

	for _, t := range knownTargets {
		abs := resolvePath(homeDir, t.homePath)
		size := pathSize(abs)
		item := Item{
			ID:         t.id,
			Label:      t.label,
			HomeRel:    homeRelPath(homeDir, abs),
			AbsPath:    abs,
			SizeBytes:  size,
			SizeHuman:  humanSize(size),
			Category:   t.category,
			Risk:       t.risk,
			SingineCmd: singineCmd(abs),
			ShellCmd:   shellCmd(abs),
			WinCmd:     winCmd(abs),
			Notes:      t.notes,
		}
		r.Items = append(r.Items, item)
		if size > 0 && (t.risk == RiskSafe || t.risk == RiskReview) {
			r.TotalReclaimable += size
		}
	}

	// Sort: largest first
	sort.Slice(r.Items, func(i, j int) bool {
		return r.Items[i].SizeBytes > r.Items[j].SizeBytes
	})

	r.TotalHuman = humanSize(r.TotalReclaimable)
	return r
}

// ── Delete subcommand ─────────────────────────────────────────────────────────

func deletePath(path string) error {
	info, err := os.Stat(path)
	if err != nil {
		return fmt.Errorf("stat %s: %w", path, err)
	}
	fmt.Fprintf(os.Stderr, "deleting %s (%s)\n", path, humanSize(info.Size()))
	return os.RemoveAll(path)
}

// ── XML output for silkpage ───────────────────────────────────────────────────

type xmlReport struct {
	XMLName   xml.Name  `xml:"cleanup-report"`
	ScannedAt string    `xml:"scanned-at,attr"`
	OS        string    `xml:"os,attr"`
	HomeDir   string    `xml:"home-dir,attr"`
	Total     string    `xml:"total-reclaimable,attr"`
	Items     []xmlItem `xml:"item"`
}

type xmlItem struct {
	ID         string `xml:"id,attr"`
	Label      string `xml:"label,attr"`
	Path       string `xml:"path,attr"`
	SizeHuman  string `xml:"size,attr"`
	SizeBytes  int64  `xml:"size-bytes,attr"`
	Category   string `xml:"category,attr"`
	Risk       string `xml:"risk,attr"`
	SingineCmd string `xml:"singine-cmd"`
	ShellCmd   string `xml:"shell-cmd"`
	WinCmd     string `xml:"win-cmd"`
	Notes      string `xml:"notes,omitempty"`
}

func toXML(r Report) xmlReport {
	xr := xmlReport{
		ScannedAt: r.ScannedAt,
		OS:        r.OS,
		HomeDir:   r.HomeDir,
		Total:     r.TotalHuman,
	}
	for _, it := range r.Items {
		xr.Items = append(xr.Items, xmlItem{
			ID:         it.ID,
			Label:      it.Label,
			Path:       it.HomeRel,
			SizeHuman:  it.SizeHuman,
			SizeBytes:  it.SizeBytes,
			Category:   it.Category,
			Risk:       string(it.Risk),
			SingineCmd: it.SingineCmd,
			ShellCmd:   it.ShellCmd,
			WinCmd:     it.WinCmd,
			Notes:      it.Notes,
		})
	}
	return xr
}

// ── main ──────────────────────────────────────────────────────────────────────

func main() {
	homeFlag   := flag.String("home",   "", "home directory (default: os.UserHomeDir)")
	outFlag    := flag.String("out",    "", "JSON output file (default: stdout)")
	xmlFlag    := flag.String("xml",    "", "silkpage XML output file")
	prettyFlag := flag.Bool("pretty",  true, "pretty-print JSON")
	flag.Parse()

	// Subcommand: delete
	args := flag.Args()
	if len(args) > 0 && args[0] == "delete" {
		delFlags := flag.NewFlagSet("delete", flag.ExitOnError)
		pathFlag := delFlags.String("path", "", "path to delete (required)")
		_ = delFlags.Parse(args[1:])
		if *pathFlag == "" {
			fmt.Fprintln(os.Stderr, "scan delete: --path is required")
			os.Exit(1)
		}
		if err := deletePath(*pathFlag); err != nil {
			fmt.Fprintln(os.Stderr, "scan delete:", err)
			os.Exit(1)
		}
		return
	}

	homeDir := *homeFlag
	if homeDir == "" {
		var err error
		homeDir, err = os.UserHomeDir()
		if err != nil {
			fmt.Fprintln(os.Stderr, "scan: cannot resolve home dir:", err)
			os.Exit(1)
		}
	}

	report := buildReport(homeDir)

	// JSON output
	var enc *json.Encoder
	if *outFlag != "" {
		f, err := os.Create(*outFlag)
		if err != nil {
			fmt.Fprintln(os.Stderr, "scan:", err)
			os.Exit(1)
		}
		defer f.Close()
		enc = json.NewEncoder(f)
	} else {
		enc = json.NewEncoder(os.Stdout)
	}
	if *prettyFlag {
		enc.SetIndent("", "  ")
	}
	if err := enc.Encode(report); err != nil {
		fmt.Fprintln(os.Stderr, "scan: json encode:", err)
		os.Exit(1)
	}

	// XML output for silkpage
	if *xmlFlag != "" {
		xr := toXML(report)
		data, err := xml.MarshalIndent(xr, "", "  ")
		if err != nil {
			fmt.Fprintln(os.Stderr, "scan: xml marshal:", err)
			os.Exit(1)
		}
		f, err := os.Create(*xmlFlag)
		if err != nil {
			fmt.Fprintln(os.Stderr, "scan:", err)
			os.Exit(1)
		}
		defer f.Close()
		f.Write([]byte(xml.Header))
		f.Write(data)
		f.Write([]byte("\n"))
	}
}
