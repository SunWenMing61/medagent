"""Pairwise preference learning for concise versus detailed safe answers."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.answer_preference import AnswerPreference, UserAnswerPreferenceProfile
from app.models.chat import ChatMessage, ChatSession
from app.schemas.memory import MemoryCandidate
from app.services.memory_service import agent_memory_service


STYLES = {"concise_evidence", "detailed_guidance"}
logger = logging.getLogger(__name__)


class AnswerPreferenceService:
    def get_profile(self, db: Session, *, tenant_id: int, user_id: int) -> dict[str, Any]:
        row = db.query(UserAnswerPreferenceProfile).filter_by(
            tenant_id=tenant_id, user_id=user_id,
        ).first()
        if not row:
            return {
                "preferred_style": "concise_evidence",
                "preference_strength": 0.5,
                "concise_votes": 0,
                "detailed_votes": 0,
                "total_choices": 0,
                "profile_version": 0,
            }
        return self._profile(row)

    def record_choice(
        self,
        db: Session,
        *,
        tenant_id: int,
        user_id: int,
        message_id: int,
        chosen_variant_id: str,
    ) -> dict[str, Any]:
        message = db.query(ChatMessage).join(
            ChatSession, ChatSession.id == ChatMessage.session_id,
        ).filter(
            ChatMessage.id == message_id,
            ChatSession.user_id == user_id,
        ).first()
        if not message:
            raise LookupError("Answer message not found")
        variants = message.answer_variants_json or []
        chosen = next((item for item in variants if item.get("variant_id") == chosen_variant_id), None)
        if not chosen:
            raise ValueError("Unknown answer variant")
        rejected = next((item for item in variants if item.get("variant_id") != chosen_variant_id), None)
        if not rejected:
            raise ValueError("Pairwise preference requires two answer variants")
        if chosen.get("style") not in STYLES or rejected.get("style") not in STYLES:
            raise ValueError("Unsupported answer style")

        profile = db.query(UserAnswerPreferenceProfile).filter_by(
            tenant_id=tenant_id, user_id=user_id,
        ).first()
        if not profile:
            profile = UserAnswerPreferenceProfile(tenant_id=tenant_id, user_id=user_id)
            db.add(profile)
            db.flush()
        existing = db.query(AnswerPreference).filter_by(user_id=user_id, message_id=message_id).first()
        changed = existing is None or existing.chosen_variant_id != chosen_variant_id
        if changed and existing:
            self._change_vote(profile, existing.chosen_style, -1)
        if changed:
            self._change_vote(profile, chosen["style"], 1)
        if not existing:
            existing = AnswerPreference(
                tenant_id=tenant_id, user_id=user_id, session_id=message.session_id,
                message_id=message.id,
            )
            db.add(existing)
        existing.request_id = chosen.get("request_id")
        existing.chosen_variant_id = chosen_variant_id
        existing.rejected_variant_id = rejected["variant_id"]
        existing.chosen_style = chosen["style"]
        existing.rejected_style = rejected["style"]
        existing.context_json = {
            "recommended_variant_id": message.recommended_variant_id,
            "changed_existing_choice": bool(changed and message.selected_variant_id),
        }
        message.selected_variant_id = chosen_variant_id
        message.content = chosen.get("answer") or message.content
        message.references_json = chosen.get("citations") or message.references_json
        self._refresh_profile(profile)
        if changed:
            try:
                agent_memory_service.write_candidate(
                    db,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    candidate=MemoryCandidate(
                        category="communication_style",
                        subject="user",
                        predicate="answer_detail_level",
                        value=profile.preferred_style,
                        source_message_ids=[str(message.id)],
                        confidence=float(profile.preference_strength or 0.5),
                        importance=0.8,
                        reason_to_remember="Explicit pairwise answer choice",
                        source_type="user_confirmed",
                        source_role="user",
                        explicit_instruction=True,
                        confirmed=True,
                    ),
                    agent_name="user_control",
                    operator_type="user",
                    operator_id=str(user_id),
                )
            except Exception:
                logger.exception("Failed to synchronize pairwise choice into Agent Memory")
        db.flush()
        return {
            "message_id": message.id,
            "chosen_variant_id": chosen_variant_id,
            "changed": changed,
            "profile": self._profile(profile),
        }

    @staticmethod
    def _change_vote(profile: UserAnswerPreferenceProfile, style: str, delta: int) -> None:
        if style == "detailed_guidance":
            profile.detailed_votes = max(0, int(profile.detailed_votes or 0) + delta)
        else:
            profile.concise_votes = max(0, int(profile.concise_votes or 0) + delta)

    @staticmethod
    def _refresh_profile(profile: UserAnswerPreferenceProfile) -> None:
        concise = int(profile.concise_votes or 0)
        detailed = int(profile.detailed_votes or 0)
        total = concise + detailed
        profile.total_choices = total
        profile.preferred_style = "detailed_guidance" if detailed > concise else "concise_evidence"
        profile.preference_strength = (max(concise, detailed) + 1) / (total + 2)
        profile.profile_version = int(profile.profile_version or 0) + 1

    @staticmethod
    def _profile(row: UserAnswerPreferenceProfile) -> dict[str, Any]:
        return {
            "preferred_style": row.preferred_style,
            "preference_strength": float(row.preference_strength or 0.5),
            "concise_votes": int(row.concise_votes or 0),
            "detailed_votes": int(row.detailed_votes or 0),
            "total_choices": int(row.total_choices or 0),
            "profile_version": int(row.profile_version or 0),
        }


answer_preference_service = AnswerPreferenceService()
