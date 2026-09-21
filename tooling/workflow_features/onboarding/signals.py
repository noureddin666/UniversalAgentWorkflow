from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ecosystem:
    name: str
    profile: str
    markers: tuple[str, ...]
    manifest: str
    package_managers: tuple[tuple[str, str], ...] = ()


ECOSYSTEMS = (
    Ecosystem(
        name="node",
        profile="javascript-typescript",
        markers=("package.json",),
        manifest="package.json",
        package_managers=(
            ("pnpm-lock.yaml", "pnpm"),
            ("yarn.lock", "yarn"),
            ("bun.lockb", "bun"),
            ("package-lock.json", "npm"),
        ),
    ),
    Ecosystem(
        name="python",
        profile="python",
        markers=("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "Pipfile"),
        manifest="pyproject.toml",
        package_managers=(("uv.lock", "uv"), ("poetry.lock", "poetry"), ("Pipfile.lock", "pipenv")),
    ),
    Ecosystem(
        name="dotnet",
        profile="dotnet",
        markers=("*.slnx", "*.sln", "*.csproj", "*.fsproj", "*.vbproj"),
        manifest="*.csproj",
    ),
    Ecosystem(name="go", profile="", markers=("go.mod",), manifest="go.mod"),
    Ecosystem(name="rust", profile="", markers=("Cargo.toml",), manifest="Cargo.toml"),
    Ecosystem(name="dart", profile="", markers=("pubspec.yaml",), manifest="pubspec.yaml"),
    Ecosystem(name="java-maven", profile="", markers=("pom.xml",), manifest="pom.xml"),
    Ecosystem(
        name="java-gradle",
        profile="",
        markers=("build.gradle", "build.gradle.kts"),
        manifest="build.gradle",
    ),
    Ecosystem(name="ruby", profile="", markers=("Gemfile",), manifest="Gemfile"),
    Ecosystem(name="php", profile="", markers=("composer.json",), manifest="composer.json"),
    Ecosystem(name="make", profile="", markers=("Makefile", "makefile"), manifest="Makefile"),
)

MANIFEST_MARKERS = (
    "package.json",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
    "pubspec.yaml",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "*.csproj",
    "*.fsproj",
)

RESTORE = "Restore"
BUILD = "Build"
UNIT_TESTS = "Unit tests"
INTEGRATION_TESTS = "Integration tests"
LINT = "Lint"
TYPE_CHECK = "Type check"
RUN_LOCALLY = "Run locally"

OPERATION_ORDER = (
    RESTORE,
    BUILD,
    UNIT_TESTS,
    INTEGRATION_TESTS,
    LINT,
    TYPE_CHECK,
    RUN_LOCALLY,
)

SCRIPT_OPERATIONS = {
    "build": BUILD,
    "compile": BUILD,
    "bundle": BUILD,
    "test": UNIT_TESTS,
    "test:unit": UNIT_TESTS,
    "unit": UNIT_TESTS,
    "jest": UNIT_TESTS,
    "vitest": UNIT_TESTS,
    "test:e2e": INTEGRATION_TESTS,
    "e2e": INTEGRATION_TESTS,
    "integration": INTEGRATION_TESTS,
    "test:integration": INTEGRATION_TESTS,
    "lint": LINT,
    "eslint": LINT,
    "format:check": LINT,
    "typecheck": TYPE_CHECK,
    "type-check": TYPE_CHECK,
    "tsc": TYPE_CHECK,
    "check-types": TYPE_CHECK,
    "dev": RUN_LOCALLY,
    "start": RUN_LOCALLY,
    "serve": RUN_LOCALLY,
}

MAKE_TARGET_OPERATIONS = {
    "install": RESTORE,
    "restore": RESTORE,
    "deps": RESTORE,
    "build": BUILD,
    "test": UNIT_TESTS,
    "unit": UNIT_TESTS,
    "integration": INTEGRATION_TESTS,
    "lint": LINT,
    "typecheck": TYPE_CHECK,
    "run": RUN_LOCALLY,
    "dev": RUN_LOCALLY,
    "serve": RUN_LOCALLY,
}

CI_FILES = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".gitlab-ci.yml",
    "azure-pipelines.yml",
    "Jenkinsfile",
)

COMMAND_TOOLS = (
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "bun",
    "deno",
    "node",
    "python",
    "python3",
    "pytest",
    "poetry",
    "uv",
    "pip",
    "ruff",
    "mypy",
    "tox",
    "dotnet",
    "go",
    "cargo",
    "make",
    "mvn",
    "gradle",
    "./gradlew",
    "gradlew.bat",
    "flutter",
    "dart",
    "bundle",
    "rake",
    "composer",
    "php",
    "tsc",
    "eslint",
    "vitest",
    "jest",
    "playwright",
)

CI_COMMAND_PREFIXES = (
    ("npm ci", RESTORE),
    ("go mod download", RESTORE),
    ("go mod tidy", RESTORE),
)

CI_OPERATION_KEYWORDS = (
    ("integration", INTEGRATION_TESTS),
    ("e2e", INTEGRATION_TESTS),
    ("playwright", INTEGRATION_TESTS),
    ("test", UNIT_TESTS),
    ("pytest", UNIT_TESTS),
    ("lint", LINT),
    ("eslint", LINT),
    ("ruff", LINT),
    ("clippy", LINT),
    ("typecheck", TYPE_CHECK),
    ("type-check", TYPE_CHECK),
    ("mypy", TYPE_CHECK),
    ("tsc", TYPE_CHECK),
    ("restore", RESTORE),
    ("install", RESTORE),
    ("sync", RESTORE),
    ("build", BUILD),
    ("compile", BUILD),
)

APPLICATION_DIRECTORY_NAMES = ("apps", "app", "services", "sites", "clients", "servers")
LIBRARY_DIRECTORY_NAMES = ("packages", "libs", "libraries", "modules")
FALLBACK_SOURCE_DIRECTORIES = ("src", "app", "lib", "source", "server", "client", "backend", "frontend")

NODE_INSTALL_COMMANDS = {
    "pnpm": "pnpm install --frozen-lockfile",
    "yarn": "yarn install --frozen-lockfile",
    "bun": "bun install",
    "npm": "npm ci",
}

DOTNET_COMMANDS = (
    (RESTORE, "dotnet restore {solution}"),
    (BUILD, "dotnet build {solution} --no-restore"),
)
DOTNET_TEST_COMMAND = "dotnet test {solution} --no-build"
DOTNET_RUN_COMMAND = "dotnet run --project {project}"
DOTNET_TEST_SDK = "Microsoft.NET.Test.Sdk"
DOTNET_RUNNABLE_SDKS = (
    "Microsoft.NET.Sdk.Web",
    "Microsoft.NET.Sdk.BlazorWebAssembly",
    "Microsoft.NET.Sdk.Worker",
    "Aspire.AppHost.Sdk",
)

PYTHON_RESTORE_COMMANDS = (
    ("uv.lock", "uv sync"),
    ("poetry.lock", "poetry install"),
    ("Pipfile.lock", "pipenv install --dev"),
    ("requirements.txt", "python -m pip install -r requirements.txt"),
)

PYTHON_TOOL_COMMANDS = (
    ("pytest", UNIT_TESTS, "python -m pytest"),
    ("ruff", LINT, "python -m ruff check ."),
    ("mypy", TYPE_CHECK, "python -m mypy ."),
)

CONVENTION_COMMANDS = {
    "go": ((RESTORE, "go mod download"), (BUILD, "go build ./..."), (UNIT_TESTS, "go test ./...")),
    "rust": ((BUILD, "cargo build"), (UNIT_TESTS, "cargo test"), (LINT, "cargo clippy")),
    "java-maven": ((BUILD, "mvn -B package -DskipTests"), (UNIT_TESTS, "mvn -B test")),
    "java-gradle": ((BUILD, "./gradlew build -x test"), (UNIT_TESTS, "./gradlew test")),
    "ruby": ((RESTORE, "bundle install"), (UNIT_TESTS, "bundle exec rspec")),
    "php": ((RESTORE, "composer install"), (UNIT_TESTS, "composer test")),
    "flutter": (
        (RESTORE, "flutter pub get"),
        (UNIT_TESTS, "flutter test"),
        (RUN_LOCALLY, "flutter run"),
    ),
    "dart": ((RESTORE, "dart pub get"), (UNIT_TESTS, "dart test")),
}

FRAMEWORK_PACKAGES = (
    ("@angular/core", "Angular"),
    ("next", "Next.js"),
    ("nuxt", "Nuxt"),
    ("@remix-run/react", "Remix"),
    ("astro", "Astro"),
    ("@sveltejs/kit", "SvelteKit"),
    ("svelte", "Svelte"),
    ("vue", "Vue"),
    ("react-native", "React Native"),
    ("expo", "Expo"),
    ("react", "React"),
    ("@nestjs/core", "NestJS"),
    ("express", "Express"),
    ("fastify", "Fastify"),
    ("koa", "Koa"),
    ("hono", "Hono"),
    ("electron", "Electron"),
    ("django", "Django"),
    ("fastapi", "FastAPI"),
    ("flask", "Flask"),
    ("Aspire.Hosting", ".NET Aspire"),
    ("Microsoft.AspNetCore.Components.WebAssembly", "Blazor WebAssembly"),
    ("Microsoft.AspNetCore", "ASP.NET Core"),
    ("Microsoft.Extensions.Hosting", ".NET Worker Service"),
    ("Microsoft.Maui", ".NET MAUI"),
    ("flutter", "Flutter"),
    ("github.com/gin-gonic/gin", "Gin"),
    ("rails", "Ruby on Rails"),
    ("laravel/framework", "Laravel"),
    ("spring-boot", "Spring Boot"),
)

EXTERNAL_SYSTEM_PACKAGES = (
    ("pg", "PostgreSQL"),
    ("postgres", "PostgreSQL"),
    ("psycopg", "PostgreSQL"),
    ("psycopg2", "PostgreSQL"),
    ("asyncpg", "PostgreSQL"),
    ("Npgsql", "PostgreSQL"),
    ("Npgsql.", "PostgreSQL"),
    ("mysql", "MySQL"),
    ("mysql2", "MySQL"),
    ("pymysql", "MySQL"),
    ("MySqlConnector", "MySQL"),
    ("Microsoft.EntityFrameworkCore.SqlServer", "SQL Server"),
    ("Microsoft.Data.SqlClient", "SQL Server"),
    ("mssql", "SQL Server"),
    ("sqlite3", "SQLite"),
    ("better-sqlite3", "SQLite"),
    ("Microsoft.EntityFrameworkCore.Sqlite", "SQLite"),
    ("mongodb", "MongoDB"),
    ("mongoose", "MongoDB"),
    ("pymongo", "MongoDB"),
    ("MongoDB.Driver", "MongoDB"),
    ("redis", "Redis"),
    ("ioredis", "Redis"),
    ("StackExchange.Redis", "Redis"),
    ("@prisma/client", "Database via Prisma"),
    ("@supabase/supabase-js", "Supabase"),
    ("firebase", "Firebase"),
    ("firebase-admin", "Firebase"),
    ("stripe", "Stripe"),
    ("Stripe.net", "Stripe"),
    ("@aws-sdk/", "AWS"),
    ("aws-sdk", "AWS"),
    ("boto3", "AWS"),
    ("AWSSDK.", "AWS"),
    ("@azure/", "Azure"),
    ("azure-", "Azure"),
    ("Azure.", "Azure"),
    ("@google-cloud/", "Google Cloud"),
    ("google-cloud-", "Google Cloud"),
    ("openai", "OpenAI API"),
    ("@anthropic-ai/sdk", "Anthropic API"),
    ("anthropic", "Anthropic API"),
    ("nodemailer", "SMTP email"),
    ("MailKit", "SMTP email"),
    ("Microsoft.EntityFrameworkCore.Cosmos", "Azure Cosmos DB"),
    ("Oracle.", "Oracle Database"),
    ("@sendgrid/mail", "SendGrid"),
    ("twilio", "Twilio"),
    ("kafkajs", "Kafka"),
    ("confluent-kafka", "Kafka"),
    ("amqplib", "RabbitMQ"),
    ("pika", "RabbitMQ"),
    ("RabbitMQ.Client", "RabbitMQ"),
    ("@elastic/elasticsearch", "Elasticsearch"),
    ("elasticsearch", "Elasticsearch"),
    ("@sentry/", "Sentry"),
    ("sentry-sdk", "Sentry"),
)

DEPLOYMENT_MARKERS = (
    ("netlify.toml", "Netlify"),
    ("vercel.json", "Vercel"),
    ("fly.toml", "Fly.io"),
    ("render.yaml", "Render"),
    ("railway.json", "Railway"),
    ("app.yaml", "Google App Engine"),
    ("firebase.json", "Firebase Hosting"),
    ("wrangler.toml", "Cloudflare Workers"),
    ("serverless.yml", "Serverless Framework"),
    ("Procfile", "Procfile-based platform"),
    ("Dockerfile", "Docker"),
    ("docker-compose.yml", "Docker Compose"),
    ("docker-compose.yaml", "Docker Compose"),
    ("compose.yaml", "Docker Compose"),
    ("Chart.yaml", "Kubernetes (Helm)"),
    ("azure.yaml", "Azure Developer CLI"),
    ("web.config", "IIS"),
)

TEST_DIRECTORY_NAMES = ("test", "tests", "__tests__", "spec", "specs", "e2e", "cypress", "playwright")
TEST_FILE_PATTERNS = (
    "*.spec.ts",
    "*.spec.tsx",
    "*.spec.js",
    "*.test.ts",
    "*.test.tsx",
    "*.test.js",
    "*.test.jsx",
    "test_*.py",
    "*_test.py",
    "*_test.go",
    "*_test.dart",
    "*Tests.cs",
    "*Test.java",
    "*_spec.rb",
)
TEST_PROJECT_SUFFIXES = (".Tests", ".Test", ".UnitTests", ".IntegrationTests")

DOCUMENTATION_FILES = ("README.md", "README.rst", "README.txt", "README", "CONTRIBUTING.md", "CHANGELOG.md")
DOCUMENTATION_DIRECTORIES = ("docs", "doc", "documentation", "wiki")

PROTECTED_DIRECTORY_NAMES = (("migrations", "database migrations"),)

DEPLOYMENT_SCRIPT_PATTERNS = ("*deploy*", "*publish*")
DEPLOYMENT_SCRIPT_SUFFIXES = (".ps1", ".sh", ".cmd", ".bat")
DEPLOYMENT_NAME_HINTS = (
    ("iis", "IIS"),
    ("azure", "Azure"),
    ("aws", "AWS"),
    ("docker", "Docker"),
    ("k8s", "Kubernetes"),
)

PROTECTED_PATH_MARKERS = (
    (".github/workflows", "CI pipeline definitions"),
    (".gitlab-ci.yml", "CI pipeline definition"),
    ("azure-pipelines.yml", "CI pipeline definition"),
    ("migrations", "database migrations"),
    ("Migrations", "database migrations"),
    ("prisma/migrations", "database migrations"),
    ("db/migrate", "database migrations"),
    ("deploy", "deployment scripts"),
    ("deployment", "deployment scripts"),
    ("infra", "infrastructure definitions"),
    ("terraform", "infrastructure definitions"),
    ("k8s", "cluster manifests"),
    ("helm", "cluster manifests"),
)

CONTRACT_PATTERNS = (
    ("openapi.yaml", "OpenAPI"),
    ("openapi.yml", "OpenAPI"),
    ("openapi.json", "OpenAPI"),
    ("swagger.json", "OpenAPI"),
    ("swagger.yaml", "OpenAPI"),
    ("*.proto", "Protocol Buffers"),
    ("*.graphql", "GraphQL schema"),
    ("asyncapi.yaml", "AsyncAPI"),
)

FRAMEWORK_SUBSUMES = {
    "React": ("Next.js", "Remix", "React Native", "Expo"),
    "Svelte": ("SvelteKit",),
    "Vue": ("Nuxt",),
    "Express": ("NestJS",),
}

README_BOILERPLATE = (
    "this project was generated with",
    "this project was bootstrapped with",
    "bootstrapped with create",
    "this template should help",
    "this is a [next.js]",
    "this is a next.js",
    "this is a new [react native]",
    "a new flutter project",
    "getting started",
)
