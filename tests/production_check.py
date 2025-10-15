#!/usr/bin/env python3
"""
Production Readiness Check Script
验证 Fintellic 订阅系统的生产环境配置完整性
"""
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import json
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.core.config import settings
    import redis
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请确保在项目虚拟环境中运行此脚本")
    sys.exit(1)


class Color:
    """终端颜色"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """打印标题"""
    print(f"\n{Color.BOLD}{Color.BLUE}{'=' * 70}{Color.RESET}")
    print(f"{Color.BOLD}{Color.BLUE}{text:^70}{Color.RESET}")
    print(f"{Color.BOLD}{Color.BLUE}{'=' * 70}{Color.RESET}\n")


def print_success(text: str):
    """打印成功信息"""
    print(f"{Color.GREEN}✓ {text}{Color.RESET}")


def print_error(text: str):
    """打印错误信息"""
    print(f"{Color.RED}✗ {text}{Color.RESET}")


def print_warning(text: str):
    """打印警告信息"""
    print(f"{Color.YELLOW}⚠ {text}{Color.RESET}")


def print_info(text: str):
    """打印信息"""
    print(f"{Color.BLUE}ℹ {text}{Color.RESET}")


def check_environment_config() -> Tuple[bool, List[str]]:
    """检查环境配置"""
    print_header("环境配置检查")
    
    issues = []
    
    # 环境类型
    env = settings.ENVIRONMENT
    print_info(f"当前环境: {env}")
    
    if env not in ["development", "staging", "production"]:
        issues.append(f"无效的环境类型: {env}")
        print_error(f"环境类型无效: {env}")
    else:
        print_success(f"环境类型有效: {env}")
    
    # 生产环境特殊检查
    if settings.is_production:
        print_info("检测到生产环境，执行额外验证...")
        
        # SECRET_KEY 强度检查
        if len(settings.SECRET_KEY) < 32:
            issues.append("生产环境 SECRET_KEY 太短，建议至少 32 字符")
            print_warning("SECRET_KEY 长度不足 32 字符")
        else:
            print_success("SECRET_KEY 长度符合要求")
        
        # Mock 支付检查
        if settings.ENABLE_MOCK_PAYMENTS:
            issues.append("生产环境不应启用 Mock 支付")
            print_error("生产环境检测到 Mock 支付已启用")
        else:
            print_success("Mock 支付已禁用")
        
        # Apple 沙盒检查
        if settings.APPLE_USE_SANDBOX:
            issues.append("生产环境应禁用 Apple 沙盒模式")
            print_error("Apple 沙盒模式仍然启用")
        else:
            print_success("Apple 生产模式已启用")
    else:
        print_success(f"{env} 环境基础检查通过")
    
    return len(issues) == 0, issues


def check_database_config() -> Tuple[bool, List[str]]:
    """检查数据库配置"""
    print_header("数据库配置检查")
    
    issues = []
    
    # 检查数据库 URL
    db_url = settings.DATABASE_URL
    if not db_url:
        issues.append("DATABASE_URL 未配置")
        print_error("DATABASE_URL 缺失")
        return False, issues
    
    print_success(f"数据库 URL: {db_url[:30]}...")
    
    # 尝试连接数据库
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        print_success("数据库连接成功")
        
        # 检查表是否存在
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        required_tables = ['users', 'subscriptions', 'payment_records', 'pricing_plans']
        missing_tables = [t for t in required_tables if t not in tables]
        
        if missing_tables:
            issues.append(f"缺少数据库表: {', '.join(missing_tables)}")
            print_error(f"缺少表: {', '.join(missing_tables)}")
        else:
            print_success(f"所有必需表存在 ({len(required_tables)} 个)")
        
        # 检查数据
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            from app.models.user import User
            from app.models.company import Company
            
            user_count = session.query(User).count()
            company_count = session.query(Company).count()
            
            print_success(f"用户数量: {user_count}")
            print_success(f"公司数量: {company_count}")
            
            if company_count == 0:
                print_warning("数据库中没有公司数据")
        finally:
            session.close()
        
    except Exception as e:
        issues.append(f"数据库连接失败: {str(e)}")
        print_error(f"数据库连接失败: {str(e)}")
    
    return len(issues) == 0, issues


def check_redis_config() -> Tuple[bool, List[str]]:
    """检查 Redis 配置"""
    print_header("Redis 配置检查")
    
    issues = []
    
    redis_url = settings.REDIS_URL
    if not redis_url:
        issues.append("REDIS_URL 未配置")
        print_error("REDIS_URL 缺失")
        return False, issues
    
    print_success(f"Redis URL: {redis_url}")
    
    # 尝试连接 Redis
    try:
        r = redis.from_url(redis_url)
        r.ping()
        print_success("Redis 连接成功")
        
        # 检查 Redis 信息
        info = r.info()
        print_success(f"Redis 版本: {info.get('redis_version', 'N/A')}")
        print_success(f"已用内存: {info.get('used_memory_human', 'N/A')}")
        
    except Exception as e:
        issues.append(f"Redis 连接失败: {str(e)}")
        print_error(f"Redis 连接失败: {str(e)}")
    
    return len(issues) == 0, issues


def check_apple_iap_config() -> Tuple[bool, List[str]]:
    """检查 Apple IAP 配置"""
    print_header("Apple In-App Purchase 配置检查")
    
    issues = []
    
    # Bundle ID
    bundle_id = settings.APPLE_BUNDLE_ID
    print_info(f"Bundle ID: {bundle_id}")
    
    if bundle_id != "com.fintellic.app":
        issues.append(f"Bundle ID 不匹配，期望: com.fintellic.app，实际: {bundle_id}")
        print_error("Bundle ID 不匹配")
    else:
        print_success("Bundle ID 正确")
    
    # Product IDs
    monthly_id = settings.APPLE_MONTHLY_PRODUCT_ID
    yearly_id = settings.APPLE_YEARLY_PRODUCT_ID
    
    print_info(f"月度产品 ID: {monthly_id}")
    print_info(f"年度产品 ID: {yearly_id}")
    
    expected_monthly = "com.fintellic.app.monthly"
    expected_yearly = "com.fintellic.app.yearly"
    
    if monthly_id != expected_monthly:
        issues.append(f"月度产品 ID 不匹配")
        print_error(f"月度产品 ID 不匹配，期望: {expected_monthly}")
    else:
        print_success("月度产品 ID 正确")
    
    if yearly_id != expected_yearly:
        issues.append(f"年度产品 ID 不匹配")
        print_error(f"年度产品 ID 不匹配，期望: {expected_yearly}")
    else:
        print_success("年度产品 ID 正确")
    
    # Shared Secret
    shared_secret = settings.APPLE_SHARED_SECRET
    if settings.is_production:
        if not shared_secret:
            issues.append("生产环境缺少 Apple Shared Secret")
            print_error("生产环境缺少 Shared Secret")
        else:
            print_success("Apple Shared Secret 已配置")
    else:
        if shared_secret:
            print_success("Shared Secret 已配置 (开发环境)")
        else:
            print_warning("Shared Secret 未配置 (开发环境可选)")
    
    # 沙盒模式
    sandbox = settings.APPLE_USE_SANDBOX_AUTO
    print_info(f"沙盒模式: {'启用' if sandbox else '禁用'}")
    
    if settings.is_production and sandbox:
        issues.append("生产环境不应使用沙盒模式")
        print_error("生产环境使用了沙盒模式")
    
    return len(issues) == 0, issues


def check_google_play_config() -> Tuple[bool, List[str]]:
    """检查 Google Play 配置"""
    print_header("Google Play Billing 配置检查")
    
    issues = []
    
    # Package Name
    package_name = settings.GOOGLE_PACKAGE_NAME
    print_info(f"Package Name: {package_name}")
    
    if package_name != "com.fintellic.app":
        issues.append(f"Package Name 不匹配，期望: com.fintellic.app，实际: {package_name}")
        print_error("Package Name 不匹配")
    else:
        print_success("Package Name 正确")
    
    # Product IDs
    monthly_id = settings.GOOGLE_MONTHLY_PRODUCT_ID
    yearly_id = settings.GOOGLE_YEARLY_PRODUCT_ID
    
    print_info(f"月度产品 ID: {monthly_id}")
    print_info(f"年度产品 ID: {yearly_id}")
    
    expected_monthly = "monthly_subscription"
    expected_yearly = "yearly_subscription"
    
    if monthly_id != expected_monthly:
        issues.append(f"月度产品 ID 不匹配")
        print_error(f"月度产品 ID 不匹配，期望: {expected_monthly}")
    else:
        print_success("月度产品 ID 正确")
    
    if yearly_id != expected_yearly:
        issues.append(f"年度产品 ID 不匹配")
        print_error(f"年度产品 ID 不匹配，期望: {expected_yearly}")
    else:
        print_success("年度产品 ID 正确")
    
    # Service Account
    has_path = bool(settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH)
    has_base64 = bool(settings.GOOGLE_SERVICE_ACCOUNT_KEY_BASE64)
    has_json = bool(settings.GOOGLE_SERVICE_ACCOUNT_KEY_JSON)
    
    if settings.is_production:
        if not (has_path or has_base64 or has_json):
            issues.append("生产环境缺少 Google Service Account 配置")
            print_error("生产环境缺少 Service Account")
        else:
            print_success("Google Service Account 已配置")
            if has_path:
                print_info(f"配置方式: 文件路径")
            elif has_base64:
                print_info(f"配置方式: Base64 编码")
            else:
                print_info(f"配置方式: JSON 字符串")
    else:
        if has_path or has_base64 or has_json:
            print_success("Service Account 已配置 (开发环境)")
        else:
            print_warning("Service Account 未配置 (开发环境可选)")
    
    return len(issues) == 0, issues


def check_webhook_config() -> Tuple[bool, List[str]]:
    """检查 Webhook 配置"""
    print_header("Webhook 配置检查")
    
    issues = []
    
    base_url = settings.WEBHOOK_BASE_URL
    apple_path = settings.APPLE_WEBHOOK_PATH
    google_path = settings.GOOGLE_WEBHOOK_PATH
    
    if settings.is_production:
        if not base_url:
            issues.append("生产环境缺少 WEBHOOK_BASE_URL")
            print_error("生产环境缺少 Webhook Base URL")
        else:
            print_success(f"Webhook Base URL: {base_url}")
            print_info(f"Apple Webhook: {base_url}{apple_path}")
            print_info(f"Google Webhook: {base_url}{google_path}")
            
            if not base_url.startswith("https://"):
                issues.append("Webhook URL 必须使用 HTTPS")
                print_error("Webhook URL 不是 HTTPS")
    else:
        if base_url:
            print_info(f"Webhook Base URL: {base_url}")
        else:
            print_warning("Webhook URL 未配置 (开发环境可选)")
    
    return len(issues) == 0, issues


def check_pricing_config() -> Tuple[bool, List[str]]:
    """检查定价配置"""
    print_header("定价配置检查")
    
    issues = []
    
    pricing_info = settings.get_pricing_info()
    
    print_info(f"使用优惠价格: {'是' if settings.USE_DISCOUNTED_PRICING else '否'}")
    print_info(f"当前月度价格: ${pricing_info['monthly_price']}")
    print_info(f"当前年度价格: ${pricing_info['yearly_price']}")
    print_info(f"年付节省: ${pricing_info['yearly_savings']}")
    print_info(f"节省百分比: {pricing_info['savings_percentage']}%")
    
    # 检查价格合理性
    monthly = pricing_info['monthly_price']
    yearly = pricing_info['yearly_price']
    
    if monthly <= 0 or yearly <= 0:
        issues.append("价格必须大于 0")
        print_error("价格配置错误")
    else:
        print_success("价格配置有效")
    
    # 检查年付折扣
    expected_yearly = monthly * 12 * 0.6
    if abs(yearly - expected_yearly) > 1:
        print_warning(f"年付价格与预期不符 (预期: ${expected_yearly:.2f})")
    else:
        print_success("年付折扣计算正确 (40% off)")
    
    return len(issues) == 0, issues


def check_product_id_consistency():
    """检查产品 ID 一致性"""
    print_header("产品 ID 一致性检查")
    
    # 后端配置
    backend_apple_monthly = settings.APPLE_MONTHLY_PRODUCT_ID
    backend_apple_yearly = settings.APPLE_YEARLY_PRODUCT_ID
    backend_google_monthly = settings.GOOGLE_MONTHLY_PRODUCT_ID
    backend_google_yearly = settings.GOOGLE_YEARLY_PRODUCT_ID
    
    # 前端配置 (从文档中读取)
    frontend_config_expected = {
        'ios': {
            'monthly': 'com.hermespeed.pro.monthly',
            'yearly': 'com.hermespeed.pro.yearly'
        },
        'android': {
            'monthly': 'hermespeed_pro_monthly',
            'yearly': 'hermespeed_pro_yearly'
        }
    }
    
    # 检查是否匹配 (考虑到项目名称的变化)
    print_info("检查 Apple 产品 ID...")
    if "fintellic" in backend_apple_monthly.lower():
        print_success(f"Apple 月度: {backend_apple_monthly}")
    else:
        print_warning(f"Apple 月度 ID 使用非标准格式: {backend_apple_monthly}")
    
    if "fintellic" in backend_apple_yearly.lower():
        print_success(f"Apple 年度: {backend_apple_yearly}")
    else:
        print_warning(f"Apple 年度 ID 使用非标准格式: {backend_apple_yearly}")
    
    print_info("检查 Google 产品 ID...")
    print_success(f"Google 月度: {backend_google_monthly}")
    print_success(f"Google 年度: {backend_google_yearly}")
    
    print_warning("⚠️ 注意: 前端配置使用 'hermespeed'，后端使用 'fintellic'")
    print_warning("   部署前需要统一产品 ID 命名")


def generate_report(checks: Dict[str, Tuple[bool, List[str]]]):
    """生成检查报告"""
    print_header("配置检查报告")
    
    total_checks = len(checks)
    passed_checks = sum(1 for result, _ in checks.values() if result)
    
    print(f"总检查项: {total_checks}")
    print(f"通过: {Color.GREEN}{passed_checks}{Color.RESET}")
    print(f"失败: {Color.RED}{total_checks - passed_checks}{Color.RESET}")
    
    # 收集所有问题
    all_issues = []
    for check_name, (result, issues) in checks.items():
        if not result:
            all_issues.extend([f"[{check_name}] {issue}" for issue in issues])
    
    if all_issues:
        print_header("发现的问题")
        for issue in all_issues:
            print_error(issue)
    else:
        print_success("\n🎉 所有检查通过！系统配置完整。")
    
    # 环境特定建议
    print_header("建议")
    
    if settings.is_production:
        print_info("生产环境建议:")
        print("  1. 确保所有密钥和证书已妥善保管")
        print("  2. 定期轮换 SECRET_KEY 和 API 密钥")
        print("  3. 监控支付成功率和系统可用性")
        print("  4. 备份数据库和配置文件")
    elif settings.is_development:
        print_info("开发环境建议:")
        print("  1. 可以使用 Mock 支付进行测试")
        print("  2. 使用 Apple 沙盒环境测试 IAP")
        print("  3. 配置完成后运行端到端测试")
    
    # 保存报告
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "environment": settings.ENVIRONMENT,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "failed_checks": total_checks - passed_checks,
        "issues": all_issues,
        "production_ready": settings.is_production_ready if settings.is_production else None
    }
    
    report_file = project_root / "tests" / "production_check_report.json"
    report_file.parent.mkdir(exist_ok=True)
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print_info(f"\n报告已保存至: {report_file}")


def main():
    """主函数"""
    print(f"{Color.BOLD}Fintellic 订阅支付系统配置检查{Color.RESET}")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 执行所有检查
    checks = {
        "环境配置": check_environment_config(),
        "数据库配置": check_database_config(),
        "Redis配置": check_redis_config(),
        "Apple IAP配置": check_apple_iap_config(),
        "Google Play配置": check_google_play_config(),
        "Webhook配置": check_webhook_config(),
        "定价配置": check_pricing_config(),
    }
    
    # 产品 ID 一致性检查 (不计入通过/失败)
    check_product_id_consistency()
    
    # 生成报告
    generate_report(checks)
    
    # 返回退出码
    all_passed = all(result for result, _ in checks.values())
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()