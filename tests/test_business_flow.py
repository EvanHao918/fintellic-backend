import asyncio
import httpx
from datetime import datetime

async def test_business_flow():
    """测试完整的业务流程"""
    
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient() as client:
        # 1. 检查健康状态
        print("1. 检查系统健康状态...")
        health = await client.get(f"{base_url}/health")
        print(f"   健康检查: {health.json()}")
        
        # 2. 触发手动扫描
        print("\n2. 触发手动扫描...")
        scan_result = await client.post(f"{base_url}/api/v1/scan/trigger")
        print(f"   扫描结果: {scan_result.json()}")
        
        # 3. 获取最新财报列表
        print("\n3. 获取财报列表...")
        filings = await client.get(f"{base_url}/api/v1/filings/?limit=5")
        filing_data = filings.json()
        print(f"   找到财报: {filing_data.get('total', 0)} 个")
        
        # 4. 检查公司列表
        print("\n4. 获取公司列表...")
        companies = await client.get(f"{base_url}/api/v1/companies/?limit=5")
        company_data = companies.json()
        print(f"   找到公司: {company_data.get('total', 0)} 个")
        
        # 5. 测试统计数据
        print("\n5. 测试缓存和统计...")
        if filing_data.get('data'):
            first_filing = filing_data['data'][0]
            print(f"   第一个财报: {first_filing.get('company', {}).get('ticker')} - {first_filing.get('form_type')}")
            print(f"   查看次数: {first_filing.get('vote_counts', {})}")

if __name__ == "__main__":
    asyncio.run(test_business_flow())
