# Databricks Skills Plugin

This is a Claude Code plugin that provides comprehensive skills for working with Databricks services, CLI tools, and development workflows.

## Plugin Structure

- `.claude-plugin/plugin.json` - Plugin manifest with metadata
- `skills/` - All skill definitions for the plugin
- `.claude/` - Local development configuration (not included when plugin is distributed)
- `README.md` - Plugin documentation and usage guide
- `CLAUDE.md` - Development guidelines and security practices

## Development Workflow

1. Perform tasks using the Claude agent to explore Databricks capabilities
2. Document findings and successful approaches
3. Create or update skills in the `skills/` directory
4. Test the plugin locally with: `claude --plugin-dir .`
5. Update version in `.claude-plugin/plugin.json` when ready to release

## Documentation Guidelines

### Security and Privacy

**CRITICAL**: When documenting examples in skills, always obfuscate sensitive information:

1. **Workspace IDs/URLs**: Replace real workspace IDs with sequences of repeated digits
   - ❌ Bad: `https://adb-1966697730403610.10.azuredatabricks.net`
   - ✅ Good: `https://adb-1111111111111111.10.azuredatabricks.net`
   - ✅ Good: `https://company-workspace.cloud.databricks.com`

2. **Obfuscation Pattern**: Use repeated digits (e.g., `1111111111111111`, `2222222222222222`) instead of real identifiers
   - For numeric IDs: Use sequences like `11111111`, `22222222`, `99999999`
   - For alphanumeric: Use generic placeholders like `company-workspace`, `your-workspace`

3. **Other Sensitive Information**:
   - Never include real access tokens, passwords, or credentials
   - Use placeholder names for users, teams, and organizations
   - Obfuscate job IDs, cluster IDs, and other resource identifiers

### Why This Matters

- Protects internal workspace information from being exposed publicly
- Prevents potential security risks from sharing real identifiers
- Makes examples more universal and relatable for all users
- Follows security best practices for documentation
