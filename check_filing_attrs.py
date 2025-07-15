from app.core.database import SessionLocal
from app.models import Filing

db = SessionLocal()

# 获取一个filing实例
filing = db.query(Filing).filter(Filing.id == 6).first()

if filing:
    print("Filing attributes:")
    # 获取所有列名
    for column in Filing.__table__.columns:
        print(f"  {column.name}: {getattr(filing, column.name, 'N/A')}")
else:
    print("Filing not found")

db.close()
