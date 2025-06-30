import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all modules first
import asyncio
import logging
from contextlib import AsyncExitStack
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Set up logging first so we can debug the instrumentation
from src.mcpinstrumentor import setup_ctx_logger
ctx_logger = setup_ctx_logger()

# Set up OpenTelemetry tracing with service name
# resource = Resource.create({"service.name": "mcp-client"})
tracer_provider = TracerProvider(sampler=ALWAYS_ON)

otlp_exporter = OTLPSpanExporter(
    endpoint = "localhost:4317",
    insecure = True,  # Use insecure connection for local testing
)

tracer_provider.add_span_processor(
    BatchSpanProcessor(otlp_exporter)
)
trace.set_tracer_provider(tracer_provider)
from src.mcpinstrumentor import MCPInstrumentor
instrumentor = MCPInstrumentor()
instrumentor.instrument(tracer_provider=tracer_provider)

from mcp import StdioServerParameters
from mcp.client.session import ClientSession


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
                # **os.environ,
                # "MCP_TRANSPORT": "stdio",
                # "OTEL_TRACES_EXPORTER": "console",
                # "OTEL_LOG_LEVEL": "debug",
                # "OTEL_SERVICE_NAME": "mcp-server",
            }
        )
        reader, writer = await exit_stack.enter_async_context(stdio_client(server_params))
        session = await exit_stack.enter_async_context(ClientSession(reader, writer))
        await session.send_notification(
            ClientNotification(
                InitializedNotification(method="notifications/initialized")
            )
        )
        response = await session.call_tool(
            name="list_application_signals_services",
            arguments={}
        )
        ctx_logger.info(f"Response: {response}")
        # Print tool result
        print("\nTool execution result:")
        if hasattr(response, 'content') and response.content:
            for item in response.content:
                if hasattr(item, 'type') and item.type == 'text':
                    if hasattr(item, 'text'):
                        print(item.text)
        else:
            print("No content found in response")
        
        # Force flush to ensure all spans are exported
        tracer_provider.force_flush()
    
if __name__ == "__main__":
    asyncio.run(main())
