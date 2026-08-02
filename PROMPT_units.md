Read PROMPT_plan.md, AGENTS.md, and every file under specs/.

Task: restate every count in specs/02-audit-findings.md in the units that
scripts/audit_check.py actually reports.

Run audit_check.py against upstream/main to get the unremediated baseline.
For each finding class, replace the audit's stated count with the checker's,
name the unit explicitly - occurrences, links, files, or skills - and where
the two differ, record the reconciliation the way SPEC-10b and the in-fence
exemption already are.

Known divergences:
  PD-5       spec 17 skills        checker 228 links
  PD-6       spec ~120 files       checker 125 files
  DESC-1     spec 5 skills         checker 6 descriptions
  SPEC-10a   spec 128 occurrences  checker 90 cross, 21 intra, 3 prose,
                                   81 fence-exempt, 3 self-parent-exempt

Edit no file under skills/ or experimental/. This is a spec-alignment pass,
not a remediation pass.

Commit with git commit -s.

Emit the completion promise only when every must-fix and blocked row in the
checker's table has a matching spec entry stated in the same units.
