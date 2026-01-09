# Databricks Skills Development

This folder is for developing skills for working with Databricks and Databricks apps.

## Structure

- `.claude/skills/` - Contains all skill definitions locally

## Workflow

1. Perform tasks using the Claude agent to explore Databricks capabilities
2. Document findings and successful approaches
3. Create skills from these learnings in the `.claude/skills/` directory

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
