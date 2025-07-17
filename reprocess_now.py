from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.tasks.filing_tasks import process_filing_task

db = SessionLocal()

# 获取失败的财报
failed = db.query(Filing).filter(Filing.status == ProcessingStatus.FAILED).all()
print(f"找到 {len(failed)} 个失败的财报")

# 重新处理
for f in failed:
    f.status = ProcessingStatus.PENDING
    f.error_message = None
    db.commit()
    process_filing_task.delay(f.id)
    print(f"重新处理: {f.company.ticker} {f.filing_type.value}")

db.close()
print("完成！查看日志: tail -f logs/celery.log")
