"""
Database Configuration - SQLAlchemy setup for Supabase PostgreSQL integration
Handles connection pooling, session management, and base model definitions
"""

import os
import logging
from typing import Generator
from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from decouple import config

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = config('SUPABASE_DATABASE_URL', default=None)
ENABLE_SUPABASE = config('ENABLE_SUPABASE', default=False, cast=bool)

# SQLAlchemy engine configuration
engine = None
SessionLocal = None
Base = declarative_base()

def init_database():
    """Initialize database engine and session factory."""
    global engine, SessionLocal
    
    if not ENABLE_SUPABASE or not DATABASE_URL:
        logger.info("Supabase integration disabled or no database URL provided")
        return False
    
    try:
        # Create engine with connection pooling
        engine = create_engine(
            DATABASE_URL,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before use
            pool_recycle=3600,   # Recycle connections every hour
            echo=False  # Set to True for SQL query logging
        )
        
        # Create session factory
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine
        )
        
        logger.info("✓ Supabase database connection initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Failed to initialize Supabase database: {e}")
        return False

def create_tables():
    """Create all tables defined in models."""
    if engine is None:
        logger.warning("Database engine not initialized")
        return False
    
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables created/verified successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to create database tables: {e}")
        return False

def get_db_session() -> Generator[Session, None, None]:
    """
    Dependency function to get database session with automatic cleanup.
    Use this in your application code for proper session management.
    """
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_session_sync() -> Session:
    """
    Get a database session for synchronous operations.
    Remember to close the session when done.
    """
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    return SessionLocal()

def is_database_available() -> bool:
    """Check if Supabase database is available and configured."""
    return ENABLE_SUPABASE and DATABASE_URL is not None and engine is not None