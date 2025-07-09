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
from amazon.opentelemetry.distro.otlp_aws_span_exporter import OTLPAwsSpanExporter

# Set up logging first so we can debug the instrumentation
# from src.mcpinstrumentor import setup_ctx_logger
# ctx_logger = setup_ctx_logger()

# Set up OpenTelemetry tracing with service name
# resource = Resource.create({"service.name": "mcp-client"})
resource = Resource.create({
    "service.name": "Client Agent",
    "service.version": "1.0.0"
})
tracer_provider = TracerProvider(sampler=ALWAYS_ON,resource=resource)

otlp_exporter = OTLPAwsSpanExporter(
    endpoint = "https://xray.us-east-1.amazonaws.com/v1/traces",
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
from unittest.mock import Mock, patch
from datetime import datetime

async def main():
    async with AsyncExitStack() as exit_stack:
        server_params = StdioServerParameters(
            command="python",
            args=["mcpserver.py"],
        )
        reader, writer = await exit_stack.enter_async_context(stdio_client(server_params))
        session = await exit_stack.enter_async_context(ClientSession(reader, writer))    
        await session.send_notification(
            ClientNotification(
                InitializedNotification(method="notifications/initialized")
            )
        )
        # await session.initialize()
        response = await session.call_tool(
            name="list_application_signals_services",
            arguments={}
        )
        # print("\nTool execution result:")
        # if hasattr(response, 'content') and response.content:
        #     for item in response.content:
        #         if hasattr(item, 'type') and item.type == 'text':
        #             if hasattr(item, 'text'):
        #                 print(item.text)
        # else:
        #     print("No content found in response")

        responsetwo = await session.list_tools()
        # print("Available Tools:")
        # print("=" * 50)
        # for i, tool in enumerate(responsetwo.tools, 1):
        #     print(f"{i}. {tool.name}")
        #     print(f"   Description: {tool.description[:100]}...")
        #     if tool.inputSchema and 'properties' in tool.inputSchema:
        #         required = tool.inputSchema.get('required', [])
        #         props = list(tool.inputSchema['properties'].keys())
        #         print(f"   Parameters: {', '.join(props)}")
        #         if required:
        #             print(f"   Required: {', '.join(required)}")
        #     print()
        # responsethree = await session.list_resources()
    
if __name__ == "__main__":
    asyncio.run(main())