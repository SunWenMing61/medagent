"""Pairwise answer choices and the continuously updated per-user style profile."""

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, JSON, String, UniqueConstraint, func

from app.db.base import MySQLBase


class AnswerPreference(MySQLBase):
    __tablename__ = "answer_preference"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_answer_preference_user_message"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    session_id = Column(BigInteger, nullable=False, index=True)
    message_id = Column(BigInteger, nullable=False, index=True)
    request_id = Column(String(64), nullable=True, index=True)
    chosen_variant_id = Column(String(64), nullable=False)
    rejected_variant_id = Column(String(64), nullable=False)
    chosen_style = Column(String(32), nullable=False, index=True)
    rejected_style = Column(String(32), nullable=False)
    context_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserAnswerPreferenceProfile(MySQLBase):
    __tablename__ = "user_answer_preference_profile"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_user_answer_preference_profile"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    concise_votes = Column(Integer, nullable=False, default=0)
    detailed_votes = Column(Integer, nullable=False, default=0)
    total_choices = Column(Integer, nullable=False, default=0)
    preferred_style = Column(String(32), nullable=False, default="concise_evidence")
    preference_strength = Column(Float, nullable=False, default=0.5)
    profile_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
