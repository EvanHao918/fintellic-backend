import sys
sys.path.append('.')

# 查看ai_processor.py中的问题
with open('app/services/ai_processor.py', 'r') as f:
    content = f.read()
    
# 检查是否调用了不存在的方法
if '_extract_structured_financial_data' in content:
    print("Found call to _extract_structured_financial_data")
    
    # 找到所有相关的行
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if '_extract_structured_financial_data' in line:
            print(f"\nLine {i+1}: {line.strip()}")
            # 显示上下文
            start = max(0, i-2)
            end = min(len(lines), i+3)
            print("\nContext:")
            for j in range(start, end):
                marker = ">>> " if j == i else "    "
                print(f"{marker}{j+1}: {lines[j]}")

# 建议修复
print("\n" + "="*50)
print("SUGGESTED FIX:")
print("="*50)
print("""
Add this method to the AIProcessor class:

    def _extract_structured_financial_data(self, text: str) -> Dict:
        \"\"\"Extract structured financial data from filing text\"\"\"
        # Simple extraction for now
        financial_data = {}
        
        # Try to extract revenue
        import re
        revenue_patterns = [
            r'revenue[s]?\s*(?:of|:)?\s*\$?([\d,]+(?:\.\d+)?)\s*(?:million|billion)',
            r'total\s+revenue[s]?\s*(?:of|:)?\s*\$?([\d,]+(?:\.\d+)?)',
        ]
        
        for pattern in revenue_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                financial_data['revenue'] = match.group(1).replace(',', '')
                break
        
        return financial_data
""")

# 或者更简单的修复
print("\nOR, for a quick fix, replace the line with:")
print("financial_data = {}")
