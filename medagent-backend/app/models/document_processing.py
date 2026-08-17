"""Raw/Clean document layers and parser quality/audit records."""

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint, func

from app.db.base import MySQLBase


class DocumentPage(MySQLBase):
    __tablename__ = "document_page"
    __table_args__ = (UniqueConstraint("document_id", "page_num", name="uq_document_page_number"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, nullable=False, index=True)
    page_num = Column(Integer, nullable=False)
    page_type = Column(String(32), nullable=False, index=True)
    extraction_method = Column(String(32), nullable=False)
    raw_text = Column(Text, nullable=False, default="")
    cleaned_text = Column(Text, nullable=False, default="")
    width = Column(Float)
    height = Column(Float)
    classification_json = Column(JSON)
    ocr_spans_json = Column(JSON)
    ocr_confidence = Column(Float)
    quality_score = Column(Float)
    quality_status = Column(String(32), nullable=False, default="good", index=True)
    warnings_json = Column(JSON)
    metadata_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class DocumentRawBlock(MySQLBase):
    __tablename__ = "document_raw_block"
    __table_args__ = (UniqueConstraint("document_id", "block_id", name="uq_document_raw_block"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, nullable=False, index=True)
    page_num = Column(Integer, nullable=False, index=True)
    block_id = Column(String(96), nullable=False)
    block_type = Column(String(32), nullable=False)
    text = Column(Text, nullable=False, default="")
    bbox_json = Column(JSON)
    spans_json = Column(JSON)
    reading_order = Column(Integer, nullable=False, default=0)
    extraction_method = Column(String(32), nullable=False)
    confidence = Column(Float)
    metadata_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class DocumentCleanBlock(MySQLBase):
    __tablename__ = "document_clean_block"
    __table_args__ = (UniqueConstraint("document_id", "block_id", name="uq_document_clean_block"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, nullable=False, index=True)
    raw_block_id = Column(BigInteger, nullable=True, index=True)
    page_num = Column(Integer, nullable=False, index=True)
    block_id = Column(String(96), nullable=False)
    block_type = Column(String(32), nullable=False, index=True)
    text = Column(Text, nullable=False)
    bbox_json = Column(JSON)
    section_path_json = Column(JSON)
    reading_order = Column(Integer, nullable=False, default=0)
    extraction_method = Column(String(32), nullable=False)
    metadata_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class DocumentTable(MySQLBase):
    __tablename__ = "document_table"
    __table_args__ = (UniqueConstraint("document_id", "table_id", name="uq_document_table"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, nullable=False, index=True)
    table_id = Column(String(96), nullable=False)
    title = Column(String(500))
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    section_path_json = Column(JSON)
    headers_json = Column(JSON)
    rows_json = Column(JSON)
    units_json = Column(JSON)
    footnotes_json = Column(JSON)
    markdown = Column(Text, nullable=False)
    bbox_json = Column(JSON)
    extraction_method = Column(String(32), nullable=False)
    confidence = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())


class DocumentQualityReportRecord(MySQLBase):
    __tablename__ = "document_quality_report"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, nullable=False, unique=True, index=True)
    report_json = Column(JSON, nullable=False)
    overall_quality = Column(String(32), nullable=False, index=True)
    average_ocr_confidence = Column(Float)
    low_quality_pages_json = Column(JSON)
    warnings_json = Column(JSON)
    reviewed_by = Column(BigInteger)
    review_status = Column(String(32), nullable=False, default="not_required", index=True)
    review_comment = Column(Text)
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DocumentCleaningActionRecord(MySQLBase):
    __tablename__ = "document_cleaning_action"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, nullable=False, index=True)
    page_num = Column(Integer, nullable=False, index=True)
    block_id = Column(String(96), nullable=False, index=True)
    action_type = Column(String(64), nullable=False, index=True)
    original_text = Column(Text, nullable=False)
    cleaned_text = Column(Text, nullable=False)
    rule = Column(String(255), nullable=False)
    confidence = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
