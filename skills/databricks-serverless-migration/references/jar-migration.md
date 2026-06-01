# Scala JAR Migration Reference

Deep reference for migrating a **compiled Scala JAR** (`SPARK_JAR_TASK`) from classic compute to serverless. The parent `databricks-serverless-migration` skill routes here when the workload is a JAR rather than a notebook or script.

Serverless runs JARs on a Spark Connect kernel with a **fixed classpath**: **Scala 2.13.16, JDK 17, Databricks Connect 17.3.1** (environment version 4). Migration is about making the JAR match that classpath instead of bundling its own conflicting copies.

## When the parent skill delegates here

Route into this flow when any of these are true:
- A `spark_jar_task` / `SPARK_JAR_TASK` job, or a build that produces a JAR (`build.sbt`, `pom.xml`, `build.gradle`).
- A serverless run whose output contains a `>>> Scala Version Check` or `>>> Dependency Conflict Detection` block.
- A `NoSuchMethodError: scala.Predef$.wrapRefArray`, `NoClassDefFoundError: scala/Serializable`, or `NoClassDefFoundError` for a Spark-internal class on a serverless JAR run.

## The four failure modes (cover 100% of classified production JAR failures)

| # | Failure | Signature | Root cause | Fix |
|---|---|---|---|---|
| 1 | **Scala version mismatch** | `NoSuchMethodError: scala.Predef$.wrapRefArray`, `NoClassDefFoundError: scala/Serializable` | JAR compiled against Scala 2.12 (classic default). Serverless is 2.13.16. Binary-incompatible at classload. | Recompile against **2.13.16**; `%%` cross-version on every Scala dep. |
| 2 | **Spark internals not on classpath** | `NoClassDefFoundError` for `org/apache/spark/...` driver-side classes (`JavaSparkContext`, Catalyst internals) | Code reaches behind the Spark Connect boundary; Spark is provided by the runtime, not bundled. | Mark Spark `% Provided` (don't bundle it). If the **source** uses `SparkContext`/RDD/Catalyst, rewrite to the DataFrame / Spark Connect surface — a code change, not just a build change. |
| 3 | **Dependency conflict / shadowing** | Jackson/Guava/log4j version errors; behavior differs from the bundled version | The JAR bundles a library the kernel also ships; the kernel's copy wins on the classpath, so the bundled version is silently shadowed. | Declare every overlapping dependency `% Provided` (or align to the kernel version). See the classpath table below. |
| 4 | **Streaming / config** | `ProcessingTime` trigger errors, blocked Spark configs | Serverless requires `availableNow` triggers and only allows a short config allowlist. | Source change: `.trigger(availableNow=true)`; remove unsupported `spark.conf.set`. |

## Step 1 — Analyze the build statically (do not wait for a failed run)

Read the build file and flag issues before running anything.

**Scala version.** In `build.sbt`, find `scalaVersion`. If it is not `2.13.x`, that is failure mode 1.
```
grep -nE 'scalaVersion\s*:=' build.sbt
```
Also flag any explicit `_2.12` artifact suffix and any Scala dep declared with single `%` (no cross-version) instead of `%%`.

**JDK version.** Serverless runs **JDK 17**. A JAR compiled with a newer JDK (21+) fails on the kernel. Check the build's `javacOptions`/`-release` and the local `java -version`, and compile with JDK 17. (JDK 8/11 bytecode runs fine — forward-compatible.)

**Bundled Spark.** Any `spark-core`, `spark-sql`, `spark-catalyst` dependency that is *not* marked `% Provided` is bundling Spark (mode 3). The fix is to mark it `% Provided` (the runtime supplies it). **Watch for mode 2 separately:** if the *source* uses `SparkContext`, `sc.parallelize`, RDD APIs, or Catalyst internals, marking Spark provided is not enough — that code must be rewritten to the DataFrame/Spark Connect surface (a source change, not just a build change). Flag it so the build gate expects a recompile.

**Conflicting dependencies — scan the *full* tree, not just direct deps.** Most conflicts are transitive: our demo JAR pulls guava, log4j, json4s, and Jackson *through* `spark-sql`, never declaring them directly. Matching only `libraryDependencies` misses them. Enumerate what the JAR will actually bundle and match every entry against the kernel classpath table:
```
sbt 'set asciiGraphWidth := 240' dependencyTree   # full transitive tree
sbt evicted                                        # version conflicts already resolved by sbt
# Maven:  mvn dependency:tree
# Gradle: ./gradlew dependencies --configuration runtimeClasspath
```
Every node that appears in the classpath table is a conflict (mode 3). Fix the **whole set** at once: mark the direct deps `% Provided`, and for transitive offenders pulled by another dep, either mark that parent `% Provided` (removes the whole subtree) or add an explicit `% Provided` override. Confirm with `dependencyTree` again that no table entry remains in the assembled set. This is also what lets the skill reproduce the runtime's `Dependency Conflict Detection` list before any run.

**Assembly metadata.** If `assemblyMergeStrategy` discards `META-INF/maven/**`, the runtime cannot read exact bundled versions (it falls back to class-name matching, and says so in the diagnostic). Recommend keeping it:
```scala
case PathList("META-INF", "maven", _ @ _*) => MergeStrategy.first
```

## Step 2 — Apply the fixes (sbt)

**Scala version → 2.13.16:**
```diff
- scalaVersion := "2.12.18"
+ scalaVersion := "2.13.16"
```
Use `%%` on every Scala dependency so it resolves the `_2.13` artifact. One stray `_2.12` artifact re-breaks the runtime.

**Spark → Databricks Connect, provided (default):** serverless provides **Databricks Connect**, not OSS Spark — `com.databricks : databricks-connect_2.13 : 17.3.1` is on the kernel classpath. Compile against the artifact the runtime actually supplies:
```diff
- "org.apache.spark" %% "spark-sql" % "3.5.0"
+ "com.databricks" %% "databricks-connect" % "17.3.1" % Provided
```
`databricks-connect` provides the `org.apache.spark.sql.*` API, so DataFrame/SQL code compiles unchanged. Keep `SparkSession.builder().getOrCreate()` / `SparkSession.active` in the JAR — on the serverless kernel that returns the ambient session. Add a `DatabricksSession.builder().serverless()` bootstrap only if you also want to run the JAR locally against serverless (Step 3.2).

*Fallback, not recommended:* marking OSS `spark-sql % Provided` can work because the public DataFrame API signatures match, but you would be compiling against a **different artifact than the runtime provides** — fragile, and not the documented path. Prefer `databricks-connect`.

**Conflicting libraries → `Provided`:** for every dependency that appears in the kernel classpath table, add `% Provided` so the runtime's copy is the only one on the classpath:
```diff
- "com.fasterxml.jackson.core" % "jackson-databind" % "2.17.0"
+ "com.fasterxml.jackson.core" % "jackson-databind" % "2.15.2" % Provided
```
Prefer `% Provided` over version-pinning; the runtime supplies the version it pins regardless, so `Provided` is the durable fix and shrinks the JAR.

**Exclude Scala from the fat JAR.** The kernel provides `scala-library 2.13.16`; do not bundle your own copy. Mirror the `default-scala` template:
```scala
assembly / assemblyOption ~= { _.withIncludeScala(false) }
```

**Build tools other than sbt.** This reference is sbt-first (the common case). The same three moves apply elsewhere; only the syntax changes:
- **Maven** (`maven-shade-plugin`): set the Scala 2.13 artifacts, add `<scope>provided</scope>` to Spark and every conflicting dependency, and do not exclude `META-INF/maven/**` in the shade filters.
- **Gradle** (`shadow`): use the `_2.13` deps, move conflicting libs to `compileOnly` (Gradle's `provided`), and keep `META-INF/maven` in the minimize/relocate config.

Full Maven/Gradle fix recipes are a TODO; for now, translate the sbt steps above.

## Step 3 — Verify before deploying (do not skip)

Editing `build.sbt` is not the fix; a JAR that compiles and runs is. Gate on both before the slow upload, smallest/fastest check first.

**1. Compile + assemble (build gate).** The migrated JAR must build. Marking deps `% Provided` keeps them on the *compile* classpath (they are only excluded from the package), so compilation still resolves them, this step catches the case where a version change or removed dependency breaks the code.
```
sbt clean assembly
```
If this fails, fix the source/build and repeat. Never upload a JAR that did not assemble cleanly.

**2. Local smoke test via Databricks Connect.** Because the default fix depends on `databricks-connect`, you can run the logic against serverless from the laptop in seconds — no upload, no job run — once the project has a `DatabricksSession.builder().serverless()` bootstrap (add one if migrating from a bare `SparkSession.builder()`; the `default-scala` template includes it):
```
export DATABRICKS_CONFIG_PROFILE=<your-serverless-profile>
sbt test     # if the project has tests
sbt run      # runs Main against serverless via the DatabricksSession
```
A green local run means the migration worked end to end against the real serverless kernel. This is the fast inner loop — only after it passes do you pay for the deploy.

*(If you took the not-recommended `spark-sql % Provided` fallback, there is no local session to connect with — the assemble gate in 3.1 is your only local check and Step 4's deploy run is the first real test.)*

## Step 4 — Deploy and confirm

Two levels of rigor. Use the **fast path** for a quick migration; use **production rigor** when the migrated job is going back into production and outputs must match.

### Fast path (quick validation)
```
databricks fs cp target/scala-2.13/<artifact>.jar dbfs:/Volumes/<cat>/<schema>/<vol>/<artifact>.jar --overwrite
databricks jobs run-now <job_id>
```
Confirm the run reaches `TERMINATED / SUCCESS`. For a clean target, prefer the `default-scala` bundle template (`databricks bundle init default-scala`), which sets this up by default and deploys with `databricks bundle deploy`.

### Production rigor (adapt the parent flow — a JAR is NOT a notebook)

The parent skill's notebook testing relies on **re-pointing the workload at a sampled test catalog** via a catalog widget/variable. **Do not assume that works for a JAR.** A compiled JAR usually **hardcodes its source and output tables in Scala**, so you cannot redirect it to a test catalog without changing code. Before borrowing the parent's test-data step, branch on this:

**Is the JAR parameterized** (reads catalog / schema / tables from args or config, like the `default-scala` template's `--catalog` / `--schema`)?

- **Yes (parameterized):** the parent approach transfers directly. Create **sampled upstream tables in a test catalog** (`CREATE TABLE … LIMIT N` from the job's lineage), pass the test catalog as a job parameter, and run the migrated JAR against it.
- **No (hardcoded tables — the common case):** the "sampled test catalog" step **will not work** — the JAR can't see it. Do **not** fabricate a test catalog the JAR can't read. Instead, pick one:
  - **(a) Parameterize it first** — a small source change to read catalog/schema/output table from args. Recommended if the team will keep iterating. Then proceed as the parameterized case.
  - **(b) A/B on real inputs, redirected output** — run the **original JAR on classic** and the **migrated JAR on serverless** against the *same* production source tables, each writing to a **distinct output table** (redirect the migrated run's output via a param or a one-line source edit so it does not clobber prod), then diff the two outputs.

**A/B comparison** (either path): diff the output tables — row counts first, then full content / checksums. Equal output is the real proof the migration preserved behavior, not just that it ran.

**Git flow transfers fine** (it's the *data*-repointing that doesn't): make the `build.sbt` changes on a `serverless-test-<job>-<ts>` branch, then put **only** the real migration fixes on a clean `serverless-prod-<job>` branch off master and open a **PR** — no test-only workarounds (catalog overrides, output redirects, sampled data) in the prod branch.

So: build gate + DB Connect loop (Step 3) are the fast inner loop; this branch + A/B is the production gate — but the test-data setup is conditional on the JAR being re-pointable, which is exactly the assumption that breaks if you copy the notebook flow blindly.

## Kernel classpath — serverless environment version 4

Scala **2.13.16**, JDK **17**, Databricks Connect **17.3.1**. If the JAR bundles any of these, declare it `% Provided` (the runtime's version below wins regardless). Grouped by collision risk for application JARs.

### A. High-collision application libraries (the usual offenders)
| Group : Artifact | Kernel version |
|---|---|
| com.fasterxml.jackson.core : jackson-core / jackson-databind / jackson-annotations | 2.15.2 |
| com.fasterxml.jackson.datatype : jackson-datatype-jsr310 | 2.15.2 |
| com.google.guava : guava | 32.0.1-jre |
| com.google.guava : failureaccess | 1.0.1 |
| com.google.code.gson : gson | 2.10.1 |
| org.apache.logging.log4j : log4j-api / log4j-core | 2.20.0 |
| org.apache.logging.log4j : log4j-slf4j-impl | 2.24.3 |
| org.slf4j : slf4j-api | 2.0.10 |
| org.json4s : json4s-ast/core/jackson/jackson-core/scalap _2.13 | 4.0.7 |
| org.json : json | 20240303 |
| com.thoughtworks.paranamer : paranamer | 2.8 |
| commons-codec : commons-codec | 1.11 |
| commons-io : commons-io | 2.14.0 |
| commons-logging : commons-logging | 1.3.2 |
| org.apache.commons : commons-lang3 | 3.14.0 |
| org.apache.commons : commons-text | 1.12.0 |
| org.apache.commons : commons-configuration2 | 2.11.0 |
| org.apache.httpcomponents : httpclient | 4.5.14 |
| org.apache.httpcomponents : httpcore | 4.4.16 |
| com.thesamet.scalapb : scalapb-runtime / lenses _2.13 | 0.11.15 |

### B. Spark / Databricks Connect — never bundle, mark `Provided`
| Group : Artifact | Kernel version |
|---|---|
| com.databricks : databricks-connect_2.13 | 17.3.1 |
| com.databricks : databricks-dbutils-scala_2.13 | 0.1.4 |
| com.databricks : databricks-sdk-java | 0.52.0 |

### C. Scala toolchain — must match exactly (mark `Provided` / let sbt manage)
| Group : Artifact | Kernel version |
|---|---|
| org.scala-lang : scala-library / scala-reflect / scala-compiler _2.13 | 2.13.16 |
| org.scala-lang : scalap_2.13 | 2.13.13 |
| org.scala-lang.modules : scala-collection-compat_2.13 | 2.13.0 |
| org.scala-lang.modules : scala-java8-compat_2.13 | 1.0.2 |

### D. Google / transitive infra (collide only if your JAR pulls them)
| Group : Artifact | Kernel version |
|---|---|
| com.google.auth : google-auth-library-credentials / -oauth2-http | 1.20.0 |
| com.google.http-client : google-http-client / -gson | 1.43.3 |
| com.google.errorprone : error_prone_annotations | 2.18.0 |
| org.checkerframework : checker-qual | 3.33.0 |
| io.grpc : grpc-context | 1.27.2 |
| io.opencensus : opencensus-api / -contrib-http-util | 0.31.1 |

### E. Kernel / REPL internals — rarely bundled by app JARs, but conflict if present
The serverless Scala kernel runs on Ammonite/Almond. These are kernel internals; an application JAR seldom depends on them, but `os-lib`, `scalatags`, `pprint`, `fansi`, and the `scalameta`/`mtags` family do show up in tooling-heavy JARs and will conflict.
| Group | Artifacts (all `_2.13`) | Version |
|---|---|---|
| com.lihaoyi | ammonite-*, fansi, mainargs, os-lib, pprint, scalaparse, scalatags, ammonite-terminal, ammonite-util | 3.0.8 / 0.5.1 / 0.7.6 / 0.11.3 / 0.9.0 / 3.1.1 / 0.13.1 |
| org.scalameta | scalameta, parsers, trees, io, mtags, mtags-shared, mtags-interfaces, semanticdb-scalac-core | 4.13.10 / 1.6.3 |
| sh.almond | scala-kernel, kernel, interpreter, protocol, jupyter-api, channels, logger, ... | 0.14.5 |
| org.jline | jline / jline-reader / jline-terminal | 3.27.1 / 3.14.1 |

> This table is the env-4 classpath snapshot provided by the runtime team (Scala 2.13.16 / JDK 17 / DBConnect 17.3.1). Refresh it per environment version; env 5 may differ. The runtime's own `Dependency Conflict Detection` output is the live source of truth at failure time, this table lets the skill flag the same conflicts statically before a run.

## Output the skill should produce
1. A diff of `build.sbt` (Scala 2.13.16, `databricks-connect` provided, conflicting deps `% Provided`, `META-INF/maven` preserved).
2. **Build result:** confirmation that `sbt clean assembly` succeeded (or the compile errors, if not). Do not proceed past a failed build.
3. **Local test result:** confirmation that `sbt test` / `sbt run` ran green against serverless via Databricks Connect (or why it was skipped, e.g. no tests).
4. **Deploy result:** the re-upload + rerun outcome (run state), or the `default-scala` bundle equivalent.
5. A short report: which failure modes were found, which dependencies were marked `Provided` and why (cite the kernel version), and anything it could not resolve statically.

**Success criterion:** the skill has not "migrated" the JAR until it both **assembles** and **runs green** (locally via DB Connect and/or as the deployed job). Editing the build is necessary but not sufficient.
