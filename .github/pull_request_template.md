<!--
Pull request creation is restricted to repository collaborators.
If you are not a Databricks maintainer, use the Change proposal issue template.
Open it at https://github.com/databricks/databricks-agent-skills/issues/new/choose.
See CONTRIBUTING.md for details.
-->

## Summary

<!-- Briefly describe the change. -->

## Documentation safety checklist

- [ ] Examples use least-privilege permissions (no unnecessary `ALL PRIVILEGES`, admin tokens, or broad scopes)
- [ ] Elevated permissions are explicitly called out where required
- [ ] Sensitive values are obfuscated (placeholder workspace IDs, URLs, no real tokens)
- [ ] No insecure patterns introduced (e.g. disabled TLS verification, hardcoded credentials)
