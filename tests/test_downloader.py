#!/usr/bin/env python3
"""
测试改进后的 FilingDownloader
专门测试 Ford 和其他失败案例
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
from app.services.filing_downloader import filing_downloader


async def test_specific_filing(filing_id: int = None, accession_number: str = None):
    """测试特定的财报下载"""
    db = SessionLocal()
    
    try:
        # 获取财报
        if filing_id:
            filing = db.query(Filing).filter(Filing.id == filing_id).first()
        elif accession_number:
            filing = db.query(Filing).filter(Filing.accession_number == accession_number).first()
        else:
            # 默认测试 Ford 的案例
            filing = db.query(Filing).filter(
                Filing.accession_number == "0000037996-25-000141"
            ).first()
        
        if not filing:
            print("❌ 找不到指定的财报")
            return
        
        print(f"\n{'='*60}")
        print(f"测试财报下载 - {filing.company.ticker} {filing.filing_type.value}")
        print(f"Accession: {filing.accession_number}")
        print(f"{'='*60}\n")
        
        # 重置状态
        filing.status = ProcessingStatus.PENDING
        filing.error_message = None
        db.commit()
        
        # 记录开始时间
        start_time = datetime.now()
        
        # 执行下载
        success = await filing_downloader.download_filing(db, filing)
        
        # 计算耗时
        duration = (datetime.now() - start_time).total_seconds()
        
        # 检查结果
        filing_dir = filing_downloader._get_filing_directory(filing)
        
        print(f"\n📊 下载结果:")
        print(f"├── 状态: {'✅ 成功' if success else '❌ 失败'}")
        print(f"├── 耗时: {duration:.2f} 秒")
        print(f"├── Filing状态: {filing.status.value}")
        print(f"├── 错误信息: {filing.error_message or '无'}")
        print(f"└── 文档URL: {filing.primary_doc_url or '未设置'}")
        
        if filing_dir.exists():
            files = list(filing_dir.glob("*"))
            print(f"\n📁 下载的文件 ({len(files)} 个):")
            for file in sorted(files):
                size_kb = file.stat().st_size / 1024
                print(f"├── {file.name} ({size_kb:.1f} KB)")
                
                # 检查是否是 iXBRL viewer
                if file.suffix in ['.htm', '.html']:
                    content = file.read_text(errors='ignore')[:500]
                    if 'loadViewer' in content:
                        print(f"    ⚠️  检测到 iXBRL Viewer 页面")
            
            # 特别检查主文档
            main_doc = filing_downloader.get_filing_path(filing)
            if main_doc and main_doc.name != 'index.htm':
                print(f"\n✅ 找到主文档: {main_doc.name}")
                
                # 读取前1000个字符检查内容
                content = main_doc.read_text(errors='ignore')[:1000]
                if filing.company.name in content or filing.company.ticker in content:
                    print("✅ 文档包含公司信息")
                if 'financial' in content.lower() or 'revenue' in content.lower():
                    print("✅ 文档包含财务相关内容")
            else:
                print("\n❌ 未找到主文档（只有 index.htm）")
        
        return success
        
    finally:
        db.close()


async def test_failed_cases():
    """测试多个失败案例"""
    db = SessionLocal()
    
    # 获取一些失败的案例
    failed_filings = db.query(Filing).filter(
        Filing.status.in_([ProcessingStatus.FAILED, ProcessingStatus.PENDING])
    ).limit(5).all()
    
    print(f"\n🔍 找到 {len(failed_filings)} 个失败/待处理的财报")
    
    results = []
    for filing in failed_filings:
        print(f"\n{'='*60}")
        print(f"测试 {filing.company.ticker} - {filing.accession_number}")
        
        success = await test_specific_filing(filing_id=filing.id)
        results.append({
            'ticker': filing.company.ticker,
            'accession': filing.accession_number,
            'success': success
        })
        
        # 避免请求过快
        await asyncio.sleep(1)
    
    # 汇总结果
    print(f"\n\n{'='*60}")
    print("📊 测试汇总:")
    print(f"{'='*60}")
    
    success_count = sum(1 for r in results if r['success'])
    print(f"成功率: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")
    
    print("\n详细结果:")
    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"{status} {r['ticker']} - {r['accession']}")
    
    db.close()


async def check_file_statistics():
    """检查所有财报的文件统计"""
    db = SessionLocal()
    
    all_filings = db.query(Filing).all()
    
    stats = {
        'total': len(all_filings),
        'has_main_doc': 0,
        'only_index': 0,
        'no_files': 0,
        'avg_file_size': []
    }
    
    print(f"\n📊 正在分析 {len(all_filings)} 个财报的文件...")
    
    for filing in all_filings:
        filing_dir = filing_downloader._get_filing_directory(filing)
        
        if not filing_dir.exists():
            stats['no_files'] += 1
            continue
        
        files = list(filing_dir.glob("*"))
        non_index_files = [f for f in files if f.name != 'index.htm']
        
        if non_index_files:
            stats['has_main_doc'] += 1
            # 记录主文档大小
            main_doc = max(non_index_files, key=lambda f: f.stat().st_size)
            stats['avg_file_size'].append(main_doc.stat().st_size)
        elif files:
            stats['only_index'] += 1
    
    # 计算平均大小
    avg_size = sum(stats['avg_file_size']) / len(stats['avg_file_size']) if stats['avg_file_size'] else 0
    
    print(f"\n📈 文件统计结果:")
    print(f"├── 总财报数: {stats['total']}")
    print(f"├── 有主文档: {stats['has_main_doc']} ({stats['has_main_doc']/stats['total']*100:.1f}%)")
    print(f"├── 只有index: {stats['only_index']} ({stats['only_index']/stats['total']*100:.1f}%)")
    print(f"├── 无文件: {stats['no_files']} ({stats['no_files']/stats['total']*100:.1f}%)")
    print(f"└── 主文档平均大小: {avg_size/1024:.1f} KB")
    
    db.close()


async def main():
    """主测试函数"""
    print("🚀 Fintellic 下载器测试工具")
    print("="*60)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "stats":
            # 统计模式
            await check_file_statistics()
        elif sys.argv[1] == "all":
            # 测试所有失败案例
            await test_failed_cases()
        else:
            # 测试特定的 accession number
            await test_specific_filing(accession_number=sys.argv[1])
    else:
        # 默认测试 Ford 案例
        print("测试 Ford 的失败案例 (0000037996-25-000141)")
        print("使用方法:")
        print("  python tests/test_downloader.py [accession-number]  # 测试特定财报")
        print("  python tests/test_downloader.py all                 # 测试所有失败案例")
        print("  python tests/test_downloader.py stats               # 查看文件统计")
        print()
        
        await test_specific_filing(accession_number="0000037996-25-000141")


if __name__ == "__main__":
    asyncio.run(main())