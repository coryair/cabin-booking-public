from sqlalchemy.orm import Session as DBSession

from db.models import Share, Shareholder, ShareholderShareAccess


class ShareAccessService:
    @staticmethod
    def get_allowed_share_ids(db: DBSession, shareholder: Shareholder) -> set[str]:
        ids = {shareholder.share}
        rows = db.query(ShareholderShareAccess.share_id).filter(
            ShareholderShareAccess.shareholder_id == shareholder.id
        ).all()
        ids.update(share_id for (share_id,) in rows)
        return ids

    @staticmethod
    def get_allowed_shares(db: DBSession, shareholder: Shareholder) -> list[Share]:
        allowed_ids = ShareAccessService.get_allowed_share_ids(db, shareholder)
        if not allowed_ids:
            return []
        return db.query(Share).filter(
            Share.share_id.in_(allowed_ids)
        ).order_by(Share.priority).all()

    @staticmethod
    def is_share_allowed(db: DBSession, shareholder: Shareholder, share_id: str) -> bool:
        return share_id in ShareAccessService.get_allowed_share_ids(db, shareholder)

    @staticmethod
    def resolve_share_selection(db: DBSession, shareholder: Shareholder, requested_share: str | None) -> str:
        selected = (requested_share or "").strip() or shareholder.share
        if not ShareAccessService.is_share_allowed(db, shareholder, selected):
            raise ValueError("You do not have access to that share")
        return selected
