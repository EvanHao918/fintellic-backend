import smtplib
import secrets
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import logging

from app.core.config import settings
from app.models.user import User
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Resend SDK - 懒加载以避免未安装时报错
_resend = None

def get_resend():
    """懒加载 Resend SDK"""
    global _resend
    if _resend is None:
        try:
            import resend
            _resend = resend
        except ImportError:
            logger.warning("Resend SDK not installed. Run: pip install resend")
            _resend = False
    return _resend if _resend else None


class EmailService:
    """
    邮件服务类 - 支持 Resend API 和 SMTP 两种发送方式
    
    优先级：
    1. Resend API (推荐，现代邮件服务)
    2. SMTP (备用/传统方式)
    3. 开发模式 (仅打印日志)
    """
    
    def __init__(self):
        # Resend 配置
        self.resend_api_key = settings.RESEND_API_KEY
        self.resend_from_email = settings.RESEND_FROM_EMAIL
        self.resend_from_name = settings.RESEND_FROM_NAME
        
        # SMTP 配置 (备用)
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_use_tls = settings.SMTP_USE_TLS
        
        # 通用配置
        self.from_name = settings.RESEND_FROM_NAME if settings.EMAIL_PROVIDER == "resend" else settings.EMAIL_FROM_NAME
        self.from_address = settings.email_from_address
        self.email_provider = settings.EMAIL_PROVIDER
        
        # 初始化日志
        self._log_configuration()
    
    def _log_configuration(self):
        """记录邮件服务配置状态"""
        if self.email_provider == "resend" and self.resend_api_key:
            logger.info(f"📧 Email service initialized with Resend API (from: {self.resend_from_email})")
        elif self.smtp_user and self.smtp_password:
            logger.info(f"📧 Email service initialized with SMTP ({self.smtp_host})")
        else:
            logger.warning("📧 Email service in development mode (emails will be logged only)")
    
    # ==================== 发送方法 ====================
    
    def _send_via_resend(self, to_email: str, subject: str, html_content: str, text_content: str = None) -> bool:
        """通过 Resend API 发送邮件"""
        resend = get_resend()
        if not resend:
            logger.error("Resend SDK not available")
            return False
        
        try:
            resend.api_key = self.resend_api_key
            
            params = {
                "from": f"{self.resend_from_name} <{self.resend_from_email}>",
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }
            
            # 添加纯文本版本（可选）
            if text_content:
                params["text"] = text_content
            
            response = resend.Emails.send(params)
            logger.info(f"✅ Email sent via Resend to {to_email}, id: {response.get('id', 'unknown')}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Resend API error sending to {to_email}: {e}")
            return False
    
    def _send_via_smtp(self, to_email: str, subject: str, html_content: str, text_content: str = None) -> bool:
        """通过 SMTP 发送邮件（备用方法）"""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_address}>"
            msg['To'] = to_email
            
            if text_content:
                text_part = MIMEText(text_content, 'plain', 'utf-8')
                msg.attach(text_part)
            
            html_part = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(html_part)
            
            with self._get_smtp_connection() as server:
                server.send_message(msg)
            
            logger.info(f"✅ Email sent via SMTP to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ SMTP error sending to {to_email}: {e}")
            return False
    
    def _get_smtp_connection(self):
        """获取 SMTP 连接"""
        try:
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            if self.smtp_use_tls:
                server.starttls()
            if self.smtp_user and self.smtp_password:
                server.login(self.smtp_user, self.smtp_password)
            return server
        except Exception as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            raise
    
    def _send_email(self, to_email: str, subject: str, html_content: str, text_content: str = None) -> bool:
        """
        统一的邮件发送方法
        
        发送优先级：
        1. Resend API (如果配置了 RESEND_API_KEY)
        2. SMTP (如果配置了 SMTP 凭据)
        3. 开发模式 (仅打印日志)
        """
        # 方式1: Resend API (推荐)
        if self.email_provider == "resend" and self.resend_api_key:
            return self._send_via_resend(to_email, subject, html_content, text_content)
        
        # 方式2: SMTP (备用)
        if self.smtp_user and self.smtp_password:
            return self._send_via_smtp(to_email, subject, html_content, text_content)
        
        # 方式3: 开发模式 (仅记录日志)
        logger.info(f"""
        ===========================================
        📧 EMAIL (Development Mode - No Provider Configured)
        ===========================================
        To: {to_email}
        Subject: {subject}
        Provider: {self.email_provider}
        Resend Key: {'configured' if self.resend_api_key else 'NOT configured'}
        SMTP: {'configured' if self.smtp_user else 'NOT configured'}
        
        {text_content or '(HTML content omitted)'}
        ===========================================
        """)
        return True  # 开发模式下返回成功
    
    # ==================== 工具方法 ====================
    
    def generate_verification_token(self) -> str:
        """生成安全的验证令牌"""
        return secrets.token_urlsafe(32)
    
    # ==================== 密码重置邮件 ====================
    
    def send_password_reset_email(self, user: User, db: Session) -> bool:
        """发送密码重置邮件"""
        try:
            # 检查是否可以发送重置邮件（频率限制）
            if not user.can_request_password_reset():
                logger.warning(f"Password reset request denied for {user.email} - rate limited")
                return False
            
            # 生成重置令牌
            token = self.generate_verification_token()
            
            # 更新用户重置信息
            user.password_reset_token = token
            user.password_reset_sent_at = datetime.now(timezone.utc)
            db.commit()
            
            # 生成重置链接
            reset_url = settings.get_frontend_password_reset_url(token)
            
            # 邮件内容
            app_name = self.from_name
            subject = f"Reset your {app_name} password"
            
            # HTML 邮件模板
            html_content = self._get_password_reset_email_html(user, reset_url)
            
            # 纯文本内容（备用）
            text_content = f"""
Password Reset Request for {app_name}

Hi {user.full_name or user.email},

We received a request to reset your password. Click the link below to set a new password:

{reset_url}

This link will expire in {settings.PASSWORD_RESET_EXPIRE_HOURS} hour(s).

If you didn't request this password reset, you can safely ignore this email. Your password will remain unchanged.

For security reasons, this link can only be used once.

Best regards,
The {app_name} Team
            """.strip()
            
            return self._send_email(user.email, subject, html_content, text_content)
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {user.email}: {e}")
            return False
    
    def _get_password_reset_email_html(self, user: User, reset_url: str) -> str:
        """获取密码重置的 HTML 模板"""
        app_name = self.from_name
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Your Password</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            padding: 30px 20px;
            background: linear-gradient(135deg, #1a5e3a 0%, #2d8a5e 100%);
        }}
        .logo {{
            width: 70px;
            height: 70px;
            background: white;
            border-radius: 16px;
            margin: 0 auto 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
        }}
        .header h1 {{
            margin: 0;
            color: white;
            font-size: 28px;
            font-weight: 700;
        }}
        .content {{
            padding: 40px 30px;
        }}
        .content h2 {{
            color: #1a5e3a;
            margin-top: 0;
        }}
        .button {{
            display: inline-block;
            background: linear-gradient(135deg, #E88B00 0%, #f5a623 100%);
            color: white !important;
            padding: 14px 40px;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 16px;
            margin: 20px 0;
            box-shadow: 0 4px 12px rgba(232, 139, 0, 0.3);
        }}
        .button:hover {{
            background: linear-gradient(135deg, #d47d00 0%, #e69a1f 100%);
        }}
        .link-text {{
            word-break: break-all;
            color: #666;
            font-size: 13px;
            background: #f8f9fa;
            padding: 12px;
            border-radius: 6px;
            margin: 15px 0;
        }}
        .warning {{
            background: #fff8e6;
            border-left: 4px solid #E88B00;
            padding: 15px;
            margin: 20px 0;
            border-radius: 0 6px 6px 0;
        }}
        .security-notice {{
            background: #f0f7f4;
            border-left: 4px solid #1a5e3a;
            padding: 15px;
            margin: 20px 0;
            border-radius: 0 6px 6px 0;
        }}
        .security-notice ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .footer {{
            color: #666;
            font-size: 13px;
            border-top: 1px solid #eee;
            padding: 20px 30px;
            background: #fafafa;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">👁️</div>
            <h1>{app_name}</h1>
        </div>
        
        <div class="content">
            <h2>Password Reset Request</h2>
            
            <p>Hi {user.full_name or user.email},</p>
            
            <p>We received a request to reset your password for your {app_name} account. Click the button below to set a new password:</p>
            
            <div style="text-align: center;">
                <a href="{reset_url}" class="button">Reset Password</a>
            </div>
            
            <p>Or copy and paste this link into your browser:</p>
            <div class="link-text">{reset_url}</div>
            
            <div class="warning">
                <strong>⏰ Time Sensitive:</strong> This password reset link will expire in {settings.PASSWORD_RESET_EXPIRE_HOURS} hour(s).
            </div>
            
            <div class="security-notice">
                <strong>🔒 Security Notice:</strong>
                <ul>
                    <li>This link can only be used once</li>
                    <li>If you didn't request this reset, your password remains secure</li>
                    <li>Always use a strong, unique password</li>
                </ul>
            </div>
        </div>
        
        <div class="footer">
            <p><strong>Didn't request this password reset?</strong> You can safely ignore this email. Your password will remain unchanged.</p>
            <p>For security questions, contact us at support@allsight.finance</p>
        </div>
    </div>
</body>
</html>
        """
    
    # ==================== 密码修改通知 ====================
    
    def send_password_changed_notification(self, user: User) -> bool:
        """发送密码修改成功通知邮件"""
        try:
            app_name = self.from_name
            subject = f"Your {app_name} password has been changed"
            
            change_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            
            text_content = f"""
Password Changed Successfully

Hi {user.full_name or user.email},

This email confirms that your password for {app_name} was successfully changed.

Time: {change_time}

If you did not make this change, please contact our support team immediately at support@allsight.finance.

Best regards,
The {app_name} Team
            """.strip()
            
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Password Changed</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f5f5f5;">
    <div style="background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <div style="text-align: center; padding: 30px 20px; background: linear-gradient(135deg, #28a745 0%, #34c759 100%);">
            <div style="font-size: 40px; margin-bottom: 10px;">✅</div>
            <h1 style="margin: 0; color: white; font-size: 24px;">Password Changed Successfully</h1>
        </div>
        
        <div style="padding: 30px;">
            <p>Hi {user.full_name or user.email},</p>
            
            <p>This email confirms that your password for <strong>{app_name}</strong> was successfully changed.</p>
            
            <p><strong>Time:</strong> {change_time}</p>
            
            <div style="background: #fff5f5; border-left: 4px solid #dc3545; padding: 15px; margin: 20px 0; border-radius: 0 6px 6px 0;">
                <strong>⚠️ Didn't make this change?</strong><br>
                If you did not change your password, please contact our support team immediately at support@allsight.finance.
            </div>
            
            <p>Best regards,<br>The {app_name} Team</p>
        </div>
    </div>
</body>
</html>
            """
            
            return self._send_email(user.email, subject, html_content, text_content)
            
        except Exception as e:
            logger.error(f"Failed to send password change notification to {user.email}: {e}")
            return False
    
    # ==================== 邮箱验证（可选功能） ====================
    
    def send_email_verification(self, user: User, db: Session) -> bool:
        """发送邮箱验证邮件"""
        try:
            # 生成验证令牌
            token = self.generate_verification_token()
            
            # 更新用户验证信息
            user.email_verification_token = token
            user.email_verification_sent_at = datetime.now(timezone.utc)
            db.commit()
            
            # 生成验证链接
            verify_url = settings.get_frontend_verification_url(token)
            
            app_name = self.from_name
            subject = f"Verify your {app_name} email address"
            
            text_content = f"""
Welcome to {app_name}!

Hi {user.full_name or user.email},

Please verify your email address by clicking the link below:

{verify_url}

This link will expire in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours.

If you didn't create an account with {app_name}, you can safely ignore this email.

Best regards,
The {app_name} Team
            """.strip()
            
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Verify Your Email</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f5f5f5;">
    <div style="background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
        <div style="text-align: center; padding: 30px 20px; background: linear-gradient(135deg, #1a5e3a 0%, #2d8a5e 100%);">
            <div style="font-size: 40px; margin-bottom: 10px;">👁️</div>
            <h1 style="margin: 0; color: white; font-size: 24px;">Welcome to {app_name}!</h1>
        </div>
        
        <div style="padding: 30px;">
            <h2 style="color: #1a5e3a; margin-top: 0;">Verify Your Email Address</h2>
            
            <p>Hi {user.full_name or user.email},</p>
            
            <p>Thanks for signing up! Please verify your email address to get started.</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{verify_url}" style="display: inline-block; background: linear-gradient(135deg, #E88B00 0%, #f5a623 100%); color: white; padding: 14px 40px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px;">Verify Email</a>
            </div>
            
            <p style="color: #666; font-size: 13px;">Or copy and paste this link:</p>
            <div style="word-break: break-all; color: #666; font-size: 13px; background: #f8f9fa; padding: 12px; border-radius: 6px;">{verify_url}</div>
            
            <div style="background: #fff8e6; border-left: 4px solid #E88B00; padding: 15px; margin: 20px 0; border-radius: 0 6px 6px 0;">
                <strong>⏰ This link expires in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours.</strong>
            </div>
            
            <p>Best regards,<br>The {app_name} Team</p>
        </div>
    </div>
</body>
</html>
            """
            
            return self._send_email(user.email, subject, html_content, text_content)
            
        except Exception as e:
            logger.error(f"Failed to send email verification to {user.email}: {e}")
            return False


# 创建全局邮件服务实例
email_service = EmailService()