"""
Database Models - SQLAlchemy models for Supabase PostgreSQL
Mirrors the existing SQLite schema for seamless dual storage
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Index
from sqlalchemy.sql import func
from shared.config.database import Base

class Creator(Base):
    """
    Creator model - stores creator metadata and cached content
    Mirrors the existing SQLite 'creators' table structure
    """
    __tablename__ = 'creators'
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Creator identification
    name = Column(String(255), nullable=False, index=True)
    
    # Content metadata (stored as JSON text)
    content = Column(Text, nullable=True)  # JSON string of posts/content
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Cache metadata
    post_count = Column(Integer, default=0)
    last_scraped = Column(DateTime(timezone=True), nullable=True)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_creator_name_lower', func.lower(name)),
        Index('idx_creator_updated_at', updated_at),
        Index('idx_creator_last_scraped', last_scraped),
    )
    
    def __repr__(self):
        return f"<Creator(id={self.id}, name='{self.name}', posts={self.post_count})>"

class OnlyFansUser(Base):
    """
    OnlyFans user model - stores OnlyFans specific user data
    Mirrors the existing SQLite 'onlyfans_users' table structure
    """
    __tablename__ = 'onlyfans_users'
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User identification
    username = Column(String(255), nullable=False, unique=True, index=True)
    
    # User metadata
    display_name = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def __repr__(self):
        return f"<OnlyFansUser(id={self.id}, username='{self.username}')>"

class OnlyFansPost(Base):
    """
    OnlyFans post model - stores individual post data
    Mirrors the existing SQLite 'onlyfans_posts' table structure
    """
    __tablename__ = 'onlyfans_posts'
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Post identification
    username = Column(String(255), nullable=False, index=True)
    post_id = Column(String(255), nullable=True)
    
    # Post content (stored as JSON text)
    content = Column(Text, nullable=True)  # JSON string of post data
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_onlyfans_username', username),
        Index('idx_onlyfans_post_id', post_id),
        Index('idx_onlyfans_updated_at', updated_at),
    )
    
    def __repr__(self):
        return f"<OnlyFansPost(id={self.id}, username='{self.username}', post_id='{self.post_id}')>"