from contextlib import asynccontextmanager
from dataclasses import dataclass
import datetime
from typing import Any, AsyncGenerator, Callable, Collection, Tuple, cast

from opentelemetry import context, propagate
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor  # type: ignore
from opentelemetry.instrumentation.utils import unwrap
from wrapt import ObjectProxy, register_post_import_hook, wrap_function_wrapper

from openinference.instrumentation.mcp.package import _instruments

import logging
import os
from mcp import types


# Set up file logging
log_file = os.path.join(os.path.dirname(__file__), 'instrumentor.log')
instrumentor_logger = logging.getLogger('instrumentor')
file_handler = logging.FileHandler(log_file, mode='w')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
instrumentor_logger.addHandler(file_handler)
instrumentor_logger.setLevel(logging.DEBUG)

class MCPInstrumentor(BaseInstrumentor):  # type: ignore
    """
    An instrumenter for MCP.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:
        instrumentor_logger.info("Instrumenting MCP")
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.client.streamable_http",
                "streamablehttp_client",
                self._wrap_transport_with_callback,
            ),
            "mcp.client.streamable_http",
        )

        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.streamable_http",
                "StreamableHTTPServerTransport.connect",
                self._wrap_plain_transport,
            ),
            "mcp.server.streamable_http",
        )

        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.client.sse", "sse_client", self._wrap_plain_transport
            ),
            "mcp.client.sse",
        )
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.sse", "SseServerTransport.connect_sse", self._wrap_plain_transport
            ),
            "mcp.server.sse",
        )
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.client.stdio", "stdio_client", self._wrap_plain_transport
            ),
            "mcp.client.stdio",
        )
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.stdio", "stdio_server", self._wrap_plain_transport
            ),
            "mcp.server.stdio",
        )

        # While we prefer to instrument the lowest level primitive, the transports above, it doesn't
        # mean context will be propagated to handlers automatically. Notably, the MCP SDK passes
        # server messages to a handler with a separate stream in between, losing context. We go
        # ahead and instrument this second stream just to propagate context so transports can still
        # be used independently while also supporting the major usage of the MCP SDK. Notably, this
        # may be a reasonable generic instrumentation for anyio itself to allow its streams to
        # propagate context broadly.
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.session", "ServerSession.__init__", self._base_session_init_wrapper
            ),
            "mcp.server.session",
        )


        #toolcall wrapper
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.lowlevel.server",
                "Server.call_tool",
                self._toolcall_wrapper,
            ),
            "mcp.server.lowlevel.server",
        )
        # register_post_import_hook(
        #     lambda _: wrap_function_wrapper(
        #         "mcp.server.lowlevel.server",
        #         "Server._handle_request",
        #         self._handle_request_wrapper,
        #     ),
        #     "mcp.server.lowlevel.server",
        # )

    def _uninstrument(self, **kwargs: Any) -> None:
        unwrap("mcp.client.stdio", "stdio_client")
        unwrap("mcp.server.stdio", "stdio_server")


    def _handle_request_wrapper(self, wrapped, instance, args, kwargs):
        instrumentor_logger.info("Server._handle_request wrapper called")
        
        # Log to arg.log as well for better visibility
        log_file1 = os.path.join(os.path.dirname(__file__), 'arg.log')
        arg_logger = logging.getLogger('arg_logger')
        if not arg_logger.handlers:
            file_handler1 = logging.FileHandler(log_file1, mode='a')
            file_handler1.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            arg_logger.addHandler(file_handler1)
            arg_logger.setLevel(logging.DEBUG)
        
        arg_logger.info("Server._handle_request wrapper registered")
        
        async def wrapped_handler(message, req, session, lifespan_context, raise_exceptions):
            # Log all requests, not just tool calls
            arg_logger.info(f"_handle_request called with request type: {type(req).__name__}")
            
            # Log request details
            if hasattr(req, "method"):
                arg_logger.info(f"Request method: {req.method}")
            
            if hasattr(req, "params"):
                arg_logger.info(f"Request params: {req.params}")
            
            # Check if this is a tool call request
            if hasattr(req, "params") and hasattr(req.params, "name"):
                # This is likely a tool call
                tool_name = req.params.name
                tool_args = req.params.arguments or {}
                
                arg_logger.info(f"Detected tool call: {tool_name} with args: {tool_args}")
                
                # Create a span for the tool call
                from opentelemetry import trace
                import json
                
                tracer = trace.get_tracer("mcp.server.lowlevel")
                with tracer.start_as_current_span(
                    "server.tool.call", 
                    kind=trace.SpanKind.SERVER
                ) as span:
                    span.set_attribute("tool.name", tool_name)
                    span.set_attribute("tool.arguments", str(tool_args))
                    span.set_attribute("server_side", True)
                    span.set_attribute("server_type", "Server")
                    
                    # Log span to file
                    span_file = os.path.join(os.path.dirname(__file__), 'spans.log')
                    span_context = span.get_span_context()
                    with open(span_file, 'a') as f:
                        span_info = {
                            "name": "server.tool.call",
                            "kind": "SERVER",
                            "trace_id": format(span_context.trace_id, '032x'),
                            "span_id": format(span_context.span_id, '016x'),
                            "attributes": {
                                "tool.name": tool_name,
                                "tool.arguments": str(tool_args),
                                "server_side": True,
                                "server_type": "Server"
                            },
                            "timestamp": str(datetime.datetime.now())
                        }
                        f.write(json.dumps(span_info, indent=2) + "\n\n")
            
            # Call the original handler
            result = await wrapped(message, req, session, lifespan_context, raise_exceptions)
            return result
        
        return wrapped_handler

    # def _toolcall_wrapper(self, wrapped, instance, args, kwargs):
    #     instrumentor_logger.info("Server.call_tool wrapper called")
    #     instrumentor_logger.info(f"Args: {args}")
    #     instrumentor_logger.info(f"Kwargs: {kwargs}")
        
    #     original_decorator = wrapped(*args, **kwargs)
        
    #     def wrapped_decorator(func):
    #         # Set up logging for arg.log
    #         log_file1 = os.path.join(os.path.dirname(__file__), 'arg.log')
    #         arg_logger = logging.getLogger('arg_logger')
            
    #         # Remove existing handlers to avoid duplicate logs
    #         for handler in arg_logger.handlers[:]:
    #             arg_logger.removeHandler(handler)
                
    #         file_handler1 = logging.FileHandler(log_file1, mode='a')  # Use append mode
    #         file_handler1.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    #         arg_logger.addHandler(file_handler1)
    #         arg_logger.setLevel(logging.DEBUG)
            
    #         from opentelemetry import trace
    #         tracer = trace.get_tracer("instrumentor.call_tool")
            
    #         arg_logger.info(f"Creating handler wrapper for function: {func.__name__}")
    #         arg_logger.info(f"Function: {func}")
            
    #         async def wrapped_handler(*args, **kwargs):
    #             from opentelemetry import trace
    #             import json
                
    #             tool_name = args[0] if args and isinstance(args[0], str) else "unknown"
    #             tool_args = args[1] if len(args) > 1 else {}
    #             span_file = os.path.join(os.path.dirname(__file__), 'spans.log')
    #             tracer = trace.get_tracer("mcp.server")
    #             with tracer.start_as_current_span("server.tool.call", kind=trace.SpanKind.SERVER) as span:
    #                 span.set_attribute("tool.name", tool_name)
    #                 span.set_attribute("tool.arguments", str(tool_args))
    #                 span.set_attribute("server_side", True)
    #                 span_context = span.get_span_context()
    #                 with open(span_file, 'a') as f:
    #                     span_info = {
    #                         "name": "server.tool.call",
    #                         "kind": "SERVER",
    #                         "trace_id": format(span_context.trace_id, '032x'),  # Format as hex string
    #                         "span_id": format(span_context.span_id, '016x'),    # Format as hex string
    #                         "attributes": {
    #                             "tool.name": tool_name,
    #                             "tool.arguments": str(tool_args),
    #                             "server_side": True
    #                         },
    #                         "timestamp": str(datetime.datetime.now())
    #                     }
    #                     f.write(json.dumps(span_info, indent=2) + "\n\n")
    #                 result = await func(*args, **kwargs)
    #                 return result
    #         return original_decorator(wrapped_handler)
        
    #     return wrapped_decorator


    def _toolcall_wrapper(self, wrapped, instance, args, kwargs):
        from opentelemetry import context, propagate

        instrumentor_logger.info("Server.call_tool wrapper called")
        
        # Set up new logger for span context testing
        test_log_file = os.path.join(os.path.dirname(__file__), 'testforspancontext.log')
        test_logger = logging.getLogger('span_context_test')
        
        # Clear existing handlers
        for handler in test_logger.handlers[:]:
            test_logger.removeHandler(handler)
        
        test_handler = logging.FileHandler(test_log_file, mode='w')
        test_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        test_logger.addHandler(test_handler)
        test_logger.setLevel(logging.INFO)

        original_decorator = wrapped(*args, **kwargs)
        
        # Create a new decorator that wraps the function
        def wrapper(func):
            test_logger.info(f"Wrapping Server.call_tool: {func.__name__}")
            async def instrumented_func(name, arguments=None):
                from opentelemetry import trace, context
                import json
                tracer = trace.get_tracer("mcp.server.lowlevel")
                test_logger.info(f"Server tool called: {name}")
                test_logger.info(f"Arguments: {arguments}")
                meta = None
                if isinstance(arguments, dict):
                    meta = arguments.get("_meta", {})
                ctx = propagate.extract(meta)
                test_logger.info(f"Extracted context: {ctx}")
                with tracer.start_as_current_span(name="server.tool.call",kind=trace.SpanKind.SERVER, context=ctx ) as span:
                    span.set_attribute("tool.name", name)
                    span.set_attribute("server_side", True)
                    span_context = span.get_span_context()
                    log_data = {
                        "name": span.name,
                        "trace_id": format(span_context.trace_id, '032x'),
                        "span_id": format(span_context.span_id, '016x'),
                        "attributes": {
                            "tool.name": name,
                            "server_side": True
                        },
                        "timestamp": str(datetime.datetime.now())
                    }

                    # Log it to `spans.log` in the same folder
                    log_file_path = os.path.join(os.path.dirname(__file__), 'spans.log')
                    with open(log_file_path, "a") as f:
                        f.write(json.dumps(log_data, indent=2) + "\n\n")
                result = await func(name, arguments)
                return result

            return original_decorator(instrumented_func)
        
        return wrapper



    @asynccontextmanager
    async def _wrap_transport_with_callback(
        self, wrapped: Callable[..., Any], instance: Any, args: Any, kwargs: Any
    ) -> AsyncGenerator[Tuple["InstrumentedStreamReader", "InstrumentedStreamWriter", Any], None]:
        async with wrapped(*args, **kwargs) as (read_stream, write_stream, get_session_id_callback):
            yield (
                InstrumentedStreamReader(read_stream),
                InstrumentedStreamWriter(write_stream),
                get_session_id_callback,
            )

    @asynccontextmanager
    async def _wrap_plain_transport(
        self, wrapped: Callable[..., Any], instance: Any, args: Any, kwargs: Any
    ) -> AsyncGenerator[Tuple["InstrumentedStreamReader", "InstrumentedStreamWriter"], None]:
        instrumentor_logger.info("WRAPPING plain transport")
        async with wrapped(*args, **kwargs) as (read_stream, write_stream):
            yield InstrumentedStreamReader(read_stream), InstrumentedStreamWriter(write_stream)

    def _base_session_init_wrapper(
        self, wrapped: Callable[..., None], instance: Any, args: Any, kwargs: Any
    ) -> None:
        wrapped(*args, **kwargs)
        reader = getattr(instance, "_incoming_message_stream_reader", None)
        writer = getattr(instance, "_incoming_message_stream_writer", None)
        if reader and writer:
            setattr(
                instance, "_incoming_message_stream_reader", ContextAttachingStreamReader(reader)
            )
            setattr(instance, "_incoming_message_stream_writer", ContextSavingStreamWriter(writer))


class InstrumentedStreamReader(ObjectProxy):  # type: ignore
    # ObjectProxy missing context manager - https://github.com/GrahamDumpleton/wrapt/issues/73
    instrumentor_logger.info("hereinstreamreader")
    async def __aenter__(self) -> Any:
        return await self.__wrapped__.__aenter__()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        return await self.__wrapped__.__aexit__(exc_type, exc_value, traceback)

    async def __aiter__(self) -> AsyncGenerator[Any, None]:
        from mcp.shared.message import SessionMessage
        from mcp.types import JSONRPCRequest
        from opentelemetry import trace
    
        tracer = trace.get_tracer("mcp.server")
        async for item in self.__wrapped__:
            session_message = cast(SessionMessage, item)
            request = session_message.message.root

            if not isinstance(request, JSONRPCRequest):
                yield item
                continue

            if request.params:
                meta = request.params.get("_meta")
                instrumentor_logger.info(f"metainstreamreader: {meta}")
                if meta:
                    ctx = propagate.extract(meta)
                    restore = context.attach(ctx)
                    try:
                        with tracer.start_as_current_span(f"server.{request.method}",kind=trace.SpanKind.SERVER) as span:
                            span.set_attribute("mcp.server.session_id", session_message.session_id)
                        yield item
                        continue
                    finally:
                        context.detach(restore)
            yield item
            

class InstrumentedStreamWriter(ObjectProxy):  # type: ignore
    # ObjectProxy missing context manager - https://github.com/GrahamDumpleton/wrapt/issues/73
    instrumentor_logger.info("hereinstreamwriter")
    async def __aenter__(self) -> Any:
        return await self.__wrapped__.__aenter__()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        return await self.__wrapped__.__aexit__(exc_type, exc_value, traceback)

    async def send(self, item: Any) -> Any:
        from mcp.shared.message import SessionMessage
        from mcp.types import JSONRPCRequest

        session_message = cast(SessionMessage, item)
        request = session_message.message.root
        if not isinstance(request, JSONRPCRequest):
            return await self.__wrapped__.send(item)
        meta = None
        if not request.params:
            request.params = {}
        meta = request.params.setdefault("_meta", {})
        if isinstance(request.params, dict):
            arguments = request.params.setdefault("arguments", {})
            if isinstance(arguments, dict):
                meta = arguments.setdefault("_meta", {})
                propagate.get_global_textmap().inject(meta)
        # propagate.get_global_textmap().inject(meta)
        instrumentor_logger.info(f"metainstreamwriter: {meta}")
        return await self.__wrapped__.send(item)


@dataclass(slots=True, frozen=True)
class ItemWithContext:
    item: Any
    ctx: context.Context

#internal components
#When sending data, it "saves" the context along with the data
class ContextSavingStreamWriter(ObjectProxy):  # type: ignore
    # ObjectProxy missing context manager - https://github.com/GrahamDumpleton/wrapt/issues/73
    async def __aenter__(self) -> Any:
        return await self.__wrapped__.__aenter__()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        return await self.__wrapped__.__aexit__(exc_type, exc_value, traceback)

    async def send(self, item: Any) -> Any:
        ctx = context.get_current()
        return await self.__wrapped__.send(ItemWithContext(item, ctx))

#When reading data, it "attaches" the context back to the data, ensuring that the trace information is passed along.
class ContextAttachingStreamReader(ObjectProxy):  # type: ignore
    # ObjectProxy missing context manager - https://github.com/GrahamDumpleton/wrapt/issues/73
    async def __aenter__(self) -> Any:
        return await self.__wrapped__.__aenter__()

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        return await self.__wrapped__.__aexit__(exc_type, exc_value, traceback)

    async def __aiter__(self) -> AsyncGenerator[Any, None]:
        async for item in self.__wrapped__:
            item_with_context = cast(ItemWithContext, item)
            restore = context.attach(item_with_context.ctx)
            try:
                yield item_with_context.item
            finally:
                context.detach(restore)
