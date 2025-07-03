import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.mcpinstrumentor import MCPInstrumentor
MCPInstrumentor().instrument()
import asyncio
import os
from contextlib import AsyncExitStack
from opentelemetry import trace
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
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

async def main():
    # Set up OpenTelemetry tracer
    console_exporter = ConsoleSpanExporter()
    tracer_provider = trace_sdk.TracerProvider(sampler=trace_sdk.sampling.ALWAYS_ON)
    tracer_provider.add_span_processor(SimpleSpanProcessor(console_exporter))
    trace.set_tracer_provider(tracer_provider)
    tracer = trace.get_tracer("testclient")

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

        # Open a client span to cover the whole session
        with tracer.start_as_current_span("client.session", kind=trace.SpanKind.CLIENT) as span:
            span.set_attribute("client_side", True)
            span.set_attribute("tool_name", "list_application_signals_services")

            session = await exit_stack.enter_async_context(ClientSession(reader, writer))

            await session.send_notification(
                ClientNotification(
                    InitializedNotification(method="notifications/initialized")
                )
            )

            # List tools
            tools_result = await session.send_request(
                ClientRequest(
                    root=ListToolsRequest(method="tools/list")
                ),
                ListToolsResult,
            )
            print("Tools available:", [tool.name for tool in tools_result.tools])

            # Call the tool while span is active
            span.add_event("Sending tool call request")
            response = await session.send_request(
                ClientRequest(
                    root=CallToolRequest(
                        method="tools/call",
                        params={
                            "name": "list_application_signals_services",
                            "arguments": {}
                        }
                   )
                ),
                ClientResult,
            )
            span.add_event("Received tool call response")

    # Print tool result
    print("\nTool execution result:")
    if hasattr(response.root, 'content') and response.root.content:
        for item in response.root.content:
            if item.get('type') == 'text':
                print(item.get('text', ''))
    else:
        print("No content found in response")

if __name__ == "__main__":
    asyncio.run(main())
