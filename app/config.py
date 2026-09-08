"""Application configuration via environment variables or YAML file."""

from __future__ import annotations

import ipaddress
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import yaml  # type: ignore[import-untyped]
from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MAX_REQUEST_BODY_BYTES = 1_048_576
_PLACEHOLDER_MAIL_HOST = "mail.example.com"
_PLACEHOLDER_DOMAIN = "example.com"


class UsernameFormat(StrEnum):
    """How mail clients should present the mailbox username."""

    EMAIL = "email"
    LOCALPART = "localpart"


class SocketType(StrEnum):
    """Transport encryption mode for IMAP, SMTP, or POP3."""

    SSL = "SSL"
    STARTTLS = "STARTTLS"
    PLAIN = "plain"


class MailServerSettings(BaseModel):
    """Connection settings for one mail protocol."""

    host: str
    port: int
    socket_type: SocketType
    authentication: str

    @field_validator("socket_type", mode="before")
    @classmethod
    def normalize_socket_type(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper() if value.lower() != "plain" else "plain"
        return value


class Pop3Settings(MailServerSettings):
    """POP3 settings for a domain."""

    enabled: bool = False


class DomainMailSettings(BaseModel):
    """Mail settings for a single email domain."""

    display_name: str
    display_short_name: str
    imap: MailServerSettings
    smtp: MailServerSettings
    pop3: Pop3Settings | None = None

    @classmethod
    def from_env_settings(cls, settings: Settings) -> DomainMailSettings:
        """Build a domain config from the global environment-based settings."""
        return cls(
            display_name=settings.mail_display_name,
            display_short_name=settings.mail_display_short_name,
            imap=MailServerSettings(
                host=settings.imap_host,
                port=settings.imap_port,
                socket_type=settings.imap_socket_type,
                authentication=settings.imap_authentication,
            ),
            smtp=MailServerSettings(
                host=settings.smtp_host,
                port=settings.smtp_port,
                socket_type=settings.smtp_socket_type,
                authentication=settings.smtp_authentication,
            ),
            pop3=Pop3Settings(
                enabled=settings.pop3_enabled,
                host=settings.pop3_host,
                port=settings.pop3_port,
                socket_type=settings.pop3_socket_type,
                authentication=settings.pop3_authentication,
            ),
        )


class DomainConfigFile(BaseModel):
    """Top-level YAML configuration shape for multi-domain setup."""

    domains: dict[str, DomainMailSettings]


class Settings(BaseSettings):
    """Environment-driven mail autodiscovery configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = Field(default="mail-autodiscover", alias="APP_NAME")
    app_env: str = Field(default="production", alias="APP_ENV")
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")
    config_file: str = Field(default="/config/config.yaml", alias="CONFIG_FILE")

    allowed_domains: str = Field(default=_PLACEHOLDER_DOMAIN, alias="ALLOWED_DOMAINS")

    mail_display_name: str = Field(default="Example Mail", alias="MAIL_DISPLAY_NAME")
    mail_display_short_name: str = Field(default="Example", alias="MAIL_DISPLAY_SHORT_NAME")

    imap_host: str = Field(default=_PLACEHOLDER_MAIL_HOST, alias="IMAP_HOST")
    imap_port: int = Field(default=993, alias="IMAP_PORT")
    imap_socket_type: SocketType = Field(default=SocketType.SSL, alias="IMAP_SOCKET_TYPE")
    imap_authentication: str = Field(default="password-cleartext", alias="IMAP_AUTHENTICATION")

    smtp_host: str = Field(default=_PLACEHOLDER_MAIL_HOST, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_socket_type: SocketType = Field(default=SocketType.STARTTLS, alias="SMTP_SOCKET_TYPE")
    smtp_authentication: str = Field(default="password-cleartext", alias="SMTP_AUTHENTICATION")

    username_format: UsernameFormat = Field(default=UsernameFormat.EMAIL, alias="USERNAME_FORMAT")

    container_port: int = Field(default=8000, alias="CONTAINER_PORT")

    trust_proxy_headers: bool = Field(default=False, alias="TRUST_PROXY_HEADERS")
    trusted_proxy_ips: str = Field(
        default="",
        validation_alias=AliasChoices("TRUSTED_PROXY_IPS", "FORWARDED_ALLOW_IPS"),
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    structured_json_logs: bool = Field(default=False, alias="STRUCTURED_JSON_LOGS")

    max_request_body_bytes: int = Field(default=16384, alias="MAX_REQUEST_BODY_BYTES")
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_max_clients: int = Field(default=10000, alias="RATE_LIMIT_MAX_CLIENTS")
    rate_limit_cleanup_interval_seconds: int = Field(
        default=300, alias="RATE_LIMIT_CLEANUP_INTERVAL_SECONDS"
    )

    pop3_enabled: bool = Field(default=False, alias="POP3_ENABLED")
    pop3_host: str = Field(default=_PLACEHOLDER_MAIL_HOST, alias="POP3_HOST")
    pop3_port: int = Field(default=995, alias="POP3_PORT")
    pop3_socket_type: SocketType = Field(default=SocketType.SSL, alias="POP3_SOCKET_TYPE")
    pop3_authentication: str = Field(default="password-cleartext", alias="POP3_AUTHENTICATION")

    outlook_enabled: bool = Field(default=True, alias="OUTLOOK_ENABLED")
    thunderbird_enabled: bool = Field(default=True, alias="THUNDERBIRD_ENABLED")

    return_404_for_unknown_domain: bool = Field(
        default=True, alias="RETURN_404_FOR_UNKNOWN_DOMAIN"
    )
    disable_access_log: bool = Field(default=False, alias="DISABLE_ACCESS_LOG")
    access_log_skip_paths: str = Field(
        default="/health,/ready,/favicon.ico,/apple-touch-icon.png",
        alias="ACCESS_LOG_SKIP_PATHS",
    )
    security_headers_enabled: bool = Field(default=True, alias="SECURITY_HEADERS_ENABLED")

    apple_mobileconfig_enabled: bool = Field(default=True, alias="APPLE_MOBILECONFIG_ENABLED")
    domain_configs: dict[str, DomainMailSettings] = Field(default_factory=dict, exclude=True)

    @field_validator("allowed_domains", mode="before")
    @classmethod
    def parse_allowed_domains(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @property
    def allowed_domains_set(self) -> frozenset[str]:
        if self.domain_configs:
            return frozenset(self.domain_configs)
        domains = {d.strip().lower() for d in self.allowed_domains.split(",") if d.strip()}
        return frozenset(domains)

    @property
    def access_log_skip_paths_set(self) -> frozenset[str]:
        paths = {p.strip() for p in self.access_log_skip_paths.split(",") if p.strip()}
        return frozenset(paths)

    @staticmethod
    def _parse_trusted_proxy_token(
        token: str,
    ) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
        """Return a parsed network for a TRUSTED_PROXY_IPS token, or None when invalid."""
        try:
            if "/" in token:
                return ipaddress.ip_network(token, strict=False)
            prefix = "128" if ":" in token else "32"
            return ipaddress.ip_network(f"{token}/{prefix}", strict=False)
        except ValueError:
            return None

    @property
    def trusted_proxy_networks(
        self,
    ) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        """Parsed CIDR/IP entries from TRUSTED_PROXY_IPS."""
        entries: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for part in self.trusted_proxy_ips.split(","):
            token = part.strip()
            if not token:
                continue
            network = self._parse_trusted_proxy_token(token)
            if network is not None:
                entries.append(network)
        return tuple(entries)

    @field_validator("imap_socket_type", "smtp_socket_type", "pop3_socket_type", mode="before")
    @classmethod
    def normalize_socket_type(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper() if value.lower() != "plain" else "plain"
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> Settings:
        """Load config file when present and reject unsafe production settings."""
        self.domain_configs = self._load_domain_configs()
        errors: list[str] = self._shared_validation_errors()

        if self.domain_configs:
            self._validate_domain_config(errors)
        elif self.app_env.lower() == "production":
            self._validate_env_config(errors)

        if errors:
            raise ValueError("; ".join(errors))
        return self

    def _load_domain_configs(self) -> dict[str, DomainMailSettings]:
        """Read and validate per-domain YAML config if the configured file exists."""
        config_path = self.config_file.strip()
        if not config_path:
            return {}

        path = Path(config_path)
        if not path.exists():
            return {}

        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"Unable to read CONFIG_FILE {path}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"CONFIG_FILE {path} is not valid YAML: {exc}") from exc

        if raw in (None, ""):
            raise ValueError(f"CONFIG_FILE {path} is empty")

        try:
            parsed = DomainConfigFile.model_validate(raw)
        except Exception as exc:
            raise ValueError(f"CONFIG_FILE {path} has invalid domain config: {exc}") from exc

        normalized: dict[str, DomainMailSettings] = {}
        for domain, domain_settings in parsed.domains.items():
            token = domain.strip().lower()
            if not token:
                raise ValueError("CONFIG_FILE contains an empty domain key")
            normalized[token] = domain_settings
        if not normalized:
            raise ValueError(f"CONFIG_FILE {path} must define at least one domain")
        return normalized

    def _shared_validation_errors(self) -> list[str]:
        """Return validation errors shared by env and YAML modes."""
        errors: list[str] = []
        if self.app_env.lower() == "production":
            self._validate_proxy_settings(errors)
            self._validate_public_base_url(errors)
        self._validate_rate_limit_settings(errors)
        self._validate_body_limit(errors)
        return errors

    def _validate_proxy_settings(self, errors: list[str]) -> None:
        """Validate TRUSTED_PROXY_IPS / TRUST_PROXY_HEADERS for production use."""
        if self.trust_proxy_headers and self.trusted_proxy_ips.strip():
            for part in self.trusted_proxy_ips.split(","):
                token = part.strip()
                if token and self._parse_trusted_proxy_token(token) is None:
                    errors.append(f"TRUSTED_PROXY_IPS contains invalid entry: {token}")

        if self.trust_proxy_headers:
            if not self.trusted_proxy_ips.strip():
                errors.append(
                    "TRUST_PROXY_HEADERS=true requires non-empty "
                    "TRUSTED_PROXY_IPS in production"
                )
            elif not self.trusted_proxy_networks:
                errors.append(
                    "TRUSTED_PROXY_IPS contains no valid CIDR or IP entries in production"
                )

    def _validate_public_base_url(self, errors: list[str]) -> None:
        """Validate PUBLIC_BASE_URL for production use."""
        base_url = self.public_base_url.lower()
        if "localhost" in base_url:
            errors.append("PUBLIC_BASE_URL must not use localhost in production")
        if not base_url.startswith("https://"):
            errors.append("PUBLIC_BASE_URL must use https:// in production")

    def _validate_rate_limit_settings(self, errors: list[str]) -> None:
        """Validate rate limiter bounds."""
        if self.rate_limit_enabled and self.rate_limit_per_minute <= 0:
            errors.append(
                "RATE_LIMIT_PER_MINUTE must be greater than 0 when rate limiting is enabled"
            )
        if self.rate_limit_enabled and self.rate_limit_max_clients <= 0:
            errors.append(
                "RATE_LIMIT_MAX_CLIENTS must be greater than 0 when rate limiting is enabled"
            )

    def _validate_body_limit(self, errors: list[str]) -> None:
        """Validate MAX_REQUEST_BODY_BYTES."""
        if self.max_request_body_bytes <= 0:
            errors.append("MAX_REQUEST_BODY_BYTES must be greater than 0")
        elif (
            self.app_env.lower() == "production"
            and self.max_request_body_bytes > _MAX_REQUEST_BODY_BYTES
        ):
            errors.append(
                f"MAX_REQUEST_BODY_BYTES must not exceed {_MAX_REQUEST_BODY_BYTES} in production"
            )

    def _validate_env_config(self, errors: list[str]) -> None:
        """Validate the single-profile environment-based configuration."""
        domains = self.allowed_domains_set
        if not domains or domains == frozenset({_PLACEHOLDER_DOMAIN}):
            errors.append(
                "ALLOWED_DOMAINS must be set to your real domain(s) in production "
                f"(not {_PLACEHOLDER_DOMAIN})"
            )

        if self.imap_host == _PLACEHOLDER_MAIL_HOST and self.smtp_host == _PLACEHOLDER_MAIL_HOST:
            errors.append(
                f"IMAP_HOST and SMTP_HOST still use placeholder {_PLACEHOLDER_MAIL_HOST} "
                "in production"
            )

    def _validate_domain_config(self, errors: list[str]) -> None:
        """Validate the per-domain YAML configuration."""
        if not self.domain_configs:
            errors.append("CONFIG_FILE must define at least one domain")
            return

        if self.app_env.lower() != "production":
            return

        for domain, domain_settings in self.domain_configs.items():
            if domain == _PLACEHOLDER_DOMAIN:
                errors.append(f"CONFIG_FILE must not use {_PLACEHOLDER_DOMAIN} in production")
            if (
                domain_settings.imap.host == _PLACEHOLDER_MAIL_HOST
                and domain_settings.smtp.host == _PLACEHOLDER_MAIL_HOST
            ):
                errors.append(
                    f"CONFIG_FILE domain {domain} still uses placeholder {_PLACEHOLDER_MAIL_HOST}"
                )

    def domain_settings_for(self, domain: str) -> DomainMailSettings | None:
        """Return the resolved per-domain mail settings for a normalized domain."""
        normalized = domain.strip().lower()
        if self.domain_configs:
            return self.domain_configs.get(normalized)
        if normalized not in self.allowed_domains_set:
            return None
        return DomainMailSettings.from_env_settings(self)


class SettingsProvider(Protocol):
    """Injectable source of application settings (for tests and DI)."""

    def get_settings(self) -> Settings: ...


class EnvSettingsProvider:
    """Reads configuration from environment variables (MVP default)."""

    def get_settings(self) -> Settings:
        return get_settings()


@lru_cache
def get_settings() -> Settings:
    """Load and cache settings from the process environment."""
    return Settings()
