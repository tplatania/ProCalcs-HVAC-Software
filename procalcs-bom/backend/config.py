"""
config.py — Centralized configuration for ProCalcs BOM
Single source of truth for all environment-based settings.
Follows ProCalcs Design Standards v2.0
"""

import os
import logging
from dotenv import load_dotenv

# ===============================
# Environment Loading
# ===============================

load_dotenv('.env.local', override=True)  # Local dev overrides
load_dotenv('.env')                        # Base config


# ===============================
# Configuration Class
# ===============================

class Config:
    """Base configuration — all environments inherit from this."""

    # App
    APP_NAME = "ProCalcs BOM"
    VERSION  = "1.0.0"
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-production')

    # Anthropic AI
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    ANTHROPIC_MODEL   = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
    ANTHROPIC_MAX_TOKENS = int(os.environ.get('ANTHROPIC_MAX_TOKENS', '4096'))

    # Firestore
    FIRESTORE_PROJECT_ID   = os.environ.get('FIRESTORE_PROJECT_ID', '')
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')

    # CORS — Designer Desktop + Dashboard origins (comma-separated env).
    # Whitespace-tolerant: "a, b,, c " -> ["a", "b", "c"].
    ALLOWED_ORIGINS = [
        o.strip()
        for o in os.environ.get(
            'ALLOWED_ORIGINS',
            'http://localhost:3000,http://localhost:5173'
        ).split(',')
        if o.strip()
    ]

    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    # Admin access
    ADMIN_EMAILS = [
        e.strip()
        for e in os.environ.get('ADMIN_EMAILS', '').split(',')
        if e.strip()
    ]

    # Shared-secret auth — every non-health request must present the same
    # token via X-Procalcs-Service-Token. BFFs (Designer Desktop, Designer
    # Dashboard) keep this in their own env and forward it per request.
    # Leaving this blank disables the check (dev only).
    SERVICE_SHARED_SECRET = os.environ.get('SERVICE_SHARED_SECRET', '')

    # ---------------------------------------------------------------------
    # Billing / subscriptions (Apr 30 2026 — see _repo-docs/SAAS_BILLING_DESIGN.md)
    # ---------------------------------------------------------------------

    # Master switch. When false (the default in dev), billing routes still
    # mount and webhooks still record events, but per-request usage gating
    # is bypassed and the SPA hides billing UI. Lets the internal MVP run
    # without any billing surface visible to the team.
    BILLING_ENABLED = os.environ.get('BILLING_ENABLED', 'false').lower() == 'true'

    # Postgres connection. Two paths:
    #   - DATABASE_URL set explicitly (local dev, e.g. sqlite:///billing.db
    #     or a direct postgresql+pg8000:// URL pointing at a local Postgres)
    #   - INSTANCE_CONNECTION_NAME + DB_USER/DB_PASS/DB_NAME for Cloud SQL
    #     in production (matches Ask-Your-HVAC-Pro's pattern).
    # If neither is set, SQLAlchemy is initialized against an in-memory
    # SQLite — every test creates schema fresh, prod logs a loud warning.
    DATABASE_URL                = os.environ.get('DATABASE_URL', '')
    INSTANCE_CONNECTION_NAME    = os.environ.get('INSTANCE_CONNECTION_NAME', '')
    DB_USER                     = os.environ.get('DB_USER', '')
    DB_PASS                     = os.environ.get('DB_PASS', '')
    DB_NAME                     = os.environ.get('DB_NAME', 'procalcs_billing')

    SQLALCHEMY_DATABASE_URI = (
        DATABASE_URL or 'sqlite:///:memory:'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # silence flask-sqlalchemy warning

    # Stripe — live + publishable + webhook signing secret. All three are
    # safe to be empty in dev (billing routes return a clear "not
    # configured" error rather than crashing).
    STRIPE_SECRET_KEY     = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

    # Stripe price IDs per plan. Keys match TIER_PLANS below.
    # Each plan has both a monthly and annual price ID; populated via env.
    STRIPE_PRICES = {
        'starter_monthly':    os.environ.get('STRIPE_PRICE_STARTER_MONTHLY', ''),
        'starter_yearly':     os.environ.get('STRIPE_PRICE_STARTER_YEARLY', ''),
        'pro_monthly':        os.environ.get('STRIPE_PRICE_PRO_MONTHLY', ''),
        'pro_yearly':         os.environ.get('STRIPE_PRICE_PRO_YEARLY', ''),
        # Enterprise is custom-quoted; no Stripe price ID — handled by sales.
    }

    # Trial length in days for new signups. No credit card required to
    # start a trial (lowest signup friction); they're prompted for one
    # when the trial expires or when they explicitly upgrade.
    TRIAL_DAYS = int(os.environ.get('TRIAL_DAYS', '14'))

    # Domain that gets the free internal tier automatically (no billing
    # check, unlimited everything). Matches the existing OAuth domain
    # restriction in designer-desktop's auth config.
    INTERNAL_DOMAIN = os.environ.get('INTERNAL_DOMAIN', 'procalcs.net')


# ---------------------------------------------------------------------
# Tier definitions — single source of truth for limits + pricing display.
# Stripe holds the actual money side; this dict tells the rest of the
# code what a tier MEANS in terms of behavior.
# ---------------------------------------------------------------------

# bom_limit semantics:
#   -1   = unlimited
#    N   = N BOMs per calendar month, resets via invoice.paid webhook
#          (and a 30-day safety net in the User model — same pattern as
#          Ask-Your-HVAC-Pro).
TIER_LIMITS = {
    'internal': {
        'label':           'Internal',
        'bom_limit':       -1,
        'price_monthly':   None,   # not for sale; assigned to @procalcs.net
        'price_yearly':    None,
        'features':        ['unlimited_boms', 'all_features'],
    },
    'trial': {
        'label':           'Trial',
        'bom_limit':       5,
        'price_monthly':   0,
        'price_yearly':    0,
        'features':        ['core_bom', 'pdf_output'],
    },
    'starter': {
        'label':           'Starter',
        'bom_limit':       25,
        'price_monthly':   None,   # PLACEHOLDER — Tom to lock
        'price_yearly':    None,
        'features':        ['core_bom', 'pdf_output', 'csv_export'],
    },
    'pro': {
        'label':           'Pro',
        'bom_limit':       -1,
        'price_monthly':   None,   # PLACEHOLDER — Tom to lock
        'price_yearly':    None,
        'features':        ['core_bom', 'pdf_output', 'csv_export', 'priority_support'],
    },
    'enterprise': {
        'label':           'Enterprise',
        'bom_limit':       -1,
        'price_monthly':   None,   # custom quoted — handled by sales
        'price_yearly':    None,
        'features':        ['core_bom', 'pdf_output', 'csv_export', 'priority_support', 'custom_branding', 'sso'],
    },
}

# Map Stripe price-IDs (sent in checkout) to the tier they grant.
# Inverse of STRIPE_PRICES on the Config class — built at runtime.
def plan_to_tier(plan_key: str) -> str:
    """starter_monthly -> 'starter', pro_yearly -> 'pro', etc."""
    return plan_key.split('_', 1)[0] if plan_key else 'trial'


class DevelopmentConfig(Config):
    """Local development settings."""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Google Cloud Run production settings."""
    DEBUG = False
    TESTING = False


# ===============================
# Config Selector
# ===============================

config_map = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
}

def get_config():
    """Return the correct config class based on environment."""
    env = os.environ.get('FLASK_ENV', 'development')
    return config_map.get(env, DevelopmentConfig)

# ===============================
# Startup Validation
# ===============================

def validate_config(app):
    """
    Validate required config on startup.
    Fails fast with clear error messages so missing env vars
    are caught immediately rather than at runtime.
    """
    logger = logging.getLogger('procalcs_bom')
    required = {
        'ANTHROPIC_API_KEY': app.config.get('ANTHROPIC_API_KEY'),
        'FIRESTORE_PROJECT_ID': app.config.get('FIRESTORE_PROJECT_ID'),
        'SECRET_KEY': app.config.get('SECRET_KEY'),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        for key in missing:
            logger.error("Missing required environment variable: %s", key)
        raise RuntimeError(
            "Missing required config: %s. Check .env file." % ', '.join(missing)
        )

    # SERVICE_SHARED_SECRET is a soft-required — warn loudly in non-dev
    # environments but don't refuse to boot (keeps dev workflow frictionless).
    if not app.config.get('SERVICE_SHARED_SECRET'):
        if os.environ.get('FLASK_ENV') == 'production':
            logger.warning(
                "[WARNING] SERVICE_SHARED_SECRET is empty — shared-secret auth "
                "is DISABLED. Any caller can hit the BOM endpoints."
            )
        else:
            logger.info(
                "SERVICE_SHARED_SECRET not set — auth middleware is disabled "
                "(dev mode). Set it to enable shared-secret auth."
            )

    logger.info("Config validated successfully for environment: %s",
                os.environ.get('FLASK_ENV', 'development'))
