#!/usr/bin/env python
"""
诊断AI生成内容的质量问题
"""
import os
import sys
import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.models.filing import Filing, ProcessingStatus, FilingType
from app.models.company import Company
from app.core.database import engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def check_content_quality():
    """检查AI生成内容的质量"""
    db = SessionLocal()
    
    try:
        # 获取所有已完成的财报
        completed_filings = db.query(Filing).join(Company).filter(
            Filing.status == ProcessingStatus.COMPLETED
        ).all()
        
        print(f"📊 检查 {len(completed_filings)} 个已完成的财报\n")
        
        # 统计问题
        issues = {
            'missing_summary': [],
            'missing_questions': [],
            'missing_tags': [],
            'short_content': [],
            'json_errors': [],
            'missing_specialized': []
        }
        
        for filing in completed_filings:
            filing_info = f"{filing.company.ticker} - {filing.filing_type.value}"
            
            # 检查基础字段
            if not filing.ai_summary or len(filing.ai_summary) < 100:
                issues['short_content'].append(filing_info)
            
            if not filing.key_questions:
                issues['missing_questions'].append(filing_info)
            
            if not filing.key_tags:
                issues['missing_tags'].append(filing_info)
            
            # 检查JSON字段
            json_fields = {
                'key_questions': filing.key_questions,
                'financial_highlights': filing.financial_highlights,
                'business_segments': filing.business_segments,
                'risk_summary': filing.risk_summary
            }
            
            for field_name, field_value in json_fields.items():
                if field_value:
                    try:
                        if isinstance(field_value, str):
                            json.loads(field_value)
                    except json.JSONDecodeError:
                        issues['json_errors'].append(f"{filing_info} - {field_name}")
            
            # 检查类型特定字段
            if filing.filing_type == FilingType.FORM_10K:
                if not filing.auditor_opinion:
                    issues['missing_specialized'].append(f"{filing_info} - auditor_opinion")
                if not filing.market_impact_10k:
                    issues['missing_specialized'].append(f"{filing_info} - market_impact_10k")
                    
            elif filing.filing_type == FilingType.FORM_10Q:
                if not filing.guidance_update:
                    issues['missing_specialized'].append(f"{filing_info} - guidance_update")
                if not filing.market_impact_10q:
                    issues['missing_specialized'].append(f"{filing_info} - market_impact_10q")
                    
            elif filing.filing_type == FilingType.FORM_8K:
                if not filing.event_nature_analysis:
                    issues['missing_specialized'].append(f"{filing_info} - event_nature_analysis")
                    
            elif filing.filing_type == FilingType.FORM_S1:
                if not filing.company_overview:
                    issues['missing_specialized'].append(f"{filing_info} - company_overview")
        
        # 显示问题报告
        print("🔍 内容质量问题报告：\n")
        
        for issue_type, filings in issues.items():
            if filings:
                print(f"❌ {issue_type}: {len(filings)} 个")
                for f in filings[:5]:  # 只显示前5个
                    print(f"   - {f}")
                if len(filings) > 5:
                    print(f"   ... 还有 {len(filings) - 5} 个")
                print()
        
        # 检查具体的文本提取问题
        print("\n📄 文本提取质量检查：")
        
        sample_filings = completed_filings[:5]  # 检查前5个
        for filing in sample_filings:
            filing_dir = Path(f"data/filings/{filing.company.cik}/{filing.accession_number.replace('-', '')}")
            if filing_dir.exists():
                files = list(filing_dir.glob("*.htm*"))
                if files:
                    file_path = files[0]
                    file_size = file_path.stat().st_size
                    print(f"\n{filing.company.ticker} - {filing.filing_type.value}:")
                    print(f"  文件: {file_path.name} ({file_size:,} bytes)")
                    
                    # 读取文件内容检查
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        if len(content) < 1000:
                            print(f"  ⚠️  文件内容很短: {len(content)} 字符")
                        if "<!DOCTYPE html" not in content and "<html" not in content:
                            print(f"  ⚠️  可能不是HTML文件")
                        if content.count('<') < 10:
                            print(f"  ⚠️  HTML标签很少")
        
        # 显示示例内容
        print("\n📝 示例内容检查：")
        
        # 找一个8-K示例
        sample_8k = next((f for f in completed_filings if f.filing_type == FilingType.FORM_8K), None)
        if sample_8k:
            print(f"\n8-K 示例 ({sample_8k.company.ticker}):")
            print(f"摘要长度: {len(sample_8k.ai_summary) if sample_8k.ai_summary else 0}")
            if sample_8k.ai_summary:
                print(f"摘要开头: {sample_8k.ai_summary[:200]}...")
            
            if sample_8k.key_questions:
                try:
                    questions = json.loads(sample_8k.key_questions) if isinstance(sample_8k.key_questions, str) else sample_8k.key_questions
                    print(f"问题数量: {len(questions)}")
                except:
                    print("问题解析失败")
                    
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def fix_json_fields():
    """修复JSON字段中的常见问题"""
    db = SessionLocal()
    
    try:
        completed_filings = db.query(Filing).filter(
            Filing.status == ProcessingStatus.COMPLETED
        ).all()
        
        fixed_count = 0
        
        for filing in completed_filings:
            changed = False
            
            # 修复空列表/空对象的JSON字段
            json_fields = ['key_questions', 'financial_highlights', 'business_segments', 
                          'risk_summary', 'three_year_financials', 'items']
            
            for field_name in json_fields:
                field_value = getattr(filing, field_name, None)
                if field_value == "[]" or field_value == "{}":
                    setattr(filing, field_name, None)
                    changed = True
                elif field_value == "null" or field_value == "undefined":
                    setattr(filing, field_name, None)
                    changed = True
            
            if changed:
                fixed_count += 1
                
        if fixed_count > 0:
            db.commit()
            print(f"✅ 修复了 {fixed_count} 个财报的JSON字段")
        else:
            print("✅ 没有需要修复的JSON字段")
            
    except Exception as e:
        print(f"修复错误: {str(e)}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("🔍 财报内容质量诊断工具")
    print("=" * 60)
    
    # 检查内容质量
    check_content_quality()
    
    print("\n" + "=" * 60)
    print("\n是否尝试修复JSON字段问题？")
    if input("输入 y 继续: ").lower() == 'y':
        fix_json_fields()