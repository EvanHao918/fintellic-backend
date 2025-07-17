import sys
sys.path.append('.')

# 读取文件
with open('app/services/ai_processor.py', 'r') as f:
    lines = f.readlines()

# 找到方法开始
start_idx = None
for i, line in enumerate(lines):
    if 'async def _extract_structured_financial_data' in line:
        start_idx = i
        print(f"Found method at line {i+1}")
        break

if start_idx:
    # 找到下一个方法或类结束
    end_idx = start_idx + 1
    indent_level = len(lines[start_idx]) - len(lines[start_idx].lstrip())
    
    # 继续直到找到相同或更少缩进的行（表示方法结束）
    while end_idx < len(lines):
        line = lines[end_idx]
        if line.strip():  # 非空行
            current_indent = len(line) - len(line.lstrip())
            # 如果是另一个方法定义或者缩进更少，说明当前方法结束
            if ('def ' in line and current_indent <= indent_level) or (current_indent < indent_level and 'return' not in lines[end_idx-1]):
                break
        end_idx += 1
    
    print(f"Method ends at line {end_idx}")
    print(f"Fixing lines {start_idx+1} to {end_idx}")
    
    # 确保所有行都有正确的缩进
    method_lines = []
    for i in range(start_idx, end_idx):
        line = lines[i]
        if i == start_idx:
            # 方法定义行，确保有4个空格缩进
            if not line.startswith('    '):
                line = '    ' + line.lstrip()
        elif line.strip():
            # 其他非空行，添加额外的缩进
            stripped = line.lstrip()
            # 计算原始的相对缩进
            original_indent = len(line) - len(stripped)
            if original_indent == 0:
                # 如果原本没有缩进，给它8个空格（方法内的第一级）
                line = '        ' + stripped
            elif not line.startswith('    '):
                # 如果没有基础缩进，添加4个空格
                line = '    ' + line
        method_lines.append(line)
    
    # 替换原来的行
    lines[start_idx:end_idx] = method_lines
    
    # 写回文件
    with open('app/services/ai_processor.py', 'w') as f:
        f.writelines(lines)
    
    print("✅ Method indentation fixed!")
    
    # 显示修复后的前几行
    print("\nFixed method preview:")
    for i in range(5):
        if start_idx + i < len(lines):
            print(repr(lines[start_idx + i]))
