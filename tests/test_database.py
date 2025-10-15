#!/usr/bin/env python3
"""
Database Structure Validation Test
验证订阅系统数据库表结构的完整性和一致性
"""
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any
import json
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.core.config import settings
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.orm import sessionmaker
    from app.models.user import User
    from app.models.subscription import Subscription
    from app.models.payment_record import PaymentRecord
    from app.models.pricing_plan import PricingPlan
except ImportError as e:
    print(f"导入错误: {e}")
    sys.exit(1)


class Color:
    """终端颜色"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class DatabaseTester:
    """数据库测试器"""
    
    def __init__(self):
        self.engine = create_engine(settings.DATABASE_URL)
        self.inspector = inspect(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.test_results: List[Dict[str, Any]] = []
    
    def print_header(self, text: str):
        """打印标题"""
        print(f"\n{Color.BOLD}{Color.BLUE}{'=' * 70}{Color.RESET}")
        print(f"{Color.BOLD}{Color.BLUE}{text:^70}{Color.RESET}")
        print(f"{Color.BOLD}{Color.BLUE}{'=' * 70}{Color.RESET}\n")
    
    def print_success(self, text: str):
        """打印成功信息"""
        print(f"{Color.GREEN}✓ {text}{Color.RESET}")
    
    def print_error(self, text: str):
        """打印错误信息"""
        print(f"{Color.RED}✗ {text}{Color.RESET}")
    
    def print_warning(self, text: str):
        """打印警告信息"""
        print(f"{Color.YELLOW}⚠ {text}{Color.RESET}")
    
    def print_info(self, text: str):
        """打印信息"""
        print(f"{Color.BLUE}ℹ {text}{Color.RESET}")
    
    def test_table_existence(self) -> Tuple[bool, List[str]]:
        """测试表是否存在"""
        self.print_header("数据库表存在性检查")
        
        issues = []
        required_tables = {
            'users': '用户表',
            'subscriptions': '订阅历史表',
            'payment_records': '支付记录表',
            'pricing_plans': '定价方案表'
        }
        
        existing_tables = self.inspector.get_table_names()
        self.print_info(f"数据库中共有 {len(existing_tables)} 个表")
        
        for table_name, description in required_tables.items():
            if table_name in existing_tables:
                self.print_success(f"{description} ({table_name}) 存在")
            else:
                issues.append(f"缺少表: {table_name}")
                self.print_error(f"{description} ({table_name}) 不存在")
        
        return len(issues) == 0, issues
    
    def test_user_table_structure(self) -> Tuple[bool, List[str]]:
        """测试 users 表结构"""
        self.print_header("用户表结构检查")
        
        issues = []
        
        # 检查订阅相关字段
        required_columns = {
            'tier': 'VARCHAR',
            'is_subscription_active': 'BOOLEAN',
            'subscription_type': 'VARCHAR',
            'subscription_started_at': 'TIMESTAMP',
            'subscription_expires_at': 'TIMESTAMP',
            'subscription_cancelled_at': 'TIMESTAMP',
            'subscription_price': 'NUMERIC',
            'subscription_auto_renew': 'BOOLEAN',
            'next_billing_date': 'TIMESTAMP',
            'payment_method': 'VARCHAR',
            'monthly_price': 'NUMERIC',
            'pricing_tier': 'VARCHAR',
            'is_early_bird': 'BOOLEAN',
            'last_payment_date': 'TIMESTAMP',
            'last_payment_amount': 'NUMERIC',
            'total_payment_amount': 'NUMERIC',
            'apple_subscription_id': 'VARCHAR',
            'google_subscription_id': 'VARCHAR',
            'google_order_id': 'VARCHAR',
        }
        
        columns = self.inspector.get_columns('users')
        column_dict = {col['name']: col for col in columns}
        
        for col_name, expected_type in required_columns.items():
            if col_name in column_dict:
                col_type = str(column_dict[col_name]['type']).upper()
                # 简化类型匹配（只检查主要类型）
                if expected_type.split('(')[0] in col_type:
                    self.print_success(f"字段 {col_name} 存在 ({col_type})")
                else:
                    self.print_warning(f"字段 {col_name} 类型可能不匹配 (期望: {expected_type}, 实际: {col_type})")
            else:
                issues.append(f"用户表缺少字段: {col_name}")
                self.print_error(f"字段 {col_name} 不存在")
        
        self.print_info(f"用户表共有 {len(columns)} 个字段")
        
        return len(issues) == 0, issues
    
    def test_subscription_table_structure(self) -> Tuple[bool, List[str]]:
        """测试 subscriptions 表结构"""
        self.print_header("订阅表结构检查")
        
        issues = []
        
        required_columns = {
            'id': 'INTEGER',
            'user_id': 'INTEGER',
            'subscription_type': 'VARCHAR',
            'pricing_tier': 'VARCHAR',
            'price': 'NUMERIC',
            'currency': 'VARCHAR',
            'status': 'VARCHAR',
            'started_at': 'TIMESTAMP',
            'expires_at': 'TIMESTAMP',
            'cancelled_at': 'TIMESTAMP',
            'auto_renew': 'BOOLEAN',
            'payment_method': 'VARCHAR',
            'stripe_subscription_id': 'VARCHAR',
            'apple_subscription_id': 'VARCHAR',
            'google_subscription_id': 'VARCHAR',
            'subscription_metadata': 'JSON',
            'created_at': 'TIMESTAMP',
            'updated_at': 'TIMESTAMP',
        }
        
        columns = self.inspector.get_columns('subscriptions')
        column_dict = {col['name']: col for col in columns}
        
        for col_name, expected_type in required_columns.items():
            if col_name in column_dict:
                self.print_success(f"字段 {col_name} 存在")
            else:
                issues.append(f"订阅表缺少字段: {col_name}")
                self.print_error(f"字段 {col_name} 不存在")
        
        # 检查外键
        foreign_keys = self.inspector.get_foreign_keys('subscriptions')
        if foreign_keys:
            for fk in foreign_keys:
                self.print_success(f"外键: {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
        else:
            issues.append("订阅表缺少外键约束")
            self.print_warning("未找到外键约束")
        
        self.print_info(f"订阅表共有 {len(columns)} 个字段")
        
        return len(issues) == 0, issues
    
    def test_payment_record_table_structure(self) -> Tuple[bool, List[str]]:
        """测试 payment_records 表结构"""
        self.print_header("支付记录表结构检查")
        
        issues = []
        
        required_columns = {
            'id': 'INTEGER',
            'user_id': 'INTEGER',
            'subscription_id': 'INTEGER',
            'amount': 'NUMERIC',
            'currency': 'VARCHAR',
            'payment_method': 'VARCHAR',
            'payment_status': 'VARCHAR',
            'stripe_payment_intent_id': 'VARCHAR',
            'apple_transaction_id': 'VARCHAR',
            'google_order_id': 'VARCHAR',
            'payment_metadata': 'JSON',
            'created_at': 'TIMESTAMP',
        }
        
        columns = self.inspector.get_columns('payment_records')
        column_dict = {col['name']: col for col in columns}
        
        for col_name, expected_type in required_columns.items():
            if col_name in column_dict:
                self.print_success(f"字段 {col_name} 存在")
            else:
                issues.append(f"支付记录表缺少字段: {col_name}")
                self.print_error(f"字段 {col_name} 不存在")
        
        # 检查外键
        foreign_keys = self.inspector.get_foreign_keys('payment_records')
        if foreign_keys:
            for fk in foreign_keys:
                self.print_success(f"外键: {fk['constrained_columns']} -> {fk['referred_table']}")
        else:
            issues.append("支付记录表缺少外键约束")
            self.print_warning("未找到外键约束")
        
        self.print_info(f"支付记录表共有 {len(columns)} 个字段")
        
        return len(issues) == 0, issues
    
    def test_pricing_plan_table_structure(self) -> Tuple[bool, List[str]]:
        """测试 pricing_plans 表结构"""
        self.print_header("定价方案表结构检查")
        
        issues = []
        
        required_columns = {
            'id': 'INTEGER',
            'plan_name': 'VARCHAR',
            'plan_type': 'VARCHAR',
            'monthly_price': 'NUMERIC',
            'yearly_price': 'NUMERIC',
            'currency': 'VARCHAR',
            'is_active': 'BOOLEAN',
            'created_at': 'TIMESTAMP',
            'updated_at': 'TIMESTAMP',
        }
        
        columns = self.inspector.get_columns('pricing_plans')
        column_dict = {col['name']: col for col in columns}
        
        for col_name, expected_type in required_columns.items():
            if col_name in column_dict:
                self.print_success(f"字段 {col_name} 存在")
            else:
                issues.append(f"定价方案表缺少字段: {col_name}")
                self.print_error(f"字段 {col_name} 不存在")
        
        self.print_info(f"定价方案表共有 {len(columns)} 个字段")
        
        return len(issues) == 0, issues
    
    def test_indexes(self) -> Tuple[bool, List[str]]:
        """测试索引"""
        self.print_header("数据库索引检查")
        
        issues = []
        
        tables_to_check = ['users', 'subscriptions', 'payment_records']
        
        for table in tables_to_check:
            indexes = self.inspector.get_indexes(table)
            if indexes:
                self.print_success(f"{table} 表有 {len(indexes)} 个索引")
                for idx in indexes:
                    self.print_info(f"  索引: {idx['name']} on {idx['column_names']}")
            else:
                self.print_warning(f"{table} 表没有额外索引")
        
        return len(issues) == 0, issues
    
    def test_data_integrity(self) -> Tuple[bool, List[str]]:
        """测试数据完整性"""
        self.print_header("数据完整性检查")
        
        issues = []
        
        try:
            # 统计各表数据
            user_count = self.session.query(User).count()
            self.print_success(f"用户总数: {user_count}")
            
            # 统计 Pro 用户
            pro_users = self.session.query(User).filter(User.tier == 'PRO').count()
            self.print_info(f"Pro 用户: {pro_users}")
            
            # 统计活跃订阅
            active_subs = self.session.query(User).filter(User.is_subscription_active == True).count()
            self.print_info(f"活跃订阅: {active_subs}")
            
            # 检查订阅记录
            try:
                subscription_count = self.session.query(Subscription).count()
                self.print_info(f"订阅历史记录: {subscription_count}")
            except Exception as e:
                self.print_warning(f"订阅表查询失败: {str(e)}")
            
            # 检查支付记录
            try:
                payment_count = self.session.query(PaymentRecord).count()
                self.print_info(f"支付记录: {payment_count}")
            except Exception as e:
                self.print_warning(f"支付记录表查询失败: {str(e)}")
            
            # 检查定价方案
            try:
                pricing_count = self.session.query(PricingPlan).count()
                self.print_info(f"定价方案: {pricing_count}")
            except Exception as e:
                self.print_warning(f"定价方案表查询失败: {str(e)}")
            
            # 数据一致性检查
            if pro_users != active_subs:
                self.print_warning(f"Pro 用户数 ({pro_users}) 与活跃订阅数 ({active_subs}) 不一致")
            else:
                self.print_success("Pro 用户数与活跃订阅数一致")
            
        except Exception as e:
            issues.append(f"数据完整性检查失败: {str(e)}")
            self.print_error(f"检查失败: {str(e)}")
        
        return len(issues) == 0, issues
    
    def test_subscription_data_samples(self) -> Tuple[bool, List[str]]:
        """测试订阅数据样本"""
        self.print_header("订阅数据样本检查")
        
        issues = []
        
        try:
            # 获取有订阅的用户样本
            users_with_subs = self.session.query(User).filter(
                User.is_subscription_active == True
            ).limit(3).all()
            
            if users_with_subs:
                self.print_success(f"找到 {len(users_with_subs)} 个活跃订阅用户样本")
                
                for user in users_with_subs:
                    self.print_info(f"\n用户 ID: {user.id}")
                    self.print_info(f"  层级: {user.tier}")
                    self.print_info(f"  订阅类型: {user.subscription_type}")
                    self.print_info(f"  定价层级: {user.pricing_tier}")
                    self.print_info(f"  月度价格: ${user.monthly_price}")
                    self.print_info(f"  订阅价格: ${user.subscription_price}")
                    self.print_info(f"  支付方式: {user.payment_method}")
                    if user.subscription_expires_at:
                        self.print_info(f"  过期时间: {user.subscription_expires_at}")
                    if user.total_payment_amount:
                        self.print_info(f"  总支付: ${user.total_payment_amount}")
            else:
                self.print_warning("没有找到活跃订阅用户")
            
            # 检查订阅字段完整性
            users_with_incomplete_data = self.session.query(User).filter(
                User.is_subscription_active == True,
                User.subscription_type == None
            ).count()
            
            if users_with_incomplete_data > 0:
                issues.append(f"{users_with_incomplete_data} 个活跃用户缺少订阅类型")
                self.print_warning(f"{users_with_incomplete_data} 个活跃用户缺少订阅类型")
            else:
                self.print_success("所有活跃订阅用户数据完整")
            
        except Exception as e:
            issues.append(f"订阅数据检查失败: {str(e)}")
            self.print_error(f"检查失败: {str(e)}")
        
        return len(issues) == 0, issues
    
    def generate_report(self, checks: Dict[str, Tuple[bool, List[str]]]):
        """生成测试报告"""
        self.print_header("数据库结构测试报告")
        
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
            self.print_header("发现的问题")
            for issue in all_issues:
                self.print_error(issue)
        else:
            self.print_success("\n✅ 数据库结构完整，所有检查通过！")
        
        # 保存报告
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "database_url": settings.DATABASE_URL[:30] + "...",
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "issues": all_issues,
            "environment": settings.ENVIRONMENT
        }
        
        report_file = project_root / "tests" / "database_test_report.json"
        report_file.parent.mkdir(exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        self.print_info(f"\n报告已保存至: {report_file}")
    
    def cleanup(self):
        """清理资源"""
        try:
            self.session.close()
            self.engine.dispose()
        except Exception as e:
            print(f"清理资源时出错: {e}")


def main():
    """主函数"""
    print(f"{Color.BOLD}Fintellic 数据库结构验证测试{Color.RESET}")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    tester = DatabaseTester()
    
    try:
        # 执行所有检查
        checks = {
            "表存在性": tester.test_table_existence(),
            "用户表结构": tester.test_user_table_structure(),
            "订阅表结构": tester.test_subscription_table_structure(),
            "支付记录表结构": tester.test_payment_record_table_structure(),
            "定价方案表结构": tester.test_pricing_plan_table_structure(),
            "索引检查": tester.test_indexes(),
            "数据完整性": tester.test_data_integrity(),
            "订阅数据样本": tester.test_subscription_data_samples(),
        }
        
        # 生成报告
        tester.generate_report(checks)
        
        # 返回退出码
        all_passed = all(result for result, _ in checks.values())
        sys.exit(0 if all_passed else 1)
        
    finally:
        tester.cleanup()


if __name__ == "__main__":
    main()