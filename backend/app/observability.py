import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger("wemakedevs2026.backend")


def configure_observability(service_name: str) -> None:
    resource = Resource.create({"service.name": service_name})
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        trace_provider = TracerProvider(resource=resource)
        trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(trace_provider)
        metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))


tracer = trace.get_tracer("wemakedevs2026.backend")
meter = metrics.get_meter("wemakedevs2026.backend")
request_counter = meter.create_counter("backend.requests", description="Backend endpoint requests")
error_counter = meter.create_counter("backend.errors", description="Backend endpoint errors")
