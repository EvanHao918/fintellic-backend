# 在 app/services/edgar_scanner.py 中找到公司创建逻辑
# 添加ticker检查

def create_or_update_company(self, cik: str, company_data: dict):
    """创建或更新公司信息"""
    
    # 如果没有ticker，跳过（这些通常是基金或信托）
    if not company_data.get('ticker'):
        logger.info(f"Skipping company without ticker: {company_data.get('name', 'Unknown')} (CIK: {cik})")
        return None
    
    # 继续原有逻辑...
