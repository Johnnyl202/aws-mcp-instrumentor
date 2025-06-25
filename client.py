import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all modules first
import asyncio
from contextlib import AsyncExitStack
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from amazon.opentelemetry.distro.otlp_aws_span_exporter import OTLPAwsSpanExporter
from src.mcpinstrumentor import MCPInstrumentor

# Set up OpenTelemetry tracing with AWS X-Ray exporter
tracer_provider = TracerProvider(sampler=ALWAYS_ON)
tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPAwsSpanExporter(endpoint="https://xray.us-east-1.amazonaws.com/v1/traces"))
)
trace.set_tracer_provider(tracer_provider)

# Instrument MCP with the same tracer provider
MCPInstrumentor().instrument(tracer_provider=tracer_provider)
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import (
    ClientRequest,
    ClientNotification,
    ClientResult,
    InitializedNotification,
    ListToolsRequest,
    ListToolsResult,
    CallToolRequest
)
from opentelemetry.context import Context


async def main():
    # OpenTelemetry tracer is already set up at the module level
    tracer = trace.get_tracer("mcp.client")
    # Connect to the server and manage session
    async with AsyncExitStack() as exit_stack:
        server_params = StdioServerParameters(
            command="python",
            args=["mcpserver.py"],
            env={
                **os.environ,
                "MCP_TRANSPORT": "stdio",
                "OTEL_TRACES_EXPORTER": "console",
                "OTEL_LOG_LEVEL": "debug"
            }
        )
        reader, writer = await exit_stack.enter_async_context(stdio_client(server_params))
        with tracer.start_as_current_span("client.session", kind=trace.SpanKind.CLIENT) as span:
            span.set_attribute("tool_name", "list_application_signals_services")

            session = await exit_stack.enter_async_context(ClientSession(reader, writer))

            await session.send_notification(
                ClientNotification(
                    InitializedNotification(method="notifications/initialized")
                )
            )

            ctx = span.get_span_context()

            response = await session.send_request(
                ClientRequest(
                    root=CallToolRequest(
                        method="tools/call",
                        params={
                            "name": "list_application_signals_services",
                            "arguments": {
                                "_meta": {
                                    "trace_id": ctx.trace_id,
                                    "span_id": ctx.span_id,
                                }
                            }
                        }
                   )
                ),
                ClientResult,
            )
            span.add_event("Received tool call response")
            print(f"Span type: {type(span).__name__}")
            print(f"Span recording: {span.is_recording()}")
            print(f"Span context: {span.get_span_context()}")
        # Print tool result
        print("\nTool execution result:")
        if hasattr(response.root, 'content') and response.root.content:
            for item in response.root.content:
                if item.get('type') == 'text':
                    print(item.get('text', ''))
        else:
            print("No content found in response")
        
        # Force flush to ensure all spans are exported
        tracer_provider.force_flush()
    
if __name__ == "__main__":
    asyncio.run(main())
