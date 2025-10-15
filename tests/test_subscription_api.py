#!/usr/bin/env python3
"""
Subscription API Integration Test
测试订阅系统所有 API 端点的可达性和响应格式
"""
import sys
from pathlib import Path
import httpx
import asyncio
from typing import Dict, Any, List, Tuple
import json
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from app.core.config import settings
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


class APITester:
    """API 测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.api_base = f"{base_url}/api/v1"
        self.test_user_token = None
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
    
    async def check_server_health(self) -> bool:
        """检查服务器健康状态"""
        self.print_header("服务器健康检查")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 检查主服务器
                response = await client.get(f"{self.base_url}/")
                if response.status_code == 200:
                    self.print_success(f"主服务器响应: {response.status_code}")
                else:
                    self.print_warning(f"主服务器响应: {response.status_code}")
                
                # 检查 API 文档
                response = await client.get(f"{self.base_url}/docs")
                if response.status_code == 200:
                    self.print_success("API 文档可访问")
                else:
                    self.print_warning("API 文档不可访问")
                
                # 检查健康端点（如果存在）
                try:
                    response = await client.get(f"{self.base_url}/health")
                    if response.status_code == 200:
                        health_data = response.json()
                        self.print_success(f"健康检查: {health_data.get('status', 'OK')}")
                except:
                    self.print_info("未找到 /health 端点")
                
                return True
        except Exception as e:
            self.print_error(f"服务器不可达: {str(e)}")
            self.print_info("请确保后端服务器正在运行:")
            self.print_info("  uvicorn app.main:app --reload")
            return False
    
    async def get_test_user_token(self) -> bool:
        """获取测试用户令牌"""
        self.print_header("获取测试用户令牌")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 尝试登录或创建测试用户
                # 这里假设有一个测试用户
                login_data = {
                    "username": "test@fintellic.com",
                    "password": "testpassword123"
                }
                
                response = await client.post(
                    f"{self.api_base}/auth/login",
                    json=login_data
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.test_user_token = data.get("access_token")
                    if self.test_user_token:
                        self.print_success("成功获取测试用户令牌")
                        return True
                    else:
                        self.print_error("响应中未找到 access_token")
                        return False
                else:
                    self.print_warning(f"登录失败: {response.status_code}")
                    self.print_info("将使用无认证模式测试公共端点")
                    return False
                    
        except Exception as e:
            self.print_warning(f"无法获取令牌: {str(e)}")
            self.print_info("将测试不需要认证的端点")
            return False
    
    def get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        if self.test_user_token:
            headers["Authorization"] = f"Bearer {self.test_user_token}"
        return headers
    
    async def test_endpoint(
        self, 
        method: str, 
        path: str, 
        data: Dict = None,
        expected_status: int = 200,
        description: str = None
    ) -> Tuple[bool, Dict]:
        """测试单个端点"""
        full_url = f"{self.api_base}{path}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method.upper() == "GET":
                    response = await client.get(full_url, headers=self.get_headers())
                elif method.upper() == "POST":
                    response = await client.post(full_url, json=data, headers=self.get_headers())
                elif method.upper() == "PUT":
                    response = await client.put(full_url, json=data, headers=self.get_headers())
                elif method.upper() == "DELETE":
                    response = await client.delete(full_url, headers=self.get_headers())
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                success = response.status_code == expected_status
                
                result = {
                    "method": method,
                    "path": path,
                    "description": description or path,
                    "status_code": response.status_code,
                    "expected_status": expected_status,
                    "success": success,
                    "response_time": response.elapsed.total_seconds(),
                    "content_type": response.headers.get("content-type", ""),
                }
                
                # 尝试解析 JSON
                try:
                    result["response_body"] = response.json()
                except:
                    result["response_body"] = response.text[:200]
                
                self.test_results.append(result)
                
                if success:
                    self.print_success(f"{method} {path} - {response.status_code} ({response.elapsed.total_seconds():.2f}s)")
                else:
                    self.print_error(f"{method} {path} - Expected {expected_status}, got {response.status_code}")
                    if response.status_code >= 400:
                        self.print_warning(f"  错误详情: {response.text[:100]}")
                
                return success, result
                
        except httpx.TimeoutException:
            self.print_error(f"{method} {path} - 请求超时")
            return False, {"error": "timeout"}
        except Exception as e:
            self.print_error(f"{method} {path} - {str(e)}")
            return False, {"error": str(e)}
    
    async def test_pricing_endpoints(self):
        """测试定价相关端点"""
        self.print_header("定价端点测试")
        
        # 测试获取定价信息（需要认证）
        if self.test_user_token:
            await self.test_endpoint(
                "GET", 
                "/subscriptions/pricing",
                expected_status=200,
                description="获取用户定价信息"
            )
        else:
            self.print_info("跳过需要认证的定价端点")
    
    async def test_subscription_query_endpoints(self):
        """测试订阅查询端点"""
        self.print_header("订阅查询端点测试")
        
        if not self.test_user_token:
            self.print_info("跳过需要认证的查询端点")
            return
        
        # 获取当前订阅
        await self.test_endpoint(
            "GET",
            "/subscriptions/current",
            expected_status=200,
            description="获取当前订阅状态"
        )
        
        # 获取订阅历史
        await self.test_endpoint(
            "GET",
            "/subscriptions/history",
            expected_status=200,
            description="获取订阅历史"
        )
        
        # 获取支付历史
        await self.test_endpoint(
            "GET",
            "/subscriptions/payments",
            expected_status=200,
            description="获取支付历史"
        )
    
    async def test_subscription_management_endpoints(self):
        """测试订阅管理端点"""
        self.print_header("订阅管理端点测试")
        
        if not self.test_user_token:
            self.print_info("跳过需要认证的管理端点")
            return
        
        # 测试创建订阅（开发环境应该允许 Mock）
        if settings.is_development:
            self.print_info("测试 Mock 订阅创建（仅开发环境）")
            await self.test_endpoint(
                "POST",
                "/subscriptions/mock/upgrade",
                data={"subscription_type": "MONTHLY"},
                expected_status=200,
                description="Mock 升级到 Pro"
            )
        
        # 测试取消订阅（可能返回 400 如果没有活跃订阅）
        await self.test_endpoint(
            "POST",
            "/subscriptions/cancel",
            data={"cancel_immediately": False},
            expected_status=None,  # 任何响应都接受
            description="取消订阅"
        )
    
    async def test_payment_verification_endpoints(self):
        """测试支付验证端点"""
        self.print_header("支付验证端点测试")
        
        if not self.test_user_token:
            self.print_info("跳过需要认证的验证端点")
            return
        
        self.print_info("支付验证端点需要真实收据，这里仅测试端点可达性")
        
        # 测试 Apple 验证（应该返回 400 或 401，因为没有真实收据）
        await self.test_endpoint(
            "POST",
            "/subscriptions/verify/apple",
            data={
                "receipt_data": "test_receipt",
                "product_id": "com.fintellic.app.monthly",
                "transaction_id": "test_transaction"
            },
            expected_status=400,
            description="Apple IAP 验证（预期失败）"
        )
        
        # 测试 Google 验证
        await self.test_endpoint(
            "POST",
            "/subscriptions/verify/google",
            data={
                "purchase_token": "test_token",
                "product_id": "monthly_subscription",
                "order_id": "test_order"
            },
            expected_status=400,
            description="Google Play 验证（预期失败）"
        )
        
        # 测试 Apple 恢复购买
        await self.test_endpoint(
            "POST",
            "/subscriptions/restore/apple",
            data={"receipt_data": "test_receipt"},
            expected_status=400,
            description="Apple 恢复购买（预期失败）"
        )
    
    async def test_webhook_endpoints(self):
        """测试 Webhook 端点"""
        self.print_header("Webhook 端点测试")
        
        self.print_info("Webhook 端点不需要认证，但需要特定格式的数据")
        
        # 测试 Apple Webhook（应该返回错误或处理）
        await self.test_endpoint(
            "POST",
            "/subscriptions/webhook/apple",
            data={"test": "data"},
            expected_status=200,  # Webhook 通常总是返回 200
            description="Apple Webhook 端点"
        )
        
        # 测试 Google Webhook
        await self.test_endpoint(
            "POST",
            "/subscriptions/webhook/google",
            data={"test": "data"},
            expected_status=200,
            description="Google Webhook 端点"
        )
    
    async def test_admin_endpoints(self):
        """测试管理端点"""
        self.print_header("管理端点测试")
        
        if not self.test_user_token:
            self.print_info("跳过需要认证的管理端点")
            return
        
        self.print_info("管理端点需要管理员权限，可能返回 403")
        
        # 测试系统状态
        await self.test_endpoint(
            "GET",
            "/subscriptions/admin/system-status",
            expected_status=None,  # 可能 403 或 200
            description="系统状态"
        )
        
        # 测试定价配置
        await self.test_endpoint(
            "GET",
            "/subscriptions/admin/pricing-config",
            expected_status=None,
            description="定价配置"
        )
        
        # 测试统计信息
        await self.test_endpoint(
            "GET",
            "/subscriptions/admin/statistics",
            expected_status=None,
            description="订阅统计"
        )
    
    def generate_report(self):
        """生成测试报告"""
        self.print_header("API 测试报告")
        
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r.get("success"))
        failed_tests = total_tests - successful_tests
        
        print(f"总测试数: {total_tests}")
        print(f"成功: {Color.GREEN}{successful_tests}{Color.RESET}")
        print(f"失败: {Color.RED}{failed_tests}{Color.RESET}")
        
        if successful_tests == total_tests:
            self.print_success("\n🎉 所有 API 端点测试通过！")
        else:
            self.print_warning(f"\n{failed_tests} 个端点测试失败")
        
        # 按状态码分组
        status_codes = {}
        for result in self.test_results:
            code = result.get("status_code", "error")
            status_codes[code] = status_codes.get(code, 0) + 1
        
        print("\n状态码分布:")
        for code, count in sorted(status_codes.items()):
            print(f"  {code}: {count} 次")
        
        # 响应时间统计
        response_times = [r["response_time"] for r in self.test_results if "response_time" in r]
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            max_time = max(response_times)
            min_time = min(response_times)
            
            print("\n响应时间统计:")
            print(f"  平均: {avg_time:.3f}s")
            print(f"  最快: {min_time:.3f}s")
            print(f"  最慢: {max_time:.3f}s")
        
        # 保存详细报告
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": failed_tests,
            "has_auth_token": bool(self.test_user_token),
            "environment": settings.ENVIRONMENT,
            "test_results": self.test_results
        }
        
        report_file = project_root / "tests" / "api_test_report.json"
        report_file.parent.mkdir(exist_ok=True)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        
        self.print_info(f"\n详细报告已保存至: {report_file}")


async def main():
    """主函数"""
    print(f"{Color.BOLD}Fintellic 订阅 API 集成测试{Color.RESET}")
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    tester = APITester()
    
    # 1. 检查服务器健康
    if not await tester.check_server_health():
        print(f"\n{Color.RED}服务器不可用，测试终止{Color.RESET}")
        sys.exit(1)
    
    # 2. 尝试获取测试用户令牌
    await tester.get_test_user_token()
    
    # 3. 运行所有端点测试
    await tester.test_pricing_endpoints()
    await tester.test_subscription_query_endpoints()
    await tester.test_subscription_management_endpoints()
    await tester.test_payment_verification_endpoints()
    await tester.test_webhook_endpoints()
    await tester.test_admin_endpoints()
    
    # 4. 生成报告
    tester.generate_report()
    
    # 5. 返回退出码
    successful = sum(1 for r in tester.test_results if r.get("success"))
    total = len(tester.test_results)
    
    sys.exit(0 if successful == total else 1)


if __name__ == "__main__":
    asyncio.run(main())