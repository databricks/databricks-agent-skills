## Summary

<!-- Brief description of the change -->

## Documentation safety checklist

- [ ] Examples use least-privilege permissions (no unnecessary `ALL PRIVILEGES`, admin tokens, or broad scopes)
- [ ] Elevated permissions are explicitly called out where required
- [ ] Sensitive values are obfuscated (placeholder workspace IDs, URLs, no real tokens)
- [ ] No insecure patterns introduced (e.g. disabled TLS verification, hardcoded credentials)
