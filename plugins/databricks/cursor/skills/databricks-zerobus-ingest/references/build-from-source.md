# Build a Zerobus SDK from source

Read this when the user **wants to build the SDK themselves** (their own toolchain, an audited or reproducible build, a custom platform), or when the platform has **no prebuilt native binary**: Alpine or another musl Linux, an older glibc distro, an uncommon CPU architecture, FreeBSD, or a macOS release without published binaries. Every wrapper SDK (Python, TypeScript, Java, Go cgo, .NET, C++) loads a compiled **Rust core**; a source build compiles that core on the user's machine. The commands below follow each SDK README's own "build from source" section, linked per SDK.

## Build, or choose another path?
| Situation | Do this |
|-----------|---------|
| The user wants their own build (policy, audit, custom flags) | **Build from source** with the per-SDK steps below |
| The platform has a prebuilt binary (table below) and the user is fine with it | Install normally. No build needed |
| No prebuilt binary, but the user can install a Rust toolchain and build tools | **Build from source** |
| Policy forbids third-party prebuilt binaries but allows compiling | A source build satisfies it. So does a **pure SDK** |
| Toolchains can't be installed, or the build is too heavy for the environment | Use a **pure SDK**: **Rust** (it compiles with the user's own toolchain) or **pure Go** (`purego`, Go 1.25+). Pure C (`purec`) doesn't send data yet. See [choose-an-interface.md](choose-an-interface.md) |
| No compiled code at all (edge runtimes, locked-down hosts) | Use **REST** ([rest.md](rest.md)) |

On **Alpine**, check the table first: **Java, .NET, and C++ already ship musl binaries**. Only **Python, TypeScript, and Go (cgo)** need a source build there, or a switch to a pure SDK or REST.

## Do you need to build? Prebuilt platforms per SDK
| SDK | Prebuilt for | Not prebuilt (build, or choose another path) |
|-----|--------------|----------------------------------------------|
| **Python** (PyPI) | Linux x86_64 and aarch64 **with glibc 2.34 or newer** (`manylinux_2_34` wheels); macOS x86_64 and arm64; Windows x86_64. All wheels are `cp39-abi3` (CPython 3.9 to 3.14) | **Alpine and other musl Linux** (no `musllinux` wheel); **glibc older than 2.34**, for example Ubuntu 20.04 and Debian 11 (2.31), RHEL or CentOS 8 (2.28), Amazon Linux 2 (2.26); other architectures; free-threaded Python builds (`3.14t`, not supported at all) |
| **TypeScript** (npm) | `linux-x64-gnu`, `linux-arm64-gnu`, `win32-x64-msvc`, `darwin-x64`, `darwin-arm64` | **Linux musl (Alpine)**, FreeBSD, other architectures |
| **Java** (Maven Central) | Linux glibc x86_64 and aarch64 (glibc 2.26 or newer, including Amazon Linux 2); **Linux musl x86_64 and aarch64**; Windows x86_64 | macOS x86_64 and aarch64 ("source-build only"); other architectures |
| **Go, cgo** (`go/`) | Static archives committed under `go/lib/` for `linux_amd64`, `linux_arm64`, `darwin_amd64`, `darwin_arm64`, `windows_amd64`. The Linux archives are glibc builds | **musl Linux (Alpine)**; any other GOOS or GOARCH (no linker flags exist for them; use `purego`) |
| **.NET** (NuGet) | `linux-x64`, `linux-arm64` (glibc), **`linux-musl-x64`, `linux-musl-arm64`**, `win-x64` | macOS `osx-x64` and `osx-arm64` ("source build only") |
| **C++** (GitHub release bundle) | Per-platform bundles with a prebuilt FFI archive: Linux glibc x86_64 and aarch64, **Linux musl x86_64 and aarch64**, macOS x86_64 and aarch64, Windows x86_64 | Other platforms: build from a source checkout |

The monorepo README adds: "macOS binaries are built locally and may not be available for every SDK or release."

To check if a build is needed: `uname -m` (CPU), `ldd --version 2>&1 | head -1` (libc), `cat /etc/os-release` (distribution). For Python, `pip download --only-binary=:all: --no-deps databricks-zerobus-ingest-sdk -d /tmp/check` fails with "No matching distribution" if there's no wheel for the platform.

## Python
Needs **Rust 1.88 or newer** ([rustup.rs](https://rustup.rs/)) and a C toolchain; on Alpine also `patchelf`. Two ways:

- **Let pip build it:** `pip install databricks-zerobus-ingest-sdk`. With no matching wheel, pip downloads the source distribution and builds it with maturin (installed automatically).
- **Build a wheel from a checkout** (the README's [Building from Source](https://github.com/databricks/zerobus-sdk/tree/main/python#building-from-source)), then install that wheel wherever it's needed:
  ```bash
  git clone https://github.com/databricks/zerobus-sdk.git
  cd zerobus-sdk/python
  make dev     # create .venv and install in editable mode
  make build   # release wheel in dist/ (maturin build --release)
  pip install dist/*.whl
  ```

**Alpine Dockerfile (musl Linux):**
```dockerfile
FROM python:3.12-alpine
RUN apk add --no-cache build-base rust cargo patchelf
RUN pip install --no-cache-dir databricks-zerobus-ingest-sdk
```
This builds on Alpine 3.24 (Rust 1.96+, maturin 1.11+, Python 3.12) and produces a `musllinux_1_2` wheel.

## TypeScript (Node.js)
Needs Node.js 16+, **Rust 1.70+**, and C/C++ build tools (the README's [Local Development From Source](https://github.com/databricks/zerobus-sdk/tree/main/typescript#local-development-from-source)):
```bash
git clone https://github.com/databricks/zerobus-sdk.git
cd zerobus-sdk/typescript
npm install
npm run build                                   # builds the native .node module
npm install /path/to/zerobus-sdk/typescript     # from the app's directory
```

## Java
The published JAR already includes Linux (glibc and musl) and Windows natives; build only for macOS, other architectures, or a self-built native. The README's [Build from Source](https://github.com/databricks/zerobus-sdk/tree/main/java#option-2-build-from-source) needs JDK 11+ and Maven 3.6+:
```bash
git clone https://github.com/databricks/zerobus-sdk.git
cd zerobus-sdk/java
mvn clean package -Dzerobus.skipNativeLibCheck=true
```
That flag compiles the Java classes **without** native libraries; the JARs can't ingest until the JNI library is available. Build it from the same checkout with `cargo build -p zerobus-jni --release` (in `rust/`). Then either stage it under `java/src/main/resources/native/` and rerun Maven without the flag, or keep the published JAR and point the JVM at it: `java -Djava.library.path=/path/to/zerobus-sdk/rust/target/release ...`. The SDK's loader tries `java.library.path` first.

## Go (cgo)
Tagged releases and checkouts include the `go/lib/` archives, so no build is needed on the platforms above. To rebuild the Rust FFI (needs Go, a C compiler, and Rust), follow the README's [Building from Source](https://github.com/databricks/zerobus-sdk/tree/main/go#building-from-source):
```bash
git clone https://github.com/databricks/zerobus-sdk.git
cd zerobus-sdk/go
make build     # builds the Rust FFI, then the Go package (make build-rust for the FFI only)
go mod edit -replace github.com/databricks/zerobus-sdk/go=/path/to/zerobus-sdk/go   # from the app's module
```
For Alpine or other unsupported platforms, `purego` avoids the build entirely.

## .NET
NuGet already ships Linux glibc and musl, and Windows. For macOS or a self-built native, the README's [From Source](https://github.com/databricks/zerobus-sdk/tree/main/dotnet#from-source): `cd dotnet && dotnet build`. The build runs `build_native.sh` to compile the Rust FFI into `runtimes/<RID>/native/`, so `cargo` must be on `PATH`.

## C++
Two ways, per the README's [Building](https://github.com/databricks/zerobus-sdk/tree/main/cpp#building):
- **Release bundle, no Rust:** the bundle has the C++ source and a prebuilt FFI archive. `cmake -S cpp -B build -DZEROBUS_FFI_LIBRARY="$PWD/lib/libzerobus_ffi.a" -DZEROBUS_FFI_HEADER_DIR="$PWD/lib" && cmake --build build -j`.
- **Source checkout, builds the FFI with Rust:** from `cpp/`, `make build`, or `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j`.

## Rust
Rust is a pure SDK: `cargo add databricks-zerobus-ingest-sdk` always compiles it from source with the user's toolchain. To build the repo itself, see the README's [Building from Source](https://github.com/databricks/zerobus-sdk/tree/main/rust#building-from-source) (`cd zerobus-sdk/rust && cargo build --workspace`).

## Common build errors
| Symptom | Fix |
|---------|-----|
| `pip install` downloads `.tar.gz` and fails with a Rust error | Install Rust 1.88+ and a C toolchain, or use a pure SDK or REST |
| `patchelf` not found on Alpine | `apk add patchelf` (maturin needs it) |
| `rustc: command not found` after installing Rust | Source `~/.cargo/env`, or restart the terminal |
| Missing compiler toolchain on Linux | Install `build-essential` (or the distro's equivalent) |
| Build fails on Windows (TypeScript) | Install Visual Studio Build Tools with C++ support |
| Java JARs built from source can't ingest | They were built with `-Dzerobus.skipNativeLibCheck=true` and have no native library; stage it or use `java.library.path` (see Java above) |

## Sources
- [Zerobus SDKs monorepo README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/README.md) (platform support)
- [Python SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md) ("Building from Source"), `python/Makefile`, `python/pyproject.toml`
- [TypeScript SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/typescript/README.md) (source build requirements, local development from source)
- [Java SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/java/README.md) (build requirements, build from source), `java/src/main/java/com/databricks/zerobus/NativeLoader.java`
- [Go SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/go/README.md) (building from source), `go/Makefile`
- [.NET SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/dotnet/README.md) (from source, manual build), `dotnet/build_native.sh`
- [C++ SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/cpp/README.md) (building)
- [Rust SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/rust/README.md) (building from source)
