# Model Serving

Databricks Model Serving provides real-time inference for ML models with auto-scaling, monitoring, and version management.

## Serving Endpoints

### List and Get Endpoints

```bash
# List all serving endpoints
databricks serving-endpoints list --profile my-workspace

# Get endpoint details
databricks serving-endpoints get --name <endpoint-name> --profile my-workspace

# Get endpoint status
databricks serving-endpoints get-status --name <endpoint-name> --profile my-workspace
```

### Create Serving Endpoint

```bash
# Create endpoint from JSON config
databricks serving-endpoints create \
  --name <endpoint-name> \
  --json @endpoint-config.json \
  --profile my-workspace
```

**endpoint-config.json**:
```json
{
  "name": "customer-churn-model",
  "config": {
    "served_entities": [{
      "entity_name": "my_catalog.my_schema.customer_churn_model",
      "entity_version": "1",
      "workload_size": "Small",
      "scale_to_zero_enabled": true
    }]
  }
}
```

### Update Serving Endpoint

```bash
# Update endpoint configuration
databricks serving-endpoints update-config \
  --name <endpoint-name> \
  --json @updated-config.json \
  --profile my-workspace
```

### Delete Serving Endpoint

```bash
# Delete endpoint
databricks serving-endpoints delete --name <endpoint-name> --profile my-workspace
```

## Workload Sizes

Available workload sizes for serving endpoints:

- **Small**: 4 CPU cores, 16 GB RAM
- **Medium**: 8 CPU cores, 32 GB RAM
- **Large**: 16 CPU cores, 64 GB RAM

Choose based on:
- Model size
- Inference complexity
- Expected traffic
- Latency requirements

## Querying Endpoints

### Query with JSON Input

```bash
# Query endpoint
databricks serving-endpoints query \
  --name <endpoint-name> \
  --json @input-data.json \
  --profile my-workspace
```

**input-data.json**:
```json
{
  "inputs": [
    {"feature1": 1.0, "feature2": 2.0, "feature3": "value"},
    {"feature1": 1.5, "feature2": 2.5, "feature3": "value"}
  ]
}
```

### Query with Inline JSON

```bash
databricks serving-endpoints query \
  --name my-model \
  --json '{"inputs": [{"feature1": 1.0}]}' \
  --profile my-workspace
```

## Monitoring Endpoints

### Get Logs

```bash
# Get endpoint logs
databricks serving-endpoints logs --name <endpoint-name> --profile my-workspace
```

### Get Metrics

```bash
# Get endpoint metrics
databricks serving-endpoints get-metrics --name <endpoint-name> --profile my-workspace
```

## Model Serving Workflow

### 1. Register Model in Unity Catalog

First, register your model in Unity Catalog (typically done via MLflow or the UI).

### 2. Create Endpoint Configuration

```json
{
  "name": "my-model-endpoint",
  "config": {
    "served_entities": [{
      "entity_name": "my_catalog.my_schema.my_model",
      "entity_version": "1",
      "workload_size": "Small",
      "scale_to_zero_enabled": true
    }]
  }
}
```

Configuration options:
- **entity_name**: Full UC path to model (`catalog.schema.model_name`)
- **entity_version**: Model version number
- **workload_size**: Small, Medium, or Large
- **scale_to_zero_enabled**: Auto-shutdown when idle (saves costs)

### 3. Create the Endpoint

```bash
databricks serving-endpoints create \
  --json @endpoint-config.json \
  --profile my-workspace
```

### 4. Wait for Endpoint to be Ready

The endpoint takes a few minutes to deploy. Check status:

```bash
databricks serving-endpoints get --name my-model-endpoint --profile my-workspace
```

Look for `state: "READY"` in the output.

### 5. Query the Endpoint

```bash
databricks serving-endpoints query \
  --name my-model-endpoint \
  --json '{"inputs": [{"feature1": 1.0, "feature2": 2.0}]}' \
  --profile my-workspace
```

### 6. Monitor Performance

```bash
# Check logs
databricks serving-endpoints logs --name my-model-endpoint --profile my-workspace

# Check metrics
databricks serving-endpoints get-metrics --name my-model-endpoint --profile my-workspace
```

## Multi-Model Serving

Serve multiple model versions or models in a single endpoint.

### A/B Testing Configuration

```json
{
  "name": "ab-test-endpoint",
  "config": {
    "served_entities": [
      {
        "entity_name": "my_catalog.my_schema.model_v1",
        "entity_version": "1",
        "workload_size": "Small",
        "scale_to_zero_enabled": false
      },
      {
        "entity_name": "my_catalog.my_schema.model_v2",
        "entity_version": "2",
        "workload_size": "Small",
        "scale_to_zero_enabled": false
      }
    ],
    "traffic_config": {
      "routes": [
        {
          "served_model_name": "model_v1-1",
          "traffic_percentage": 80
        },
        {
          "served_model_name": "model_v2-2",
          "traffic_percentage": 20
        }
      ]
    }
  }
}
```

## External Models (AI Gateway)

Databricks can serve external models (OpenAI, Anthropic, etc.) through AI Gateway.

### List External Models

```bash
databricks serving-endpoints list-external-models --profile my-workspace
```

### Create External Model Endpoint

```json
{
  "name": "openai-gpt4",
  "config": {
    "served_entities": [{
      "external_model": {
        "name": "gpt-4",
        "provider": "openai",
        "openai_config": {
          "openai_api_key": "{{secrets/my-scope/openai-key}}"
        }
      }
    }]
  }
}
```

```bash
databricks serving-endpoints create \
  --json @external-model-config.json \
  --profile my-workspace
```

### Supported External Providers

- OpenAI (GPT-3.5, GPT-4, etc.)
- Anthropic (Claude)
- Cohere
- AI21 Labs
- Azure OpenAI

## Endpoint Configuration Examples

### Basic Endpoint

```json
{
  "name": "simple-model",
  "config": {
    "served_entities": [{
      "entity_name": "main.default.my_model",
      "entity_version": "1",
      "workload_size": "Small",
      "scale_to_zero_enabled": true
    }]
  }
}
```

### Production Endpoint (No Auto-Scale Down)

```json
{
  "name": "prod-model",
  "config": {
    "served_entities": [{
      "entity_name": "prod_catalog.models.customer_model",
      "entity_version": "3",
      "workload_size": "Large",
      "scale_to_zero_enabled": false
    }]
  }
}
```

### GPU-Enabled Endpoint

```json
{
  "name": "gpu-model",
  "config": {
    "served_entities": [{
      "entity_name": "main.models.llm_model",
      "entity_version": "1",
      "workload_size": "Large",
      "workload_type": "GPU_LARGE",
      "scale_to_zero_enabled": false
    }]
  }
}
```

## Best Practices

### 1. Use Unity Catalog for Models

Always register models in Unity Catalog:
- Centralized model registry
- Version control
- Access control
- Audit logging

### 2. Enable Scale-to-Zero for Dev/Testing

```json
{
  "scale_to_zero_enabled": true  // For dev/test
}
```

Disable for production:
```json
{
  "scale_to_zero_enabled": false  // For prod (faster response)
}
```

### 3. Choose Appropriate Workload Size

Start small and scale up based on:
- Actual traffic patterns
- Latency requirements
- Model complexity

### 4. Monitor Performance

Regularly check:
- Latency metrics
- Error rates
- Traffic patterns
- Resource utilization

### 5. Use A/B Testing for Model Updates

Deploy new versions alongside existing ones:
```json
{
  "traffic_config": {
    "routes": [
      {"served_model_name": "old-model", "traffic_percentage": 90},
      {"served_model_name": "new-model", "traffic_percentage": 10}
    ]
  }
}
```

### 6. Secure API Keys with Secrets

Never hardcode API keys:
```json
{
  "openai_api_key": "{{secrets/my-scope/openai-key}}"  // ✅ Good
}
```

### 7. Use Descriptive Endpoint Names

```bash
# ✅ Good: Descriptive names
customer-churn-model-v2
fraud-detection-prod
recommendation-engine-staging

# ❌ Avoid: Generic names
model1
test
endpoint
```

## Troubleshooting

### Endpoint Creation Fails

**Symptom**: `databricks serving-endpoints create` fails

**Solution**:
1. Validate JSON configuration
2. Verify model exists in Unity Catalog
3. Check model version is correct
4. Ensure you have permissions to create endpoints
5. Check workspace capacity

### Endpoint Not Ready

**Symptom**: Endpoint stuck in "NOT_READY" state

**Solution**:
1. Check logs: `databricks serving-endpoints logs --name <name>`
2. Verify model can be loaded
3. Check model dependencies are met
4. Ensure sufficient workspace resources
5. Try recreating the endpoint

### Query Returns Error

**Symptom**: Endpoint query fails or returns error

**Solution**:
1. Verify endpoint is in "READY" state
2. Check input data format matches model expectations
3. Review endpoint logs for errors
4. Validate JSON syntax in query
5. Check model input schema

### High Latency

**Symptom**: Slow query responses

**Solution**:
1. Disable scale-to-zero for production endpoints
2. Increase workload size
3. Check model inference time
4. Optimize model if possible
5. Consider using GPU for large models

### Scale-to-Zero Not Working

**Symptom**: Endpoint doesn't scale down when idle

**Solution**:
1. Verify `scale_to_zero_enabled: true` in config
2. Wait for idle timeout period (typically 15 minutes)
3. Check if endpoint is receiving traffic
4. Review endpoint configuration

## Related Topics

- [Unity Catalog](unity-catalog.md) - Register models in UC
- [Secrets](secrets.md) - Store API keys securely
- [Jobs](jobs.md) - Schedule model retraining jobs
- [Workflows](workflows.md) - Complete ML deployment workflows
