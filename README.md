# AWS Application Signals MCP Server

MCP server for monitoring AWS Application Signals services with OpenTelemetry instrumentation.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

Run the MCP server:
```bash
python mcpserver.py
```

## Tools

- `list_application_signals_services` - List all monitored services
- `get_service_details` - Get detailed service information
- `get_service_metrics` - Retrieve CloudWatch metrics for services
- `get_service_level_objective` - Get detailed SLO configuration and thresholds
- `run_transaction_search` - Execute CloudWatch Logs Insights queries on spans data
- `get_sli_status` - Check SLI status and SLO compliance across all services
- `query_xray_traces` - Query AWS X-Ray traces for error investigation

## Configuration

Ensure AWS credentials are configured via:
- AWS CLI (`aws configure`)
- Environment variables
- IAM roles

Required AWS permissions:
- `application-signals:ListServices`
- `application-signals:GetService`
- `cloudwatch:GetMetricStatistics`
- `logs:DescribeLogGroups`