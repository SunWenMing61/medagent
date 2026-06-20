from fastapi import APIRouter

from app.api.v1 import auth, users, knowledge_base, documents, chat, feedback, admin, sources

router = APIRouter(prefix="/api")

router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(users.router, prefix="/users", tags=["Users"])
router.include_router(knowledge_base.router, prefix="/kb", tags=["Knowledge Base"])
router.include_router(documents.router, prefix="/documents", tags=["Documents"])
router.include_router(sources.router, prefix="/sources", tags=["Sources"])
router.include_router(chat.router, prefix="/chat", tags=["Chat"])
router.include_router(feedback.router, prefix="/feedback", tags=["Feedback"])
router.include_router(admin.router, prefix="/admin", tags=["Admin"])
