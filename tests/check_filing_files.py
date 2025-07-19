#!/usr/bin/env python3
"""
检查财报文件下载状态
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from bs4 import BeautifulSoup

def check_filing_files():
    print("=" * 80)
    print("检查财报文件状态")
    print("=" * 80)
    
    data_dir = Path("data/filings")
    
    if not data_dir.exists():
        print(f"❌ 数据目录不存在: {data_dir}")
        return
    
    # 1. 统计文件
    print("\n1. 文件统计:")
    total_dirs = 0
    total_files = 0
    small_files = 0
    large_files = 0
    index_files = 0
    
    for cik_dir in data_dir.glob("*"):
        if cik_dir.is_dir():
            for acc_dir in cik_dir.glob("*"):
                if acc_dir.is_dir():
                    total_dirs += 1
                    files = list(acc_dir.glob("*"))
                    total_files += len(files)
                    
                    for f in files:
                        size_kb = f.stat().st_size / 1024
                        if f.name == "index.htm":
                            index_files += 1
                        if size_kb < 10:
                            small_files += 1
                        elif size_kb > 100:
                            large_files += 1
    
    print(f"  - 总目录数: {total_dirs}")
    print(f"  - 总文件数: {total_files}")
    print(f"  - 小文件(<10KB): {small_files}")
    print(f"  - 大文件(>100KB): {large_files}")
    print(f"  - index.htm文件: {index_files}")
    
    # 2. 检查几个样本文件
    print("\n2. 样本文件分析:")
    sample_count = 0
    
    for cik_dir in data_dir.glob("*"):
        if cik_dir.is_dir():
            for acc_dir in cik_dir.glob("*"):
                if acc_dir.is_dir() and sample_count < 5:
                    files = list(acc_dir.glob("*.htm*"))
                    if files:
                        sample_count += 1
                        print(f"\n  目录: {acc_dir.relative_to(data_dir)}")
                        
                        for f in files[:2]:  # 每个目录最多看2个文件
                            size_kb = f.stat().st_size / 1024
                            print(f"    文件: {f.name} ({size_kb:.1f} KB)")
                            
                            # 读取内容判断类型
                            try:
                                content = f.read_text(errors='ignore')[:5000]
                                
                                # 判断文件类型
                                if f.name == "index.htm":
                                    print("      类型: SEC索引页")
                                    # 查找主文档链接
                                    soup = BeautifulSoup(content, 'html.parser')
                                    links = soup.find_all('a', href=True)
                                    doc_links = [a for a in links if '10-Q' in a.text or '10-K' in a.text or 'primary_doc' in a['href']]
                                    if doc_links:
                                        print(f"      找到主文档链接: {doc_links[0]['href']}")
                                elif "QUARTERLY REPORT" in content.upper() or "ANNUAL REPORT" in content.upper():
                                    print("      类型: ✅ 真正的财报")
                                    # 提取一些关键信息
                                    if "Item 1." in content or "ITEM 1." in content:
                                        print("      包含: 财务报表章节")
                                elif size_kb < 10:
                                    print("      类型: ❌ 文件太小，可能是错误页")
                                else:
                                    print("      类型: ⚠️  未知类型")
                                    
                            except Exception as e:
                                print(f"      读取错误: {e}")
    
    # 3. 诊断结论
    print("\n\n3. 诊断结论:")
    print("=" * 80)
    
    if index_files > large_files:
        print("❌ 问题: 大部分下载的是index.htm而不是真正的财报")
        print("   解决方案: 需要解析index.htm并下载真正的财报文件")
    
    if small_files > large_files:
        print("❌ 问题: 大部分文件太小，可能是错误页或404页面")
        print("   解决方案: 检查URL格式和下载逻辑")
    
    if large_files > 0:
        print(f"✅ 好消息: 有{large_files}个大文件，可能是真正的财报")
    
    print("\n建议的修复步骤:")
    print("1. 修改下载器，先获取index.htm")
    print("2. 从index.htm中提取真正的财报文件链接")
    print("3. 下载并验证文件大小(>50KB)")
    print("4. 确保文本提取器能处理真正的财报格式")


if __name__ == "__main__":
    check_filing_files()