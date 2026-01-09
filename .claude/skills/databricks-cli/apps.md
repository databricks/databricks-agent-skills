# Databricks Apps

Databricks Apps allow you to build and deploy data and AI applications on Databricks.

## Common App Commands

```bash
# List all apps
databricks apps list --profile my-workspace

# Get details about a specific app
databricks apps get <app-name> --profile my-workspace

# Create a new app
databricks apps create <app-name> --source-code-path /path/to/app --profile my-workspace

# Deploy an app
databricks apps deploy <app-name> --profile my-workspace

# Update an app
databricks apps update <app-name> --profile my-workspace

# Delete an app
databricks apps delete <app-name> --profile my-workspace

# Get app logs
databricks apps logs <app-name> --profile my-workspace

# Start an app
databricks apps start <app-name> --profile my-workspace

# Stop an app
databricks apps stop <app-name> --profile my-workspace
```

## App Development Workflow

### 1. Initialize App Locally

Use Asset Bundles to initialize your app (see [asset-bundles.md](asset-bundles.md)):

```bash
# Initialize a new bundle with app template
databricks bundle init --profile my-workspace
# Select: databricks-app
```

### 2. Create App in Workspace

```bash
databricks apps create my-app \
  --source-code-path ./app \
  --profile my-workspace
```

### 3. Deploy App

```bash
databricks apps deploy my-app --profile my-workspace
```

### 4. Monitor App

```bash
# Check status
databricks apps get my-app --profile my-workspace

# View logs
databricks apps logs my-app --profile my-workspace
```

## App Management with Asset Bundles

Apps can be managed more efficiently using Databricks Asset Bundles. This is the recommended approach for production applications.

### Example Bundle Configuration

```yaml
# resources/my_app.yml
resources:
  apps:
    my_app:
      name: my-app
      description: "My Databricks App"
      source_code_path: ./src/app
```

### Deploy with Bundle

```bash
# Validate
databricks bundle validate --profile my-workspace

# Deploy to dev
databricks bundle deploy -t dev --profile my-workspace

# Deploy to prod
databricks bundle deploy -t prod --profile my-workspace
```

## App Structure

A typical Databricks App structure:

```
my-app/
├── app.yaml           # App configuration
├── app.py             # Main application file
├── requirements.txt   # Python dependencies
└── static/           # Static assets (optional)
    ├── css/
    └── js/
```

## App Configuration (app.yaml)

```yaml
# app.yaml
command:
  - "python"
  - "app.py"

env:
  - name: APP_PORT
    value: "8080"
  - name: LOG_LEVEL
    value: "INFO"
```

## Common App Patterns

### Flask App Example

```python
# app.py
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return 'Hello from Databricks App!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

### Streamlit App Example

```python
# app.py
import streamlit as st

st.title('My Databricks App')
st.write('Welcome to my data application!')
```

### Dash App Example

```python
# app.py
from dash import Dash, html

app = Dash(__name__)

app.layout = html.Div([
    html.H1('My Databricks Dashboard')
])

if __name__ == '__main__':
    app.run_server(host='0.0.0.0', port=8080)
```

## Troubleshooting

### App Won't Start

**Symptom**: App status shows error or won't start

**Solution**:
1. Check logs: `databricks apps logs <app-name> --profile my-workspace`
2. Verify app.yaml configuration
3. Check Python dependencies in requirements.txt
4. Ensure port 8080 is exposed in your application

### App Deployment Fails

**Symptom**: `databricks apps deploy` fails

**Solution**:
1. Validate source code path exists
2. Check app.yaml syntax
3. Verify you have permissions to create/update apps
4. Review error message for specific issues

### Can't Access App URL

**Symptom**: App deployed but URL not accessible

**Solution**:
1. Check app status: `databricks apps get <app-name> --profile my-workspace`
2. Verify app is running (not stopped)
3. Check network/firewall settings
4. Ensure you have permissions to access the app

## Best Practices

### 1. Use Asset Bundles

Manage apps through Asset Bundles for:
- Version control
- Environment management (dev/staging/prod)
- Reproducible deployments

### 2. Structure Your App

```
my-app/
├── databricks.yml      # Bundle configuration
├── resources/
│   └── app.yml        # App resource definition
├── src/
│   ├── app.py         # Application code
│   └── utils/         # Helper modules
├── tests/             # Unit tests
├── requirements.txt   # Dependencies
└── README.md          # Documentation
```

### 3. Environment-Specific Configuration

```yaml
# databricks.yml
targets:
  dev:
    resources:
      apps:
        my_app:
          name: my-app-dev

  prod:
    resources:
      apps:
        my_app:
          name: my-app-prod
```

### 4. Monitor App Health

Regularly check:
- App status
- Application logs
- Resource usage
- Error rates

### 5. Secure Your App

- Use Databricks Secrets for credentials
- Implement authentication/authorization
- Validate user inputs
- Keep dependencies updated

## Related Topics

- [Asset Bundles](asset-bundles.md) - Manage apps with Infrastructure-as-Code
- [Secrets](secrets.md) - Store credentials securely
- [Workspace](workspace.md) - Manage app files and notebooks
