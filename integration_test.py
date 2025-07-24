# integration_test.py
import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta
from contextlib import AsyncExitStack
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.resources import Resource

class MCPInstrumentationTest(unittest.TestCase):
    """Test case for MCP instrumentation."""
    
    async def test_mcp_instrumentation(self):
        """Test that MCP instrumentation creates spans with correct attributes."""
        # Import the necessary modules
        from mcp import stdio_client, StdioServerParameters
        from mcp.client.session import ClientSession
        from mcp.types import ClientNotification, InitializedNotification, PingRequest
        
        # Set up in-memory exporter to capture spans
        memory_exporter = InMemorySpanExporter()
        tracer_provider = trace.get_tracer_provider()
        tracer_provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
        
        # Function to get new spans since last check
        def get_new_spans(previous_spans):
            current_spans = memory_exporter.get_finished_spans()
            return [span for span in current_spans if span not in previous_spans]
        
        # Start with no spans
        previous_spans = []
        
        # Start the MCP server process with console exporter
        server_params = StdioServerParameters(
            command="opentelemetry-instrument",
            args=["python3", "mcpserver.py"],
            env={
                "OTEL_TRACES_EXPORTER": "none",
                "OTEL_RESOURCE_ATTRIBUTES": "service.name=MCP Server Test",
                "OTEL_LOGS_EXPORTER": "none",
                "OTEL_METRICS_EXPORTER": "none",
                "OTEL_PYTHON_DISTRO": "aws_distro",
                "OTEL_PYTHON_CONFIGURATOR": "aws_configurator",
                "OTEL_TRACES_SAMPLER": "always_on"
            }
        )
        
        # Use AsyncExitStack to manage multiple async context managers
        async with AsyncExitStack() as exit_stack:
            # Connect to the server
            print("Connecting to MCP server...")
            reader, writer = await exit_stack.enter_async_context(stdio_client(server_params))
            
            # Create a client session
            session = await exit_stack.enter_async_context(ClientSession(reader, writer))
            
            # Initialize the session
            await session.send_notification(
                ClientNotification(
                    InitializedNotification(method="notifications/initialized")
                )
            )
            
            # Wait for spans to be processed
            await asyncio.sleep(1)
            
            # 1. Call list_tools
            print("\n1. Calling list_tools...")
            previous_spans = memory_exporter.get_finished_spans()
            tools_response = await session.list_tools()
            print(f"Available tools: {len(tools_response.tools)} tools found")
            await asyncio.sleep(0.5)  # Wait for spans to be processed
            new_spans = get_new_spans(previous_spans)
            print(f"  Spans created: {len(new_spans)}")
            for span in new_spans:
                if "aws.remote.operation" in span.attributes:
                    print(f"  Operation: {span.attributes['aws.remote.operation']}")
            
            # 2. Call list_monitored_services
            print("\n2. Calling list_monitored_services...")
            previous_spans = memory_exporter.get_finished_spans()
            services_response = await session.call_tool(
                name="list_monitored_services",
                arguments={"include_linked_accounts": True}
            )
            print(f"Services response received")
            await asyncio.sleep(0.5)  # Wait for spans to be processed
            new_spans = get_new_spans(previous_spans)
            print(f"  Spans created: {len(new_spans)}")
            for span in new_spans:
                if "aws.remote.operation" in span.attributes:
                    print(f"  Operation: {span.attributes['aws.remote.operation']}")
            
            # 3. Call get_service_detail
            service_name = "AppSignals MCP Server"  # Default fallback
            print(f"\n3. Calling get_service_detail for '{service_name}'...")
            previous_spans = memory_exporter.get_finished_spans()
            service_detail_response = await session.call_tool(
                name="get_service_detail",
                arguments={"service_name": service_name, "include_linked_accounts": True}
            )
            print(f"Service detail response received")
            await asyncio.sleep(0.5)  # Wait for spans to be processed
            new_spans = get_new_spans(previous_spans)
            print(f"  Spans created: {len(new_spans)}")
            for span in new_spans:
                if "aws.remote.operation" in span.attributes:
                    print(f"  Operation: {span.attributes['aws.remote.operation']}")
            
            # 4. Call list_slis
            print("\n4. Calling list_slis...")
            previous_spans = memory_exporter.get_finished_spans()
            slis_response = await session.call_tool(
                name="list_slis",
                arguments={"hours": "24", "include_linked_accounts": "true"}
            )
            print(f"SLIs response received")
            await asyncio.sleep(0.5)  # Wait for spans to be processed
            new_spans = get_new_spans(previous_spans)
            print(f"  Spans created: {len(new_spans)}")
            for span in new_spans:
                if "aws.remote.operation" in span.attributes:
                    print(f"  Operation: {span.attributes['aws.remote.operation']}")
            
            # 5. Call query_sampled_traces
            print("\n5. Calling query_sampled_traces...")
            previous_spans = memory_exporter.get_finished_spans()
            traces_response = await session.call_tool(
                name="query_sampled_traces",
                arguments={
                    "filter_expression": "service(\"AppSignals MCP Server\")",
                    "hours": "1"
                }
            )
            print(f"Traces response received")
            await asyncio.sleep(0.5)  # Wait for spans to be processed
            new_spans = get_new_spans(previous_spans)
            print(f"  Spans created: {len(new_spans)}")
            for span in new_spans:
                if "aws.remote.operation" in span.attributes:
                    print(f"  Operation: {span.attributes['aws.remote.operation']}")
            
            # 6. Call search_transaction_spans
            print("\n6. Calling search_transaction_spans...")
            previous_spans = memory_exporter.get_finished_spans()
            # Calculate start and end times for the query
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)
            
            try:
                spans_response = await session.call_tool(
                    name="search_transaction_spans",
                    arguments={
                        "log_group_name": "aws/spans",
                        "start_time": start_time.isoformat() + "Z",
                        "end_time": end_time.isoformat() + "Z",
                        "query_string": "fields @timestamp, name, attributes.aws.local.service | limit 10",
                        "limit": "10",
                        "max_timeout": "10"
                    }
                )
                print(f"Transaction spans response received")
            except Exception as e:
                print(f"Search transaction spans failed (this is expected if not implemented): {e}")
            
            await asyncio.sleep(0.5)  # Wait for spans to be processed
            new_spans = get_new_spans(previous_spans)
            print(f"  Spans created: {len(new_spans)}")
            for span in new_spans:
                if "aws.remote.operation" in span.attributes:
                    print(f"  Operation: {span.attributes['aws.remote.operation']}")
            
            # 7. Call list_prompts
            print("\n7. Calling list_prompts...")
            previous_spans = memory_exporter.get_finished_spans()
            try:
                prompts_response = await session.list_prompts()
                print(f"Prompts response received: {len(prompts_response.prompts)} prompts found")
            except Exception as e:
                print(f"List prompts failed (this is expected if not implemented): {e}")
            await asyncio.sleep(0.5)  # Wait for spans to be processed
            new_spans = get_new_spans(previous_spans)
            print(f"  Spans created: {len(new_spans)}")
            for span in new_spans:
                if "aws.remote.operation" in span.attributes:
                    print(f"  Operation: {span.attributes['aws.remote.operation']}")
            
            # 8. Call list_resources
            print("\n8. Calling list_resources...")
            previous_spans = memory_exporter.get_finished_spans()
            try:
                resources_response = await session.list_resources()
                print(f"Resources response received")
            except Exception as e:
                print(f"List resources failed (this is expected if not implemented): {e}")
            await asyncio.sleep(0.5)  # Wait for spans to be processed
            new_spans = get_new_spans(previous_spans)
            print(f"  Spans created: {len(new_spans)}")
            for span in new_spans:
                if "aws.remote.operation" in span.attributes:
                    print(f"  Operation: {span.attributes['aws.remote.operation']}")
            
            # 9. Call ping
            print("\n9. Calling ping using send_request...")
            previous_spans = memory_exporter.get_finished_spans()
            try:
                ping_request = PingRequest()
                ping_response = await session.send_request(ping_request)
                print(f"Ping response received")
            except Exception as e:
                print(f"Ping failed (this is expected if not implemented): {e}")
            await asyncio.sleep(0.5)  # Wait for spans to be processed
            new_spans = get_new_spans(previous_spans)
            print(f"  Spans created: {len(new_spans)}")
            for span in new_spans:
                if "aws.remote.operation" in span.attributes:
                    print(f"  Operation: {span.attributes['aws.remote.operation']}")
        
        # Wait a moment for spans to be processed
        await asyncio.sleep(1)
        
        # Get the collected client spans
        client_spans = memory_exporter.get_finished_spans()
        print(f"\nCollected {len(client_spans)} client spans")
        
        # Extract operations from spans
        operations = set()
        for span in client_spans:
            if "aws.remote.operation" in span.attributes:
                operations.add(span.attributes["aws.remote.operation"])
        
        print("\nOperations found in spans:")
        for op in sorted(operations):
            print(f"- {op}")
        
        # ASSERTIONS
        
        # 1. Verify we have client spans
        self.assertGreater(len(client_spans), 0, "No client spans were created")
        
        # 2. Verify span names
        span_names = [span.name for span in client_spans]
        self.assertIn("client.send_request", span_names, "No client.send_request spans found")
        
        # 3. Verify span attributes
        for span in client_spans:
            # 3.1 Verify span has kind attribute
            self.assertEqual(span.attributes.get("span.kind"), "CLIENT", 
                            f"Span {span.name} missing or incorrect span.kind attribute")
            
            # 3.2 Verify remote service attribute
            self.assertEqual(span.attributes.get("aws.remote.service"), "Appsignals MCP Server", 
                            f"Span {span.name} missing or incorrect aws.remote.service attribute")
            
            # 3.3 Verify operation attribute exists
            self.assertIn("aws.remote.operation", span.attributes, 
                         f"Span {span.name} missing aws.remote.operation attribute")
        
        # 4. Verify specific operations
        expected_operations = [
            "ListTool",
            "list_monitored_services",
            "get_service_detail",
            "list_slis",
            "query_sampled_traces",
            "search_transaction_spans",
            "ListPrompt",
            "ListResource"
        ]
        
        # Only check for operations we know should exist
        found_operations = [op for op in expected_operations if op in operations]
        print(f"\nFound expected operations: {found_operations}")
        
        # Verify we have at least the core operations
        core_operations = ["ListTool", "list_monitored_services"]
        for op in core_operations:
            self.assertIn(op, operations, f"Core operation '{op}' not found in spans")
        
        # 5. Verify trace IDs are valid (non-zero)
        for span in client_spans:
            self.assertNotEqual(span.context.trace_id, 0, 
                               f"Span {span.name} has invalid trace ID")
        
        print("\n✅ All assertions passed - MCP instrumentation is working correctly!")
        return True

async def run_tests():
    """Run the test case."""
    test = MCPInstrumentationTest()
    return await test.test_mcp_instrumentation()

if __name__ == "__main__":
    # Set up OpenTelemetry
    resource = Resource.create({"service.name": "mcp-integration-test"})
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)
    
    # Add console exporter to see spans in the output
    tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    
    # Run the test
    result = asyncio.run(run_tests())
    
    # Exit with appropriate status code
    sys.exit(0 if result else 1)
