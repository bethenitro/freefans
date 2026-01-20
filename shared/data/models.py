"""
Database Models - SQLAlchemy models for Supabase PostgreSQL
Mirrors the existing SQLite schema for seamless dual storage
"""

from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Text, Boolean, Index, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
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

class LandingPage(Base):
    """
    Landing page model - stores landing page data for content links
    """
    __tablename__ = 'landing_pages'
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Landing page identification
    short_id = Column(String(16), nullable=False, unique=True, index=True)
    
    # Content metadata
    creator = Column(String(255), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    content_type = Column(String(50), nullable=False)
    original_url = Column(Text, nullable=False)
    preview_url = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_landing_short_id', short_id),
        Index('idx_landing_creator', creator),
        Index('idx_landing_expires_at', expires_at),
    )
    
    def __repr__(self):
        return f"<LandingPage(id={self.id}, short_id='{self.short_id}', creator='{self.creator}')>"

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


class UserProfile(Base):
    """
    User profile model - stores user payment and subscription data
    """
    __tablename__ = 'user_profiles'
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # User identification
    user_id = Column(BigInteger, nullable=False, unique=True, index=True)  # Telegram user ID
    username = Column(String(255), nullable=True)  # Telegram username
    
    # Payment data
    balance = Column(Integer, default=0)  # Balance in Telegram Stars
    total_spent = Column(Integer, default=0)  # Total spent in Stars
    total_contributed = Column(Integer, default=0)  # Total contributed to pools
    
    # Subscription data
    subscription_tier = Column(String(50), default='free')  # free, basic, premium
    subscription_expires = Column(DateTime(timezone=True), nullable=True)
    
    # Usage tracking
    total_searches = Column(Integer, default=0)
    total_downloads = Column(Integer, default=0)
    pools_joined = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_user_profile_user_id', user_id),
        Index('idx_user_profile_subscription', subscription_tier),
    )
    
    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, balance={self.balance}, tier='{self.subscription_tier}')>"


class ContentPool(Base):
    """
    Content pool model - stores community pooling data for content requests
    """
    __tablename__ = 'content_pools'
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Pool identification
    pool_id = Column(String(50), nullable=False, unique=True, index=True)  # e.g., "POOL-20240115-001"
    
    # Content details
    creator_name = Column(String(255), nullable=False, index=True)
    content_title = Column(String(500), nullable=False)
    content_description = Column(Text, nullable=True)
    content_type = Column(String(50), nullable=False)  # 'photo_set', 'video', 'live_stream'
    
    # Pool economics
    total_cost = Column(Integer, nullable=False)  # Total cost for the content in Stars
    current_amount = Column(Integer, default=0)  # Current contributed amount
    contributors_count = Column(Integer, default=0)  # Number of contributors
    max_contributors = Column(Integer, default=100)  # Maximum number of contributors allowed
    current_price_per_user = Column(Integer, nullable=False)  # Current price per user (dynamic)
    
    # Pool status
    status = Column(String(50), default='active')  # active, completed, cancelled, expired
    completion_percentage = Column(Float, default=0.0)  # Calculated field
    
    # Pool metadata
    request_id = Column(String(50), nullable=True, index=True)  # Related request ID from CSV
    created_by = Column(BigInteger, nullable=False, index=True)  # User ID who created the pool
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Content delivery
    content_url = Column(Text, nullable=True)  # URL when content is unlocked
    landing_page_id = Column(String(16), nullable=True)  # Landing page short ID
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    contributions = relationship("PoolContribution", back_populates="pool")
    
    # Indexes
    __table_args__ = (
        Index('idx_pool_creator', creator_name),
        Index('idx_pool_status', status),
        Index('idx_pool_expires_at', expires_at),
        Index('idx_pool_created_by', created_by),
    )
    
    def __repr__(self):
        return f"<ContentPool(pool_id='{self.pool_id}', creator='{self.creator_name}', status='{self.status}')>"


class PoolContribution(Base):
    """
    Pool contribution model - stores individual user contributions to pools
    """
    __tablename__ = 'pool_contributions'
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Contribution identification
    contribution_id = Column(String(50), nullable=False, unique=True, index=True)
    
    # Relationships
    user_id = Column(BigInteger, nullable=False, index=True)  # Telegram user ID
    pool_id = Column(String(50), ForeignKey('content_pools.pool_id'), nullable=False, index=True)
    
    # Contribution details
    amount = Column(Integer, nullable=False)  # Amount in Telegram Stars
    payment_charge_id = Column(String(255), nullable=True)  # Telegram payment charge ID
    
    # Status
    status = Column(String(50), default='pending')  # pending, completed, refunded, failed
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    pool = relationship("ContentPool", back_populates="contributions")
    
    # Indexes
    __table_args__ = (
        Index('idx_contribution_user_id', user_id),
        Index('idx_contribution_pool_id', pool_id),
        Index('idx_contribution_status', status),
    )
    
    def __repr__(self):
        return f"<PoolContribution(user_id={self.user_id}, pool_id='{self.pool_id}', amount={self.amount})>"


class Transaction(Base):
    """
    Transaction model - stores all payment transactions
    """
    __tablename__ = 'transactions'
    
    # Primary key
    id = Column(Integer, primary_key=True, index=True)
    
    # Transaction identification
    transaction_id = Column(String(50), nullable=False, unique=True, index=True)
    
    # Transaction details
    user_id = Column(BigInteger, nullable=False, index=True)  # Telegram user ID
    transaction_type = Column(String(50), nullable=False)  # 'pool_contribution', 'subscription', 'refund'
    amount = Column(Integer, nullable=False)  # Amount in Telegram Stars
    
    # Related entities
    pool_id = Column(String(50), nullable=True, index=True)  # If related to a pool
    contribution_id = Column(String(50), nullable=True)  # If related to a contribution
    
    # Payment details
    payment_charge_id = Column(String(255), nullable=True)  # Telegram payment charge ID
    payment_method = Column(String(50), default='telegram_stars')
    
    # Status
    status = Column(String(50), default='pending')  # pending, completed, failed, refunded
    
    # Metadata
    description = Column(Text, nullable=True)
    extra_data = Column(Text, nullable=True)  # JSON string for additional data
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Indexes
    __table_args__ = (
        Index('idx_transaction_user_id', user_id),
        Index('idx_transaction_type', transaction_type),
        Index('idx_transaction_status', status),
        Index('idx_transaction_pool_id', pool_id),
    )
    
    def __repr__(self):
        return f"<Transaction(transaction_id='{self.transaction_id}', user_id={self.user_id}, amount={self.amount})>"