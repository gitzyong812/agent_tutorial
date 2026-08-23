"""知识库接口：标签、文档增删改查、上传、重建索引与检索调试。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..rag import indexer, parser, retriever

router = APIRouter(prefix="/api", tags=["knowledge"])


# ---------- 标签 ----------
@router.get("/tags", response_model=list[schemas.TagOut])
def list_tags(db: Session = Depends(get_db)):
    return db.query(models.KnowledgeTag).order_by(models.KnowledgeTag.id).all()


@router.post("/tags", response_model=schemas.TagOut)
def create_tag(payload: schemas.TagIn, db: Session = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="标签名不能为空")
    if db.query(models.KnowledgeTag).filter(models.KnowledgeTag.name == name).first():
        raise HTTPException(status_code=400, detail="标签已存在")
    obj = models.KnowledgeTag(name=name)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    obj = db.get(models.KnowledgeTag, tag_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.delete(obj)
    db.commit()
    return {"ok": True}


# ---------- 文档 ----------
def _get_doc_or_404(db: Session, document_id: int) -> models.KnowledgeDocument:
    obj = db.get(models.KnowledgeDocument, document_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return obj


def _apply_tags(db: Session, document: models.KnowledgeDocument, tag_ids: list[int]) -> None:
    """按标签 id 列表设置文档标签。"""
    if tag_ids:
        document.tags = db.query(models.KnowledgeTag).filter(models.KnowledgeTag.id.in_(tag_ids)).all()
    else:
        document.tags = []


@router.get("/documents", response_model=list[schemas.DocumentOut])
def list_documents(tag_id: int | None = None, keyword: str | None = None, db: Session = Depends(get_db)):
    """文档列表，支持按标签筛选与名称/来源关键词搜索。"""
    query = db.query(models.KnowledgeDocument)
    if tag_id:
        query = query.join(models.KnowledgeDocument.tags).filter(models.KnowledgeTag.id == tag_id)
    if keyword:
        like = f"%{keyword.strip()}%"
        query = query.filter(
            models.KnowledgeDocument.name.like(like) | models.KnowledgeDocument.source.like(like)
        )
    return query.order_by(models.KnowledgeDocument.id.desc()).all()


@router.post("/documents", response_model=schemas.DocumentDetailOut)
def create_document(payload: schemas.DocumentIn, db: Session = Depends(get_db)):
    """创建文档（粘贴文本），保存后立即分块并建索引。"""
    obj = models.KnowledgeDocument(
        name=payload.name.strip() or "未命名文档",
        source=payload.source,
        version=payload.version,
        content=payload.content,
        file_type=payload.file_type,
        expires_at=payload.expires_at,
        status="pending",
    )
    _apply_tags(db, obj, payload.tag_ids)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    indexer.reindex_document(db, obj)
    return obj


@router.post("/documents/upload", response_model=schemas.DocumentDetailOut)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """上传 .txt / .md 文件，读取文本后入库并建索引。"""
    raw = await file.read()
    text = raw.decode("utf-8", errors="ignore")
    obj = models.KnowledgeDocument(
        name=file.filename or "上传文档",
        source=file.filename or "",
        content=text,
        file_type=parser.detect_file_type(file.filename or ""),
        status="pending",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    indexer.reindex_document(db, obj)
    return obj


@router.get("/documents/{document_id}", response_model=schemas.DocumentDetailOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    return _get_doc_or_404(db, document_id)


@router.put("/documents/{document_id}", response_model=schemas.DocumentDetailOut)
def update_document(document_id: int, payload: schemas.DocumentIn, db: Session = Depends(get_db)):
    """编辑文档：更新内容/标签/有效期后重新索引。"""
    obj = _get_doc_or_404(db, document_id)
    obj.name = payload.name.strip() or obj.name
    obj.source = payload.source
    obj.version = payload.version
    obj.content = payload.content
    obj.file_type = payload.file_type
    obj.expires_at = payload.expires_at
    _apply_tags(db, obj, payload.tag_ids)
    db.commit()
    indexer.reindex_document(db, obj)
    return obj


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    obj = _get_doc_or_404(db, document_id)
    db.delete(obj)  # 关联片段通过 cascade 一并删除
    db.commit()
    return {"ok": True}


@router.post("/documents/{document_id}/reindex", response_model=schemas.DocumentDetailOut)
def reindex_document(document_id: int, strategy: str = "structure", db: Session = Depends(get_db)):
    """重建索引，可指定分块策略（structure / fixed），便于对比检索效果。"""
    obj = _get_doc_or_404(db, document_id)
    return indexer.reindex_document(db, obj, strategy=strategy)


# ---------- 检索调试 ----------
@router.post("/knowledge/search", response_model=list[schemas.PassageOut])
def search_knowledge(payload: schemas.SearchIn, db: Session = Depends(get_db)):
    """检索调试：直接返回命中片段与分数，便于教学观察“检索是否命中”。"""
    passages = retriever.search(
        db,
        query=payload.query,
        tag_ids=payload.tag_ids,
        top_k=payload.top_k,
        retriever_type=payload.retriever_type,
    )
    return [
        schemas.PassageOut(
            document_id=p.document_id,
            document_name=p.document_name,
            source_title=p.source_title,
            embedding_model_name=p.embedding_model_name,
            content=p.content,
            score=p.score,
        )
        for p in passages
    ]
