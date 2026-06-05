# Scala JAR Migration Reference

Deep reference for migrating a **compiled Scala JAR** (`SPARK_JAR_TASK`) from classic compute to serverless. The parent `databricks-serverless-migration` skill routes here when the workload is a JAR rather than a notebook or script.

Serverless runs JARs on a Spark Connect kernel with a **fixed classpath**: **Scala 2.13.16, JDK 17, Databricks Connect 17.3.1** (environment version 4). Migration is about making the JAR match that classpath instead of bundling its own conflicting copies.

## When the parent skill delegates here

Route into this flow when any of these are true:
- A `spark_jar_task` / `SPARK_JAR_TASK` job, or a build that produces a JAR (`build.sbt`, `pom.xml`, `build.gradle`).
- A serverless run whose output contains a `>>> Scala Version Check` or `>>> Dependency Conflict Detection` block. (These diagnostic blocks are emitted by recent serverless runtimes — environment version 4 and later; older runtimes may not print them, so fall back to the error signatures below.)
- A `NoSuchMethodError: scala.Predef$.wrapRefArray`, `NoClassDefFoundError: scala/Serializable`, or `NoClassDefFoundError` for a Spark-internal class on a serverless JAR run.

## The four failure modes (every failure mode we've seen across JAR migrations to date)

| # | Failure | Signature | Root cause | Fix |
|---|---|---|---|---|
| 1 | **Scala version mismatch** | `NoSuchMethodError: scala.Predef$.wrapRefArray`, `NoClassDefFoundError: scala/Serializable` | JAR compiled against Scala 2.12 (classic default). Serverless is 2.13.16. Binary-incompatible at classload. | Recompile against **2.13.16**; `%%` cross-version on every Scala dep. |
| 2 | **Spark internals not on classpath** | `NoClassDefFoundError` for `org/apache/spark/...` driver-side classes (`JavaSparkContext`, Catalyst internals) | Code reaches behind the Spark Connect boundary; Spark is provided by the runtime, not bundled. | Mark Spark `% Provided` (don't bundle it). If the **source** uses `SparkContext`/RDD/Catalyst, rewrite to the DataFrame / Spark Connect surface — a code change, not just a build change. |
| 3 | **Dependency conflict / shadowing** | Jackson/Guava/log4j version errors; behavior differs from the bundled version | The JAR bundles a library the kernel also ships; the kernel's copy wins on the classpath, so the bundled version is silently shadowed. | Declare every overlapping dependency `% Provided` (or align to the kernel version). See the classpath table below. |
| 4 | **Streaming / config** | `ProcessingTime` trigger errors, blocked Spark configs | Serverless requires `availableNow` triggers and only allows a short config allowlist. | Source change: `.trigger(Trigger.AvailableNow())` (`import org.apache.spark.sql.streaming.Trigger`); remove unsupported `spark.conf.set`. |

## Narrate the migration as you go

This is an interactive migration. After each step below, tell the user **what you did and what happened** before moving to the next step — do not silently apply a batch of changes and reveal them only at the end. Each step ends with a **Report after this step** line stating the minimum to surface. The value of the skill is the user seeing which failure modes were detected, what was changed and why, and the result of each gate. The end-of-run summary (see "Output the skill should produce") consolidates these per-step reports; it does not replace them.

## Step 1 — Analyze the build statically (do not wait for a failed run)

Read the build file and flag issues before running anything.

**Scala version.** In `build.sbt`, find `scalaVersion`. If it is not `2.13.x`, that is failure mode 1.
```
grep -nE 'scalaVersion\s*:=' build.sbt
```
Also flag any explicit `_2.12` artifact suffix and any Scala dep declared with single `%` (no cross-version) instead of `%%`.

**JDK version.** Serverless runs **JDK 17**. A JAR compiled with a newer JDK (21+) fails on the kernel. Check the build's `javacOptions`/`-release` and the local `java -version`, and compile with JDK 17. (JDK 8/11 bytecode runs fine — forward-compatible.)

**Bundled Spark.** Any `spark-core`, `spark-sql`, `spark-catalyst` dependency that is *not* marked `% Provided` is bundling Spark (mode 3). The fix is to mark it `% Provided` (the runtime supplies it). **Watch for mode 2 separately:** if the *source* uses `SparkContext`, `sc.parallelize`, RDD APIs, or Catalyst internals, marking Spark provided is not enough — that code must be rewritten to the DataFrame/Spark Connect surface (a source change, not just a build change). Flag it so the build gate expects a recompile.

**Conflicting dependencies — scan the *full* tree, not just direct deps.** Most conflicts are transitive: our demo JAR pulls guava, log4j, json4s, and Jackson *through* `spark-sql`, never declaring them directly. Matching only `libraryDependencies` misses them. Enumerate what the JAR will actually bundle and match every entry against the kernel classpath table. (These commands invoke the workload's own build system — `sbt`/`mvn`/`gradle` execute project plugins and settings — which is expected here because the user is migrating their own JAR. If the build's provenance is unknown or untrusted, confirm with the user before invoking.)
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
If the project already defines an `assemblyMergeStrategy`, **add** this case to the existing strategy rather than replacing it wholesale — overwriting it can drop merge rules the build already relies on.

**Report after this step:** State the verdict before changing anything — which of the four failure modes are present, the JAR's current Scala and JDK versions, the exact conflicting dependencies found in the tree (naming the kernel version each one collides with), and whether any mode-2 source rewrites are required. If the build is already clean, say so and stop here.

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

**Build tools other than sbt.** This reference is sbt-first (the common case), but the same three moves — Scala 2.13 artifacts, `provided` scope on Spark and every conflicting dependency, preserve `META-INF/maven` — translate directly. Recipes for both below.

**Maven** (`maven-shade-plugin`). Set the Scala 2.13 toolchain via properties, mark Spark/Databricks Connect and every conflicting dependency `provided`, and do **not** enable `<minimizeJar>` or filter `META-INF/maven/**` (the runtime reads bundled versions from there):
```xml
<properties>
  <scala.binary.version>2.13</scala.binary.version>
  <scala.version>2.13.16</scala.version>
</properties>

<dependencies>
  <!-- Scala stdlib: provided — the kernel ships 2.13.16 -->
  <dependency>
    <groupId>org.scala-lang</groupId>
    <artifactId>scala-library</artifactId>
    <version>${scala.version}</version>
    <scope>provided</scope>
  </dependency>
  <!-- Spark API via Databricks Connect: provided, the artifact the runtime supplies -->
  <dependency>
    <groupId>com.databricks</groupId>
    <artifactId>databricks-connect_${scala.binary.version}</artifactId>
    <version>17.3.1</version>
    <scope>provided</scope>
  </dependency>
  <!-- Every dependency that appears in the kernel classpath table: provided -->
  <dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <version>2.15.2</version>
    <scope>provided</scope>
  </dependency>
</dependencies>

<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-shade-plugin</artifactId>
      <executions>
        <execution>
          <phase>package</phase>
          <goals><goal>shade</goal></goals>
          <configuration>
            <!-- No <minimizeJar>, no <filter> excluding META-INF/maven/** -->
            <transformers>
              <transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
            </transformers>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```
`provided` keeps a dependency on the compile classpath but out of the shaded JAR, the exact analogue of sbt's `% Provided`. Build with `mvn clean package`; the tree-scan command is `mvn dependency:tree`.

**Gradle** (`shadow` plugin). Use the `_2.13` artifacts, move Spark and every conflicting dependency to `compileOnly` (Gradle's `provided`), and do **not** call `minimize()` or `exclude 'META-INF/maven/**'` in the `shadowJar` block:
```groovy
plugins {
  id 'scala'
  id 'com.github.johnrengelman.shadow' version '8.1.1'
}

ext {
  scalaBinary  = '2.13'
  scalaVersion = '2.13.16'
}

dependencies {
  // Scala stdlib + Spark API via Databricks Connect: compileOnly — the kernel supplies them
  compileOnly "org.scala-lang:scala-library:${scalaVersion}"
  compileOnly "com.databricks:databricks-connect_${scalaBinary}:17.3.1"
  // Every dependency that appears in the kernel classpath table: compileOnly
  compileOnly 'com.fasterxml.jackson.core:jackson-databind:2.15.2'
}

shadowJar {
  // No minimize(), no exclude('META-INF/maven/**')
  mergeServiceFiles()
}
```
Build with `./gradlew shadowJar`; the tree-scan command is `./gradlew dependencies --configuration runtimeClasspath`. Note: `compileOnly` deps are not on the **test** runtime classpath, so if a `provided` library is needed to run tests, also add it as `testRuntimeOnly`.

**Report after this step:** Show the `build.sbt` (or `pom.xml`/`build.gradle`) diff and explain each change in one line — the Scala bump, every dependency newly marked `% Provided` (naming the kernel version it would otherwise shadow), and Scala excluded from the assembly. The user should see what changed and why *before* any build runs.

## Step 3 — Verify before deploying (do not skip)

Editing `build.sbt` is not the fix; a JAR that compiles and runs is. The build gate below is required and cheap. The local run is **optional** — it can catch issues before the slow upload, but the Step 4 deploy run is the authoritative test, so skip it if you'd rather not wire it up.

**1. Compile + assemble (build gate).** The migrated JAR must build. Marking deps `% Provided` keeps them on the *compile* classpath (they are only excluded from the package), so compilation still resolves them, this step catches the case where a version change or removed dependency breaks the code.
```
sbt clean assembly
```
If this fails, fix the source/build and repeat. Never upload a JAR that did not assemble cleanly.

**2. (Optional) Local smoke test via Databricks Connect.** Skippable — only do this if you want a laptop-side check before deploying. It requires a source change (a `DatabricksSession.builder().serverless()` bootstrap, if the project uses a bare `SparkSession.builder()`). If you'd rather not touch source, skip straight to the Step 4 deploy run, which validates the same thing. If you do want it — because the compile dep is `databricks-connect`, you can run the logic against serverless from the laptop in seconds, no upload, no job run (the `default-scala` template ships the bootstrap):
```scala
// Local-run bootstrap. On the serverless kernel the ambient session is injected,
// so this path is only exercised when you run the JAR from your laptop.
import com.databricks.connect.DatabricksSession
val spark = DatabricksSession.builder().serverless().getOrCreate()
```
```
export DATABRICKS_CONFIG_PROFILE=<your-serverless-profile>
sbt test     # if the project has tests
sbt run      # runs Main against serverless via the DatabricksSession
```
A green local run means the migration worked end to end against the real serverless kernel. Treat it as an optional accelerator, not a required gate — the deploy run in Step 4 is the authoritative test.

*(If you took the not-recommended `spark-sql % Provided` fallback, there is no local session to connect with — the assemble gate in 3.1 is your only local check and Step 4's deploy run is the first real test.)*

**Report after this step:** Report the build-gate result (assembled cleanly, or the compile errors). If you ran the optional local smoke test, report its result; otherwise note it was skipped and that validation happens at the Step 4 deploy run. Do not move on from a failed build — say it failed and what you are fixing.

## Step 4 — Deploy and confirm

Two levels of rigor. Use the **fast path** for a quick migration; use **production rigor** when the migrated job is going back into production and outputs must match.

### Deploy with a bundle (durable default)

The version-controlled end state is a DABs bundle, and it is where the rest of this skill is already heading — the git-flow section below puts `build.sbt` on a branch and opens a PR. Make the bundle the durable artifact rather than an afterthought. For a clean target, `databricks bundle init default-scala` scaffolds a serverless Scala JAR job; deploy with `databricks bundle deploy` and trigger with `databricks bundle run <job>`. Lean on the sibling skills for the mechanics instead of re-teaching them here:
- **`databricks-dabs`** — bundle structure, targets, `deploy`/`run`.
- **`databricks-jobs`** — the job and task definition.

This reference covers only the serverless-JAR-specific wiring those skills don't (the `environments` / `java_dependencies` shape below).

### Quick inner-loop check (fast path)

To re-test a freshly rebuilt JAR against an already-deployed job — without a full redeploy — upload and re-run it directly:
```
databricks fs cp target/scala-2.13/<artifact>.jar dbfs:/Volumes/<cat>/<schema>/<vol>/<artifact>.jar --overwrite
databricks jobs run-now <job_id>
```
Confirm the run reaches `TERMINATED / SUCCESS`. This is a fast iteration loop, not the durable deploy — fold the validated change back into the bundle above before shipping.

### Job config — attach the JAR to the serverless environment

A serverless JAR task wires up the JAR differently from a classic `spark_jar_task`, and the differences are **rejected at deploy time** (`databricks bundle deploy` / `jobs reset`) rather than at run time — so fix them in the job definition up front instead of discovering them on a failed deploy:

- Define a job-level `environments` entry with `spec.environment_version: "4"`. The value must be the quoted **string** `"4"`, not the integer `4` — the Jobs API rejects the unquoted form. (`environment_version` is the current field and supersedes the deprecated `spec.client` the parent skill's Python/notebook examples still use — same concept, newer name.)
- Attach the JAR in `environments[].spec.java_dependencies` (a `/Volumes/...` path) — **not** the task-level `libraries` field, which is not supported for serverless tasks.
- Reference the environment from the task with `environment_key` (in place of `job_cluster_key` / `new_cluster`).
- Remove the classic cluster scaffolding entirely: `new_cluster`, `num_workers`, `node_type_id`, `data_security_mode`, `spark_conf`, `init_scripts`, `cluster_log_conf`.

```yaml
# DABs job YAML — serverless spark_jar_task
environments:
  - environment_key: default
    spec:
      environment_version: "4"            # Scala 2.13.16 / JDK 17 / DBConnect 17.3.1
      java_dependencies:
        - /Volumes/<cat>/<schema>/<vol>/<artifact>.jar
tasks:
  - task_key: my_task
    environment_key: default              # not job_cluster_key / new_cluster
    spark_jar_task:
      main_class_name: com.example.Main
      parameters: ["--flag", "value"]
    # no task-level `libraries:` — the JAR is in java_dependencies above
```

Deploy-time errors and their fix:

| Error (at `bundle deploy` / `jobs reset`) | Fix |
|---|---|
| `Libraries field is not supported for serverless task, please specify libraries in environment` | Move the JAR out of the task `libraries` field into `environments[].spec.java_dependencies` |
| `Serverless jar task must have java_dependencies in environment` | The JAR belongs in `java_dependencies` specifically — not `dependencies` (which is for PyPI/wheels) |

### Production rigor — follow the parent skill, with one JAR prerequisite

Do not invent a JAR-specific testing methodology. Use the parent skill's **Step 3** unchanged: the two-branch strategy, **Test Data Setup** (sample upstream tables into a test catalog), the **A/B comparison**, and the prod-vs-test decision table. The build gate + Databricks Connect loop (Step 3 above) are the fast inner loop; the parent's test-branch + A/B is the production gate.

The only thing a JAR adds is the *seam*. The parent flow re-points the workload at the test catalog by flipping a parameter — a notebook does this with a `catalog` widget. A compiled JAR has no widget: if its catalog/schema/tables are **hardcoded in Scala**, there is nothing to re-point. So before borrowing the parent's test-data step, check whether the JAR can read them from args (like the `default-scala` template's `--catalog` / `--schema`):

- **Parameterized** → the parent flow applies directly. Sample upstream tables into a test catalog (`CREATE TABLE … LIMIT N` from the job's lineage), pass the test catalog as a job parameter, and run the migrated JAR against it.
- **Hardcoded** → parameterize it first (a small source change to read catalog/schema/output table from args), then proceed exactly as the parameterized case.

Either way, **test output lands in a non-production table — never overwrite the production output table to test.** This is the parent's rule, not a JAR exception.

**Git flow is identical to the parent:** make the `build.sbt` changes on a `serverless-test-<job>-<ts>` branch, then put **only** the real compatibility fixes on a clean `serverless-prod-<job>` branch off master and open a **PR** — no test-only workarounds (catalog overrides, sampled data) in the prod branch.

**Report after this step:** Report the deploy + run outcome (run state and run URL/ID). On the production-rigor path, also report the A/B result — row counts, schema match, and row-level diff — and state explicitly whether output matched the classic baseline, not just that the run was green.

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

Produce the parent skill's **Migration Deliverables** (test/prod branch, test job run + URL, A/B comparison, environment spec, change summary) as the baseline — the deploy outcome is captured there. A JAR migration adds these JAR-specific deliverables on top:

1. **Build diff:** the `build.sbt` (or `pom.xml` / `build.gradle`) diff — Scala 2.13.16, `databricks-connect` provided, conflicting deps `% Provided`, `META-INF/maven` preserved.
2. **Build result:** confirmation that `sbt clean assembly` (or `mvn clean package` / `./gradlew shadowJar`) succeeded, or the compile errors if not. Do not proceed past a failed build.
3. **Local test result:** confirmation that the optional Databricks Connect smoke test ran green (or why it was skipped, e.g. no tests).
4. **Failure modes resolved:** which of the four modes were found, which dependencies were marked `Provided` and why (cite the kernel version), and anything that could not be resolved statically.

**Success criterion:** the skill has not "migrated" the JAR until it both **assembles** and **runs green** (locally via DB Connect and/or as the deployed job). Editing the build is necessary but not sufficient.
