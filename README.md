# Databricks Skills Plugin for Claude Code

A comprehensive Claude Code plugin that provides specialized skills for working with Databricks services, CLI tools, and development workflows.

## Overview

This plugin equips Claude with deep knowledge of Databricks development, enabling it to help you:

- Build and deploy Databricks Apps
- Work with Unity Catalog (catalogs, schemas, tables, volumes)
- Execute SQL queries and explore data
- Manage ML model serving endpoints
- Create and manage Asset Bundles (DABs)
- Configure Databricks CLI authentication
- Install and troubleshoot Databricks CLI
- Scaffold new Databricks projects

## Installation

### From Plugin Directory

```bash
claude --plugin-dir /path/to/databricks-skills
```

### As a Permanent Plugin

1. Copy this directory to your Claude plugins folder:
   ```bash
   cp -r databricks-skills ~/.claude/plugins/
   ```

2. Claude will automatically load the plugin on next startup

### Testing the Plugin

To test the plugin before permanent installation:

```bash
cd /path/to/databricks-skills
claude --plugin-dir .
```

## Included Skills

### 🚀 Databricks CLI (Main Skill)
**Trigger:** Automatically activated for any Databricks-related task

Comprehensive guidance for all Databricks services:
- **Project Scaffolding** - Create AI-friendly Databricks projects
- **Apps** - Build and deploy data/AI applications
- **Unity Catalog** - Data governance and catalog management
- **Data Exploration** - Schema discovery and SQL execution
- **Model Serving** - Deploy and manage ML models
- **Asset Bundles (DABs)** - Infrastructure-as-Code
- **DBSQL** - SQL warehouses and analytics
- **LakeFlow** - Delta Live Tables and ETL pipelines
- **Jobs** - Workflow orchestration
- **AI/BI Dashboards** - Interactive analytics
- **Genie** - AI-powered data analysis

### 🔐 Databricks CLI Auth
**Trigger:** Authentication and profile configuration tasks

Handles:
- Workspace/profile selection
- OAuth2 authentication (no PAT)
- Profile switching with `--profile` flags
- `DATABRICKS_CONFIG_PROFILE` environment variable
- Claude Code-specific authentication guidance
- Troubleshooting authentication issues

### ⚙️ Databricks CLI Install
**Trigger:** CLI installation and update tasks

Supports:
- macOS (Homebrew)
- Windows (WinGet)
- Linux (curl install script)
- Manual downloads
- User directory installs (non-sudo environments)
- Installation verification
- Common failure recovery

## Plugin Structure

```
databricks-skills/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── skills/                    # Skills directory
│   ├── databricks-cli/       # Main Databricks CLI skill
│   │   ├── SKILL.md
│   │   ├── apps.md
│   │   ├── unity-catalog.md
│   │   ├── model-serving.md
│   │   └── ... (more modules)
│   ├── databricks-cli-auth/  # Authentication skill
│   │   └── SKILL.md
│   └── databricks-cli-install/ # Installation skill
│       └── SKILL.md
├── README.md                 # This file
└── CLAUDE.md                 # Development guidelines

```

## Usage Examples

### Creating a Databricks App

```
You: Create a new Databricks app for analyzing customer data

Claude: [Uses databricks-cli skill]
I'll help you create a Databricks app. Let me scaffold a new project...
```

### Troubleshooting Authentication

```
You: I'm getting authentication errors with Databricks CLI

Claude: [Uses databricks-cli-auth skill]
Let me check your Databricks authentication configuration...
```

### Installing Databricks CLI

```
You: How do I install the Databricks CLI on macOS?

Claude: [Uses databricks-cli-install skill]
I'll help you install the Databricks CLI using Homebrew...
```

## Development

### Adding New Skills

1. Create a new directory in `skills/`
2. Add a `SKILL.md` file with frontmatter:
   ```markdown
   ---
   name: "Your Skill Name"
   description: "When and how Claude should use this skill"
   ---

   # Skill content...
   ```

### Security Guidelines

When documenting examples, always obfuscate sensitive information:

- **Workspace IDs/URLs**: Use repeated digits
  - ✅ Good: `https://adb-1111111111111111.10.azuredatabricks.net`
  - ❌ Bad: Real workspace IDs

- **Credentials**: Never include real tokens or passwords
- **Resource IDs**: Use placeholder sequences (`11111111`, `22222222`)

## Contributing

1. Follow the security guidelines in `CLAUDE.md`
2. Test skills with `claude --plugin-dir .`
3. Ensure all skills have proper frontmatter
4. Document any new capabilities in this README

## Version History

- **1.0.0** - Initial plugin release
  - Databricks CLI skill with 15+ service modules
  - Authentication configuration skill
  - Installation and troubleshooting skill

## License

Internal use for Databricks development workflows.

## Support

For issues or questions:
- Check `CLAUDE.md` for development guidelines
- Review individual skill documentation in `skills/`
- Test with `claude --plugin-dir .` for debugging
