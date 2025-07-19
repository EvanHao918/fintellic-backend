import sys
sys.path.append('.')

# 读取文件
with open('app/services/ai_processor.py', 'r') as f:
    lines = f.readlines()

# 找到类定义
class_indent = None
for i, line in enumerate(lines):
    if 'class AIProcessor' in line:
        class_indent = len(line) - len(line.lstrip())
        print(f"Found class AIProcessor at line {i+1} with indent {class_indent}")
        break

# 找到错误定义的方法
method_line = None
for i, line in enumerate(lines):
    if 'async def _extract_structured_financial_data' in line and line.startswith('async'):
        method_line = i
        print(f"Found misplaced method at line {i+1}")
        break

if method_line:
    # 修复从这个方法开始的所有行的缩进
    print("\nFixing indentation...")
    
    # 找到方法的结束位置（下一个没有缩进的行）
    end_line = method_line + 1
    while end_line < len(lines) and (lines[end_line].strip() == '' or lines[end_line].startswith(' ') or lines[end_line].startswith('\t')):
        end_line += 1
    
    # 给这些行添加适当的缩进（4个空格）
    for i in range(method_line, end_line):
        if lines[i].strip():  # 非空行
            lines[i] = '    ' + lines[i]
    
    # 写回文件
    with open('app/services/ai_processor.py', 'w') as f:
        f.writelines(lines)
    
    print(f"Fixed indentation for lines {method_line+1} to {end_line}")
    print("✅ File has been fixed!")
else:
    print("Method not found or already properly indented")
