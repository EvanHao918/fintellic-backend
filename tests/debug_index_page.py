#!/usr/bin/env python3
"""
调试index页面内容，找出正确的文档链接
"""

import httpx
from bs4 import BeautifulSoup
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.filing import Filing, ProcessingStatus
import asyncio


async def debug_index_page():
    """下载并分析index页面内容"""
    db = SessionLocal()
    
    # 获取一个失败的财报
    filing = db.query(Filing).filter(
        Filing.status == ProcessingStatus.FAILED,
        Filing.company.ticker == "MAS"  # 使用我们知道正确URL的这个
    ).first()
    
    if not filing:
        print("没有找到MAS的失败财报")
        return
    
    print(f"调试财报: {filing.company.ticker} {filing.filing_type.value}")
    print(f"Accession: {filing.accession_number}")
    print("=" * 80)
    
    # 构建正确的URL（基于诊断结果）
    cik_no_zeros = filing.company.cik.lstrip('0')
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{filing.accession_number}/-index.htm"
    
    print(f"获取index页面: {index_url}")
    
    headers = {
        'User-Agent': 'Fintellic/1.0 (contact@fintellic.com)',
        'Accept': 'text/html,application/xhtml+xml'
    }
    
    async with httpx.AsyncClient(headers=headers) as client:
        response = await client.get(index_url)
        
        if response.status_code != 200:
            print(f"❌ 获取失败: HTTP {response.status_code}")
            return
        
        print(f"✅ 成功获取index页面 ({len(response.content)} bytes)")
        
        # 保存原始HTML供分析
        with open("debug_index.html", "w", encoding='utf-8') as f:
            f.write(response.text)
        print("已保存到 debug_index.html")
        
        # 解析HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        print("\n" + "=" * 40)
        print("查找文档表格...")
        
        # 查找所有表格
        tables = soup.find_all('table')
        print(f"找到 {len(tables)} 个表格")
        
        # 查找包含文档链接的表格
        doc_found = False
        for i, table in enumerate(tables):
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:
                    # 打印行内容
                    row_text = [cell.get_text(strip=True) for cell in cells]
                    
                    # 查找包含财报类型的行
                    if any(filing.filing_type.value in str(cell) for cell in cells):
                        print(f"\n找到匹配的行:")
                        print(f"  类型: {row_text[0]}")
                        print(f"  描述: {row_text[1] if len(row_text) > 1 else 'N/A'}")
                        
                        # 查找链接
                        link = row.find('a')
                        if link and link.get('href'):
                            href = link['href']
                            link_text = link.get_text(strip=True)
                            print(f"  链接文本: {link_text}")
                            print(f"  链接URL: {href}")
                            
                            # 构建完整URL
                            if not href.startswith('http'):
                                if href.startswith('/'):
                                    full_url = f"https://www.sec.gov{href}"
                                else:
                                    base_url = index_url.rsplit('/', 1)[0]
                                    full_url = f"{base_url}/{href}"
                            else:
                                full_url = href
                            
                            print(f"  完整URL: {full_url}")
                            
                            # 测试这个URL
                            print(f"\n测试文档URL...")
                            doc_response = await client.head(full_url)
                            if doc_response.status_code == 200:
                                print(f"  ✅ 文档URL有效!")
                                doc_found = True
                            else:
                                print(f"  ❌ HTTP {doc_response.status_code}")
        
        if not doc_found:
            print("\n未找到有效的文档链接")
            print("\n查找所有链接...")
            all_links = soup.find_all('a', href=True)
            print(f"页面中共有 {len(all_links)} 个链接")
            
            # 显示前20个链接
            for link in all_links[:20]:
                href = link['href']
                text = link.get_text(strip=True)
                if text and not href.startswith('#'):
                    print(f"  - {text[:50]}: {href}")
    
    db.close()


if __name__ == "__main__":
    print("开始调试index页面...\n")
    asyncio.run(debug_index_page())