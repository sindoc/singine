use clap::Parser;
use rayon::prelude::*;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{BufReader, Read, Write};
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

/// Walk a photo directory and emit a newline-delimited JSON manifest.
///
/// Each line is a PhotoRecord JSON object. Suitable as input to the
/// singine-photo MCP classification pipeline.
///
/// Example:
///   singine-photo-scan ~/Pictures/icloud --output scan-manifest.ndjson
#[derive(Parser)]
#[command(name = "singine-photo-scan", version, about)]
struct Args {
    /// Directory to scan (recursively)
    dir: PathBuf,

    /// Output file path (default: stdout)
    #[arg(short, long)]
    output: Option<PathBuf>,

    /// Only include files with these extensions (comma-separated, e.g. jpg,heic,png)
    #[arg(long, default_value = "jpg,jpeg,png,heic,webp,tiff,tif,raw,arw,cr2,nef,dng")]
    ext: String,
}

#[derive(Serialize)]
struct PhotoRecord {
    path: String,
    filename: String,
    size_bytes: u64,
    sha256: String,
    exif: ExifData,
}

#[derive(Serialize, Default)]
struct ExifData {
    taken: Option<String>,
    make: Option<String>,
    model: Option<String>,
    gps_lat: Option<f64>,
    gps_lon: Option<f64>,
    width: Option<u32>,
    height: Option<u32>,
}

fn allowed_extensions(ext_arg: &str) -> Vec<String> {
    ext_arg
        .split(',')
        .map(|s| s.trim().to_lowercase())
        .filter(|s| !s.is_empty())
        .collect()
}

fn sha256_file(path: &Path) -> String {
    let file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return "unavailable".into(),
    };
    let mut reader = BufReader::new(file);
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 65536];
    loop {
        match reader.read(&mut buf) {
            Ok(0) => break,
            Ok(n) => hasher.update(&buf[..n]),
            Err(_) => return "error".into(),
        }
    }
    format!("{:x}", hasher.finalize())
}

fn read_exif(path: &Path) -> ExifData {
    let file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return ExifData::default(),
    };
    let mut reader = BufReader::new(file);
    let exif = match exif::Reader::new().read_from_container(&mut reader) {
        Ok(e) => e,
        Err(_) => return ExifData::default(),
    };

    let mut data = ExifData::default();

    if let Some(f) = exif.get_field(exif::Tag::DateTimeOriginal, exif::In::PRIMARY) {
        data.taken = Some(f.display_value().to_string());
    }
    if let Some(f) = exif.get_field(exif::Tag::Make, exif::In::PRIMARY) {
        data.make = Some(f.display_value().to_string());
    }
    if let Some(f) = exif.get_field(exif::Tag::Model, exif::In::PRIMARY) {
        data.model = Some(f.display_value().to_string());
    }
    if let Some(f) = exif.get_field(exif::Tag::PixelXDimension, exif::In::PRIMARY) {
        if let exif::Value::Long(v) = &f.value {
            data.width = v.first().copied();
        }
    }
    if let Some(f) = exif.get_field(exif::Tag::PixelYDimension, exif::In::PRIMARY) {
        if let exif::Value::Long(v) = &f.value {
            data.height = v.first().copied();
        }
    }

    // GPS — simple extraction (decimal degrees)
    if let (Some(lat_f), Some(lon_f)) = (
        exif.get_field(exif::Tag::GPSLatitude, exif::In::PRIMARY),
        exif.get_field(exif::Tag::GPSLongitude, exif::In::PRIMARY),
    ) {
        data.gps_lat = dms_to_decimal(&lat_f.value);
        data.gps_lon = dms_to_decimal(&lon_f.value);
    }

    data
}

fn dms_to_decimal(value: &exif::Value) -> Option<f64> {
    if let exif::Value::Rational(v) = value {
        if v.len() >= 3 {
            let deg = v[0].num as f64 / v[0].denom as f64;
            let min = v[1].num as f64 / v[1].denom as f64;
            let sec = v[2].num as f64 / v[2].denom as f64;
            return Some(deg + min / 60.0 + sec / 3600.0);
        }
    }
    None
}

fn scan_dir(dir: &Path, allowed_ext: &[String]) -> Vec<PathBuf> {
    WalkDir::new(dir)
        .follow_links(false)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_type().is_file())
        .filter(|e| {
            e.path()
                .extension()
                .and_then(|s| s.to_str())
                .map(|s| allowed_ext.contains(&s.to_lowercase()))
                .unwrap_or(false)
        })
        .map(|e| e.path().to_path_buf())
        .collect()
}

fn process_file(path: &Path) -> PhotoRecord {
    let size_bytes = std::fs::metadata(path).map(|m| m.len()).unwrap_or(0);
    PhotoRecord {
        path: path.to_string_lossy().into_owned(),
        filename: path.file_name().unwrap_or_default().to_string_lossy().into_owned(),
        size_bytes,
        sha256: sha256_file(path),
        exif: read_exif(path),
    }
}

fn main() {
    let args = Args::parse();
    let allowed_ext = allowed_extensions(&args.ext);

    if !args.dir.exists() {
        eprintln!("error: directory not found: {}", args.dir.display());
        std::process::exit(1);
    }

    let paths = scan_dir(&args.dir, &allowed_ext);
    eprintln!("singine-photo-scan: found {} photos in {}", paths.len(), args.dir.display());

    let records: Vec<PhotoRecord> = paths.par_iter().map(|p| process_file(p)).collect();

    let output: Box<dyn Write> = match &args.output {
        Some(p) => {
            let f = File::create(p).unwrap_or_else(|e| {
                eprintln!("error: cannot create output file {}: {}", p.display(), e);
                std::process::exit(1);
            });
            Box::new(f)
        }
        None => Box::new(std::io::stdout()),
    };
    let mut writer = std::io::BufWriter::new(output);

    for record in &records {
        let line = serde_json::to_string(record).unwrap_or_else(|_| "{}".into());
        writeln!(writer, "{}", line).unwrap_or(());
    }

    eprintln!("singine-photo-scan: wrote {} records", records.len());
}
