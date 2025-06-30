from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Collection, Tuple, cast
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
                self._toolcall_wrapper,
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
    def _uninstrument(self, **kwargs: Any) -> None:
        unwrap("mcp.client.stdio", "stdio_client")
        unwrap("mcp.server.stdio", "satdio_server")
    
    async def _client_call_tool_wrapper(self, wrapped, instance, args, kwargs):
        tracer = trace.get_tracer("mcp.client")
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

        with tracer.start_as_current_span("client.tool.call", kind=trace.SpanKind.CLIENT) as span:
            span.set_attribute("span.kind", "CLIENT")
            span.set_attribute("tool.name", name)
            span.set_attribute("aws.span.kind", "CLIENT")
            span.set_attribute("aws:service.span.kind", "CLIENT")
            span.set_attribute("aws.xray.type", "segment")
            span.set_attribute("aws.service.span.kind", "CLIENT")
            span.set_attributes
            span_ctx = span.get_span_context()
            arguments["_meta"] = {
                "trace_id": span_ctx.trace_id,
                "span_id": span_ctx.span_id,
            }
            new_args = list(args)
            if len(new_args) >= 2:
                new_args[1] = arguments
            elif len(new_args) == 1:
                new_args.append(arguments)
            else:
                new_args = [name, arguments]

            ctx_logger.info(f"[CLIENT WRAPPER] injected _meta: {arguments['_meta']}")
            if len(args) >= 2:
                new_args = (args[0], arguments)
                result = await wrapped(*new_args)
            else:
                result = await wrapped(name=name, arguments=arguments)
            
            ctx_logger.info(f"kwargs:{kwargs}")
            ctx_logger.info(f"args: {args}")
            ctx_logger.info(f"newargs:{new_args}")
            ctx_logger.info(f"args received in clientcalltoolwrapper:{arguments}")

            return result


    def _toolcall_wrapper(self, wrapped, instance, args, kwargs):
        original_decorator = wrapped(*args, **kwargs)
        def wrapper(func):
            async def instrumented_func(name, arguments=None):
                from opentelemetry import trace, context
                loggertwo.info(f"Server received - name: {name}, arguments: {arguments}")
                
                # Check for _meta trace context
                if arguments and isinstance(arguments, dict) and "_meta" in arguments:
                    meta = arguments["_meta"]
                    loggertwo.info(f"Found _meta context: {meta}")
                else:
                    loggertwo.info("No _meta context found in arguments")
                tracer = trace.get_tracer("mcp.server")
                if isinstance(arguments, dict) and arguments.get("_meta"):
                    incomingtraceid = int(arguments.get("_meta").get("trace_id"))
                    incomingspanid = int(arguments.get("_meta").get("span_id"))
                span_context = trace.SpanContext(
                    trace_id=incomingtraceid,
                    span_id=incomingspanid,
                    is_remote=True,
                )

                # # Create a context that includes the non-recording parent span
                parent_ctx = trace.set_span_in_context(trace.NonRecordingSpan(span_context))

                # Attach the context and make sure to detach afterward
                with tracer.start_as_current_span("server.tool.call", kind=trace.SpanKind.SERVER,context= parent_ctx) as span:
                    span.set_attribute("tool.name", name)
                    span.set_attribute("server_side", True)
                    span.set_attribute("aws.span.kind", "SERVER")
                    span.set_attribute("aws.xray.type", "subsegment")
                    span.set_attribute("aws.service.span.kind", "SERVER")
                    parent_id = getattr(span, '_parent', None)
                    parent_span_id = parent_id.span_id if parent_id else None
                    loggertwo.info(f"Span parent_id: {format(parent_span_id)}")
                    loggertwo.info(f"Span traceid without formatting: {span.get_span_context().trace_id}")
                    loggertwo.info(f"Span trace_id: {format(span.get_span_context().trace_id, '032x')}")
                    loggertwo.info(f"Span span_id: {format(span.get_span_context().span_id, '016x')}")
                loggertwo.info(f"Spanaftertoken: {span}")
                self.tracer_provider.force_flush()
                result = await func(name, arguments)
                return result
            return original_decorator(instrumented_func)
        return wrapper
