# Networking and Security Migration Guide

Guide for migrating networking and security configurations from classic compute to serverless compute.

## Overview

Serverless compute uses a Databricks-managed VPC/VNet, so classic networking patterns like VPC peering and instance profiles do not apply. The key changes:

| Classic Pattern | Serverless Replacement |
|----------------|----------------------|
| VPC peering | Network Connectivity Configurations (NCCs) |
| Instance profiles (AWS) | UC storage credentials + external locations |
| Private Link (existing) | Serverless Private Link endpoints |
| Security groups / NSGs | Firewall rules using NCC stable IPs |
| Direct S3/ADLS credentials | UC external locations |

## VPC Peering to NCCs

### Why the Change

Classic compute runs in a customer-managed or Databricks-managed VPC that can be peered with other VPCs for private connectivity. Serverless compute runs in a shared Databricks-managed network, so VPC peering is not available. Instead, use **Network Connectivity Configurations (NCCs)** to establish private network paths.

### Migration Steps

#### Step 1: Identify Resources Requiring Private Connectivity

List all resources your classic clusters connect to via VPC peering:
- Databases (RDS, Aurora, Azure SQL, etc.)
- Message brokers (Kafka, Event Hubs, etc.)
- Storage accounts with firewall rules
- Internal APIs and services

#### Step 2: Create a Network Connectivity Configuration

```bash
# AWS: Create NCC using Databricks CLI
databricks account network-connectivity create \
  --name "production-ncc" \
  --region "us-east-1"

# Get the NCC details including stable NAT IPs
databricks account network-connectivity get <NCC_ID>
```

```bash
# Azure: Create NCC
databricks account network-connectivity create \
  --name "production-ncc" \
  --region "eastus"
```

#### Step 3: Attach NCC to Workspace

```bash
databricks account workspaces update <WORKSPACE_ID> \
  --network-connectivity-config-id <NCC_ID>
```

#### Step 4: Get Stable IPs and Update Firewall Rules

Each NCC provides stable NAT IP addresses. Add these to your resource firewalls:

```bash
# Get the stable IPs from the NCC configuration
databricks account network-connectivity get <NCC_ID> \
  --output json | jq '.egress_config.default_rules.stable_ip_addresses'
```

Then allowlist these IPs on your target resources:
- **AWS RDS**: Add IPs to the RDS security group inbound rules
- **Azure SQL**: Add IPs to the Azure SQL firewall rules
- **Kafka brokers**: Add IPs to the broker security group or ACL
- **On-premises resources**: Add IPs to your firewall/VPN gateway ACLs

### NCC Limits

- Maximum 10 NCCs per region per account
- Each NCC provides a fixed set of stable NAT IPs
- S3 same-region access uses gateway endpoints (no NCC needed for same-region S3)

## Private Link Setup

For enhanced security, configure Private Link endpoints for serverless compute.

### AWS Private Link

1. **Create a VPC endpoint** in your VPC targeting the Databricks serverless service
2. **Create a Private Link rule** in your NCC:

```bash
# Create a private endpoint rule for your resource
databricks account network-connectivity create-private-endpoint-rule \
  --network-connectivity-config-id <NCC_ID> \
  --resource-id "<aws-resource-arn>" \
  --group-id "<service-endpoint-group>"
```

3. **Approve the endpoint** on the resource side (e.g., approve in the RDS/S3 console)

### Azure Private Link

1. **Create a private endpoint rule** in your NCC:

```bash
databricks account network-connectivity create-private-endpoint-rule \
  --network-connectivity-config-id <NCC_ID> \
  --resource-id "<azure-resource-id>" \
  --group-id "<sub-resource-type>"
```

2. **Approve the private endpoint** in the Azure portal on the target resource

### Supported Private Link Targets

| Cloud | Service | Group ID |
|-------|---------|----------|
| AWS | S3 | `s3` |
| AWS | RDS (MySQL) | `rds` |
| AWS | RDS (PostgreSQL) | `rds` |
| AWS | Glue | `glue` |
| Azure | Azure SQL | `sqlServer` |
| Azure | Azure Storage (Blob) | `blob` |
| Azure | Azure Storage (DFS) | `dfs` |
| Azure | Azure Cosmos DB | `sql` |
| Azure | Azure Event Hubs | `namespace` |

## Stable IPs and Firewall Rules

### Pattern: Database Firewall

```
# Classic approach:
# VPC peering allows all traffic from the customer VPC CIDR

# Serverless approach:
# Allowlist the NCC's stable NAT IPs on the database firewall
# Example for PostgreSQL (pg_hba.conf or cloud firewall):
#   host  all  all  <stable-ip-1>/32  md5
#   host  all  all  <stable-ip-2>/32  md5
```

### Pattern: Storage Account Firewall (Azure)

```
# Classic approach:
# VNet service endpoint or VNet rule on storage account

# Serverless approach:
# Option 1: Private Link (recommended for production)
# Option 2: Add NCC stable IPs to storage account firewall
#   az storage account network-rule add --account-name <name> --ip-address <stable-ip>
```

### Pattern: Same-Region Cloud Storage

For same-region cloud storage access:
- **AWS S3**: Uses VPC gateway endpoints automatically. No firewall changes needed for same-region S3 access from serverless.
- **Azure Storage**: Use Private Link for best security, or add NCC IPs to storage firewall.

## S3 and ADLS Access via UC External Locations

### Replacing IAM Instance Profiles (AWS)

Classic compute uses IAM instance profiles attached to the cluster for S3 access. Serverless compute uses Unity Catalog (UC) external locations with storage credentials.

#### Step 1: Create a Storage Credential

```sql
-- Create an IAM role-based storage credential
CREATE STORAGE CREDENTIAL my_s3_credential
WITH (
  AWS_IAM_ROLE = 'arn:aws:iam::123456789012:role/databricks-storage-role'
);
```

The IAM role must trust the Databricks account's IAM role. See the [UC documentation](https://docs.databricks.com/en/connect/unity-catalog/storage-credentials.html) for the trust policy.

#### Step 2: Create an External Location

```sql
CREATE EXTERNAL LOCATION my_data_location
URL 's3://my-bucket/data/'
WITH (STORAGE CREDENTIAL my_s3_credential);
```

#### Step 3: Create Volumes (for File Access)

```sql
-- External volume pointing to existing S3 data
CREATE EXTERNAL VOLUME main.data.raw_files
LOCATION 's3://my-bucket/data/raw/';

-- Managed volume (Databricks manages the storage)
CREATE VOLUME main.data.scratch;
```

#### Step 4: Update Code

```python
# BEFORE (instance profile):
df = spark.read.parquet("s3://my-bucket/data/raw/events/")

# AFTER (UC external location — no credentials needed in code):
df = spark.read.parquet("/Volumes/main/data/raw_files/events/")
# Or with external location directly:
df = spark.read.parquet("s3://my-bucket/data/raw/events/")
# (Works if external location is configured — UC handles auth)
```

### Replacing Azure Service Principals / Managed Identity

```sql
-- Create storage credential with Azure managed identity or service principal
CREATE STORAGE CREDENTIAL my_adls_credential
WITH (
  AZURE_MANAGED_IDENTITY = '<managed-identity-id>'
);

-- Create external location
CREATE EXTERNAL LOCATION my_adls_location
URL 'abfss://container@account.dfs.core.windows.net/path/'
WITH (STORAGE CREDENTIAL my_adls_credential);

-- Create external volume
CREATE EXTERNAL VOLUME main.data.adls_files
LOCATION 'abfss://container@account.dfs.core.windows.net/path/';
```

## Replacing Hadoop Configuration Credentials

Classic patterns that set credentials via Hadoop configuration are not supported:

```python
# BEFORE (classic — not supported on serverless):
sc.hadoopConfiguration.set("fs.s3a.access.key", "AKIAEXAMPLE")
sc.hadoopConfiguration.set("fs.s3a.secret.key", secret)
df = spark.read.parquet("s3a://bucket/path/")

# AFTER (serverless — UC handles authentication):
# 1. Create storage credential + external location (SQL, one-time setup)
# 2. Read directly — no credential config needed:
df = spark.read.parquet("s3://bucket/path/")
# Or via Volumes:
df = spark.read.parquet("/Volumes/main/schema/volume/path/")
```

## Network Configuration Checklist

Use this checklist when planning a serverless networking migration:

- [ ] Inventory all VPC peering connections and their target resources
- [ ] Create NCCs in each required region
- [ ] Attach NCCs to target workspaces
- [ ] Retrieve stable NAT IPs from each NCC
- [ ] Update firewall rules on all target resources with stable IPs
- [ ] Create Private Link rules for sensitive resources (databases, storage)
- [ ] Approve Private Link endpoints on the resource side
- [ ] Create UC storage credentials to replace instance profiles
- [ ] Create UC external locations for all data paths
- [ ] Create Volumes for file-based access patterns
- [ ] Test connectivity from serverless compute to each resource
- [ ] Remove old VPC peering connections after validation

## Documentation

- Serverless networking: https://docs.databricks.com/en/security/network/serverless-network-security/
- Network Connectivity Configurations: https://docs.databricks.com/en/security/network/serverless-network-security/serverless-firewall
- Private Link (AWS): https://docs.databricks.com/en/security/network/serverless-network-security/serverless-private-link
- Private Link (Azure): https://docs.databricks.com/en/security/network/serverless-network-security/serverless-private-link-azure
- UC storage credentials: https://docs.databricks.com/en/connect/unity-catalog/storage-credentials.html
- UC external locations: https://docs.databricks.com/en/connect/unity-catalog/external-locations.html
