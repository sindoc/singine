"""Project templates and reusable bundle archetypes for Singine."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug or "singine-project"


def _java_segment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "", value.strip())
    if not cleaned:
        return "app"
    if cleaned[0].isdigit():
        cleaned = f"app{cleaned}"
    return cleaned.lower()


def _class_name(value: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", value.strip())
    result = "".join(part[:1].upper() + part[1:] for part in parts if part)
    if not result:
        return "App"
    if result[0].isdigit():
        result = f"App{result}"
    return result


def _npm_package_name(name: str, scope: str = "") -> str:
    pkg = _slugify(name)
    if scope:
        safe_scope = _slugify(scope)
        return f"@{safe_scope}/{pkg}"
    return pkg


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write(path: Path, content: str, created: List[str], force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file without --force: {path}")
    _mkdir(path.parent)
    path.write_text(content, encoding="utf-8")
    created.append(str(path))


def _default_java_package(group_id: str, artifact_id: str) -> str:
    segments = [_java_segment(part) for part in group_id.split(".") if part.strip()]
    segments.extend(_java_segment(part) for part in artifact_id.split("-") if part.strip())
    return ".".join(part for part in segments if part)


@dataclass
class TemplateResult:
    kind: str
    name: str
    target_dir: Path
    files: List[str]
    package_name: str
    metadata: Dict[str, str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "ok": True,
            "kind": self.kind,
            "name": self.name,
            "target_dir": str(self.target_dir),
            "files": self.files,
            "package_name": self.package_name,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class LibraryEntry:
    name: str
    family: str
    description: str
    reference_command: str
    default_output_dir: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "family": self.family,
            "description": self.description,
            "reference_command": self.reference_command,
            "default_output_dir": self.default_output_dir,
        }


def builtin_template_library() -> List[LibraryEntry]:
    return [
        LibraryEntry(
            name="personal-os-essay",
            family="archetype",
            description="Reflective bundle spanning Markdown, HTML, SVG, LaTeX, XML, SinLisp, Ballerina, C, Rust, Pico, and ixml.",
            reference_command="singine essay personal-os --output-dir <dir> --json",
            default_output_dir="/tmp/singine-personal-os",
        ),
        LibraryEntry(
            name="platform-blueprint",
            family="archetype",
            description="Platform contract for OpenShift, Docker, Flowable, Node.js, Python, Spring Boot, and Collibra-aligned execution.",
            reference_command="singine platform blueprint --output-dir <dir> --json",
            default_output_dir="/tmp/singine-platform-blueprint",
        ),
        LibraryEntry(
            name="zip-neighborhood-demo",
            family="template",
            description="Notebook-friendly messaging demo across RabbitMQ, Kafka, publication artefacts, zip codes, and multilingual mappings.",
            reference_command="singine demo zip-neighborhood --output-dir <dir> --json",
            default_output_dir="/tmp/singine-zip-neighborhood-demo",
        ),
    ]


def list_template_library(*, family: Optional[str] = None) -> List[Dict[str, str]]:
    items = [entry for entry in builtin_template_library() if family in (None, "", entry.family)]
    return [entry.to_dict() for entry in items]


def materialize_library_entry(
    *,
    name: str,
    output_dir: Path,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    target = name.strip().lower()
    if target == "personal-os-essay":
        from .personal_os import write_personal_os_bundle

        return write_personal_os_bundle(
            output_dir=output_dir,
            title=title or "Singine Personal Operating System",
        )
    if target == "platform-blueprint":
        from .platform_blueprint import write_platform_blueprint_bundle

        return write_platform_blueprint_bundle(
            output_dir=output_dir,
            title=title or "Singine Multi-Model Platform Blueprint",
        )
    if target == "zip-neighborhood-demo":
        from .zip_neighborhood_demo import write_zip_neighborhood_demo_bundle

        return write_zip_neighborhood_demo_bundle(
            output_dir=output_dir,
            title=title or "Zip Neighborhood Messaging Demo",
        )
    raise KeyError(name)


def create_maven_template(
    *,
    name: str,
    target_dir: Path,
    group_id: str,
    artifact_id: str,
    version: str,
    package_name: str,
    java_version: str,
    description: str,
    force: bool = False,
) -> TemplateResult:
    created: List[str] = []
    class_name = _class_name(artifact_id)
    package_path = Path(*package_name.split("."))

    pom_xml = f"""<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>{group_id}</groupId>
  <artifactId>{artifact_id}</artifactId>
  <version>{version}</version>
  <name>{name}</name>
  <description>{description}</description>

  <properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.source>{java_version}</maven.compiler.source>
    <maven.compiler.target>{java_version}</maven.compiler.target>
    <main.class>{package_name}.{class_name}</main.class>
    <junit.version>5.11.4</junit.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>${{junit.version}}</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.5.0</version>
        <configuration>
          <mainClass>${{main.class}}</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
"""

    app_java = f"""package {package_name};

public final class {class_name} {{
    private {class_name}() {{
    }}

    public static void main(String[] args) {{
        System.out.println("{name} is ready for Maven and Singine.");
    }}
}}
"""

    test_java = f"""package {package_name};

import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

final class {class_name}Test {{
    @Test
    void projectBootstraps() {{
        assertTrue(true, "Template project compiles and tests cleanly.");
    }}
}}
"""

    readme = f"""# {name}

Generated by `singine template create maven`.

## Build

```bash
mvn test
mvn exec:java
```

## Singine

```bash
singine context --json
singine man singine-template
```
"""

    gitignore = """target/
.idea/
.classpath
.project
.settings/
"""

    _write(target_dir / "pom.xml", pom_xml, created, force)
    _write(target_dir / "README.md", readme, created, force)
    _write(target_dir / ".gitignore", gitignore, created, force)
    _write(target_dir / "src" / "main" / "java" / package_path / f"{class_name}.java", app_java, created, force)
    _write(target_dir / "src" / "test" / "java" / package_path / f"{class_name}Test.java", test_java, created, force)

    return TemplateResult(
        kind="maven",
        name=name,
        target_dir=target_dir,
        files=created,
        package_name=package_name,
        metadata={
            "group_id": group_id,
            "artifact_id": artifact_id,
            "version": version,
            "java_version": java_version,
            "main_class": f"{package_name}.{class_name}",
        },
    )


def create_npm_template(
    *,
    name: str,
    target_dir: Path,
    package_name: str,
    version: str,
    description: str,
    module_type: str,
    force: bool = False,
) -> TemplateResult:
    created: List[str] = []
    entry_ext = "js"

    package_json = {
        "name": package_name,
        "version": version,
        "description": description,
        "type": module_type,
        "private": True,
        "scripts": {
            "start": f"node src/index.{entry_ext}",
            "test": "node --test",
            "singine:context": "singine context --json",
        },
        "engines": {"node": ">=20"},
    }

    if module_type == "commonjs":
        index_js = f"""function main() {{
  console.log("{name} is ready for npm and Singine.");
}}

if (require.main === module) {{
  main();
}}

module.exports = {{ main }};
"""
        test_js = """const test = require('node:test');
const assert = require('node:assert/strict');

test('template boots', () => {
  assert.equal(1, 1);
});
"""
    else:
        index_js = f"""export function main() {{
  console.log("{name} is ready for npm and Singine.");
}}

if (import.meta.url === `file://${{process.argv[1]}}`) {{
  main();
}}
"""
        test_js = """import test from 'node:test';
import assert from 'node:assert/strict';

test('template boots', () => {
  assert.equal(1, 1);
});
"""

    readme = f"""# {name}

Generated by `singine template create npm`.

## Run

```bash
npm install
npm start
npm test
```

## Singine

```bash
npm run singine:context
singine man singine-template
```
"""

    gitignore = """node_modules/
dist/
.DS_Store
"""

    _write(target_dir / "package.json", json.dumps(package_json, indent=2) + "\n", created, force)
    _write(target_dir / "README.md", readme, created, force)
    _write(target_dir / ".gitignore", gitignore, created, force)
    _write(target_dir / "src" / f"index.{entry_ext}", index_js, created, force)
    _write(target_dir / "test" / f"index.test.{entry_ext}", test_js, created, force)

    return TemplateResult(
        kind="npm",
        name=name,
        target_dir=target_dir,
        files=created,
        package_name=package_name,
        metadata={
            "package_name": package_name,
            "version": version,
            "module_type": module_type,
        },
    )


def default_maven_args(name: str) -> Dict[str, str]:
    artifact_id = _slugify(name)
    group_id = "com.example"
    return {
        "artifact_id": artifact_id,
        "group_id": group_id,
        "package_name": _default_java_package(group_id, artifact_id),
    }


def default_java_package(group_id: str, artifact_id: str) -> str:
    return _default_java_package(group_id, artifact_id)


def default_npm_args(name: str, scope: str = "") -> Dict[str, str]:
    return {"package_name": _npm_package_name(name, scope=scope)}
