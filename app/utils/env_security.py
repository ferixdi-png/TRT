"""
Environment validation and secret redaction utilities.

Provides early validation of required environment variables
and secure logging with automatic secret redaction.
"""

import os
import re
import sys
from typing import Dict, List, Optional, Pattern
from functools import lru_cache


class SecretRedactor:
    """Redacts secrets from logs and config output."""
    
    # Patterns for secret detection
    SECRET_PATTERNS: List[Pattern[str]] = [
        # Telegram Bot Token
        re.compile(r'\b\d{8,10}:[A-Za-z0-9_-]{35}\b'),
        # Render API Key
        re.compile(r'\brnd_[A-Za-z0-9]{32}\b'),
        # Render Service ID
        re.compile(r'\bsrv-[A-Za-z0-9]{25}\b'),
        # GitHub Token
        re.compile(r'\bghp_[A-Za-z0-9]{36}\b'),
        # KIE API Key
        re.compile(r'\bkie_[A-Za-z0-9_]{32,}\b'),
        # Database URLs
        re.compile(r'(?i)(postgresql|mysql|mongodb)://[^:]+:[^@]+@[^/]+'),
        # Redis URLs
        re.compile(r'redis://[^:]+:[^@]+@'),
        # Generic API keys (32+ chars)
        re.compile(r'\b[A-Za-z0-9]{32,}\b'),
        # Passwords in URLs
        re.compile(r'://[^:]+:([^@]+)@'),
    ]
    
    @classmethod
    def redact(cls, text: str) -> str:
        """Redact secrets from text."""
        if not text:
            return text
            
        redacted = text
        for pattern in cls.SECRET_PATTERNS:
            redacted = pattern.sub('[REDACTED]', redacted)
        
        return redacted
    
    @classmethod
    def redact_dict(cls, data: Dict[str, str]) -> Dict[str, str]:
        """Redact secrets in dictionary values."""
        return {k: cls.redact(v) for k, v in data.items()}


class EnvValidator:
    """Validates required environment variables early."""
    
    # Critical variables that must be set
    CRITICAL_VARS: List[str] = [
        'TELEGRAM_BOT_TOKEN',
        'KIE_API_KEY',
        'DATABASE_URL',
        'REDIS_URL',
        'ADMIN_ID',
        'BOT_INSTANCE_ID',
    ]
    
    # Optional but recommended variables
    RECOMMENDED_VARS: List[str] = [
        'WEBHOOK_BASE_URL',
        'PORT',
        'BOT_MODE',
        'STORAGE_MODE',
        'ENV',
    ]
    
    @classmethod
    def validate_critical(cls) -> None:
        """Validate critical environment variables."""
        missing = []
        
        for var in cls.CRITICAL_VARS:
            value = os.getenv(var, '').strip()
            if not value:
                missing.append(var)
            elif var in ['TELEGRAM_BOT_TOKEN', 'KIE_API_KEY'] and len(value) < 10:
                missing.append(f"{var} (too short)")
        
        if missing:
            print("CRITICAL: Missing environment variables:")
            for var in missing:
                print(f"   - {var}")
            print("\nSet these variables in your environment or .env file")
            print("See .env.example for template")
            sys.exit(1)
        
        print("All critical environment variables are set")
    
    @classmethod
    def validate_recommended(cls) -> None:
        """Validate recommended environment variables."""
        missing = []
        
        for var in cls.RECOMMENDED_VARS:
            value = os.getenv(var, '').strip()
            if not value:
                missing.append(var)
        
        if missing:
            print("WARNING: Missing recommended environment variables:")
            for var in missing:
                print(f"   - {var}")
            print("\nConsider setting these for optimal operation")
        else:
            print("All recommended environment variables are set")
    
    @classmethod
    def validate_all(cls) -> None:
        """Validate all environment variables."""
        print("Validating environment variables...")
        
        cls.validate_critical()
        cls.validate_recommended()
        
        print("Environment validation completed")


@lru_cache(maxsize=1)
def get_redactor() -> SecretRedactor:
    """Get cached redactor instance."""
    return SecretRedactor()


@lru_cache(maxsize=1)
def get_validator() -> EnvValidator:
    """Get cached validator instance."""
    return EnvValidator()


def redact_log_message(message: str) -> str:
    """Convenience function to redact secrets in log messages."""
    return get_redactor().redact(message)


def safe_log_env_vars() -> Dict[str, str]:
    """Log environment variables safely with redaction."""
    env_vars = {}
    
    # Critical variables (redacted)
    for var in EnvValidator.CRITICAL_VARS:
        value = os.getenv(var, '')
        if value:
            if var in ['TELEGRAM_BOT_TOKEN', 'KIE_API_KEY']:
                env_vars[var] = f"[SET] ({len(value)} chars)"
            else:
                env_vars[var] = SecretRedactor.redact(value)
        else:
            env_vars[var] = "[NOT SET]"
    
    # Recommended variables
    for var in EnvValidator.RECOMMENDED_VARS:
        value = os.getenv(var, '')
        env_vars[var] = value if value else "[NOT SET]"
    
    return env_vars


def validate_environment_on_startup() -> None:
    """Validate environment on application startup."""
    try:
        get_validator().validate_all()
    except SystemExit as e:
        # Re-raise with context
        print("Environment validation failed - cannot start application")
        raise e


if __name__ == "__main__":
    # Test the validation
    validate_environment_on_startup()
    
    # Test redaction
    test_text = "Bot token: 1234567890:ABCDEFghijklmnopqrstuvwxyz123456789 and API key: rnd_1234567890abcdef1234567890abcdef"
    print(f"Original: {test_text}")
    print(f"Redacted: {redact_log_message(test_text)}")
