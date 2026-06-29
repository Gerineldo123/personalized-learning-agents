from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from api.deps import get_db
from models.conversation import Conversation, ChatMessage

router = APIRouter(prefix="/api/conversations", tags=["对话管理"])


@router.get("")
def list_conversations(
    user_id: str,
    limit: int = Query(50, le=100),
    db: Session = Depends(get_db),
):
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                "msg_count": db.query(ChatMessage).filter(
                    ChatMessage.conversation_id == c.id
                ).count(),
            }
            for c in convs
        ]
    }


@router.post("")
def create_conversation(user_id: str, title: str = "新对话", db: Session = Depends(get_db)):
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"id": conv.id, "title": conv.title}


@router.get("/weekly-usage")
def weekly_usage(user_id: str, db: Session = Depends(get_db)):
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=offset) for offset in range(6, -1, -1)]
    labels = [f"{day.month}/{day.day}" for day in days]
    buckets = {
        day.isoformat(): {"morning": 0, "afternoon": 0, "evening": 0}
        for day in days
    }
    start_at = datetime.combine(days[0], datetime.min.time())
    rows = (
        db.query(ChatMessage)
        .join(Conversation, Conversation.id == ChatMessage.conversation_id)
        .filter(
            Conversation.user_id == user_id,
            ChatMessage.role == "user",
            ChatMessage.created_at >= start_at,
        )
        .all()
    )
    for message in rows:
        created_at = message.created_at
        if not created_at:
            continue
        day_key = created_at.date().isoformat()
        if day_key not in buckets:
            continue
        hour = created_at.hour
        if hour < 12:
            buckets[day_key]["morning"] += 1
        elif hour < 18:
            buckets[day_key]["afternoon"] += 1
        else:
            buckets[day_key]["evening"] += 1
    return {
        "days": labels,
        "morning": [buckets[day.isoformat()]["morning"] for day in days],
        "afternoon": [buckets[day.isoformat()]["afternoon"] for day in days],
        "evening": [buckets[day.isoformat()]["evening"] for day in days],
    }


@router.get("/{conv_id}/messages")
def get_messages(conv_id: int, db: Session = Depends(get_db)):
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return {
        "items": [
            {"role": m.role, "content": m.content, "id": m.id}
            for m in msgs
        ]
    }


@router.post("/{conv_id}/messages")
def add_message(conv_id: int, role: str, content: str, db: Session = Depends(get_db)):
    msg = ChatMessage(conversation_id=conv_id, role=role, content=content)
    db.add(msg)

    conv = db.query(Conversation).get(conv_id)
    if conv:
        conv.updated_at = datetime.now(timezone.utc)
        if role == "user" and conv.title == "新对话":
            conv.title = content[:30]

    db.commit()
    return {"ok": True, "id": msg.id}


@router.patch("/messages/{msg_id}")
def update_message(msg_id: int, content: str, db: Session = Depends(get_db)):
    msg = db.query(ChatMessage).get(msg_id)
    if msg:
        msg.content = content
        db.commit()
    return {"ok": True}


@router.delete("/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    db.query(ChatMessage).filter(ChatMessage.conversation_id == conv_id).delete()
    db.query(Conversation).filter(Conversation.id == conv_id).delete()
    db.commit()
    return {"ok": True}


@router.post("/batch_delete")
def batch_delete_conversations(user_id: str, ids: str, db: Session = Depends(get_db)):
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if not id_list:
        return {"ok": True, "deleted": 0}

    convs = db.query(Conversation).filter(
        Conversation.user_id == user_id,
        Conversation.id.in_(id_list),
    ).all()
    conv_ids = [c.id for c in convs]
    if not conv_ids:
        return {"ok": True, "deleted": 0}

    db.query(ChatMessage).filter(ChatMessage.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
    deleted = db.query(Conversation).filter(Conversation.id.in_(conv_ids)).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.delete("")
def clear_conversations(user_id: str, db: Session = Depends(get_db)):
    convs = db.query(Conversation).filter(Conversation.user_id == user_id).all()
    conv_ids = [c.id for c in convs]
    if not conv_ids:
        return {"ok": True, "deleted": 0}

    db.query(ChatMessage).filter(ChatMessage.conversation_id.in_(conv_ids)).delete(synchronize_session=False)
    deleted = db.query(Conversation).filter(Conversation.id.in_(conv_ids)).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": deleted}


@router.put("/{conv_id}")
def update_conversation(conv_id: int, title: str, db: Session = Depends(get_db)):
    conv = db.query(Conversation).get(conv_id)
    if conv:
        conv.title = title
        db.commit()
    return {"ok": True}
