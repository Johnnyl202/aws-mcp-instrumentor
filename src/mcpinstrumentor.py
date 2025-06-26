from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Callable, Collection, Tuple, cast
from opentelemetry import context, propagate
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor  
from opentelemetry.instrumentation.utils import unwrap
from wrapt import ObjectProxy, register_post_import_hook, wrap_function_wrapper
from openinference.instrumentation.mcp.package import _instruments

from opentelemetry import trace as trace_api


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

ctx_logger = setup_ctx_logger()
class MCPInstrumentor(BaseInstrumentor):  
    """
    An instrumenter for MCP.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return _instruments

    def _instrument(self, **kwargs: Any) -> None:

        if kwargs.get("tracer_provider"):
            tracer_provider = kwargs["tracer_provider"]
        self.tracer_provider = tracer_provider
        register_post_import_hook(
            lambda _: wrap_function_wrapper(
                "mcp.server.lowlevel.server",
                "Server.call_tool",
                self._toolcall_wrapper,
            ),
            "mcp.server.lowlevel.server",
        )

    def _uninstrument(self, **kwargs: Any) -> None:
        unwrap("mcp.client.stdio", "stdio_client")
        unwrap("mcp.server.stdio", "satdio_server")

    def _toolcall_wrapper(self, wrapped, instance, args, kwargs):
        from opentelemetry import propagate
        original_decorator = wrapped(*args, **kwargs)
        def wrapper(func):
            async def instrumented_func(name, arguments=None):
                from opentelemetry import trace, context
                ctx_logger.info(f"Arguments: {arguments}")
                tracer = self.tracer_provider.get_tracer("mcp.server")
                if isinstance(arguments, dict) and arguments.get("_meta"):
                    incomingtraceid = int(arguments.get("_meta").get("trace_id"))
                    incomingspanid = int(arguments.get("_meta").get("span_id"))
                ctx_logger.info(f"Trace ID: {format(incomingtraceid,"032x")}, Span ID: {format(incomingspanid,"016x")}")
                span_context = trace.SpanContext(span_id=incomingspanid, trace_id=incomingtraceid, is_remote=False)
                # contexttoattach = trace.set_span_in_context(trace.NonRecordingSpan(span_context))
                # ctx_logger.info(f"Context to attach: {span_context}")
                # with tracer.start_as_current_span(name="server.tool.call",kind=trace.SpanKind.SERVER) as span:
                #     trace.set_span_in_context(trace.get_current_span(),contexttoattach)
                #     span.set_attribute("tool.name", name)
                #     span.set_attribute("server_side", True)
                #     ctx_logger.info(f"Span context: {span}")
                span_context = trace.SpanContext(
                    trace_id=incomingtraceid,
                    span_id=incomingspanid,
                    is_remote=True,
                )

                # # Create a context that includes the non-recording parent span
                parent_ctx = trace.set_span_in_context(trace.NonRecordingSpan(span_context))

                # Attach the context and make sure to detach afterward
                token = context.attach(parent_ctx)
                try:
                    with tracer.start_as_current_span(
                        name="server.tool.call",
                        kind=trace.SpanKind.SERVER,
                        # context=parent_ctx
                    ) as span:
                        span.set_attribute("tool.name", name)
                        span.set_attribute("server_side", True)
                        parent_id = getattr(span, '_parent', None)
                        parent_span_id = parent_id.span_id if parent_id else incomingspanid
                        ctx_logger.info(f"Span parent_id: {format(parent_span_id)}")
                        ctx_logger.info(f"Span trace_id: {format(span.get_span_context().trace_id, '032x')}")
                        ctx_logger.info(f"Span span_id: {format(span.get_span_context().span_id, '016x')}")
                finally:
                    context.detach(token)
                ctx_logger.info(f"Spanaftertoken: {span}")
                self.tracer_provider.force_flush()
                result = await func(name, arguments)
                return result
            return original_decorator(instrumented_func)
        return wrapper