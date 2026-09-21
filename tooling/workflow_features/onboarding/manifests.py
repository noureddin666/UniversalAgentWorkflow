from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tooling.workflow_features.onboarding.detection import read_json, read_text, relative


REQUIREMENT_PATTERN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)", re.MULTILINE)
QUOTED_PATTERN = re.compile(r"[\"']([A-Za-z0-9][A-Za-z0-9_.\-]*)")
TOML_ARRAY_PATTERN = re.compile(r"^\s*dependencies\s*=\s*\[(.*?)\]", re.MULTILINE | re.DOTALL)
TOML_STRING_PATTERN = re.compile(r"^\s*{key}\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)
TOML_TABLE_PATTERN = re.compile(r"^\[{table}\]\s*$(.*?)(?=^\[|\Z)", re.MULTILINE | re.DOTALL)
TOML_KEY_PATTERN = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*=", re.MULTILINE)
PACKAGE_REFERENCE_PATTERN = re.compile(r"<PackageReference\s+Include=\"([^\"]+)\"")
TARGET_FRAMEWORK_PATTERN = re.compile(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>")
PROJECT_SDK_PATTERN = re.compile(r"<Project\s+Sdk=\"([^\"/]+)")
GO_REQUIRE_PATTERN = re.compile(r"^\s*(?:require\s+)?([a-z0-9.\-]+\.[a-z]+/\S+)\s+v", re.MULTILINE)
GO_VERSION_PATTERN = re.compile(r"^go\s+(\S+)", re.MULTILINE)
GEM_PATTERN = re.compile(r"^\s*gem\s+[\"']([^\"']+)[\"']", re.MULTILINE)
YAML_KEY_PATTERN = re.compile(r"^\s{2}([A-Za-z0-9_]+):", re.MULTILINE)
YAML_DESCRIPTION_PATTERN = re.compile(r"^description:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)
DART_SDK_PATTERN = re.compile(r"^\s*sdk:\s*[\"']?([^\"'\n]+)", re.MULTILINE)
MAVEN_ARTIFACT_PATTERN = re.compile(r"<artifactId>([^<]+)</artifactId>")
GRADLE_DEPENDENCY_PATTERN = re.compile(r"[\"']([a-zA-Z0-9_.\-]+):([a-zA-Z0-9_.\-]+)")


@dataclass
class Manifest:
    location: str
    name: str = ""
    description: str = ""
    dependencies: set[str] = field(default_factory=set)
    versions: dict[str, str] = field(default_factory=dict)
    runtimes: list[str] = field(default_factory=list)


def _node(path: Path) -> Manifest:
    value = read_json(path)
    manifest = Manifest(location=path.name, name=str(value.get("name") or ""))
    manifest.description = str(value.get("description") or "")
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        section = value.get(key)
        if isinstance(section, dict):
            manifest.dependencies.update(section)
            manifest.versions.update({name: str(version) for name, version in section.items()})
    engines = value.get("engines")
    if isinstance(engines, dict) and engines.get("node"):
        manifest.runtimes.append(f"Node.js {engines['node']}")
    return manifest


def _toml_string(text: str, key: str) -> str:
    match = re.compile(TOML_STRING_PATTERN.pattern.format(key=re.escape(key)), re.MULTILINE).search(text)
    return match.group(1) if match else ""


def _pyproject(path: Path) -> Manifest:
    text = read_text(path)
    manifest = Manifest(location=path.name, name=_toml_string(text, "name"))
    manifest.description = _toml_string(text, "description")
    array = TOML_ARRAY_PATTERN.search(text)
    if array:
        manifest.dependencies.update(QUOTED_PATTERN.findall(array.group(1)))
    for table in ("tool.poetry.dependencies", "tool.poetry.group.dev.dependencies"):
        pattern = re.compile(TOML_TABLE_PATTERN.pattern.format(table=re.escape(table)), re.MULTILINE | re.DOTALL)
        section = pattern.search(text)
        if section:
            manifest.dependencies.update(
                key for key in TOML_KEY_PATTERN.findall(section.group(1)) if key != "python"
            )
    requires = _toml_string(text, "requires-python")
    if requires:
        manifest.runtimes.append(f"Python {requires}")
    return manifest


def _requirements(path: Path) -> Manifest:
    manifest = Manifest(location=path.name)
    manifest.dependencies.update(REQUIREMENT_PATTERN.findall(read_text(path)))
    return manifest


def _project_file(path: Path) -> Manifest:
    text = read_text(path)
    manifest = Manifest(location=path.name, name=path.stem)
    manifest.dependencies.update(PACKAGE_REFERENCE_PATTERN.findall(text))
    sdk = PROJECT_SDK_PATTERN.search(text)
    if sdk and sdk.group(1) in PROJECT_SDK_PACKAGES:
        manifest.dependencies.add(PROJECT_SDK_PACKAGES[sdk.group(1)])
    target = TARGET_FRAMEWORK_PATTERN.search(text)
    if target:
        manifest.runtimes.extend(target.group(1).split(";"))
    return manifest


def _global_json(path: Path) -> Manifest:
    manifest = Manifest(location=path.name)
    sdk = read_json(path).get("sdk")
    if isinstance(sdk, dict) and sdk.get("version"):
        manifest.runtimes.append(f".NET SDK {sdk['version']}")
    return manifest


def _go(path: Path) -> Manifest:
    text = read_text(path)
    manifest = Manifest(location=path.name)
    manifest.dependencies.update(GO_REQUIRE_PATTERN.findall(text))
    version = GO_VERSION_PATTERN.search(text)
    if version:
        manifest.runtimes.append(f"Go {version.group(1)}")
    return manifest


def _pubspec(path: Path) -> Manifest:
    text = read_text(path)
    manifest = Manifest(location=path.name)
    manifest.dependencies.update(YAML_KEY_PATTERN.findall(text))
    description = YAML_DESCRIPTION_PATTERN.search(text)
    if description:
        manifest.description = description.group(1)
    sdk = DART_SDK_PATTERN.search(text)
    if sdk and sdk.group(1).strip() != "flutter":
        manifest.runtimes.append(f"Dart {sdk.group(1).strip()}")
    return manifest


def _composer(path: Path) -> Manifest:
    value = read_json(path)
    manifest = Manifest(location=path.name, name=str(value.get("name") or ""))
    manifest.description = str(value.get("description") or "")
    for key in ("require", "require-dev"):
        section = value.get(key)
        if isinstance(section, dict):
            manifest.dependencies.update(section)
    return manifest


def _gemfile(path: Path) -> Manifest:
    manifest = Manifest(location=path.name)
    manifest.dependencies.update(GEM_PATTERN.findall(read_text(path)))
    return manifest


def _maven(path: Path) -> Manifest:
    manifest = Manifest(location=path.name)
    manifest.dependencies.update(MAVEN_ARTIFACT_PATTERN.findall(read_text(path)))
    return manifest


def _gradle(path: Path) -> Manifest:
    manifest = Manifest(location=path.name)
    manifest.dependencies.update(artifact for _, artifact in GRADLE_DEPENDENCY_PATTERN.findall(read_text(path)))
    return manifest


READERS = (
    ("package.json", _node),
    ("pyproject.toml", _pyproject),
    ("requirements.txt", _requirements),
    ("*.csproj", _project_file),
    ("*.fsproj", _project_file),
    ("Directory.Build.props", _project_file),
    ("global.json", _global_json),
    ("go.mod", _go),
    ("pubspec.yaml", _pubspec),
    ("composer.json", _composer),
    ("Gemfile", _gemfile),
    ("pom.xml", _maven),
    ("build.gradle", _gradle),
    ("build.gradle.kts", _gradle),
)

PROJECT_SDK_PACKAGES = {
    "Microsoft.NET.Sdk.Web": "Microsoft.AspNetCore",
    "Microsoft.NET.Sdk.Razor": "Microsoft.AspNetCore",
    "Microsoft.NET.Sdk.BlazorWebAssembly": "Microsoft.AspNetCore.Components.WebAssembly",
    "Microsoft.NET.Sdk.Worker": "Microsoft.Extensions.Hosting",
    "Aspire.AppHost.Sdk": "Aspire.Hosting",
}

RUNTIME_PIN_FILES = (
    (".nvmrc", "Node.js"),
    (".node-version", "Node.js"),
    (".python-version", "Python"),
    (".ruby-version", "Ruby"),
)


def read_manifests(project_root: Path, directories: list[Path]) -> list[Manifest]:
    manifests: list[Manifest] = []
    for directory in directories:
        for pattern, reader in READERS:
            for path in sorted(directory.glob(pattern)):
                if path.is_file():
                    manifest = reader(path)
                    manifest.location = relative(project_root, path)
                    manifests.append(manifest)
        for filename, runtime in RUNTIME_PIN_FILES:
            pinned = read_text(directory / filename).strip()
            if pinned:
                manifests.append(
                    Manifest(location=relative(project_root, directory / filename), runtimes=[f"{runtime} {pinned}"])
                )
    return manifests


def matches(dependency: str, package: str) -> bool:
    if package.endswith(("/", ".", "-")):
        return dependency.startswith(package)
    return dependency == package or dependency.lower() == package.lower()
