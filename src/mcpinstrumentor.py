from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Collection, Tuple, cast
from opentelemetry.sdk.resources import Resource
from opentelemetry import context, propagate
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor  
from opentelemetry.instrumentation.utils import unwrap
from wrapt import ObjectProxy, register_post_import_hook, wrap_function_wrapper
from openinference.instrumentation.mcp.package import _instruments

from opentelemetry import trace 
import asyncio

import logging

# Add this at the top of your file, after the imports
def setup_ctx_logger():
    logger = logging.getLogger('ctx_logger')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler('ctx.log', mode='w')
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    if not logger.handlers:
        logger.addHandler(handler)
    return logger

def setup_loggertwo():
    logger = logging.getLogger('loggertwo')
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler('loggertwo.log', mode='w')
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    if not logger.handlers:
        logger.addHandler(handler)
    return logger

ctx_logger = setup_ctx_logger()
loggertwo = setup_loggertwo()
class MCPInstrumentor(BaseInstrumentor):  
    """
    An instrumenter for MCP.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:        
        if kwargs.get("tracer_provider"):
            tracer_provider = kwargs["tracer_provider"]
            loggertwo.info("Using provided tracer_provider")
        else:
            loggertwo.info("No tracer_provider provided")
        self.tracer_provider = tracer_provider
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.lowlevel.server",
                "Server.call_tool",
                self._server_toolcall_wrapper,
            ),
            "mcp.server.lowlevel.server",
        )
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.client.session",
                "ClientSession.call_tool",
                self._client_call_tool_wrapper,
            ),
            "mcp.client.session",
        )
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.lowlevel.server",
                "Server.list_tools",
                self._server_listtool_wrapper,
            ),
            "mcp.server.lowlevel.server",
        )
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.client.session",
                "ClientSession.list_tools",
                self._client_list_tool_wrapper,
            ),
            "mcp.client.session",
        )
    def _uninstrument(self, **kwargs: Any) -> None:
        unwrap("mcp.client.stdio", "stdio_client")
        unwrap("mcp.server.stdio", "satdio_server")
    
    async def _client_list_tool_wrapper(self, wrapped, instance, args, kwargs):
        tracer = self.tracer_provider.get_tracer("mcp.client")
        
        with tracer.start_as_current_span("MCP List Tools Service", kind=trace.SpanKind.SERVER) as parent_span:
            parent_span.set_attribute("span.kind", "SERVER")
            current_ctx = trace.set_span_in_context(parent_span)

            with tracer.start_as_current_span(name="client.tool.list", kind=trace.SpanKind.CLIENT, context=current_ctx) as span:
                span.set_attribute("span.kind", "CLIENT")
                span.set_attribute("aws.remote.service", "appsignals")
                span.set_attribute("aws.remote.operation", "List Tools")

                # Set the span context as the current context for propagation
                token = context.attach(current_ctx)
                try:
                    result = await wrapped(*args, *kwargs)
                    return result
                finally:
                    context.detach(token)

    def _server_listtool_wrapper(self, wrapped, instance, args, kwargs):
        original_decorator = wrapped(*args, **kwargs)
        def wrapper(func):
            async def instrumented_func(*func_args, **func_kwargs):
                tracer = self.tracer_provider.get_tracer("ListToolServerSide")
                current_context = context.get_current()
                
                with tracer.start_as_current_span("server.tool.list", kind=trace.SpanKind.SERVER, context=current_context) as span:
                    span.set_attribute("server_side", True)
                    span.set_attribute("aws.span.kind", "SERVER")
                    span.set_attribute("operation", "list_tools")
                    
                result = await func(*func_args, **func_kwargs)
                self.tracer_provider.force_flush()
                return result
                
            return original_decorator(instrumented_func)
        return wrapper



    
    async def _client_call_tool_wrapper(self, wrapped, instance, args, kwargs):
        tracer = self.tracer_provider.get_tracer("mcp.client")
        if len(args) > 0:
            name = args[0]
        else:
            name = kwargs.get("name", "unknown_tool")
        if len(args) > 1:
            arguments = args[1]
        else:
            arguments = kwargs.get("arguments", {}) 
        ctx_logger.info(f"[CLIENT WRAPPER] tool name: {name}")
        ctx_logger.info(f"[CLIENT WRAPPER] original arguments: {arguments}")

        with tracer.start_as_current_span("MCP Caller Service", kind=trace.SpanKind.SERVER) as parent_span:
            parent_span.set_attribute("span.kind", "SERVER")
            parent_span.set_attribute("dummydummy", "dummyserver")
            
            current_ctx = trace.set_span_in_context(parent_span)
            
            with tracer.start_as_current_span(name = "client.tool.call", kind=trace.SpanKind.CLIENT,context=current_ctx) as span:
                span.set_attribute("span.kind", "CLIENT")
                span.set_attribute("tool.name", name)
                span.set_attribute("clientdummytest", "EFVVDSVE")
                span.set_attribute("aws.remote.service", "Client Tool Call")
                span.set_attribute("aws.remote.operation", name)
                
                span_ctx = span.get_span_context()
                arguments["_meta"] = {
                    "trace_id": span_ctx.trace_id,
                    "span_id": span_ctx.span_id,
                }
                
                ctx_logger.info(f"[CLIENT WRAPPER] injected _meta: {arguments['_meta']}")
                
                if len(args) >= 2:
                    result = await wrapped(args[0], arguments)
                else:
                    result = await wrapped(name=name, arguments=arguments)
                
                ctx_logger.info(f"kwargs:{kwargs}")
                ctx_logger.info(f"args: {args}")
                ctx_logger.info(f"args received in clientcalltoolwrapper:{arguments}")
                return result

    def _server_toolcall_wrapper(self, wrapped, instance, args, kwargs):
        original_decorator = wrapped(*args, **kwargs)
        def wrapper(func):
            async def instrumented_func(name, arguments=None):
                from opentelemetry import trace, context
                loggertwo.info(f"Server received - name: {name}, arguments: {arguments}")
                
                if arguments and isinstance(arguments, dict) and "_meta" in arguments:
                    meta = arguments["_meta"]
                    loggertwo.info(f"Found _meta context: {meta}")
                else:
                    loggertwo.info("No _meta context found in arguments")
                tracer = self.tracer_provider.get_tracer("mcp.server")
                if isinstance(arguments, dict) and arguments.get("_meta"):
                    incomingtraceid = int(arguments.get("_meta").get("trace_id"))
                    incomingspanid = int(arguments.get("_meta").get("span_id"))
                span_context = trace.SpanContext(
                    trace_id=incomingtraceid,
                    span_id=incomingspanid,
                    is_remote=True,
                )

                parent_ctx = trace.set_span_in_context(trace.NonRecordingSpan(span_context))
                result = None
                with tracer.start_as_current_span("server.tool.call", kind=trace.SpanKind.SERVER,context= parent_ctx) as span:
                    span.set_attribute("tool.name", name)
                    span.set_attribute("server_side", True)
                    span.set_attribute("aws.span.kind", "SERVER")
                    span.set_attribute("sjdfoisvmwe", "testetsetsets")
                self.tracer_provider.force_flush()
                result = await func(name, arguments)
                return result

            return original_decorator(instrumented_func)
        return wrapper
