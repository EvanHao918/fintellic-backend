import asyncio
from app.services.scheduler import filing_scheduler
import time

async def test_scheduler_control():
    """测试调度器的启动和停止"""
    
    print("测试调度器控制...")
    
    # 1. 检查初始状态
    print(f"1. 初始状态: {'运行中' if filing_scheduler.is_running else '已停止'}")
    
    # 2. 如果在运行，先停止
    if filing_scheduler.is_running:
        print("2. 停止调度器...")
        await filing_scheduler.stop()
        await asyncio.sleep(1)
        print(f"   状态: {'运行中' if filing_scheduler.is_running else '已停止'}")
    
    # 3. 启动调度器
    print("3. 启动调度器...")
    await filing_scheduler.start()
    await asyncio.sleep(1)
    print(f"   状态: {'运行中' if filing_scheduler.is_running else '已停止'}")
    
    # 4. 运行单次扫描
    print("4. 运行单次扫描...")
    results = await filing_scheduler.run_single_scan()
    print(f"   扫描结果: 找到 {len(results)} 个新财报")
    
    # 5. 再次停止
    print("5. 停止调度器...")
    await filing_scheduler.stop()
    print(f"   最终状态: {'运行中' if filing_scheduler.is_running else '已停止'}")

if __name__ == "__main__":
    # 需要在项目目录下运行
    import sys
    sys.path.append('.')
    asyncio.run(test_scheduler_control())
