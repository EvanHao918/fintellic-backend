from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from datetime import datetime, timezone

db = SessionLocal()

# 获取所有parsing状态的财报
parsing_filings = db.query(Filing).filter(
    Filing.status == ProcessingStatus.PARSING
).all()

print(f"找到 {len(parsing_filings)} 个parsing状态的财报\n")

fixed_count = 0
still_parsing_count = 0
error_count = 0

for f in parsing_filings:
    # 如果有AI摘要，说明处理已经完成
    if f.ai_summary and f.management_tone:
        print(f"✅ 修复: {f.company.ticker if f.company else f.company_id} - {f.filing_type.value}")
        f.status = ProcessingStatus.COMPLETED
        if not f.processing_completed_at:
            f.processing_completed_at = datetime.now(timezone.utc)
        fixed_count += 1
    
    # 如果有错误信息，标记为失败
    elif f.error_message:
        print(f"❌ 标记失败: {f.company.ticker if f.company else f.company_id} - {f.filing_type.value} - {f.error_message}")
        f.status = ProcessingStatus.FAILED
        error_count += 1
    
    # 如果什么都没有，保持parsing状态，稍后重新处理
    else:
        print(f"⏳ 需要重新处理: {f.company.ticker if f.company else f.company_id} - {f.filing_type.value}")
        still_parsing_count += 1

# 提交更改
if fixed_count > 0 or error_count > 0:
    db.commit()
    print(f"\n✅ 更新完成:")
    print(f"  - 修复为completed: {fixed_count}")
    print(f"  - 标记为failed: {error_count}")
    print(f"  - 仍需处理: {still_parsing_count}")
else:
    print("\n没有需要修复的财报")

db.close()
