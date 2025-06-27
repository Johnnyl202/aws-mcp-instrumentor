# AWS OpenTelemetry Setup

## Installation

Install the AWS Distro for OpenTelemetry Python auto-instrumentation agent:

```bash
pip install aws-opentelemetry-distro
```

## Environment Variables

Set the following environment variables before starting your application:

### Required Variables

```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="https://xray.[AWSRegion].amazonaws.com/v1/traces"
```

Example for us-west-2:
```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT="https://xray.us-west-2.amazonaws.com/v1/traces"
```

### Recommended Variables

```bash
export OTEL_METRICS_EXPORTER=none
export OTEL_LOGS_EXPORTER=none
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

### Optional Variables

```bash
export OTEL_RESOURCE_ATTRIBUTES="service.name=YourServiceName,deployment.environment=YourEnvironment"
```

- `service.name`: Sets the service name (default: UnknownService)
- `deployment.environment`: Sets the deployment environment (defaults based on hosting type)

## Running Your Application

Start your application with OpenTelemetry instrumentation:

```bash
OTEL_METRICS_EXPORTER=none \
OTEL_LOGS_EXPORTER=none \
OTEL_PYTHON_DISTRO=aws_distro \
OTEL_PYTHON_CONFIGURATOR=aws_configurator \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.us-east-1.amazonaws.com/v1/traces \
OTEL_RESOURCE_ATTRIBUTES="service.name=$SVC_NAME" \
opentelemetry-instrument python $MY_PYTHON_APP.py
```

Replace `$SVC_NAME` with your application name and `$MY_PYTHON_APP.py` with your Python application file.

## Viewing Traces

Traces are stored in the `aws/spans` CloudWatch Logs LogGroup and can be viewed in the CloudWatch Traces and Metrics Console.