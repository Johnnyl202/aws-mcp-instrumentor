import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging

# Set up logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create file handler
file_handler = logging.FileHandler("test_wrapper.log", mode='w')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

async def main():
    logger.info("Starting test client wrapper")
    
    # Import the client session class
    from mcp.client.session import ClientSession
    logger.info(f"Imported ClientSession from {ClientSession.__module__}")
    
    # Check if call_tool exists
    if not hasattr(ClientSession, 'call_tool'):
        logger.error("ClientSession.call_tool does not exist!")
        return
        
    logger.info("ClientSession.call_tool exists")
    
    # Store the original method before patching
    original_call_tool = ClientSession.call_tool
    
    # Define our wrapper function
    async def call_tool_wrapper(self, name, arguments=None, read_timeout_seconds=None, progress_callback=None):
        logger.info("========== WRAPPER CALLED ==========")
        logger.info(f"Name: {name}")
        logger.info(f"Arguments: {arguments}")
        
        # Add metadata
        if arguments is None:
            args_copy = {}
        else:
            args_copy = arguments.copy() if isinstance(arguments, dict) else arguments
        
        if isinstance(args_copy, dict):
            args_copy["_meta"] = {
                "trace_id": 12345,
                "span_id": 67890
            }
            logger.info(f"Added _meta: {args_copy['_meta']}")
        
        # Call original
        result = await original_call_tool(self, name, args_copy, read_timeout_seconds, progress_callback)
        return result
    
    # Patch the method
    import types
    ClientSession.call_tool = call_tool_wrapper
    logger.info("Patched ClientSession.call_tool with our wrapper")
    
    # Now create a session and call it
    from mcp import StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import ClientNotification, InitializedNotification
    
    # Create exit stack to properly handle async context managers
    from contextlib import AsyncExitStack
    
    async with AsyncExitStack() as exit_stack:
        server_params = StdioServerParameters(
            command="python",
            args=["mcpserver.py"],
            env={
                "OTEL_SERVICE_NAME": "mcp-server",
            }
        )
        
        logger.info("Setting up client connection")
        reader, writer = await exit_stack.enter_async_context(stdio_client(server_params))
        session = await exit_stack.enter_async_context(ClientSession(reader, writer))
        
        logger.info("Initializing session")
        await session.send_notification(
            ClientNotification(
                InitializedNotification(method="notifications/initialized")
            )
        )
        
        logger.info("Calling session.call_tool")
        response = await session.call_tool(
            name="list_application_signals_services",
            arguments={}
        )
        
        logger.info(f"Got response: {response}")
    
    logger.info("Test complete")

if __name__ == "__main__":
    asyncio.run(main())
