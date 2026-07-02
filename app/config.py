"""Application configuration via pydantic-settings.

All values are tunable via environment variables (uppercased field names).
"""

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_csv(value: str) -> List[float]:
    """Parse a comma-separated string of numbers into a list of floats.

    Raises ``ValueError`` with a descriptive message if any token is not
    parseable as a positive float.
    """
    result: List[float] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            result.append(float(token))
        except ValueError as exc:
            raise ValueError(
                f"Invalid token {token!r} in comma-separated list {value!r}: {exc}"
            ) from exc
    if not result:
        raise ValueError(f"Comma-separated list {value!r} is empty")
    return result


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="fastapi-metrics-app", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")

    # Metrics endpoint
    metrics_endpoint: str = Field(default="/metrics", description="Prometheus exposition path")

    # System metrics collection
    system_metrics_interval: float = Field(
        default=5.0,
        ge=0.5,
        le=300.0,
        description="Interval in seconds between system metric collections",
    )
    enable_default_metrics: bool = Field(
        default=True,
        description="Register default process/platform/GC collectors",
    )

    # Histogram buckets (strings parsed from env)
    http_histogram_buckets: str = Field(
        default="0.005,0.01,0.025,0.05,0.1,0.25,0.5,1.0,2.5,5.0,10.0",
        description="Buckets for HTTP request duration histogram (seconds)",
    )
    request_size_buckets: str = Field(
        default="100,1024,10240,102400,1048576,10485760",
        description="Buckets for HTTP request size histogram (bytes)",
    )
    response_size_buckets: str = Field(
        default="100,1024,10240,102400,1048576,10485760",
        description="Buckets for HTTP response size histogram (bytes)",
    )

    # /data store
    max_data_items: int = Field(
        default=1000,
        ge=1,
        description="Maximum number of items kept in the in-memory /data store",
    )

    @property
    def http_histogram_buckets_list(self) -> List[float]:
        return _parse_csv(self.http_histogram_buckets)

    @property
    def request_size_buckets_list(self) -> List[float]:
        return _parse_csv(self.request_size_buckets)

    @property
    def response_size_buckets_list(self) -> List[float]:
        return _parse_csv(self.response_size_buckets)


# Singleton settings instance
settings = Settings()
