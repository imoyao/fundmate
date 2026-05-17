from app.core.database import SessionLocal
from app.domains.watchlist.models import WatchlistItemTag, WatchlistTagDef

db = SessionLocal()
db.query(WatchlistItemTag).filter(~WatchlistItemTag.tag_id.in_(db.query(WatchlistTagDef.id))).delete(
    synchronize_session=False
)
db.commit()
db.close()
