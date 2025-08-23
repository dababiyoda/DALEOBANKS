"""
SQLAlchemy models for DaLeoBanks database
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class Tweet(Base):
    """Tweet records with engagement metrics"""
    __tablename__ = 'tweets'
    
    id = Column(String, primary_key=True)
    text = Column(Text, nullable=False)
    kind = Column(String, nullable=False)  # proposal|reply|quote
    topic = Column(Text)
    hour_bin = Column(Integer)
    cta_variant = Column(Text)
    ref_tweet_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    likes = Column(Integer, default=0)
    rts = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    quotes = Column(Integer, default=0)
    authority_score = Column(Float, default=0.0)
    j_score = Column(Float, default=0.0)

class Action(Base):
    """Action logs for all system activities"""
    __tablename__ = 'actions'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(String, nullable=False)
    meta_json = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class KPI(Base):
    """KPI tracking over time"""
    __tablename__ = 'kpis'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)

class Note(Base):
    """Improvement notes and reflections"""
    __tablename__ = 'notes'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class FollowersSnapshot(Base):
    """Daily follower count snapshots"""
    __tablename__ = 'followers_snapshot'
    
    ts = Column(DateTime, primary_key=True)
    follower_count = Column(Integer, nullable=False)

class Redirect(Base):
    """Tracked redirect links for revenue measurement"""
    __tablename__ = 'redirects'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    label = Column(Text, nullable=False)
    target_url = Column(Text, nullable=False)
    utm = Column(Text)
    clicks = Column(Integer, default=0)
    revenue = Column(Float, default=0.0)

class ArmsLog(Base):
    """Multi-armed bandit experiment logs"""
    __tablename__ = 'arms_log'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tweet_id = Column(String)
    post_type = Column(String, nullable=False)
    topic = Column(Text)
    hour_bin = Column(Integer)
    cta_variant = Column(Text)
    sampled_prob = Column(Float)
    reward_j = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

class PersonaVersion(Base):
    """Persona version history with audit trail"""
    __tablename__ = 'persona_versions'
    
    version = Column(Integer, primary_key=True)
    hash = Column(String, nullable=False)
    actor = Column(Text)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

