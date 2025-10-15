#!/usr/bin/env python3
"""
测试分析师预期数据获取
文件名: test_analyst_expectations.py
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

from app.services.ai_processor import ai_processor

async def test_single_ticker(ticker: str):
    """测试单个股票的分析师预期"""
    print(f"\n{'='*50}")
    print(f"测试股票: {ticker}")
    print(f"{'='*50}")
    
    try:
        result = await ai_processor._fetch_analyst_expectations(ticker)
        
        if result:
            print("✅ 成功获取分析师预期数据:")
            print(f"📊 数据源: {result.get('data_source', 'unknown')}")
            
            # 收入预期
            revenue_est = result.get('revenue_estimate', {})
            if revenue_est.get('value'):
                print(f"\n💰 收入预期:")
                print(f"   - 预期值: ${revenue_est.get('value', 'N/A')}B")
                print(f"   - 分析师数: {revenue_est.get('analysts', 'N/A')}")
            
            # EPS预期
            eps_est = result.get('eps_estimate', {})
            if eps_est.get('value'):
                print(f"\n📈 EPS预期:")
                print(f"   - 预期值: ${eps_est.get('value', 'N/A')}")
                print(f"   - 分析师数: {eps_est.get('analysts', 'N/A')}")
            
            print(f"\n⏰ 获取时间: {result.get('fetch_timestamp', 'N/A')}")
            
        else:
            print("❌ 未能获取分析师预期数据")
            
    except Exception as e:
        print(f"❌ 错误: {str(e)}")

async def main():
    """测试主函数"""
    print("开始测试分析师预期数据获取功能...")
    
    # 测试几个主要的股票
    test_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN"]
    
    for ticker in test_tickers:
        await test_single_ticker(ticker)
        
        # 等待3秒避免请求过快
        if ticker != test_tickers[-1]:
            print("\n⏳ 等待3秒后继续...")
            await asyncio.sleep(3)
    
    print("\n测试完成！")

if __name__ == "__main__":
    asyncio.run(main())